# switchbot_actions/exporter.py
import logging

from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import GaugeMetricFamily

from .store import DeviceStateStore

logger = logging.getLogger(__name__)


class PrometheusExporter:
    """
    Exposes device states from the DeviceStateStore as Prometheus metrics.
    """

    def __init__(self, state_store: DeviceStateStore, port: int, target_config: dict):
        self.store = state_store
        self.port = port
        self.target_config = target_config

        # Unregister default collectors to avoid exposing unwanted metrics
        for coll in list(REGISTRY._collector_to_names.keys()):
            REGISTRY.unregister(coll)

        # Register our custom collector
        REGISTRY.register(self)

    def start_server(self):
        """Starts the Prometheus HTTP server."""
        start_http_server(self.port)
        logger.info(f"Prometheus exporter server started on port {self.port}")

    def collect(self):
        """
        This method is called by the Prometheus client library when scraping.
        It yields metrics for the devices.
        """
        logger.debug("Collecting metrics for Prometheus scrape")

        target_addresses = self.target_config.get("addresses")
        target_metrics = self.target_config.get("metrics")

        gauges = {}
        label_names = ["address", "model"]
        all_states = self.store.get_all_states()
        # Filter devices based on target_addresses
        if target_addresses:
            devices_to_export = [
                state for addr, state in all_states.items() if addr in target_addresses
            ]
        else:
            devices_to_export = list(all_states.values())

        # Add RSSI metric if not filtered out
        if not target_metrics or "rssi" in target_metrics:
            rssi_gauge = GaugeMetricFamily(
                "switchbot_rssi",
                "Received Signal Strength Indicator (RSSI)",
                labels=label_names,
            )
            for device in devices_to_export:
                address = device.address
                model = device.data.get("modelName", "Unknown")
                label_values = [address, model]
                if hasattr(device, "rssi") and device.rssi is not None:
                    rssi_gauge.add_metric(label_values, device.rssi)
            yield rssi_gauge

        for device in devices_to_export:
            address = device.address
            model = device.data.get("modelName", "Unknown")
            label_values = [address, model]

            for key, value in device.data.get("data", {}).items():
                if not isinstance(value, (int, float, bool)):
                    continue
                # Filter metrics based on target_metrics
                if target_metrics and key not in target_metrics:
                    continue

                metric_name = f"switchbot_{key}"

                if metric_name not in gauges:
                    gauges[metric_name] = GaugeMetricFamily(
                        metric_name, f"SwitchBot metric {key}", labels=label_names
                    )

                gauges[metric_name].add_metric(label_values, float(value))

        for gauge in gauges.values():
            yield gauge
