"""Binary sensor platform for Shelly Cloud.

Creates binary_sensor entities for:
- ``input:N`` channels configured in switch mode.
- ``cloud.connected`` and ``mqtt.connected`` device-wide status.
- Device online flag (per device).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KEY_CLOUD, KEY_INPUT, KEY_MQTT
from .coordinator import ShellyCloudCoordinator
from .entity import ShellyCloudEntity


@dataclass(frozen=True, kw_only=True)
class ShellyBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes how to extract a value."""

    value_fn: Callable[[Any, int], Any] | None = None


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from the device subentries."""
    coordinator: ShellyCloudCoordinator = entry.runtime_data.coordinator
    entities: list[BinarySensorEntity] = []

    for subentry in entry.subentries.values():
        if subentry.subentry_type != "device":
            continue
        device_id = subentry.data["device_id"]
        device = coordinator.get_device(device_id)
        if device is None:
            continue

        # Digital inputs (only those configured as switches)
        for ch in device.iter_channels(KEY_INPUT):
            settings = ch.settings or {}
            inp_mode = settings.get("mode") or settings.get("type")
            if inp_mode == "button":
                continue
            entities.append(
                ShellyCloudInputBinarySensor(coordinator, device_id, ch.index)
            )

        # Cloud connection
        if isinstance(device.raw_status.get(KEY_CLOUD), dict):
            entities.append(
                ShellyCloudConnectionBinarySensor(
                    coordinator,
                    device_id,
                    KEY_CLOUD,
                    BinarySensorDeviceClass.CONNECTIVITY,
                )
            )

        # MQTT connection (G2 only)
        if isinstance(device.raw_status.get(KEY_MQTT), dict):
            entities.append(
                ShellyCloudConnectionBinarySensor(
                    coordinator,
                    device_id,
                    KEY_MQTT,
                    BinarySensorDeviceClass.CONNECTIVITY,
                )
            )

        # Online flag
        entities.append(ShellyCloudOnlineBinarySensor(coordinator, device_id))

    async_add_entities(entities)


class ShellyCloudInputBinarySensor(ShellyCloudEntity, BinarySensorEntity):
    """An input channel configured as a switch (boolean state)."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
        channel: int,
    ) -> None:
        super().__init__(coordinator, device_id, f"input_{channel}")
        self._channel = channel
        self._attr_translation_key = "input"

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        state = device.get_status(KEY_INPUT, self._channel)
        if "state" in state:
            return bool(state["state"])
        if "input" in state:
            return bool(state["input"])
        return None


class ShellyCloudConnectionBinarySensor(ShellyCloudEntity, BinarySensorEntity):
    """Cloud or MQTT connectivity sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
        kind: str,
        device_class: BinarySensorDeviceClass,
    ) -> None:
        super().__init__(coordinator, device_id, f"{kind}_connected")
        self._kind = kind
        self._attr_device_class = device_class
        self._attr_translation_key = f"{kind}_connected"

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        info = device.raw_status.get(self._kind)
        if isinstance(info, dict):
            return bool(info.get("connected"))
        return None


class ShellyCloudOnlineBinarySensor(ShellyCloudEntity, BinarySensorEntity):
    """Tracks the ``online`` flag returned by the cloud API."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "online"

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id, "online")

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        return device.online
