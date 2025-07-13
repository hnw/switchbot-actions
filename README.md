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

### Command-Line Options

-   `--config <path>` or `-c <path>`: Specifies the path to the configuration file (default: `config.yaml`).
-   `--debug` or `-d`: Enables `DEBUG` level logging, overriding any setting in the config file. This is useful for temporary troubleshooting.
-   `--scan-cycle <seconds>`: Overrides the scan cycle time.
-   `--scan-duration <seconds>`: Overrides the scan duration time.
-   `--interface <device>`: Overrides the Bluetooth interface (e.g., `hci1`).

### Logging (`logging`)

Configure the log output format and verbosity. This allows for fine-grained control over log output for both the application and its underlying libraries.

```yaml
logging:
  # Default log level for the application: DEBUG, INFO, WARNING, ERROR
  level: "INFO"

  # Log format using Python's logging syntax
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

  # Set specific log levels for noisy libraries.
  # This is useful for debugging specific components without enabling global debug.
  loggers:
    bleak: "WARNING" # Can be set to DEBUG for deep BLE troubleshooting
    # aiohttp: "WARNING"
```

#### Debugging Notes

-   **For Application Development (`--debug` flag):**
    When you run the exporter with `--debug` or `-d`, the `logging` section in your `config.yaml` is **ignored**. This flag is a shortcut that:
    1.  Sets the log level for `switchbot-exporter` to `DEBUG`.
    2.  Sets the log level for the `bleak` library to `INFO` to keep the output clean.

-   **For Library Troubleshooting (e.g., `bleak`):**
    If you need to see `DEBUG` messages from a specific library like `bleak`, do **not** use the `--debug` flag. Instead, edit `config.yaml` and set the desired level in the `loggers` section:
    ```yaml
    logging:
      level: "INFO" # Keep the main app quiet
      loggers:
        bleak: "DEBUG" # Enable detailed output only for bleak
    ```

-   **Troubleshooting Actions and Timers:**
    By default, the execution of `actions` and `timers` is not logged to `INFO` to avoid excessive noise. If you need to verify that your triggers are running, enable `DEBUG` logging for the triggers module in `config.yaml`:
    ```yaml
    logging:
      level: "INFO"
      loggers:
        switchbot_exporter.triggers: "DEBUG"
    ```

### Scanner (`scanner`)

Configure the behavior of the Bluetooth (BLE) scanner.

```yaml
scanner:
  # Time in seconds between the start of each scan cycle.
  cycle: 10
  # Time in seconds the scanner will actively listen for devices.
  # Must be less than or equal to `cycle`.
  duration: 3
  # Bluetooth interface to use.
  interface: "hci0"
```
        switchbot_exporter.dispatcher: "DEBUG"
        switchbot_exporter.timers: "DEBUG"
    ```

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

Trigger an action **the moment** a device's state changes to meet the specified conditions (edge-triggered). The action will only fire once and will not fire again until the conditions have first become false and then true again.

```yaml
actions:
  - name: "High Temperature Alert"
    # Cooldown for 10 minutes to prevent repeated alerts
    cooldown: "10m"
    conditions:
      device:
        modelName: "Meter"
      state:
        # Triggers the moment temperature becomes greater than 28.0
        temperature: "> 28.0"
    trigger:
      type: "webhook"
      url: "https://example.com/alert"
      payload:
        message: "High temperature detected: {temperature}°C"
      # Optional: Add custom headers for APIs that require them
      headers:
        Authorization: "Bearer YOUR_API_KEY"
        X-Custom-Header: "Value for {address}"

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

Trigger an action when a device has been in a specific state for a **continuous duration** (one-shot). Once the timer fires, it will not restart until the conditions have first become false and then true again.

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
