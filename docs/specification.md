# **Project Specification: switchbot-actions**

## **1. Overview**

This document outlines the design for `switchbot-actions`, a Python application designed to monitor SwitchBot Bluetooth Low Energy (BLE) devices and other event sources, and execute custom actions based on a flexible rule engine.

The project has two primary goals:

1. **Automation Engine**: To provide a unified mechanism for executing custom actions based on a flexible `if`/`then` rule structure defined in a single configuration file.
2. **Prometheus Exporter**: To expose sensor and state data from SwitchBot devices as metrics that can be scraped by a Prometheus server.

## **2. Architecture**

The application employs a decoupled, signal-based architecture. `SwitchbotScanner` and `MqttClient` act as event sources, emitting signals for new device advertisements or messages.

These signals are consumed by the `AutomationHandler`, which acts as a central dispatcher. Upon receiving an event, the handler retrieves the previous state of the device from the `StateStore` and constructs a `StateSnapshot` of all current device states. These pieces of context are used to create a unified `StateObject`.

This `StateObject` is then passed to the appropriate `ActionRunner` instances. Each `ActionRunner` encapsulates a `Trigger` (which determines _if_ the rule's conditions are met) and a list of `ActionExecutors` (which determine _what_ to do). This design abstracts the trigger logic from the action execution, allowing for complex and reusable components.

#### **Class Diagram**

```mermaid
classDiagram
    direction TB

    class Application {
        +start()
        +stop()
        +reload_settings()
    }

    class BaseComponent {
        <<Abstract>>
        +settings: SettingsType
        +is_running: bool
        +is_enabled: bool
        +start()
        +stop()
        #_is_enabled() bool
        #_start()
        #_stop()
    }

    class SwitchbotScanner {
    }

    class MqttClient {
        +publish()
    }

    class AutomationHandler {
        +handle_switchbot_event(state)
        +handle_mqtt_event(state)
    }

    class PrometheusExporter {
    }

    class ActionRunner {
        +run(state: StateObject)
    }

    class Trigger {
        <<Abstract>>
        #if_config: AutomationIf
        +process_state(state)
    }

    class ActionExecutor {
        <<Abstract>>
        #action_config: AutomationAction
        +execute(state: StateObject)
    }

    class StateStore {
        +get(key)
        +get_and_update(key, event)
    }

    class StateObject {
        <<Abstract>>
        +id: str
        +previous: StateObject
        +snapshot: StateSnapshot
        +format(template)
    }

    class StateSnapshot {
        +__getattr__(alias: str) : StateObject
    }

    %% --- Inheritance ---
    BaseComponent <|-- SwitchbotScanner
    BaseComponent <|-- MqttClient
    BaseComponent <|-- PrometheusExporter
    BaseComponent <|-- AutomationHandler


    %% --- Aggregation/Composition (has-a) relationships ---
    Application o-- BaseComponent : components
    Application o-- StateStore

    AutomationHandler "1" *-- "N" ActionRunner
    ActionRunner "1" o-- "1" Trigger
    ActionRunner "1" *-- "N" ActionExecutor
    StateObject o-- StateSnapshot

    %% --- Self-reference relationship for state history ---
    StateObject o-- StateObject : previous

    %% --- Dependency (uses-a) relationships ---
    ActionRunner ..> StateObject
    Trigger ..> StateObject
    ActionExecutor ..> StateObject
    ActionExecutor ..> StateStore
    AutomationHandler ..> StateStore
    AutomationHandler ..> StateSnapshot
    PrometheusExporter ..> StateObject

    %% --- Signal-based communication, represented as dependencies ---
    SwitchbotScanner ..> AutomationHandler : signal
    SwitchbotScanner ..> PrometheusExporter : signal
    MqttClient ..> AutomationHandler : signal
    ActionExecutor ..> Application : signal
    Application ..> MqttClient
```

## **3. Quick Start Configuration**

For those who want to get started quickly, here is a minimal but practical `config.yaml` that demonstrates a key feature: inter-device automation.

This configuration will log a warning if the office temperature rises above 28属C **and** the office window is closed at the same time.

```yaml
# config.yaml

# Define aliases for your devices for easy reference.
devices:
  office-meter:
    address: "aa:bb:cc:dd:ee:ff" # Your temperature sensor's address
  office-window:
    address: "11:22:33:44:55:66" # Your contact sensor's address

# Define your automation rules.
automations:
  - name: "Turn on Fan when Hot and Window is Closed"
    if:
      # This rule triggers when the temperature sensor sends an update.
      source: "switchbot"
      device: "office-meter"
      conditions:
        # Condition 1: The sensor's temperature is above 28.0.
        temperature: "> 28.0"
        # Condition 2: At the same moment, check the state of the window sensor.
        office-window.contact_open: false
    then:
      # If both conditions are true, execute this action.
      type: "log"
      level: "WARNING"
      message: "Room is hot ({office-meter.temperature}属C) and window is closed. Consider turning on the fan."
```

## **4. Automation Engine Deep Dive**

This is the core of the application. The automation engine is configured under the `automations` and `devices` top-level keys in your `config.yaml`.

### **4.1. Core Concepts**

An automation rule consists of three main parts:

- **Rule**: A container for a single automation, which can have a `name` and a `cooldown`. The cooldown is managed on a per-device basis (or per-topic for MQTT triggers).
- **Trigger (`if` block)**: Defines **when** the rule should be activated. It specifies the event `source` and a set of `conditions` to be met.
- **Actions (`then` block)**: Defines **what** happens when the rule is triggered. It contains one or more actions to be executed.

### **4.2. Trigger Configuration (`if` block)**

The `if` block determines the precise circumstances under which an automation will run.

#### **4.2.1. Trigger Behavior: Immediate vs. Duration-Based**

The behavior of a trigger is determined by the presence of the `duration` key.

- **Immediate Trigger (Edge-Triggered)**: If `duration` is **not** present, the rule triggers immediately as soon as the conditions are met.
- **Duration-Based Trigger**: If `duration` **is** present (e.g., `duration: "5m"`), the rule triggers only after the conditions have been continuously met for that entire time period.

More specifically, a timer is started the moment the conditions for the rule first become true. If the conditions become false at any point before the duration has passed, the timer is cancelled. The action is executed only if the timer is allowed to complete without interruption.

#### **4.2.2. Trigger Source (`source`)**

This mandatory key defines the origin of the event that can trigger the rule.

- `switchbot`: Triggers based on state changes from SwitchBot BLE devices.
- `mqtt`: Triggers based on messages received from an MQTT topic.

For `mqtt` sources, the `topic` key is also required.

#### **4.2.3. Conditions (`conditions`)**

The `conditions` map is where you define the specific state(s) required to trigger the rule.

##### **A. Basic Syntax and Evaluation Rules**

A condition is a key-value pair in the format: `attribute: 'operator value'`.

- **`attribute`**: The name of the state attribute to check (e.g., `temperature`).
- **`operator`**: (Optional) Can be `==`, `!=`, `>`, `<`, `>=`, `<=`.
- **`value`**: The value to compare against.

The evaluation engine follows a clear set of rules to interpret the condition string:

1.  **Operator Parsing**: If the value string begins with a recognized operator (e.g., `> `), it is parsed as a comparison. The remainder of the string is treated as the value to compare against.

2.  **Implicit Equality**: If no operator is found at the beginning of the string, the `==` (equals) operator is assumed, and the entire string is used as the value. For example, `modelName: "WoSensorTH"` is equivalent to `modelName: "== WoSensorTH"`.

3.  **Automatic Type Casting**: The engine attempts to convert the value string to match the data type of the state's `attribute` (e.g., number, boolean) before the comparison is performed. For instance, in the condition `temperature: '> 28.0'`, the string `"28.0"` is converted to a float before the numeric comparison occurs. If this conversion fails, the condition evaluates to `False`.

Example: `temperature: '> 28.0'`

##### **B. Condition Targets: Whose State to Evaluate?**

You can evaluate conditions against three different contexts:

| **Target**            | **Key Syntax**       | **Description**                                                                                                   | **Example**                    |
| :-------------------- | :------------------- | :---------------------------------------------------------------------------------------------------------------- | :----------------------------- |
| **Triggering Device** | `attribute`          | The state of the device that initiated the event.                                                                 | `temperature: '> 25.0'`        |
| **Other Devices**     | `alias.attribute`    | The state of another device at the moment of the trigger. alias must be defined in the top-level devices section. | `living-room-ac.power: 'on'`   |
| **Previous State**    | `previous.attribute` | The state of the triggering device just before the current event.                                                 | `previous.contact_open: false` |

##### **C. Dynamic Comparisons with `previous`**

The `previous` context is powerful because it can be used on both sides of a condition, allowing you to detect state _changes_.

- **Left-Hand Side (LHS)**: Use `previous.attribute` as the key to check what the state _was_.
  - **Use Case**: Trigger when a door that _was closed_ is now open.
  - **Example**:

```yaml
conditions:
  previous.contact_open: false # The door was closed.
  contact_open: true # And now it is open.
```

- **Right-Hand Side (RHS)**: Use `{previous.attribute}` as a placeholder in the value to compare the current state against the previous one.
  - **Use Case**: Trigger on a button press by detecting if `button_count` has changed.
  - **Example**:

```yaml
conditions:
  # Triggers if the current count is not equal to the previous count.
  button_count: "!= {previous.button_count}"
```

##### **D. Handling Invalid References**

If a condition refers to an alias or attribute that does not exist (e.g., `non_existent_alias.temperature`), the condition is safely evaluated as `False`, and a `WARNING` is logged. The application will not crash.

##### **E. Empty Conditions Behavior: The "First Seen" Trigger**

When the `conditions` block is omitted or left empty, the rule's condition is always considered `True`.

When combined with a standard automation rule (which is edge-triggered), this creates a **"first seen" trigger**. Crucially, this "first seen" status is tracked independently for each entity:

- For `source: switchbot`, the trigger will fire **once for each unique device** (identified by its MAC address) that matches the rule.
- For `source: mqtt`, the trigger will fire **once for each unique topic** that matches the rule.

This behavior is useful for running an action the very first time a specific device is detected by the scanner, or the first time a message appears on a particular MQTT topic.

#### **Example: Setting an Initial Position for Curtains on First Detection**

This rule ensures that any newly detected curtain device is immediately set to the fully open position (100%). It will run once for each unique curtain, making it an effective initialization task.

```yaml
automations:
  - name: "Set Initial Curtain Position on First Detection"
    if:
      source: "switchbot"
      # This rule applies to all devices of model 'WoCurtain'
      conditions:
        modelName: "WoCurtain"
    then:
      - type: "log"
        message: "Curtain {address} detected for the first time. Setting to open position."
      - type: "switchbot_command"
        address: "{address}" # The address of the triggering curtain
        command: "set_position"
        params:
          position: 100 # 0=closed, 100=open
```

> [!IMPORTANT]
> Because this trigger fires for each new entity, it is highly recommended to constrain the rule using keys like `device`, `address`, `topic`, or `modelName`. An unconstrained rule (e.g., only `source: switchbot`) could trigger for many unexpected devices.

### **4.3. Action Configuration (`then` block)**

The `then` block specifies one or more actions to execute when the `if` conditions are met. It can be a single action (a map) or a list of actions. All string parameters in actions support placeholders (e.g., `{temperature}`).

#### **Action Types**

- **`log`**: Logs a message to the application's console.
  - `message`: (string, required) The message to log.
  - `level`: (string, optional, default: `INFO`) Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- **`shell_command`**: Executes a shell command.
  - `command`: (list of strings, required) The command and its arguments as a list. The first element is the command, and subsequent elements are its arguments. This prevents command injection by avoiding shell interpretation.
- **`webhook`**: Sends an HTTP request.
  - `url`: (string, required) The target URL.
  - `method`: (string, optional, default: `POST`) `POST` or `GET`.
  - `payload`: (map or string, optional) For `POST`, this is the JSON body. For `GET`, these are the URL query parameters.
  - `headers`: (map, optional) Custom HTTP headers.
- **`mqtt_publish`**: Publishes a message to an MQTT topic.
  - `topic`: (string, required) The target topic.
  - `payload`: (map or string, optional) The message payload. Maps are sent as JSON.
  - `qos`: (integer, optional, default: `0`) Quality of Service (`0`, `1`, or `2`).
  - `retain`: (boolean, optional, default: `false`) The retain flag.
- **`switchbot_command`**: Directly controls another SwitchBot device.
  - `device`: (string, optional) A reference to an alias in the `devices` section.
  - `address`: (string, optional) The MAC address of the target device. (Use `device` or `address`, not both).
  - `command`: (string, required) The command to execute (e.g., `turn_on`, `press`, `set_position`). Must match a method in the `pySwitchbot` library.
  - `params`: (map, optional) Arguments for the command method (e.g., `position`: `100`).
  - `config`: (map, optional) Constructor arguments for the device (e.g., `password`, `key_id`).

### **4.4. Device Definitions (`devices` block)**

This top-level section allows you to define reusable aliases for your devices. This is highly recommended as it makes your automations cleaner and easier to manage.

- **Key**: The alias name you will use in `if` and `then` blocks (e.g., `office-meter`).
- **`address`**: (string, required) The MAC address of the device.
- **`config`**: (map, optional) Device-specific constructor arguments for `pyswitchbot` (e.g., `password`, `encryption_key`).

An alias can be used in two places:

- `if.device`: Automatically adds the device's address to the conditions.
- `then.device`: Specifies the target for a `switchbot_command` action.

## **5. Component Configuration Reference**

This section covers the configuration for the application's other components.

### **5.1. Configuration Precedence**

Settings are loaded in the following order, with later sources overriding earlier ones:

1. **Application Defaults**: Hardcoded default values.
2. **config.yaml Settings**: Values loaded from your configuration file.
3. **Command-Line Flags**: Arguments passed at runtime (e.g., --debug, --scan-cycle).

### **5.2. `scanner`**

Configures the BLE scanning behavior. These settings can be overridden by the `--scanner-cycle`, `--scanner-duration`, and `--scanner-interface` command-line flags.

- `cycle`: (integer, optional, default: `10`) Time in seconds between the start of each scan cycle.
- `duration`: (integer, optional, default: `3`) Time in seconds the scanner will actively listen. Must be less than or equal to `cycle`.
- `interface`: (integer, optional, default: `0`) Bluetooth adapter number (e.g., `0` for `hci0`).

### **5.3. `mqtt`**

Configures the MQTT client connection.

- `enabled`: (boolean, optional, default: `false`) Enables or disables the MQTT client. Can be overridden with the `--mqtt` and `--no-mqtt` flags.
- `host`: (string, optional, default: `localhost`) Hostname or IP of the MQTT broker.
- `port`: (integer, optional, default: `1883`)
- `username` / `password`: (string, optional)
- `reconnect_interval`: (float, optional, default: `10`) Seconds to wait before reconnecting.

### **5.4. `prometheus`**

Configures the Prometheus metrics endpoint.

- `enabled`: (boolean, optional, default: `false`)
- `port`: (integer, optional, default: `8000`)
- `target`: (map, optional)
  - `addresses`: (list, optional) List of MAC addresses to export. If empty, all are exported.
  - `metrics`: (list, optional) List of metric names (e.g., `temperature`) to export. If empty, all are exported.

- **`switchbot_device_info` metric**: This metric provides metadata about configured SwitchBot devices, including their `address`, user-defined `name` (alias), and `model`. Its value is always `1` and it's useful for joining with other metrics to make queries more readable.

  **Example PromQL Query (to get temperature by device name):**

  ```promql
  switchbot_temperature * on(address) group_left(name) switchbot_device_info{name="living_room_meter"}
  ```

### **5.5. `logging`**

Configures logging behavior.

- `level`: (string, optional, default: "`INFO`") (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
- `format`: (string, optional) Log format string.
- `loggers`: (map, optional) Set specific levels for libraries (e.g., `bleak`: "`WARNING`"). To troubleshoot why an automation rule isn't working, enable detailed logging for the automation engine by `setting switchbot_actions.automation: "DEBUG"`.

## **6. State Object & Placeholder Reference**

### **6.1. Placeholder Resolution Priority**

Placeholders allow you to insert dynamic data into your actions. They are resolved from the `StateObject` that triggered the rule by checking for a matching key in the following order of priority. The first match found is used.

1.  **The `previous` Keyword**: Keys prefixed with `previous.` (e.g., `{previous.temperature}`) always refer to the state of the triggering device just before the current event.

2.  **Triggering Device's Attributes**: Keys that match an attribute of the triggering event's device (e.g., `{temperature}`, `{humidity}`, `modelName`) are resolved next.

3.  **Other Device Aliases**: If the key does not match an attribute on the triggering device, the engine will then look for a matching device alias defined in the top-level `devices` section (e.g., `{living-room-ac.power}`).

This priority is important. For example, if a rule is triggered by a device that has a `humidity` attribute, the placeholder `{humidity}` will always use the triggering device's value, even if another device happens to be aliased as `humidity`.

### **6.2. Placeholder Syntax and Available Attributes**

The table below shows the basic syntax for accessing different state contexts.

| **Placeholder Syntax** | **Description**                                                    | **Example Value**                         |
| :--------------------- | :----------------------------------------------------------------- | :---------------------------------------- |
| `{attribute}`          | An attribute of the **triggering device**.                         | `{temperature}` -> `25.5`                 |
| `{previous.attribute}` | An attribute from the **previous state** of the triggering device. | `{previous.temperature}` -> `25.0`        |
| `{alias.attribute}`    | An attribute from **another device**, accessed via its alias.      | `{office-window.contact_open}` -> `false` |

**Commonly Available Attributes:**

- **All Devices**: `address`, `modelName`, `rssi`, `battery`.
- **Meter/Sensor**: `temperature`, `humidity`.
- **Contact Sensor**: `contact_open`, `is_light`, `motion_detected`, `button_count`.
- **Bot/Plug**: `isOn`.
- **Curtain**: `position`, `in_motion`.
- **MQTT**: `topic`, `payload`, and any keys from a JSON payload.

## **7. Developer Guide**

### **7.1. Internal Signals**

The application uses the `blinker` library for internal communication.

| **Signal Name**                    | **Emitter**        | **Role**                                        |
| :--------------------------------- | :----------------- | :---------------------------------------------- |
| `switchbot-advertisement-received` | `SwitchbotScanner` | Notifies of a new SwitchBot BLE advertisement.  |
| `mqtt-message-received`            | `MqttClient`       | Notifies of a new MQTT message.                 |
| `publish-mqtt-message-request`     | `ActionExecutor`   | Requests the `MqttClient` to publish a message. |

### **7.2. How to Add a New Trigger Source**

1. **Create a `StateObject` subclass** in `state.py`.
2. **Update the `create_state_object` factory** in `state.py` to handle the new event type.
3. **Create a new component** that emits a new signal with the raw event data.
4. **Update `AutomationHandler`** to subscribe to the new signal and dispatch it.
5. **Update `config.py`** to validate any new configuration parameters.
6. **Document** the new source and its `StateObject` structure here.

### **7.3. How to Add a New Action Type**

1. **Define a `pydantic` model** for the action in `config.py` and add it to the `AutomationAction` union type.
2. **Implement an `ActionExecutor` subclass** in `action_executor.py`.
3. **Update the `create_action_executor` factory** to instantiate your new executor.
4. **Document** the new action type and its parameters here.

## **8. Project Structure**

```
/switchbot-actions/
├── docs/
│   ├── deployment.md
│   └── specification.md
├── switchbot_actions/
│   ├── app.py              # Application main logic
│   ├── base_component.py   # Abstract base class for components
│   ├── action_executor.py  # Action execution logic
│   ├── action_runner.py    # ActionRunnerBase and concrete implementations
│   ├── cli.py              # Command-line interface entry point
│   ├── config.py           # Pydantic models for configuration
│   ├── state.py            # StateObject class hierarchy for event data encapsulation
│   ├── prometheus.py       # PrometheusExporter
│   ├── handlers.py         # AutomationHandler
│   ├── logging.py          # Logging setup
│   ├── mqtt.py             # MqttClient
│   ├── scanner.py          # SwitchbotScanner
│   ├── signals.py          # Blinker signals
│   ├── store.py            # StateStore
│   └── timers.py           # Timer class
├── tests/
├── config.yaml.example
└── README.md
```
