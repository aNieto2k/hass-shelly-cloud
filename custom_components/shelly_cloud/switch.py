"""Switch platform for Shelly Cloud.

Maps each ``switch:N`` channel (or ``relay:N`` on Gen 1) that is *not*
configured as a light (appliance_type / consumption_type = light) to a
``switch`` entity.
"""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_SWITCH
from .coordinator import ShellyCloudCoordinator
from .entity import ShellyCloudEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities from the device subentries."""
    runtime = entry.runtime_data
    coordinator: ShellyCloudCoordinator = runtime.coordinator

    entities: list[SwitchEntity] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type != "device":
            continue
        device_id = subentry.data["device_id"]
        device = coordinator.get_device(device_id)
        if device is None:
            continue
        for ch in device.iter_channels(KEY_SWITCH):
            if ch.is_light is True:
                continue
            entities.append(
                ShellyCloudSwitch(coordinator, device_id, ch.index, len(entities))
            )

    async_add_entities(entities)


class ShellyCloudSwitch(ShellyCloudEntity, SwitchEntity):
    """Representation of a Shelly Cloud relay as a switch."""

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
        channel: int,
        channel_count: int,
    ) -> None:
        suffix = f"switch_{channel}" if channel_count > 0 else "switch"
        super().__init__(coordinator, device_id, suffix)
        self._channel = channel
        self._attr_translation_key = "switch"

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        ch = device.get_channel(KEY_SWITCH, self._channel)
        if ch is None:
            return None
        return bool(ch.is_on)

    async def async_turn_on(self, **kwargs) -> None:
        device = self.device
        client = self.coordinator.client
        if device is None or device.is_gen1:
            await client.async_set_relay_v1(self._device_id, self._channel, "on")
        else:
            toggle_after = kwargs.get("turn_on_off_after")
            await client.async_set_switch(
                self._device_id,
                self._channel,
                True,
                toggle_after=toggle_after,
            )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        device = self.device
        client = self.coordinator.client
        if device is None or device.is_gen1:
            await client.async_set_relay_v1(self._device_id, self._channel, "off")
        else:
            await client.async_set_switch(self._device_id, self._channel, False)
        await self.coordinator.async_request_refresh()
