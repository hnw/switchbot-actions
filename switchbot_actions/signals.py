# switchbot_actions/signals.py
from blinker import signal

# Signal that is sent when a new advertisement is received and parsed.
# The sender will be the SwitchbotManager instance.
# The device_data will be the parsed data from pyswitchbot.
advertisement_received = signal("advertisement-received")
