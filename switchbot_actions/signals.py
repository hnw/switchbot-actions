from blinker import signal

# External event notification
state_changed = signal("switchbot-advertisement-received")
mqtt_message_received = signal("mqtt-message-received")

# Internal action request
publish_mqtt_message_request = signal("publish-mqtt-message-request")
