"""Cover platform for Shelly Cloud.

Maps ``cover:N`` channels (or ``roller:N`` on Gen 1) to ``cover`` entities.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
    CoverState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_COVER
from .coordinator import ShellyCloudCoordinator
from .entity import ShellyCloudEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cover entities from the device subentries."""
    coordinator: ShellyCloudCoordinator = entry.runtime_data.coordinator
    entities: list[CoverEntity] = []

    for subentry in entry.subentries.values():
        if subentry.subentry_type != "device":
            continue
        device_id = subentry.data["device_id"]
        device = coordinator.get_device(device_id)
        if device is None:
            continue
        for ch in device.iter_channels(KEY_COVER):
            entities.append(
                ShellyCloudCover(coordinator, device_id, ch.index, device)
            )

    async_add_entities(entities)


class ShellyCloudCover(ShellyCloudEntity, CoverEntity):
    """Representation of a Shelly Cloud cover."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
        channel: int,
        device,
    ) -> None:
        super().__init__(coordinator, device_id, f"cover_{channel}")
        self._channel = channel
        self._device_ref = device
        self._attr_translation_key = "cover"

    @property
    def current_cover_position(self) -> int | None:
        device = self.device
        if device is None:
            return None
        state = device.get_status(KEY_COVER, self._channel)
        for key in ("current_pos", "pos", "position"):
            if key in state and state[key] is not None:
                return int(state[key])
        return None

    @property
    def is_closed(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        state = device.get_status(KEY_COVER, self._channel)
        if "state" in state:
            return state["state"] == "closed"
        position = self.current_cover_position
        if position is None:
            return None
        return position == 0

    @property
    def state(self) -> CoverState | None:
        device = self.device
        if device is None:
            return None
        state = device.get_status(KEY_COVER, self._channel)
        raw = state.get("state")
        if raw == "open":
            return CoverState.OPEN
        if raw == "closed":
            return CoverState.CLOSED
        if raw == "opening":
            return CoverState.OPENING
        if raw == "closing":
            return CoverState.CLOSING
        if raw == "stopped":
            return CoverState.STOPPED
        if raw in ("calibrating",):
            return None
        if self.is_closed is None:
            return None
        return CoverState.CLOSED if self.is_closed else CoverState.OPEN

    async def async_open_cover(self, **kwargs: Any) -> None:
        device = self.device
        if device is None or device.is_gen1:
            await self.coordinator.client.async_set_roller_v1(
                self._device_id, "open"
            )
        else:
            await self.coordinator.client.async_set_cover(
                self._device_id, self._channel, position="open"
            )
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs: Any) -> None:
        device = self.device
        if device is None or device.is_gen1:
            await self.coordinator.client.async_set_roller_v1(
                self._device_id, "close"
            )
        else:
            await self.coordinator.client.async_set_cover(
                self._device_id, self._channel, position="close"
            )
        await self.coordinator.async_request_refresh()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        device = self.device
        if device is None or device.is_gen1:
            await self.coordinator.client.async_set_roller_v1(
                self._device_id, "stop"
            )
        else:
            await self.coordinator.client.async_set_cover(
                self._device_id, self._channel, position="stop"
            )
        await self.coordinator.async_request_refresh()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs[ATTR_POSITION]
        device = self.device
        if device is None or device.is_gen1:
            await self.coordinator.client.async_set_roller_pos_v1(
                self._device_id, position
            )
        else:
            await self.coordinator.client.async_set_cover(
                self._device_id, self._channel, position=position
            )
        await self.coordinator.async_request_refresh()
