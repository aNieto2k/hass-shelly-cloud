"""Base entity for Shelly Cloud."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ShellyCloudCoordinator
from .device import ShellyCloudDevice


class ShellyCloudEntity(CoordinatorEntity[ShellyCloudCoordinator]):
    """Common base for every platform entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: ShellyCloudCoordinator,
        device_id: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
        )

    @property
    def device(self) -> ShellyCloudDevice | None:
        """Return the latest cached state for this device, if available."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._device_id)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        device = self.device
        return bool(device and device.online)

    @property
    def device_name(self) -> str:
        device = self.device
        return (
            device.name
            or (device.code if device else None)
            or self._device_id
        )

    def _apply_device_to_info(self) -> None:
        """Refresh DeviceInfo fields once we know the model / firmware."""
        device = self.device
        if device is None:
            return
        info = self._attr_device_info
        if device.code:
            info["model"] = device.code
        if device.name:
            info["name"] = device.name
        if device.firmware_version:
            info["sw_version"] = device.firmware_version

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._apply_device_to_info()
