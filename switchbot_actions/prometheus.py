import logging
from http.server import HTTPServer
from typing import Dict, Optional

from prometheus_client import REGISTRY, Gauge, start_http_server

from .component import BaseComponent
from .config import DeviceSettings, PrometheusExporterSettings
from .signals import switchbot_advertisement_received
from .state import SwitchBotState, create_state_object

logger = logging.getLogger(__name__)


class PrometheusExporter(BaseComponent[PrometheusExporterSettings]):
    def __init__(self, settings: PrometheusExporterSettings, registry=REGISTRY):
        super().__init__(settings)
        self._gauges: Dict[str, Gauge] = {}
        self._label_names = ["address", "model"]
        self.server: Optional[HTTPServer] = None
        self.registry = registry
        self._address_to_name_map: Dict[str, str] = {}
        self._info_gauge: Optional[Gauge] = None

    def _is_enabled(
        self, settings: Optional[PrometheusExporterSettings] = None
    ) -> bool:
        """Checks if the component is enabled based on current or new settings."""
        current_settings = settings or self.settings
        return current_settings.enabled

    def _create_info_gauge_and_metrics(
        self, devices_to_register: Dict[str, DeviceSettings]
    ):
        """Creates or re-creates the info gauge and its initial metrics."""
        if self._info_gauge:
            try:
                self.registry.unregister(self._info_gauge)
            except KeyError:
                pass  # Ignore if already unregistered

        self._info_gauge = Gauge(
            "switchbot_device_info",
            "Information about a SwitchBot device",
            ["address", "name", "model"],
            registry=self.registry,
        )
        self._address_to_name_map = {
            v.address: k for k, v in devices_to_register.items()
        }
        for name, device in devices_to_register.items():
            info_labels = {
                "address": device.address,
                "name": name,
                "model": "Unknown",
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
        if device_name and self._info_gauge:
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
                self.logger.info(f"Dynamically creating new gauge: {metric_name}")
                self._gauges[metric_name] = Gauge(
                    metric_name,
                    f"SwitchBot metric for {key}",
                    self._label_names,
                    registry=self.registry,
                )

            self._gauges[metric_name].labels(**label_values).set(float(value))

    async def _start(self):
        """Creates gauges, connects signals, and starts the Prometheus HTTP server."""
        self._create_info_gauge_and_metrics(self.settings.devices)
        switchbot_advertisement_received.connect(self.handle_advertisement)
        self.logger.info("PrometheusExporter connected to signals.")

        if self.server:
            self.logger.warning("Prometheus server already running.")
            return
        try:
            self.server, _ = start_http_server(
                self.settings.port, registry=self.registry
            )
            self.logger.info(
                f"Prometheus exporter server started on port {self.settings.port}"
            )
        except OSError as e:
            self.logger.error(
                f"Failed to start Prometheus exporter on port {self.settings.port}: {e}"
            )
            raise

    async def _stop(self):
        """Stops the server and unregisters all gauges for a clean shutdown."""
        switchbot_advertisement_received.disconnect(self.handle_advertisement)
        self.logger.info("PrometheusExporter disconnected from signals.")

        all_gauges_to_unregister = list(self._gauges.values())
        if self._info_gauge:
            all_gauges_to_unregister.append(self._info_gauge)

        for gauge in all_gauges_to_unregister:
            try:
                self.registry.unregister(gauge)
            except KeyError:
                pass
        self._gauges.clear()
        self._info_gauge = None

        self.logger.info("All Prometheus gauges have been unregistered.")

        if self.server:
            if hasattr(self.server, "shutdown"):
                self.server.shutdown()
            self.server = None
            self.logger.info("Prometheus exporter server stopped.")

    def _require_restart(self, new_settings: PrometheusExporterSettings) -> bool:
        """A restart is required if the listening port changes."""
        return self.settings.port != new_settings.port

    async def _apply_live_update(
        self, new_settings: PrometheusExporterSettings
    ) -> None:
        """Applies live updates by re-creating info gauge if devices change."""
        if self.settings.devices != new_settings.devices:
            self.logger.info("Device list changed, re-initializing info gauge.")
            # self.settings will be updated by the base class after this method
            self._create_info_gauge_and_metrics(new_settings.devices)
