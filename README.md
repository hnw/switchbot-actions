# SwitchBot Exporter

A Prometheus exporter for SwitchBot BLE devices, with a powerful, configurable automation engine.

This application continuously scans for SwitchBot Bluetooth Low Energy (BLE) devices and provides two core functionalities:

1.  **Prometheus Exporter**: Exposes sensor data (temperature, humidity, motion, etc.) and device state (battery, RSSI) as Prometheus metrics.
2.  **Automation Engine**: Triggers custom actions (like shell commands or webhooks) based on two distinct trigger types:
    *   **Event-Driven Actions**: React immediately when a device's state changes.
    *   **Time-Driven Timers**: React when a device remains in a specific state for a continuous duration.

All behavior is controlled through a single `config.yaml` file, allowing for flexible deployment and management without any code changes.

## Features

-   **Real-time Monitoring**: Gathers data from all nearby SwitchBot devices.
-   **Prometheus Integration**: Exposes metrics at a configurable `/metrics` endpoint.
-   **Powerful Automation**: Define rules to trigger actions based on state changes (`actions`) or sustained states (`timers`).
-   **Flexible Conditions**: Build rules based on device model, address, sensor values, and even signal strength (`rssi`).
-   **Highly Configurable**: Filter devices, select metrics, and define complex rules from a single configuration file.
-   **Extensible Architecture**: Built on a clean, decoupled architecture, making it easy to extend.

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
    -   Edit `config.yaml` to match your environment. See the **Configuration** section below for details.

4.  **Run the application:**
    ```bash
    python -m switchbot_exporter.main
    ```

## Configuration

The application is controlled by `config.yaml`. See `config.yaml.example` for a full list of options.

### Prometheus Exporter (`prometheus_exporter`)

```yaml
prometheus_exporter:
  enabled: true
  port: 8000
  target:
    # Optional: Only export metrics for these MAC addresses
    addresses:
      - "XX:XX:XX:XX:XX:AA"
    # Optional: Only export these specific metrics
    metrics:
      - "temperature"
      - "humidity"
      - "battery"
      - "rssi"
```

### Event-Driven Actions (`actions`)

Trigger an action **immediately** when a device state changes.

```yaml
actions:
  - name: "High Temperature Alert"
    # Mute for 10 minutes to prevent repeated alerts
    mute_for: "10m"
    conditions:
      device:
        modelName: "Meter"
      state:
        # Triggers the moment temperature changes to a value > 28.0
        temperature: "changes to > 28.0"
    trigger:
      type: "webhook"
      url: "https://example.com/alert"
      payload:
        message: "High temperature detected: {temperature}°C"

  - name: "Weak Signal Notification"
    conditions:
      device:
        address: "XX:XX:XX:XX:XX:AA"
      state:
        # Triggers if the signal strength is weaker (more negative) than -80 dBm
        rssi: "< -80"
    trigger:
      type: "shell_command"
      command: "echo 'Device {address} has a weak signal (RSSI: {rssi})'"
```

### Time-Driven Timers (`timers`)

Trigger an action when a device has been in a specific state for a **continuous duration**.

```yaml
timers:
  - name: "Turn off Lights if No Motion"
    conditions:
      device:
        modelName: "WoPresence"
      state:
        # The state that must be true for the whole duration
        motion_detected: False
      # The duration the state must be sustained
      duration: "5m"
    trigger:
      type: "shell_command"
      command: "echo 'No motion for 5 minutes, turning off lights.'"

  - name: "Alert if Door is Left Open"
    conditions:
      device:
        modelName: "WoContact"
      state:
        contact_open: True
      duration: "10m"
    trigger:
      type: "webhook"
      url: "https://example.com/alert"
      payload:
        message: "Warning: Door {address} has been open for 10 minutes!"
```