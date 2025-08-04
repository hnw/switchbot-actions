from unittest.mock import Mock, patch

import pytest
import switchbot

from switchbot_actions.switchbot_factory import (
    DEVICE_CLASS_MAP,
    create_switchbot_device,
)


@pytest.fixture
def mock_advertisement():
    """Fixture to create a mock SwitchBotAdvertisement object."""
    mock_adv = Mock(spec=switchbot.SwitchBotAdvertisement)
    mock_adv.device = "AA:BB:CC:DD:EE:FF"
    mock_adv.data = {"modelName": "Bot"}  # Default modelName
    return mock_adv


def test_create_switchbot_device_valid_model(mock_advertisement):
    """Test creating a device with a valid modelName."""
    mock_advertisement.data["modelName"] = switchbot.SwitchbotModel.BOT.value
    with patch.dict(
        DEVICE_CLASS_MAP, {switchbot.SwitchbotModel.BOT: Mock(spec=switchbot.Switchbot)}
    ):
        device = create_switchbot_device(mock_advertisement)
        assert device is not None
        assert isinstance(device, Mock)
        DEVICE_CLASS_MAP[switchbot.SwitchbotModel.BOT].assert_called_once_with(
            device=mock_advertisement.device
        )


def test_create_switchbot_device_invalid_model(mock_advertisement):
    """Test creating a device with an invalid modelName."""
    mock_advertisement.data["modelName"] = "UnknownModel"
    device = create_switchbot_device(mock_advertisement)
    assert device is None


def test_create_switchbot_device_no_model_name(mock_advertisement):
    """Test creating a device when modelName is missing from advertisement data."""
    mock_advertisement.data = {}
    device = create_switchbot_device(mock_advertisement)
    assert device is None


def test_create_switchbot_device_with_kwargs(mock_advertisement):
    """Test creating a device with additional keyword arguments."""
    mock_advertisement.data["modelName"] = switchbot.SwitchbotModel.BOT.value
    with patch.dict(
        DEVICE_CLASS_MAP, {switchbot.SwitchbotModel.BOT: Mock(spec=switchbot.Switchbot)}
    ):
        device = create_switchbot_device(
            mock_advertisement, token="test_token", secret="test_secret"
        )
        assert device is not None
        DEVICE_CLASS_MAP[switchbot.SwitchbotModel.BOT].assert_called_once_with(
            device=mock_advertisement.device, token="test_token", secret="test_secret"
        )


@pytest.mark.parametrize(
    "model_name, expected_class",
    [
        (switchbot.SwitchbotModel.BOT, switchbot.Switchbot),
        (switchbot.SwitchbotModel.CURTAIN, switchbot.SwitchbotCurtain),
        (switchbot.SwitchbotModel.PLUG_MINI, switchbot.SwitchbotPlugMini),
        (switchbot.SwitchbotModel.HUMIDIFIER, switchbot.SwitchbotHumidifier),
        (switchbot.SwitchbotModel.COLOR_BULB, switchbot.SwitchbotBulb),
        (switchbot.SwitchbotModel.LIGHT_STRIP, switchbot.SwitchbotLightStrip),
        (switchbot.SwitchbotModel.CEILING_LIGHT, switchbot.SwitchbotCeilingLight),
        (switchbot.SwitchbotModel.FLOOR_LAMP, switchbot.SwitchbotCeilingLight),
        (switchbot.SwitchbotModel.BLIND_TILT, switchbot.SwitchbotBlindTilt),
        (switchbot.SwitchbotModel.ROLLER_SHADE, switchbot.SwitchbotRollerShade),
        (switchbot.SwitchbotModel.CIRCULATOR_FAN, switchbot.SwitchbotFan),
        (switchbot.SwitchbotModel.K10_PRO_VACUUM, switchbot.SwitchbotVacuum),
        (switchbot.SwitchbotModel.K10_VACUUM, switchbot.SwitchbotVacuum),
        (switchbot.SwitchbotModel.K20_VACUUM, switchbot.SwitchbotVacuum),
        (switchbot.SwitchbotModel.S10_VACUUM, switchbot.SwitchbotVacuum),
        (switchbot.SwitchbotModel.K10_PRO_COMBO_VACUUM, switchbot.SwitchbotVacuum),
    ],
)
def test_create_switchbot_device_all_models(
    mock_advertisement, model_name, expected_class
):
    """Test creating devices for all known models in DEVICE_CLASS_MAP."""
    mock_advertisement.data["modelName"] = model_name.value  # Use .value for enum
    with patch.dict(
        DEVICE_CLASS_MAP, {m.value: Mock(spec=c) for m, c in DEVICE_CLASS_MAP.items()}
    ):
        device = create_switchbot_device(mock_advertisement)
        assert device is not None
        assert isinstance(device, Mock)
        # Verify that the correct class was called
        DEVICE_CLASS_MAP[model_name.value].assert_called_once_with(
            device=mock_advertisement.device
        )
