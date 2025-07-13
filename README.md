# SwitchBot Actions: A YAML-based Automation Engine

A powerful, configurable automation engine for SwitchBot BLE devices, with an optional Prometheus exporter.

This application continuously scans for SwitchBot Bluetooth Low Energy (BLE) devices and provides a powerful automation engine that can:

-   **React to Events**: Trigger custom actions (like shell commands or webhooks) the moment a device's state changes.
-   **Monitor Sustained States**: Trigger actions when a device remains in a specific state for a continuous duration.

It also includes an optional **Prometheus Exporter** to expose sensor data (temperature, humidity, etc.) and device state as Prometheus metrics.

Inspired by services like GitHub Actions, all behavior is controlled through a single `config.yaml` file, allowing you to define flexible and powerful automation workflows without any code changes.

## Features

-   **Real-time Monitoring**: Gathers data from all nearby SwitchBot devices.
-   **Prometheus Integration**: Exposes metrics at a configurable `/metrics` endpoint.
-   **Powerful Automation**: Define rules to trigger actions based on state changes (`actions`) or sustained states (`timers`).
-   **Flexible Conditions**: Build rules based on device model, address, sensor values, and even signal strength (`rssi`).
-   **Highly Configurable**: Filter devices, select metrics, and define complex rules from a single configuration file.
-   **Extensible Architecture**: Built on a clean, decoupled architecture, making it easy to extend.

## Getting Started

### Prerequisites

  * Python 3.9.2+
  * A Linux-based system with a Bluetooth adapter that supports BLE (e.g., Raspberry Pi).

### Installation (Recommended using pipx)

For command-line applications like this, we strongly recommend installing with `pipx` to keep your system clean and avoid dependency conflicts.

1.  **Install pipx:**

    ```bash
    pip install pipx
    pipx ensurepath
    ```

    *(You may need to restart your terminal after this step for the path changes to take effect.)*

2.  **Install the application:**

    ```bash
    pipx install switchbot-actions
    ```

3.  **Create your configuration file:**
    Download the example configuration from the GitHub repository to get started.

    ```bash
    curl -o config.yaml https://raw.githubusercontent.com/hnw/switchbot-actions/main/config.yaml.example
    ```

    Then, edit `config.yaml` to suit your needs.

### Alternative Installation (using pip)

If you prefer to manage your environments manually, you can use `pip`. It is recommended to do this within a virtual environment (`venv`).

```bash
# This command installs the package.
# To avoid polluting your global packages, consider running this in a venv.
pip install switchbot-actions
```

## Usage

We recommend a two-step process to get started smoothly.

### Step 1: Verify Hardware and Device Discovery

First, run the application without any configuration file to confirm that your Bluetooth adapter is working and can discover your SwitchBot devices.

```bash
switchbot-actions --debug
```

The `--debug` flag will show detailed logs. If you see lines containing "Received advertisement from...", your hardware setup is correct.

> [\!IMPORTANT]
> **A Note on Permissions on Linux**
>
> If you encounter errors related to "permission denied," you may need to run the command with `sudo`:
>
> ```bash
> sudo switchbot-actions --debug
> ```

### Step 2: Configure and Run

Once you've confirmed that device discovery is working, create your `config.yaml` file. You can use the example as a starting point:

```bash
curl -o config.yaml https://raw.githubusercontent.com/hnw/switchbot-actions/main/config.yaml.example
```

Edit `config.yaml` to define your automations. Then, run the application normally:

```bash
switchbot-actions -c config.yaml
```

## Configuration

The application is controlled by `config.yaml`. See `config.yaml.example` for a full list of options.

> [!NOTE]
> This section provides a quick overview. For a detailed and complete reference of all configuration options, please see the [**Project Specification**](./docs/specification.md#4-configuration-configyaml).

### Command-Line Options

-   `--config <path>` or `-c <path>`: Specifies the path to the configuration file (default: `config.yaml`).
-   `--debug` or `-d`: Enables `DEBUG` level logging, overriding any setting in the config file. This is useful for temporary troubleshooting.
-   `--scan-cycle <seconds>`: Overrides the scan cycle time.
-   `--scan-duration <seconds>`: Overrides the scan duration time.
-   `--interface <device>`: Overrides the Bluetooth interface (e.g., `hci1`).

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

### Event-Driven Actions (`actions`)

Trigger an action **the moment** a device's state changes to meet the specified conditions (edge-triggered). The action will only fire once and will not fire again until the conditions have first become false and then true again.

In the `state` conditions, you can use the following operators for comparison: `>` (greater than), `<` (less than), `>=` (greater/equal), `<=` (less/equal), `==` (equal), and `!=` (not equal).

```yaml
actions:
  - name: "High Temperature Alert"
    # Cooldown for 10 minutes to prevent repeated alerts
    cooldown: "10m" # Supports formats like "5s", "10m", "1.5h"
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

> [!NOTE]
> You can use placeholders in `command`, `url`, `payload`, and `headers`. Available placeholders include `{address}`, `{modelName}`, `{rssi}`, and any sensor value found in the device's data (e.g., `{temperature}`, `{humidity}`, `{isOn}`).

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

### Prometheus Exporter (`prometheus_exporter`)

This feature exposes all collected SwitchBot device data as Prometheus metrics, allowing for powerful monitoring and visualization. Once enabled, metrics will be available at the `/metrics` endpoint (e.g., `http://localhost:8000/metrics`). You can scrape this endpoint with a Prometheus server and use tools like Grafana to create dashboards for temperature, humidity, battery levels, and more.

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
    1.  Sets the log level for `switchbot-actions` to `DEBUG`.
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
        switchbot_actions.triggers: "DEBUG"
    ```
