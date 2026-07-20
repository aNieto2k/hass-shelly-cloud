"""Sensor platform for Shelly Cloud.

Creates sensors for:
- Power, energy, voltage, current on switch/N channels.
- Trifásico on devicepower:N and em:N channels.
- WiFi RSSI / status.
- System uptime, RAM free, firmware version available.
- Online state (per device).
- Cloud/MQTT connection status.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfInformation,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    KEY_DEVICE_POWER,
    KEY_EM,
    KEY_SWITCH,
    KEY_WIFI,
)
from .coordinator import ShellyCloudCoordinator
from .entity import ShellyCloudEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ShellySensorEntityDescription(SensorEntityDescription):
    """Describes how to extract a value from a device."""

    value_fn: Callable[[Any, int], Any] | None = None
    """Given a device and a channel index, return the sensor value."""


def _switch_value(state_key: str) -> Callable[[Any, int], Any]:
    def _extract(device, channel):
        state = device.get_status(KEY_SWITCH, channel)
        return state.get(state_key)

    return _extract


SWITCH_SENSORS: tuple[ShellySensorEntityDescription, ...] = (
    ShellySensorEntityDescription(
        key="apower",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=_switch_value("apower"),
    ),
    ShellySensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        value_fn=_switch_value("voltage"),
    ),
    ShellySensorEntityDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=_switch_value("current"),
    ),
    ShellySensorEntityDescription(
        key="energy",
        translation_key="energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda device, ch: (
            (device.get_status(KEY_SWITCH, ch).get("aenergy") or {}).get("total")
        ),
    ),
    ShellySensorEntityDescription(
        key="temperature",
        translation_key="device_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda device, ch: (
            (device.get_status(KEY_SWITCH, ch).get("temperature") or {}).get("tC")
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from the device subentries."""
    coordinator: ShellyCloudCoordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = []

    for subentry in entry.subentries.values():
        if subentry.subentry_type != "device":
            continue
        device_id = subentry.data["device_id"]
        device = coordinator.get_device(device_id)
        if device is None:
            continue

        # Per-switch measurements
        for ch in device.iter_channels(KEY_SWITCH):
            for descr in SWITCH_SENSORS:
                entities.append(
                    ShellyCloudChannelSensor(
                        coordinator, device_id, ch.index, descr
                    )
                )

        # Three-phase / devicepower / em channels
        for kind in (KEY_DEVICE_POWER, KEY_EM):
            for ch in device.iter_channels(kind):
                _add_three_phase_sensors(
                    entities, coordinator, device_id, ch.index, kind
                )

        # WiFi RSSI / status
        wifi = device.raw_status.get(KEY_WIFI) or {}
        if isinstance(wifi, dict):
            if "rssi" in wifi:
                entities.append(
                    ShellyCloudDictSensor(
                        coordinator,
                        device_id,
                        KEY_WIFI,
                        ShellySensorEntityDescription(
                            key="rssi",
                            translation_key="rssi",
                            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                            state_class=SensorStateClass.MEASUREMENT,
                            native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
                            entity_registry_enabled_default=False,
                            value_fn=lambda dev: dev.raw_status.get(KEY_WIFI, {}).get(
                                "rssi"
                            ),
                        ),
                    )
                )

        # System sensors
        sys = device.raw_status.get("sys") or {}
        if isinstance(sys, dict):
            if "uptime" in sys:
                entities.append(
                    ShellyCloudDictSensor(
                        coordinator,
                        device_id,
                        "sys",
                        ShellySensorEntityDescription(
                            key="uptime",
                            translation_key="uptime",
                            device_class=SensorDeviceClass.DURATION,
                            state_class=SensorStateClass.TOTAL_INCREASING,
                            native_unit_of_measurement=UnitOfTime.SECONDS,
                            entity_registry_enabled_default=False,
                            value_fn=lambda dev: dev.raw_status.get("sys", {}).get(
                                "uptime"
                            ),
                        ),
                    )
                )
            if "ram_free" in sys:
                entities.append(
                    ShellyCloudDictSensor(
                        coordinator,
                        device_id,
                        "sys",
                        ShellySensorEntityDescription(
                            key="ram_free",
                            translation_key="ram_free",
                            state_class=SensorStateClass.MEASUREMENT,
                            native_unit_of_measurement=UnitOfInformation.BYTES,
                            entity_registry_enabled_default=False,
                            value_fn=lambda dev: dev.raw_status.get("sys", {}).get(
                                "ram_free"
                            ),
                        ),
                    )
                )

        # Cloud / MQTT connection
        cloud = device.raw_status.get("cloud") or {}
        if isinstance(cloud, dict) and "connected" in cloud:
            entities.append(
                ShellyCloudDictSensor(
                    coordinator,
                    device_id,
                    "cloud",
                    ShellySensorEntityDescription(
                        key="cloud_connected",
                        translation_key="cloud_connected",
                        device_class=SensorDeviceClass.ENUM,
                        options=["connected", "disconnected"],
                        value_fn=lambda dev: (
                            "connected"
                            if (dev.raw_status.get("cloud") or {}).get("connected")
                            else "disconnected"
                        ),
                    ),
                )
            )

    async_add_entities(entities)


def _add_three_phase_sensors(
    entities: list[SensorEntity],
    coordinator: ShellyCloudCoordinator,
    device_id: str,
    channel: int,
    kind: str,
) -> None:
    state = coordinator.get_device(device_id).get_status(kind, channel) if coordinator.get_device(device_id) else {}
    if not state:
        return

    def _val(key: str, sub: dict | None = None) -> Any:
        if sub is not None:
            return sub.get(key)
        return state.get(key)

    if "power" in state or "apower" in state:
        entities.append(
            ShellyCloudChannelSensor(
                coordinator,
                device_id,
                channel,
                ShellySensorEntityDescription(
                    key=f"{kind}_power",
                    translation_key="power",
                    device_class=SensorDeviceClass.POWER,
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement=UnitOfPower.WATT,
                    value_fn=lambda dev, ch: (
                        dev.get_status(kind, ch).get("power")
                        or dev.get_status(kind, ch).get("apower")
                    ),
                ),
            )
        )

    if "energy" in state or "aenergy" in state:
        def _energy(dev, ch):
            raw = dev.get_status(kind, ch)
            e = raw.get("aenergy") or raw.get("energy")
            if isinstance(e, dict):
                return e.get("total")
            return e

        entities.append(
            ShellyCloudChannelSensor(
                coordinator,
                device_id,
                channel,
                ShellySensorEntityDescription(
                    key=f"{kind}_energy",
                    translation_key="energy",
                    device_class=SensorDeviceClass.ENERGY,
                    state_class=SensorStateClass.TOTAL_INCREASING,
                    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                    value_fn=_energy,
                ),
            )
        )

    if "voltage" in state:
        entities.append(
            ShellyCloudChannelSensor(
                coordinator,
                device_id,
                channel,
                ShellySensorEntityDescription(
                    key=f"{kind}_voltage",
                    translation_key="voltage",
                    device_class=SensorDeviceClass.VOLTAGE,
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
                    value_fn=lambda dev, ch: dev.get_status(kind, ch).get("voltage"),
                ),
            )
        )

    if "current" in state:
        entities.append(
            ShellyCloudChannelSensor(
                coordinator,
                device_id,
                channel,
                ShellySensorEntityDescription(
                    key=f"{kind}_current",
                    translation_key="current",
                    device_class=SensorDeviceClass.CURRENT,
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                    value_fn=lambda dev, ch: dev.get_status(kind, ch).get("current"),
                ),
            )
        )


class ShellyCloudChannelSensor(ShellyCloudEntity, SensorEntity):
    """Sensor attached to a specific switch/cover/em channel."""

    entity_description: ShellySensorEntityDescription

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
        channel: int,
        description: ShellySensorEntityDescription,
    ) -> None:
        super().__init__(
            coordinator, device_id, f"sensor_{channel}_{description.key}"
        )
        self.entity_description = description
        self._channel = channel

    @property
    def native_value(self) -> Any:
        device = self.device
        if device is None or self.entity_description.value_fn is None:
            return None
        return self.entity_description.value_fn(device, self._channel)


class ShellyCloudDictSensor(ShellyCloudEntity, SensorEntity):
    """Sensor that pulls a value from a top-level status dict (wifi, sys...)."""

    entity_description: ShellySensorEntityDescription

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
        key: str,
        description: ShellySensorEntityDescription,
    ) -> None:
        super().__init__(
            coordinator, device_id, f"sensor_{key}_{description.key}"
        )
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        device = self.device
        if device is None or self.entity_description.value_fn is None:
            return None
        return self.entity_description.value_fn(device)
