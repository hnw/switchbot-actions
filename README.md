# SwitchBot Actions: A YAML-based Automation Engine

A powerful, configurable automation engine for SwitchBot BLE devices, with an optional Prometheus exporter.

`switchbot-actions` is a lightweight, standalone automation engine for your SwitchBot BLE devices. It turns a single `config.yaml` file into a powerful local controller, allowing you to react to device states, create time-based triggers, and integrate with MQTT and Prometheus. Its efficiency makes it a great fit for resource-constrained hardware, running comfortably on a Raspberry Pi 3 and even on a Raspberry Pi Zero. It's ideal for those who prefer a simple, configuration-driven approach to home automation without needing a large, all-in-one platform.

At its core, `switchbot-actions` monitors various input sources and, based on your rules, triggers different actions. The overall architecture can be visualized as follows:

![Architecture Diagram](https://raw.githubusercontent.com/hnw/switchbot-actions/main/docs/images/architecture.svg)

## Key Features

  - **Direct Device Control**: A new `switchbot_command` action allows you to directly control any SwitchBot device, enabling powerful, interconnected automations without external scripts.
  - **Real-time Monitoring**: Gathers data from all nearby SwitchBot devices.
  - **Full MQTT Integration**: Use MQTT messages as triggers for automations, and publish messages as an action.
  - **Prometheus Exporter**: Exposes metrics at a configurable `/metrics` endpoint.
  - **Powerful Automation Rules**: Define complex automations with a unified `if/then` structure.
  - **Flexible Conditions**: Build rules based on device model, address, sensor values, and even signal strength (`rssi`).
  - **Highly Configurable**: Control every aspect of the application from a single configuration file.

## Getting Started

### 1. Prerequisites

  - Python 3.11+
  - A Linux-based system with a Bluetooth adapter that supports BLE (e.g., a Raspberry Pi).

### 2. Installation (Recommended)

We strongly recommend installing with `pipx` to keep your system clean and avoid dependency conflicts.

```bash
# Install pipx
pip install pipx
pipx ensurepath

# Install the application
pipx install switchbot-actions
```

*(You may need to restart your terminal after the `pipx ensurepath` step for the changes to take effect.)*

## Running as a Systemd Service

For continuous, 24/7 monitoring, running this application as a background service is the ideal setup.

#### Step 1: Create a Dedicated Virtual Environment

```bash
# Create a directory and a virtual environment for the application
sudo mkdir -p /opt/switchbot-actions
sudo python3 -m venv /opt/switchbot-actions
```

#### Step 2: Install the Application into the venv

```bash
# Use the pip from the new environment to install the package
sudo /opt/switchbot-actions/bin/pip install switchbot-actions
```

#### Step 3: Place the Configuration File

```bash
# Create a dedicated directory for the config file
sudo mkdir -p /etc/switchbot-actions

# Download the example config to the new location
sudo curl -o /etc/switchbot-actions/config.yaml https://raw.githubusercontent.com/hnw/switchbot-actions/main/config.yaml.example

# Edit the configuration for your needs
sudo nano /etc/switchbot-actions/config.yaml
```

#### Step 4: Create the systemd Service File

Create a new file at `/etc/systemd/system/switchbot-actions.service` and paste the following content. Using `DynamicUser=yes` is a modern, secure way to run services without pre-existing users.

```ini
[Unit]
Description=SwitchBot Actions Daemon
After=network.target bluetooth.service

[Service]
# Run the service as its own minimal-privilege, dynamically-created user
DynamicUser=yes

# Use the absolute path to the executable and config file
ExecStart=/opt/switchbot-actions/bin/switchbot-actions -c /etc/switchbot-actions/config.yaml

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### Step 5: Enable and Start the Service

```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start automatically on boot
sudo systemctl enable switchbot-actions.service

# Start the service immediately
sudo systemctl start switchbot-actions.service

# Check the status to ensure it's running correctly
sudo systemctl status switchbot-actions.service
```

> [\!NOTE]
> **Reloading Configuration without Downtime**
> After modifying `/etc/switchbot-actions/config.yaml`, you can apply the changes without restarting the service by sending a `SIGHUP` signal.
>
> ```bash
> sudo kill -HUP $(systemctl show --value --property MainPID switchbot-actions.service)
> ```

## Usage

We recommend a two-step process to get started smoothly.

### Step 1: Verify Hardware and Device Discovery

First, run the application in debug mode to confirm that your Bluetooth adapter is working and can discover your SwitchBot devices.

```bash
switchbot-actions --debug
```

If you see log lines containing "Received advertisement from...", your hardware setup is correct.

> [\!IMPORTANT]
> **A Note on Permissions on Linux**
> If you encounter errors related to "permission denied," you may need to run the command with `sudo`.

### Step 2: Configure and Run

Once discovery is confirmed, create your `config.yaml` file. You can download the example file as a starting point.

```bash
curl -o config.yaml https://raw.githubusercontent.com/hnw/switchbot-actions/main/config.yaml.example
```

Edit `config.yaml` to define your automations, then run the application with your configuration.

```bash
switchbot-actions -c config.yaml
```

## Configuration

The application is controlled by `config.yaml`.

### Quick Start Example

To get started quickly, copy and paste the following into your `config.yaml`. This automation will log a message whenever a SwitchBot Meter's temperature rises above 28.0℃.

```yaml
automations:
  - name: "High Temperature Alert"
    if:
      source: "switchbot"
      conditions:
        modelName: "WoSensorTH"
        temperature: "> 28.0"
    then:
      type: "shell_command"
      # We redirect to stderr (>&2) so the application logs the output
      # as an ERROR, making it visible by default without needing to
      # enable DEBUG level logging.
      command: "echo 'High temperature detected: {temperature}℃' >&2"
```

### Advanced Example: Inter-Device Automation

This example showcases the power of the new `switchbot_command` action. When a SwitchBot Contact Sensor on a door is opened, it triggers a SwitchBot Bot to press a button.

```yaml
automations:
  - name: "Press Light Switch when Office Door Opens"
    if:
      source: "switchbot"
      conditions:
        modelName: "WoContact"
        address: "XX:XX:XX:XX:XX:AA" # <-- Address of your Contact Sensor
        contact_open: True
    then:
      # This action directly controls another SwitchBot device.
      type: "switchbot_command"
      address: "YY:YY:YY:YY:YY:BB" # <-- Address of your SwitchBot Bot
      command: "press"
```


#### Advanced Example: Comparing Against the Previous State

`switchbot-actions` can create automations based not just on the current state, but by comparing it against the **immediately preceding state**. This is enabled by the `previous` context, allowing for more dynamic and powerful scenarios.

A great practical use case for this is detecting a button press on devices like the SwitchBot Contact Sensor or Bot. These devices expose a `button_count` attribute that increments each time the button is pressed. By checking if the current count is different from the previous one, you can reliably trigger an action on the press event itself.

**Example: Turn on a light when the Contact Sensor's button is pressed**

```yaml
automations:
  - name: "Turn on light when sensor button is pressed"
    if:
      source: "switchbot"
      conditions:
        modelName: "WoContact"
        # Trigger if the current button_count is not equal to the previous one.
        button_count: "!= {previous.button_count}"
    then:
      type: "shell_command"
      command: "echo 'Button on {address} was pressed. Turning on light.' >&2"
```

This pattern allows you to react to discrete **events** (a state *change*), rather than just static states (a door is open/closed), making your automations more intelligent.


### Detailed Reference & More Examples

For a complete reference of all configuration options--including advanced automations, time-based triggers, MQTT settings, the Prometheus exporter, and logging--please see the [**Project Specification**](https://github.com/hnw/switchbot-actions/blob/main/docs/specification.md).

#### Using Device Aliases in `if` Blocks

You can now use device aliases, defined in the top-level `devices` section, directly within the `if` block of your automations. This improves readability and maintainability by allowing you to refer to devices by a friendly name instead of their MAC address.

**Example:**

```yaml
devices:
  livingroom-meter:
    address: "11:22:33:44:55:66"

automations:
  - name: "Monitor Living Room Meter"
    if:
      source: "switchbot"
      # Reference a device alias defined in the `devices` section.
      # The `address` from `ivingroom-meter` will be automatically injected into `conditions.address`.
      device: "livingroom-meter"
      conditions:
        # If `address` is also specified here, the `device` alias's address
        # will take precedence and overwrite it.
        temperature: "> 25.0"
        humidity: "< 60.0"
    then:
      type: "shell_command"
      command: "echo 'Living room is hot and humid! ({temperature}C, {humidity}%)' >&2"
```

### Command-Line Options

Command-line options provide a convenient way to override settings in your `config.yaml` for testing or temporary changes.

  - `--config <path>` or `-c <path>`: Path to the configuration file (default: `config.yaml`).
  - `--debug` or `-d`: Enables `DEBUG` level logging.
  - `--scan-cycle <seconds>`: Overrides the scan cycle time.
  - `--scan-duration <seconds>`: Overrides the scan duration time.
  - **Boolean Flags**: For any boolean flag like `--prometheus-exporter-enabled`, a corresponding `--no-` version is available to explicitly disable the feature, overriding any `true` setting in the configuration file.
  - And many more for MQTT, Prometheus, etc. Run `switchbot-actions --help` for a full list.

**Configuration Precedence**: Settings are applied in the following order of priority (later items override earlier ones):
1.  Application defaults.
2.  `config.yaml` settings.
3.  Command-line flags.

## Robustness Features

`switchbot-actions` is designed with reliability in mind, ensuring stable operation even in the face of certain issues.

  - **Fail-Fast Startup**: The application performs critical resource checks at startup. If a required resource (e.g., the configured Prometheus port) is unavailable, the application will fail immediately with a clear error message. This prevents silent failures and ensures that operational issues are identified and addressed promptly.
  - **Configuration Reload with Rollback**: The application supports dynamic configuration reloading by sending a `SIGHUP` signal to its process. If a new configuration contains errors or leads to a failed reload, the application will automatically attempt to roll back to the last known good configuration. This prevents service interruptions due to misconfigurations and enhances overall system stability.
