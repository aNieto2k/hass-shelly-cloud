"""Shelly Cloud integration entry point."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ShellyCloudApiClient, ShellyCloudAuthError, ShellyCloudError
from .const import CONF_AUTH_KEY, CONF_DEVICE_ID, CONF_SERVER_URL, DOMAIN
from .coordinator import ShellyCloudCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.LIGHT,
    Platform.COVER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

type ShellyCloudConfigEntry = ConfigEntry["ShellyCloudRuntimeData"]


class ShellyCloudRuntimeData:
    """Per-entry runtime data stored in ``hass.data[DOMAIN][entry_id]``."""

    def __init__(
        self,
        client: ShellyCloudApiClient,
        coordinator: ShellyCloudCoordinator,
    ) -> None:
        self.client = client
        self.coordinator = coordinator


def _device_ids_for_entry(entry: ConfigEntry) -> list[str]:
    """Return the list of registered device ids from all device subentries."""
    return [
        sub.data[CONF_DEVICE_ID]
        for sub in entry.subentries.values()
        if sub.subentry_type == "device" and CONF_DEVICE_ID in sub.data
    ]


async def async_setup_entry(
    hass: HomeAssistant, entry: ShellyCloudConfigEntry
) -> bool:
    """Set up Shelly Cloud from a config entry."""
    session = async_get_clientsession(hass)
    client = ShellyCloudApiClient(
        server_url=entry.data[CONF_SERVER_URL],
        auth_key=entry.data[CONF_AUTH_KEY],
        session=session,
    )

    coordinator = ShellyCloudCoordinator(
        hass,
        entry,
        client,
        _device_ids_for_entry(entry),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except (ShellyCloudAuthError, ShellyCloudError) as err:
        raise ConfigEntryNotReady(f"Cannot reach Shelly Cloud: {err}") from err

    entry.runtime_data = ShellyCloudRuntimeData(client, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _on_subentry_change(
        _hass: HomeAssistant,
        _entry: ConfigEntry,
        _subentry: ConfigSubentry,
    ) -> None:
        """Reload the entry when a device subentry is added / removed."""
        await hass.config_entries.async_reload(_entry.entry_id)

    entry.async_on_unload(entry.add_subentry_update_listener(_on_subentry_change))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ShellyCloudConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_subentry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    subentry: ConfigSubentry,
) -> None:
    """Clean up when a subentry is removed (best-effort)."""
    runtime = getattr(entry, "runtime_data", None)
    if runtime and subentry.data.get(CONF_DEVICE_ID):
        runtime.coordinator.remove_device(subentry.data[CONF_DEVICE_ID])


async def _async_update_listener(
    hass: HomeAssistant, entry: ShellyCloudConfigEntry
) -> None:
    """Reload entry on options change."""
    await hass.config_entries.async_reload(entry.entry_id)
