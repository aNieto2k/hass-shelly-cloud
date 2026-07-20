"""Data update coordinator.

Polls the v2 endpoint in batches of up to 10 devices, respecting the
1 req/s cloud-side rate limit. For Gen 1 devices it also issues a single
``/device/status`` request to backfill richer info.
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ShellyCloudApiClient,
    ShellyCloudCannotConnect,
    ShellyCloudError,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .device import ShellyCloudDevice

_LOGGER = logging.getLogger(__name__)


class ShellyCloudCoordinator(DataUpdateCoordinator[dict[str, ShellyCloudDevice]]):
    """One coordinator per config entry (account)."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ShellyCloudApiClient,
        device_ids: list[str],
    ) -> None:
        scan_interval: timedelta = DEFAULT_SCAN_INTERVAL
        if entry.options:
            custom = entry.options.get(CONF_SCAN_INTERVAL)
            if isinstance(custom, (int, float)):
                scan_interval = timedelta(seconds=custom)
            elif isinstance(custom, timedelta):
                scan_interval = custom

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=scan_interval,
        )
        self.entry = entry
        self.client = client
        self._device_ids: list[str] = list(device_ids)
        self._known_devices: dict[str, ShellyCloudDevice] = {}

    @property
    def device_ids(self) -> list[str]:
        return list(self._device_ids)

    def add_device(self, device_id: str) -> None:
        """Register a device so it is included in the next poll cycle."""
        device_id = device_id.lower()
        if device_id not in self._device_ids:
            self._device_ids.append(device_id)
        if device_id not in self._known_devices:
            self._known_devices[device_id] = None  # type: ignore[assignment]
        # Force an immediate refresh so the new device shows up without delay.
        self.hass.async_create_task(self.async_request_refresh())

    def remove_device(self, device_id: str) -> None:
        device_id = device_id.lower()
        if device_id in self._device_ids:
            self._device_ids.remove(device_id)
        self._known_devices.pop(device_id, None)

    def set_device_ids(self, device_ids: list[str]) -> None:
        """Replace the full device-id list (used on subentry changes)."""
        self._device_ids = [d.lower() for d in device_ids]
        # Drop cached devices that are no longer registered.
        for cached_id in list(self._known_devices.keys()):
            if cached_id not in self._device_ids:
                self._known_devices.pop(cached_id, None)

    def get_device(self, device_id: str) -> ShellyCloudDevice | None:
        return self._known_devices.get(device_id.lower())

    async def _async_update_data(self) -> dict[str, ShellyCloudDevice]:
        """Fetch latest state for every registered device."""
        if not self._device_ids:
            return self._known_devices

        try:
            states = await self.client.async_get_devices_state(
                self._device_ids,
                select=["status"],
            )
        except ShellyCloudCannotConnect as err:
            raise UpdateFailed(f"Cannot reach Shelly Cloud: {err}") from err
        except ShellyCloudError as err:
            raise UpdateFailed(f"Shelly Cloud error: {err}") from err

        for state in states:
            device_id = str(state.get("id", "")).lower()
            if not device_id:
                continue
            existing = self._known_devices.get(device_id)
            if existing is None:
                self._known_devices[device_id] = ShellyCloudDevice.from_v2_response(state)
            else:
                existing.update_from_v2(state)

        # Backfill Gen 1 devices with the legacy v1 status.
        for device in list(self._known_devices.values()):
            if device is None or not device.is_gen1:
                continue
            try:
                v1 = await self.client.async_get_v1_status(device.id)
            except ShellyCloudError as err:
                _LOGGER.debug("v1 status fetch failed for %s: %s", device.id, err)
                continue
            device.merge_v1_status(v1)

        return self._known_devices
