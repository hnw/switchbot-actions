# **Deployment Guide**

This guide covers two main ways to run switchbot-actions:

1. **Quick Start with `pipx`**: Ideal for initial testing and running the application as a user process.
2. **Running as a `systemd` Service**: The recommended method for continuous, 24/7 background operation on a Linux server.

## **Method 1: Quick Start with `pipx`**

This approach is perfect for easily testing the application or running it manually. We recommend a two-step process to ensure a smooth setup.

### **Step 1: Verify Hardware and Device Discovery**

Before creating any configuration, it's crucial to first verify that your system's Bluetooth adapter is working correctly and can discover your SwitchBot devices. This helps separate hardware/permission issues from configuration issues.

Run the application with the `--debug` flag and without a configuration file:

```
# You may need sudo for BLE permissions.
switchbot-actions --debug
```

If you see log lines containing `Received advertisement from...`, your hardware setup is correct and you can proceed to the next step. If you see permission errors, try running with `sudo`.

### **Step 2: Install, Configure, and Run**

Once hardware is verified, you can install the application and create your configuration.

1. **Installation**:

```
   # Install pipx if you haven't already
   pip install pipx
   pipx ensurepath

   # Install the application
   pipx install switchbot-actions
```

_(You may need to restart your terminal for the `pipx` command to be available.)_ 2. Configuration:
Download the example configuration and edit it for your needs.

```
   curl -o config.yaml https://raw.githubusercontent.com/hnw/switchbot-actions/main/config.yaml.example
   nano config.yaml
```

3. Running the Application:
   Run the application, pointing to your configuration file.

```
   switchbot-actions -c /path/to/your/config.yaml
```

## **Method 2: Running as a `systemd` Service (Recommended for Production)**

This method sets up switchbot-actions to run as a persistent background service that starts on boot. It uses a dedicated virtual environment (venv) for robust dependency management.

### **Step 1: Create a Dedicated Virtual Environment**

First, create a directory for the application and its virtual environment in /opt, a standard location for optional software.

```
sudo mkdir -p /opt/switchbot-actions
sudo python3 -m venv /opt/switchbot-actions
```

### **Step 2: Install the Application into the** venv

Use the pip executable from the newly created virtual environment to install the package.

```
sudo /opt/switchbot-actions/bin/pip install switchbot-actions
```

### **Step 3: Place the Configuration File**

It's good practice to store configuration files in /etc.

```
# Create a dedicated directory for the config file
sudo mkdir -p /etc/switchbot-actions

# Download the example config to the new location
sudo curl -o /etc/switchbot-actions/config.yaml https://raw.githubusercontent.com/hnw/switchbot-actions/main/config.yaml.example

# Edit the configuration for your environment
sudo nano /etc/switchbot-actions/config.yaml
```

### **Step 4: Create the** systemd **Service File**

Create a new service file at /etc/systemd/system/switchbot-actions.service.

```
sudo nano /etc/systemd/system/switchbot-actions.service
```

Paste the following content. This configuration is secure, as it runs the service as a temporary, unprivileged user (DynamicUser=yes).

```
[Unit]
Description=SwitchBot Actions Service
# Ensures the service starts after the network and Bluetooth services are ready
After=network.target bluetooth.service
Wants=bluetooth.service

[Service]
# Run the service as its own minimal-privilege, dynamically-created user
DynamicUser=yes

# Use the absolute path to the executable in your venv and the config file
ExecStart=/opt/switchbot-actions/bin/switchbot-actions -c /etc/switchbot-actions/config.yaml

# This is crucial for granting the necessary BLE permissions to the dynamic user.
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN

# Restart the service automatically if it exits
Restart=on-failure
RestartSec=10

# Redirect standard output and error to the systemd journal
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### **Step 5: Enable and Start the Service**

Now, manage the service using systemctl.

```
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start automatically on boot
sudo systemctl enable switchbot-actions.service

# Start the service immediately
sudo systemctl start switchbot-actions.service

# Check the status to ensure it's running correctly
systemctl status switchbot-actions.service
```

### **Step 6: View Logs and Reload Configuration**

- **To view logs**:

```
# Follow logs in real-time
journalctl -u switchbot-actions.service -f
```

- To reload configuration without downtime:

After editing /etc/switchbot-actions/config.yaml, send a SIGHUP signal to apply the changes.

```
sudo systemctl reload switchbot-actions.service
```

## **Method 3: Running with Docker**

`switchbot-actions` is also provided as a Docker image, allowing for easy use without setting up a Python environment. This guide covers basic setup, key requirements for Bluetooth, and advanced use cases.

### **Prerequisites**

1.  **Docker Installed**: You must have a working installation of Docker and, optionally, Docker Compose.
2.  **Configuration File**: Prepare your `config.yaml` file on the host machine.

---

### **Key Requirements for Bluetooth (BLE) Scanning**

A Docker container is typically isolated from the host machine. To allow `switchbot-actions` to access the host's physical Bluetooth adapter for BLE scanning, two specific configurations are **mandatory**.

1.  **Share the Host's Network Stack**: The container must share the host's network environment to see and control the physical Bluetooth hardware.
2.  **Access the D-Bus System**: The application communicates with the host's system Bluetooth service (BlueZ) via the D-Bus messaging system. The container needs access to this system's communication socket.

You can think of it like making a phone call: accessing D-Bus is like **knowing the right phone number**, while sharing the network is like **having permission to use the phone hardware**. You need both to connect.

Here is how to apply these settings for both `docker run` and `docker-compose`:

| Requirement       | `docker run` Flag                | `docker-compose.yml` Key                     |
| :---------------- | :------------------------------- | :------------------------------------------- |
| **Share Network** | `--net=host`                     | `network_mode: host`                         |
| **Access D-Bus**  | `-v /var/run/dbus:/var/run/dbus` | `volumes: [ "/var/run/dbus:/var/run/dbus" ]` |

---

### **1. Running with `docker run`**

This method is ideal for quick tests or manual execution.

```bash
docker run --rm \
  --name switchbot-actions \
  --net=host \
  -v /var/run/dbus:/var/run/dbus \
  -v "$(pwd)/config.yaml":/app/config.yaml \
  ghcr.io/hnw/switchbot-actions:latest -c /app/config.yaml
```

- `--rm`: Automatically removes the container when it exits.
- `--net=host`: **(Required for BLE)** Shares the host's network stack.
- `-v /var/run/dbus:/var/run/dbus`: **(Required for BLE)** Mounts the D-Bus socket for system service communication.
- `-v .../config.yaml:/app/config.yaml`: Mounts your configuration file into the container.

---

### **2. Running with `docker-compose` (Recommended)**

For long-running services or managing multiple containers (e.g., `switchbot-actions` and Alloy), using a `docker-compose.yml` file is much more convenient.

Here is an example `docker-compose.yml` file:

```yaml
# docker-compose.yml
services:
  switchbot-actions:
    image: ghcr.io/hnw/switchbot-actions:latest
    container_name: switchbot-actions
    restart: unless-stopped
    # --- Required settings for BLE scanning ---
    network_mode: host
    volumes:
      - /var/run/dbus:/var/run/dbus
      # -----------------------------------------
      # Mount your configuration file
      - ./config.yaml:/app/config.yaml
      # (Optional) Mount a directory for host command scripts
      # - ./scripts:/etc/switchbot-scripts
    command: -c /app/config.yaml
```

You can start the service in the background with the command `docker compose up -d`.

---

### **3. Advanced Topics**

#### **A. Calling Host Commands Safely**

The `shell_command` action is designed to run commands _inside_ the container. To securely execute a command on the **host** (e.g., to play a sound or send a desktop notification), the recommended pattern is to use a "wrapper script".

This involves creating a script on the host that only runs specific, pre-approved commands, and then mounting this script into the container.

1.  **Create a script on the host** (e.g., at `./scripts/host-runner.sh`):
    ```bash
    #!/bin/sh
    # This script acts as a safe gatekeeper for host commands.
    ACTION="$1"
    case "$ACTION" in
      "play_doorbell") aplay /path/to/host/sound.wav ;;
      *) echo "Error: Action not allowed" >&2; exit 1 ;;
    esac
    ```
2.  **Mount the script** in your `docker-compose.yml` (as shown in the example above).
3.  **Call the script** from your `config.yaml`:
    ```yaml
    then:
      - type: shell_command
        # Call the script mounted inside the container
        command: ["/etc/switchbot-scripts/host-runner.sh", "play_doorbell"]
    ```
