# switchbot_actions/switchbot_factory.py

import logging

import switchbot

logger = logging.getLogger(__name__)

DEVICE_CLASS_MAP = {
    switchbot.SwitchbotModel.BOT: switchbot.Switchbot,
    switchbot.SwitchbotModel.CURTAIN: switchbot.SwitchbotCurtain,
    switchbot.SwitchbotModel.PLUG_MINI: switchbot.SwitchbotPlugMini,
    switchbot.SwitchbotModel.HUMIDIFIER: switchbot.SwitchbotHumidifier,
    switchbot.SwitchbotModel.COLOR_BULB: switchbot.SwitchbotBulb,
    switchbot.SwitchbotModel.LIGHT_STRIP: switchbot.SwitchbotLightStrip,
    switchbot.SwitchbotModel.CEILING_LIGHT: switchbot.SwitchbotCeilingLight,
    switchbot.SwitchbotModel.FLOOR_LAMP: switchbot.SwitchbotCeilingLight,
    switchbot.SwitchbotModel.BLIND_TILT: switchbot.SwitchbotBlindTilt,
    switchbot.SwitchbotModel.ROLLER_SHADE: switchbot.SwitchbotRollerShade,
    switchbot.SwitchbotModel.CIRCULATOR_FAN: switchbot.SwitchbotFan,
    switchbot.SwitchbotModel.K10_PRO_VACUUM: switchbot.SwitchbotVacuum,
    switchbot.SwitchbotModel.K10_VACUUM: switchbot.SwitchbotVacuum,
    switchbot.SwitchbotModel.K20_VACUUM: switchbot.SwitchbotVacuum,
    switchbot.SwitchbotModel.S10_VACUUM: switchbot.SwitchbotVacuum,
    switchbot.SwitchbotModel.K10_PRO_COMBO_VACUUM: switchbot.SwitchbotVacuum,
    ### Devices which requires encryption
    switchbot.SwitchbotModel.EVAPORATIVE_HUMIDIFIER: switchbot.SwitchbotEvaporativeHumidifier,  # noqa: E501
    switchbot.SwitchbotModel.LOCK: switchbot.SwitchbotLock,
    switchbot.SwitchbotModel.LOCK_PRO: switchbot.SwitchbotLock,
    switchbot.SwitchbotModel.LOCK_LITE: switchbot.SwitchbotLock,
    switchbot.SwitchbotModel.LOCK_ULTRA: switchbot.SwitchbotLock,
    switchbot.SwitchbotModel.STRIP_LIGHT_3: switchbot.SwitchbotStripLight3,
    switchbot.SwitchbotModel.RELAY_SWITCH_1: switchbot.SwitchbotRelaySwitch,
    switchbot.SwitchbotModel.RELAY_SWITCH_1PM: switchbot.SwitchbotRelaySwitch,
    switchbot.SwitchbotModel.GARAGE_DOOR_OPENER: switchbot.SwitchbotRelaySwitch,
    switchbot.SwitchbotModel.RELAY_SWITCH_2PM: switchbot.SwitchbotRelaySwitch2PM,
    switchbot.SwitchbotModel.AIR_PURIFIER: switchbot.SwitchbotAirPurifier,
    switchbot.SwitchbotModel.AIR_PURIFIER_TABLE: switchbot.SwitchbotAirPurifier,
}


def create_switchbot_device(
    adv: switchbot.SwitchBotAdvertisement, **kwargs
) -> switchbot.SwitchbotDevice | None:
    model = adv.data.get("modelName")
    if model:
        device_class = DEVICE_CLASS_MAP.get(model)
        if device_class:
            return device_class(device=adv.device, **kwargs)
    return None
