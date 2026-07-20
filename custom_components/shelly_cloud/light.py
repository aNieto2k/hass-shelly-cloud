"""Light platform for Shelly Cloud.

Creates light entities for:
- ``switch:N`` channels whose ``appliance_type`` (G1) or ``consumption_type``
  (G2) is configured as ``light``.
- ``light:N`` channels (dedicated dimmable / RGBW bulbs).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ATTR_WHITE,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_LIGHT, KEY_SWITCH
from .coordinator import ShellyCloudCoordinator
from .entity import ShellyCloudEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up light entities from the device subentries."""
    coordinator: ShellyCloudCoordinator = entry.runtime_data.coordinator
    entities: list[LightEntity] = []

    for subentry in entry.subentries.values():
        if subentry.subentry_type != "device":
            continue
        device_id = subentry.data["device_id"]
        device = coordinator.get_device(device_id)
        if device is None:
            continue

        for ch in device.iter_channels(KEY_SWITCH):
            if ch.is_light is True:
                entities.append(
                    ShellyCloudSwitchAsLight(coordinator, device_id, ch.index)
                )

        for ch in device.iter_channels(KEY_LIGHT):
            entities.append(
                ShellyCloudLight(coordinator, device_id, ch.index, device)
            )

    async_add_entities(entities)


class ShellyCloudSwitchAsLight(ShellyCloudEntity, LightEntity):
    """A relay configured as a light (no dimming, no color)."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
        channel: int,
    ) -> None:
        super().__init__(coordinator, device_id, f"light_{channel}")
        self._channel = channel
        self._attr_translation_key = "light"

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        ch = device.get_channel(KEY_SWITCH, self._channel)
        return bool(ch.is_on) if ch else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_set_switch(
            self._device_id, self._channel, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.async_set_switch(
            self._device_id, self._channel, False
        )
        await self.coordinator.async_request_refresh()


class ShellyCloudLight(ShellyCloudEntity, LightEntity):
    """Dimmable / RGBW light channel."""

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
        channel: int,
        device,
    ) -> None:
        super().__init__(coordinator, device_id, f"light_{channel}")
        self._channel = channel
        self._device_ref = device
        self._attr_translation_key = "light"

        modes: set[ColorMode] = {ColorMode.ONOFF}
        state = device.get_status(KEY_LIGHT, channel)
        if "brightness" in state or "gain" in state:
            modes.add(ColorMode.BRIGHTNESS)
        if device.supports_color:
            modes.add(ColorMode.RGB)
        if device.supports_white_temperature:
            modes.add(ColorMode.COLOR_TEMP)
        if "white" in state:
            modes.add(ColorMode.WHITE)
        if not modes:
            modes = {ColorMode.ONOFF}
        self._attr_supported_color_modes = modes
        self._attr_color_mode = (
            ColorMode.RGB if ColorMode.RGB in modes else next(iter(modes))
        )

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        ch = device.get_channel(KEY_LIGHT, self._channel)
        return bool(ch.is_on) if ch else None

    @property
    def brightness(self) -> int | None:
        device = self.device
        if device is None:
            return None
        state = device.get_status(KEY_LIGHT, self._channel)
        # Shelly uses 0..100 for both brightness and gain
        value = state.get("brightness")
        if value is None:
            value = state.get("gain")
        if value is None:
            return None
        return int(float(value) * 2.55)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        device = self.device
        if device is None:
            return None
        state = device.get_status(KEY_LIGHT, self._channel)
        try:
            return (int(state["red"]), int(state["green"]), int(state["blue"]))
        except KeyError:
            return None

    @property
    def color_temp_kelvin(self) -> int | None:
        device = self.device
        if device is None:
            return None
        state = device.get_status(KEY_LIGHT, self._channel)
        if "temperature" in state:
            return int(state["temperature"])
        if "ct" in state:
            return int(state["ct"])
        return None

    @property
    def white_value(self) -> int | None:
        device = self.device
        if device is None:
            return None
        state = device.get_status(KEY_LIGHT, self._channel)
        if "white" in state:
            return int(state["white"])
        return None

    @property
    def effect_list(self) -> list[str] | None:
        device = self.device
        if device is None:
            return None
        state = device.get_status(KEY_LIGHT, self._channel)
        effects = state.get("effects_list")
        if isinstance(effects, list):
            return [str(e) for e in effects]
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        device = self.device
        if device is None or device.is_gen1:
            await self._async_turn_on_gen1(**kwargs)
        else:
            await self._async_turn_on_gen2(**kwargs)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        device = self.device
        if device is None or device.is_gen1:
            await self.coordinator.client.async_set_light_v1(
                self._device_id, self._channel, turn="off"
            )
        else:
            await self.coordinator.client.async_set_light(
                self._device_id, self._channel, on=False
            )
        await self.coordinator.async_request_refresh()

    async def _async_turn_on_gen1(self, **kwargs: Any) -> None:
        params: dict[str, Any] = {"turn": "on"}
        if ATTR_BRIGHTNESS in kwargs:
            params["brightness"] = max(1, int(kwargs[ATTR_BRIGHTNESS] / 2.55))
        if ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            params.update({"red": r, "green": g, "blue": b})
        if ATTR_WHITE in kwargs:
            params["white"] = kwargs[ATTR_WHITE]
        await self.coordinator.client.async_set_light_v1(
            self._device_id, self._channel, **params
        )

    async def _async_turn_on_gen2(self, **kwargs: Any) -> None:
        params: dict[str, Any] = {"on": True}
        if ATTR_BRIGHTNESS in kwargs:
            params["brightness"] = max(1, int(kwargs[ATTR_BRIGHTNESS] / 2.55))
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            params["temperature"] = kwargs[ATTR_COLOR_TEMP_KELVIN]
            params["mode"] = "white"
        if ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            params.update({"red": r, "green": g, "blue": b, "mode": "color"})
        if ATTR_WHITE in kwargs:
            params["white"] = kwargs[ATTR_WHITE]
        if ATTR_EFFECT in kwargs:
            params["effect"] = int(kwargs[ATTR_EFFECT])
        await self.coordinator.client.async_set_light(
            self._device_id, self._channel, **params
        )
