# SwitchBot Exporter

A Prometheus exporter for SwitchBot BLE devices, with a powerful, configurable event-driven action engine.

This application continuously scans for SwitchBot Bluetooth Low Energy (BLE) devices and provides two core functionalities:
1.  **Prometheus Exporter**: Exposes sensor data like temperature, humidity, CO2 levels, and more as Prometheus metrics.
2.  **Event-Driven Actions**: Triggers custom actions (like shell commands or webhooks) based on device events, such as a button press or a sensor value crossing a threshold.

All behavior is controlled through a single `config.yaml` file, allowing for flexible deployment and management without any code changes.

## Features

-   **Real-time Monitoring**: Gathers data from all nearby SwitchBot devices.
-   **Prometheus Integration**: Exposes metrics at a configurable `/metrics` endpoint for easy scraping.
-   **Powerful Automation**: Define custom rules to trigger actions based on device state.
-   **Highly Configurable**: Enable/disable features, set ports, filter devices, and define complex action rules from a single configuration file.
-   **Extensible Architecture**: Built on a clean, decoupled architecture using signals, making it easy to extend with new functionality.

## Getting Started

### Prerequisites

-   Python 3.11+
-   A Linux-based system with a Bluetooth adapter that supports BLE (e.g., Raspberry Pi).

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/hnw/switchbot-exporter.git
    cd switchbot-exporter
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure the application:**
    -   Copy the example configuration file:
        ```bash
        cp config.yaml.example config.yaml
        ```
    -   Edit `config.yaml` to match your environment. Set up the Prometheus exporter settings and define any actions you need. See the **Configuration** section below for details.

4.  **Run the application:**
    ```bash
    python -m switchbot_exporter.main
    ```

    You should see log messages indicating that the scanner has started. If the exporter is enabled, you can access the metrics at `http://localhost:8000/metrics` (or your configured port).

## Configuration

The application is configured using the `config.yaml` file.

```yaml
# Prometheus Exporter Settings
prometheus_exporter:
  enabled: true
  port: 8000
  # Specify the devices and metrics to target.
  target:
    # Only devices with an address in this list will be targeted.
    # If this key is missing or the list is empty, all discovered devices will be targeted.
    addresses:
      - "XX:XX:XX:XX:XX:AA"
      - "XX:XX:XX:XX:XX:BB"
    # Only metrics in this list will be exported.
    # If this key is missing or the list is empty, all available metrics will be exported.
    metrics:
      - "temperature"
      - "humidity"
      - "battery"
      - "rssi"

# Event Action Settings
actions:
  - name: "Living Room Button Press"
    event_conditions:
      modelName: "Bot"
      address: "XX:XX:XX:XX:XX:AA"
      data:
        isOn: True
    trigger:
      type: "shell_command"
      command: "bash /path/to/my_script.sh"

  - name: "Bedroom Sensor Alert"
    event_conditions:
      modelName: "Meter"
      address: "XX:XX:XX:XX:XX:BB"
      data:
        temperature: "> 28.0" # Operators like >, <, >=, <=, == are supported
    trigger:
      type: "webhook"
      url: "https://example.com/notify"
      method: "POST"
      payload:
        message: "Bedroom is too hot! {temperature}°C"
```
