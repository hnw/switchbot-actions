# switchbot_actions/signals.py
from blinker import signal

# Signal sent when a new state object is processed.
state_changed = signal("state-changed")
