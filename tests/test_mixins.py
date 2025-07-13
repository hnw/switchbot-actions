# tests/test_mixins.py
import time

import pytest

from switchbot_actions.mixins import MuteMixin


class TestMuteMixin:
    @pytest.fixture
    def mixin_instance(self):
        return MuteMixin()

    def test_initial_state(self, mixin_instance):
        assert not mixin_instance._is_muted("any_action", "addr1")

    def test_muting_is_per_device(self, mixin_instance):
        """Test that muting one device does not affect another."""
        mixin_instance._mute_action("test_action", "addr1", "1s")

        assert mixin_instance._is_muted("test_action", "addr1")
        assert not mixin_instance._is_muted("test_action", "addr2")
        assert not mixin_instance._is_muted("another_action", "addr1")

    def test_mute_duration(self, mixin_instance):
        """Test that the mute expires after the specified duration."""
        mixin_instance._mute_action("timed_action", "addr1", "0.1s")
        assert mixin_instance._is_muted("timed_action", "addr1")
        time.sleep(0.15)
        assert not mixin_instance._is_muted("timed_action", "addr1")

    def test_no_mute_if_duration_is_none(self, mixin_instance):
        mixin_instance._mute_action("no_mute", "addr1", None)
        assert not mixin_instance._is_muted("no_mute", "addr1")

    def test_invalid_duration_string(self, mixin_instance):
        mixin_instance._mute_action("invalid_duration", "addr1", "not a time")
        assert not mixin_instance._is_muted("invalid_duration", "addr1")
