# **SwitchBot Actions: A YAML-based Automation Engine**

`switchbot-actions` is a lightweight, standalone automation engine that turns a single `config.yaml` file into a powerful local controller for your SwitchBot BLE devices. React to device states, create time-based triggers, and integrate with MQTT and Prometheus—all with a simple, configuration-driven approach.

At its core, `switchbot-actions` monitors various input sources and, based on your rules, triggers a wide range of actions.

![Conceptual Diagram](https://raw.githubusercontent.com/hnw/switchbot-actions/main/docs/images/conceptual-diagram.svg)

Its efficiency makes it a great fit for resource-constrained hardware like a Raspberry Pi Zero, allowing you to build a sophisticated, private, and reliable home automation hub without needing a large, all-in-one platform.

## **Key Features**

- **Powerful Automation Rules**: Define complex automations with a unified `if`/`then` structure.
- **Inter-Device Communication**: Create rules where one device's state triggers an action based on the state of another device.
- **Direct Device Control**: A `switchbot_command` action allows you to directly control any SwitchBot device, enabling powerful, interconnected automations.
- **Event-Driven & Time-Based Triggers**: React to state changes instantly or trigger actions only when a condition has been met for a specific duration (e.g., "if a door has been open for 5 minutes").
- **Full MQTT Integration**: Use MQTT messages as triggers and publish messages as an action.
- **Prometheus Exporter**: Exposes device metrics at a configurable `/metrics` endpoint. It also provides a special `switchbot_device_info` metric, which allows you to use your custom device names in PromQL queries for improved readability. For technical details and query examples, please see the [Project Specification](https://github.com/hnw/switchbot-actions/blob/main/docs/specification.md).
  - **`switchbot_device_info` metric**: This metric provides metadata about configured SwitchBot devices, including their `address`, user-defined `name` (alias), and `model`. Its value is always `1` and it's useful for joining with other metrics to make queries more readable.

    **Example PromQL Query (to get temperature by device name):**

    ```promql
    switchbot_temperature * on(address) group_left(name) switchbot_device_info{name="living_room_meter"}
    ```

## **Prerequisites**

- **Python**: Version 3.11 or newer is required.
- **Operating System**: The application is tested and supported on Linux. It is also expected to work on other platforms like macOS and Windows, but BLE functionality may vary depending on the system's Bluetooth support.
- **Permissions (Linux)**: The application needs permissions to access the Bluetooth adapter. This can typically be achieved by running with sudo or by setting the necessary capabilities (see the [Deployment Guide](https://github.com/hnw/switchbot-actions/blob/main/docs/deployment.md)).
- **Supported Architectures (Docker)**: linux/amd64, linux/arm64

## **Quick Start**

### **1. Installation**

We strongly recommend installing with `pipx` to keep your system clean and avoid dependency conflicts.

```
# Install pipx
pip install pipx
pipx ensurepath

# Install the application
pipx install switchbot-actions
```

### **2. Configuration**

Create a config.yaml file. Start with this example that showcases inter-device automation: it turns on a fan only if the room is hot **and** the window is closed.

```yaml
# config.yaml

# 1. Define aliases for your devices for easy reference.
devices:
  office-meter:
    address: "aa:bb:cc:dd:ee:ff" # Your temperature sensor's address
  office-window:
    address: "11:22:33:44:55:66" # Your contact sensor's address

automations:
  - name: "Turn on Fan when Hot and Window is Closed"
    if:
      # This rule triggers when the temperature goes above 28 degrees.
      source: "switchbot"
      device: "office-meter"
      conditions:
        temperature: "> 28.0"
        # And at that moment, check the state of the window sensor.
        office-window.contact_open: false
    then:
      # In a real scenario, you would control a fan here.
      # This example just logs a message.
      type: "log"
      level: "WARNING"
      message: "Room is hot and window is closed. Turning on fan..."
```

### **3. Run**

Launch the application with your configuration. Use the --debug flag first to ensure your devices are discovered.

```
# Run with sudo if you encounter permission errors
switchbot-actions --debug -c config.yaml
```

## **What's Possible? (More Examples)**

switchbot-actions enables highly context-aware automations.

- **React to State Changes**: Trigger an action only when a state _changes_. This is perfect for detecting button presses.

```yaml
if:
  source: "switchbot"
  conditions:
    # Triggers when the button_count is different from its previous value.
    button_count: "!= {previous.button_count}"
```

- **Time-Based Alerts**: Send a notification if a door has been left open for more than 10 minutes.

```yaml
if:
  source: "switchbot"
  duration: "10m"
  conditions:
    contact_open: True
```

- **Full MQTT Integration**: Control your devices with MQTT messages from other systems.

```yaml
if:
  source: "mqtt"
  topic: "home/living/light/set"
  conditions:
    payload: "ON" # React to a simple string payload
```

- **Execute Shell Commands Safely**: Run external commands with arguments passed as a list, preventing command injection vulnerabilities.

```yaml
then:
  type: "shell_command"
  command: ["echo", "Hello, {username}!"]
```

**For a complete reference of all configuration options, please see the [Project Specification](https://github.com/hnw/switchbot-actions/blob/main/docs/specification.md).**

## **Advanced Usage**

- **Running as a Service**: For continuous, 24/7 monitoring, we recommend running the application as a systemd service. View the [Deployment Guide](https://github.com/hnw/switchbot-actions/blob/main/docs/deployment.md).
- **Running with Docker**: The application is also available as a multi-arch Docker image. For detailed instructions on how to run it with Docker, please see the [Deployment Guide](https://github.com/hnw/switchbot-actions/blob/main/docs/deployment.md).
- **Command-Line Overrides**: You can temporarily override settings in your `config.yaml` using command-line flags. For example, to enable the Prometheus exporter and set its port:

  ```bash
  switchbot-actions --prometheus --prometheus-port 8080
  ```

  To enable MQTT:

  ```bash
  switchbot-actions --mqtt --mqtt-host my-broker
  ```

  To disable the scanner (useful in CI/CD environments or if you don't need BLE scanning):

  ```bash
  switchbot-actions --no-scanner
  ```

  Run `switchbot-actions --help` for a full list of options, which are grouped by function (`Scanner`, `MQTT`, `Prometheus`) for clarity.

  For scanner settings, you can now specify `--scanner-duration` and `--scanner-wait` instead of `--scanner-cycle`. For example:

  ```bash
  switchbot-actions --scanner-duration 5 --scanner-wait 10
  ```

## **Robustness Features**

switchbot-actions is designed for reliability:

- **Fail-Fast Startup**: The application performs critical resource checks at startup and exits with a clear error if a resource (e.g., a port) is unavailable.
- **Configuration Reload with Rollback**: Send a SIGHUP signal (sudo systemctl kill -s HUP switchbot-actions.service) to reload your configuration without downtime. If the new configuration is invalid, the application automatically rolls back to the last known good state.
