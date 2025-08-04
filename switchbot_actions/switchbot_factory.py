# switchbot_actions/switchbot_factory.py

import switchbot

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
}


def create_switchbot_device(adv: switchbot.SwitchBotAdvertisement, **kwargs):
    model = adv.data.get("modelName")
    if model:
        device_class = DEVICE_CLASS_MAP.get(model)
        if device_class:
            return device_class(device=adv.device, **kwargs)
    return None
