import logging
from http.server import HTTPServer
from typing import Dict

from prometheus_client import REGISTRY, Gauge, start_http_server

from .config import PrometheusExporterSettings
from .signals import switchbot_advertisement_received
from .state import SwitchBotState, create_state_object

logger = logging.getLogger(__name__)


class PrometheusExporter:
    def __init__(self, settings: PrometheusExporterSettings, registry=REGISTRY):
        self.settings = settings
        self._gauges: Dict[str, Gauge] = {}
        self._label_names = ["address", "model"]
        self.server: HTTPServer | None = None
        self.registry = registry
        self._address_to_name_map = {
            v.address: k for k, v in self.settings.devices.items()
        }
        self._info_gauge = Gauge(
            "switchbot_device_info",
            "Information about a SwitchBot device",
            ["address", "name", "model"],
            registry=self.registry,
        )
        self._create_initial_info_metrics()

    def _create_initial_info_metrics(self):
        """Initialize info metrics for all configured devices at startup."""
        for name, device in self.settings.devices.items():
            info_labels = {
                "address": device.address,
                "name": name,
                "model": "Unknown",  # Initially unknown until an advertisement is seen
            }
            self._info_gauge.labels(**info_labels).set(1)

    def handle_advertisement(self, sender, **kwargs):
        raw_state = kwargs.get("new_state")
        if not raw_state:
            return

        state = create_state_object(raw_state)

        if not isinstance(state, SwitchBotState):
            return

        device_name = self._address_to_name_map.get(state.id)
        if device_name:
            # Update the info gauge with the latest model name
            info_labels = {
                "address": state.id,
                "name": device_name,
                "model": state.get_values_dict().get("modelName", "Unknown"),
            }
            self._info_gauge.labels(**info_labels).set(1)

        target_addresses = self.settings.target.get("addresses")
        if target_addresses and state.id not in target_addresses:
            return

        label_values = {
            "address": state.id,
            "model": state.get_values_dict().get("modelName", "Unknown"),
        }
        all_values = state.get_values_dict()

        for key, value in all_values.items():
            if not isinstance(value, (int, float, bool)):
                continue

            target_metrics = self.settings.target.get("metrics")
            if target_metrics and key not in target_metrics:
                continue

            metric_name = f"switchbot_{key}"

            if metric_name not in self._gauges:
                logger.info(f"Dynamically creating new gauge: {metric_name}")
                self._gauges[metric_name] = Gauge(
                    metric_name,
                    f"SwitchBot metric for {key}",
                    self._label_names,
                    registry=self.registry,
                )

            self._gauges[metric_name].labels(**label_values).set(float(value))

    async def start(self):
        """Connects to signals and starts the Prometheus HTTP server."""
        switchbot_advertisement_received.connect(self.handle_advertisement)
        logger.info("PrometheusExporter connected to signals.")

        if self.server:
            logger.warning("Prometheus server already running.")
            return
        try:
            self.server, _ = start_http_server(
                self.settings.port, registry=self.registry
            )
            logger.info(
                f"Prometheus exporter server started on port {self.settings.port}"
            )
        except OSError as e:
            logger.error(
                f"Failed to start Prometheus exporter on port {self.settings.port}: {e}"
            )
            raise

    async def stop(self):
        """Stops the server and disconnects from signals for a clean shutdown."""
        switchbot_advertisement_received.disconnect(self.handle_advertisement)
        logger.info("PrometheusExporter disconnected from signals.")

        for gauge in self._gauges.values():
            try:
                self.registry.unregister(gauge)
            except KeyError:
                logger.debug(
                    f"Gauge {gauge} was not found in registry during unregister."
                )
        self._gauges.clear()
        logger.info("All Prometheus gauges have been unregistered.")

        if self.server:
            if hasattr(self.server, "shutdown"):
                self.server.shutdown()
            self.server = None
            logger.info("Prometheus exporter server stopped.")
