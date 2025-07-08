# Project Specification: switchbot-exporter

## 1. Overview

This document outlines the design for `switchbot-exporter`, a Python application designed to monitor SwitchBot Bluetooth Low Energy (BLE) devices. The project has two primary goals:

1.  **Prometheus Exporter**: To expose sensor and state data from SwitchBot devices as metrics that can be scraped by a Prometheus server.
2.  **Automation Engine**: To provide a mechanism for executing custom actions based on two distinct trigger types:
    * **Event-Driven Actions**: Execute actions immediately when a device's state changes.
    * **Time-Driven Timers**: Execute actions when a device remains in a specific state for a continuous duration.

The application is designed to be a long-running service, managed entirely through a single YAML configuration file, ensuring flexibility and ease of use without requiring code modification for new setups.

## 2. Architecture

The application employs a decoupled, signal-based architecture. The `DeviceScanner` component is responsible for scanning advertisements. For each new advertisement, it retrieves the device's previous state from the `DeviceStateStore` and then emits a single, rich `advertisement_received` signal containing both the new and old state data as its payload.

All other core components, such as the `EventDispatcher`, `TimerHandler`, and the `DeviceStateStore` itself, listen to this signal and react independently. This design ensures components are loosely coupled and prevents race conditions by providing all necessary context within the signal itself.

### Mermaid Class Diagram
```mermaid
classDiagram
    class DeviceScanner {
        +start_scan()
    }
    class DeviceStateStore {
        +get_state(mac)
        +handle_signal(payload)
    }
    class EventDispatcher {
        +handle_signal(payload)
    }
    class TimerHandler {
        +handle_signal(payload)
    }
    class PrometheusExporter{
        +start_server()
    }

    DeviceScanner --> DeviceStateStore : reads previous state
    PrometheusExporter --> DeviceStateStore : reads current state
    
    DeviceScanner ..> EventDispatcher : notifies via signal
    DeviceScanner ..> DeviceStateStore : notifies via signal
    DeviceScanner ..> TimerHandler : notifies via signal
````

## 3. Components

### 3.1. `DeviceScanner`

  - **Responsibility**: Continuously scans for SwitchBot BLE advertisements and serves as the central publisher of device events.
  - **Functionality**:
    1.  Scans for and receives a new device advertisement (`new_data`).
    2.  Retrieves the last known state (`old_data`) for that device from the `DeviceStateStore`.
    3.  Emits an `advertisement_received` signal with a payload containing both `new_data` and `old_data`.

### 3.2. `DeviceStateStore`

  - **Responsibility**: Acts as an in-memory cache for the latest known state of every observed device. It is the single source of truth for the current state of devices.
  - **Functionality**: Connects to the `advertisement_received` signal. Upon receiving a signal, it **immediately** updates its internal state for the relevant device using the `new_data` from the signal's payload.

### 3.3. `PrometheusExporter`

  - **Responsibility**: Exposes device states as Prometheus metrics.
  - **Functionality**: Starts an HTTP server. When scraped, it fetches the latest data for all devices from the `DeviceStateStore` and formats it into Prometheus metrics.

### 3.4. `EventDispatcher`

  - **Responsibility**: Handles **event-driven** automation based on rules in the `actions` section of the configuration.
  - **Functionality**: Connects to the `advertisement_received` signal. It uses both the new and old state from the signal's payload to evaluate if any conditions are met and, if so, triggers the appropriate action. The success or failure of its actions does not affect any other components.

### 3.5. `TimerHandler`

  - **Responsibility**: Handles **time-driven** automation by creating and managing individual asynchronous tasks for each timer.
  - **Functionality**: Connects to the `advertisement_received` signal and manages timers based on device state changes:
  - **Timer Start**: When a device's state meets a timer's `conditions` and a timer for that device/rule is not already running, it creates a new asynchronous task via `asyncio.create_task`. This dedicated task then waits for the specified `duration`. If the wait completes without interruption, the action is triggered.
  - **Timer Cancellation**: If a running timer's conditions are no longer met due to a new device state, the corresponding task is cancelled, effectively resetting the timer.

## 4. Configuration (`config.yaml`)

The application is controlled by `config.yaml`. The `mute_for` and `duration` values should be specified in a format compatible with the **`pytimeparse2`** library (e.g., "10s", "5m", "1.5h").

### 4.1. `prometheus_exporter`

Configures the Prometheus metrics endpoint.

  - `enabled`: (boolean) Toggles the feature.
  - `port`: (integer) The server port.
  - `target`: (dict, optional) Settings to filter the exported targets. **If this section is omitted, or if the `addresses`/`metrics` lists are empty, all discovered devices and all available metrics will be targeted, respectively.**
      - `addresses`: (list, optional) Only devices with a MAC address in this list will be targeted.
      - `metrics`: (list, optional) Only metrics with a name in this list will be exported.

### 4.2. `actions` (Event-Driven Triggers)

This section defines a list of rules that trigger **immediately** when a device's state changes. Each rule is a map that can contain the following keys:

  - **`name`**: (string) A unique, human-readable name for the action.
  - **`mute_for`**: (string, optional) A duration (e.g., "5s", "10m") during which this action will not be re-triggered after it fires. This is useful for preventing spam from rapid events. When a rule applies to multiple devices (e.g., by targeting a `modelName`), this cooldown is managed independently for each device.
  - **`conditions`**: (map, required) The "IF" part of the rule.
      - **`device`**: Filters which devices this rule applies to based on attributes like `modelName` or `address`.
      - **`state`**: Defines the state conditions that must be met. Most keys (e.g., `temperature`, `isOn`) are evaluated against the key-value pairs within the nested `data` object of the advertisement. As a special case, the key `rssi` is evaluated against the top-level RSSI value. In addition to standard comparisons (e.g., `temperature: "> 25.0"`), it supports special operators for tracking changes:
          - `"changes"`: Triggers if the value is different from the previously seen value.
          - `"changes to [value]"`: Triggers only if the value changes *and* the new value matches the specified one.
              - You can also use a comparison operator with a numeric value (e.g., `"changes to > 28.0"`). In this case, the trigger fires only at the moment the state changes from not meeting the condition to meeting it. For example, a trigger for `temperature: "changes to > 28.0"` will fire when the temperature changes from 27.9 to 28.1, but it will not fire for a subsequent change from 28.1 to 28.2.
  - **`trigger`**: (map, required) The "THEN" part of the rule. It defines the action to be performed and consists of a `type` (e.g., `shell_command`, `webhook`) and its corresponding parameters.

```yaml
actions:
  - name: "A unique name for the action"
    mute_for: "5s" # Optional: Mutes this action for 5 seconds after it fires.
    conditions:
      # Conditions to identify the target device(s).
      device:
        modelName: "Bot"
      # Conditions based on the device's state.
      state:
        # Triggers only when 'isOn' value changes TO True.
        isOn: "changes to True" 
        # Triggers on ANY change to 'button_count'.
        button_count: "changes"
        # Triggers when temperature is greater than 25.0.
        temperature: "> 25.0"
    # The action to perform.
    trigger:
      type: "shell_command" # or "webhook"
      command: "echo 'Action Triggered for {address}'"
```

### 4.3. `timers` (Time-Driven Triggers)

This section defines a list of rules that trigger when a device's state has been sustained for a specific duration. If the state changes and the conditions are no longer met before the `duration` has elapsed, the timer for that device is automatically reset and will only start again when the conditions are met.

**Note**: The state of timers is held in memory. If the application is restarted, all timer counts will be reset.

Each rule in the list is a map that can contain the following keys:

  - **`name`**: (string) A unique, human-readable name for the timer.
  - **`mute_for`**: (string, optional) An optional duration during which this timer will not be re-triggered after it fires. When a rule applies to multiple devices (e.g., by targeting a `modelName`), this cooldown is managed independently for each device.
  - **`conditions`**: (map, required) The "IF" part of the rule.
      - **`device`**: Filters which devices this rule applies to.
      - **`state`**: Defines the state that must be sustained. These conditions are evaluated against the **`data`** object within the advertisement data. It supports standard comparisons like `temperature: "> 25.0"` or `motion_detected: False`. **Note:** The `changes` and `changes to` operators are designed for instantaneous events and are conceptually incompatible with a sustained `duration`. Their use in a `timers` rule is not supported.
  - **`duration`**: (string, required) The period the state defined in `conditions` must be continuously met for the trigger to fire.
  - **`trigger`**: (map, required) The "THEN" part of the rule, defining the action to be performed.

```yaml
timers:
  - name: "A unique name for the timer"
    mute_for: "1h" # Optional: Mutes this timer for 1 hour after it fires.
    conditions:
      # Conditions to identify the target device(s).
      device:
        modelName: "WoPresence"
      # The state that must be sustained for the entire duration.
      state:
          motion_detected: False
      # The duration the state must be continuously met.
      duration: "5m" 
    # The action to perform.
    trigger:
      type: "shell_command"
      command: "echo 'No motion detected for 5 minutes at {address}!'"
```

## 5. Project Structure

```
/switchbot-exporter/
├── docs/
│   └── specification.md
├── switchbot_exporter/
│   ├── main.py             # Application entry point
│   ├── signals.py          # Blinker signals
│   ├── scanner.py          # DeviceScanner
│   ├── store.py            # DeviceStateStore
│   ├── exporter.py         # PrometheusExporter
│   ├── dispatcher.py       # EventDispatcher (handles 'actions')
│   └── timers.py           # TimerHandler (handles 'timers')
├── tests/
├── config.yaml.example
└── README.md
```
