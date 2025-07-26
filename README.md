# SwitchBot Actions: A YAML-based Automation Engine

A powerful, configurable automation engine for SwitchBot BLE devices, with an optional Prometheus exporter.

This application continuously scans for SwitchBot Bluetooth Low Energy (BLE) devices and provides a powerful automation engine that can:

-   **React to Events**: Trigger custom actions (like shell commands or webhooks) the moment a device's state changes.
-   **Monitor Sustained States**: Trigger actions when a device remains in a specific state for a continuous duration.
-   **Integrate with MQTT**: Trigger automations from MQTT messages and publish messages to MQTT topics as an action.

It also includes an optional **Prometheus Exporter** to expose sensor data (temperature, humidity, etc.) and device state as Prometheus metrics.

Inspired by services like GitHub Actions, all behavior is controlled through a single `config.yaml` file, allowing you to define flexible and powerful automation workflows without any code changes.

## Features

-   **Real-time Monitoring**: Gathers data from all nearby SwitchBot devices.
-   **MQTT Integration**: Connect to an MQTT broker to send and receive messages, enabling seamless integration with other smart home platforms (e.g., Home Assistant).
-   **Prometheus Integration**: Exposes metrics at a configurable `/metrics` endpoint.
-   **Powerful Automation**: Define rules to trigger actions based on a unified `if/then` structure.
-   **Flexible Conditions**: Build rules based on device model, address, sensor values, and even signal strength (`rssi`).
-   **Highly Configurable**: Filter devices, select metrics, and define complex rules from a single configuration file.
-   **Extensible Architecture**: Built on a clean, decoupled architecture, making it easy to extend.

## Getting Started

### Prerequisites

  * Python 3.10+
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

### Running as a Systemd Service

For continuous, 24/7 monitoring on a server, it is best to run this application as a background service managed by `systemd`.

#### Step 1: Create a Dedicated Virtual Environment

First, we will create a self-contained environment for the application in a system-wide location, such as `/opt`.

```bash
# Create a directory for the virtual environment
sudo mkdir -p /opt/switchbot-actions

# Create the venv
sudo python3 -m venv /opt/switchbot-actions
```

#### Step 2: Install the Application into the venv

Next, use the `pip` from within the newly created environment to install the application.

```bash
sudo /opt/switchbot-actions/bin/pip install switchbot-actions
```

The executable will now be available at `/opt/switchbot-actions/bin/switchbot-actions`.

#### Step 3: Place the Configuration File

System services should use a centralized configuration file. A standard location is `/etc`.

```bash
# Create a directory for the config file
sudo mkdir -p /etc/switchbot-actions

# Copy the example config to the new location
sudo cp config.yaml.example /etc/switchbot-actions/config.yaml

# Edit the configuration for your needs
sudo nano /etc/switchbot-actions/config.yaml
```

#### Step 4: Create the systemd Service File

Create a service definition file for `systemd`.

Create a new file with `sudo nano /etc/systemd/system/switchbot-actions.service` and paste the following content.

```ini
[Unit]
Description=SwitchBot Actions Daemon
After=network.target bluetooth.service

[Service]
# It is recommended to run the service as a non-root user.
User=nobody
Group=nobody

# Use the absolute path to the executable inside the venv
ExecStart=/opt/switchbot-actions/bin/switchbot-actions -c /etc/switchbot-actions/config.yaml

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### Step 5: Enable and Start the Service

Finally, reload the `systemd` daemon, enable the service to start on boot, and start it now.

```bash
# Reload systemd to recognize the new service file
sudo systemctl daemon-reload

# Enable the service to start automatically on boot
sudo systemctl enable switchbot-actions.service

# Start the service immediately
sudo systemctl start switchbot-actions.service

# Check the status to see if it's running correctly
sudo systemctl status switchbot-actions.service

> [!NOTE]
> **Reloading Configuration with SIGHUP**
>
> After modifying `/etc/switchbot-actions/config.yaml`, you can reload the configuration without restarting the entire service by sending a `SIGHUP` signal to the `switchbot-actions` process.
>
> ```bash
> sudo kill -HUP $(systemctl show --value --property MainPID switchbot-actions.service)
> ```
> This allows for dynamic updates to your automations and settings without service interruption.
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
-   `--prometheus-exporter-enabled`: Enable Prometheus exporter (overrides `config.yaml`).
-   `--prometheus-exporter-port <port>`: Prometheus exporter port (overrides `config.yaml`).
-   `--mqtt-host <host>`: MQTT broker host (overrides `config.yaml`).
-   `--mqtt-port <port>`: MQTT broker port (overrides `config.yaml`).
-   `--mqtt-username <username>`: MQTT broker username (overrides `config.yaml`).
-   `--mqtt-password <password>`: MQTT broker password (overrides `config.yaml`).
-   `--mqtt-reconnect-interval <seconds>`: MQTT broker reconnect interval (overrides `config.yaml`).
-   `--log-level <level>`: Set the logging level (e.g., `INFO`, `DEBUG`) (overrides `config.yaml`).

### MQTT Client (`mqtt`)

Configure the connection to your MQTT broker.

```yaml
mqtt:
  host: "localhost"
  port: 1883
  username: "your_username"
  password: "your_password"
  reconnect_interval: 10 # Seconds
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
  interface: "0"
```

### Automations (`automations`)

All automation rules are defined under the `automations` key. Each rule follows a symmetric `if/then` structure.

#### `if` Block (Trigger & Conditions)

The `if` block defines what will trigger the automation.

-   **`source`**: The core of the trigger. Use `switchbot` for immediate events, `switchbot_timer` for sustained states, `mqtt` for MQTT messages, and `mqtt_timer` for sustained MQTT message values.
-   **`duration`**: Required only for `switchbot_timer` and `mqtt_timer`. Defines how long the state must be true.
-   **`device` & `state`**: Define the conditions to be met.

In the `state` conditions, you can use the following operators for comparison: `>` (greater than), `<` (less than), `>=` (greater/equal), `<=` (less/equal), `==` (equal), and `!=` (not equal).

#### `then` Block (Action)

The `then` block defines what action to execute when the `if` conditions are met.

-   **`type`**: The type of action, such as `shell_command`, `webhook`, or `mqtt_publish`.
-   **Parameters**: Additional fields like `command`, `url`, `payload`, and `headers`.

> [!NOTE]
> You can use placeholders in `command`, `url`, `payload`, and `headers`. Available placeholders include `{address}`, `{modelName}`, `{rssi}`, and any sensor value found in the device's data (e.g., `{temperature}`, `{humidity}`, `{isOn}`). For MQTT triggers, you can use `{topic}` and `{payload}`.
> For `mqtt_publish` actions, the payload also supports a dictionary format, in which case placeholders can be used in each value.

#### Example 1: Event-Driven Automation

This rule triggers **immediately** when a Meter's temperature rises above 28.0.

```yaml
automations:
  - name: "High Temperature Alert"
    cooldown: "10m" # Optional: Mute for 10 minutes after triggering
    if:
      source: "switchbot"
      device:
        modelName: "Meter"
      state:
        temperature: "> 28.0"
    then:
      type: "webhook"
      url: "https://example.com/alert"
      payload:
        message: "High temperature detected: {temperature}°C"
```

#### Example 2: Time-Driven Automation

This rule triggers when a presence sensor has detected **no motion for 5 continuous minutes**.

```yaml
automations:
  - name: "Turn off Lights if No Motion"
    if:
      source: "switchbot_timer"
      duration: "5m"
      device:
        modelName: "WoPresence"
      state:
        motion_detected: False
    then:
      type: "shell_command"
      command: "echo 'No motion for 5 minutes, turning off lights.'"
```

#### Example 3: MQTT-Driven Automation

This rule triggers when an MQTT message is received on the topic `home/living/light/set` with the payload `ON`. It then publishes a new MQTT message.

```yaml
automations:
  - name: "React to JSON payload from MQTT"
    if:
      source: "mqtt"
      topic: "home/sensors/thermostat"
      state:
        # Evaluates a key within a JSON payload.
        temperature: "> 22.0"
    then:
      type: "mqtt_publish"
      topic: "home/living/ac/set"
      payload:
        # The payload can be a dictionary.
        # Placeholders like {temperature} will be replaced with the actual values.
        action: "set_temperature"
        value: "{temperature}"
      # Optional QoS and retain flags
      qos: 1
      retain: true
```

### Prometheus Exporter (`prometheus_exporter`)

This feature exposes all collected SwitchBot device data as Prometheus metrics, allowing for powerful monitoring and visualization.

> [!IMPORTANT]
> The Prometheus Exporter is **disabled by default**. To enable it, you must explicitly set `enabled: true` in your `config.yaml` or use the `--prometheus-exporter-enabled` command-line argument.

Once enabled, metrics will be available at the `/metrics` endpoint (e.g., `http://localhost:8000/metrics`). You can scrape this endpoint with a Prometheus server and use tools like Grafana to create dashboards for temperature, humidity, battery levels, and more.

```yaml
prometheus_exporter:
  enabled: false # Default: disabled
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

-   **Troubleshooting Automations:**
    By default, the execution of `automations` is not logged to `INFO` to avoid excessive noise. If you need to verify that your triggers are running, enable `DEBUG` logging for the triggers module in `config.yaml`:
    ```yaml
    logging:
      level: "INFO"
      loggers:
        switchbot_actions.action_runner: "DEBUG"
    ```
