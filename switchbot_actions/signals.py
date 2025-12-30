from blinker import signal

# External event notification
switchbot_advertisement_received = signal("switchbot-advertisement-received")
mqtt_message_received = signal("mqtt-message-received")

# Internal monitoring notification
scan_executed = signal("scan-executed")

# Internal action request
publish_mqtt_message_request = signal("publish-mqtt-message-request")

# Internal action notification
action_executed = signal("action-executed")
