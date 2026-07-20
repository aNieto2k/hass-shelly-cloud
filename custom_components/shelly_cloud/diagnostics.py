"""Diagnostics support for Shelly Cloud."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_AUTH_KEY

TO_REDACT = {CONF_AUTH_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, with the auth key redacted."""
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data or {}

    devices: list[dict[str, Any]] = []
    for device_id, device in data.items():
        if device is None:
            continue
        devices.append(
            {
                "id": device.id,
                "code": device.code,
                "gen": device.gen,
                "type": device.type,
                "online": device.online,
                "raw_status": device.raw_status,
                "raw_settings": device.raw_settings,
            }
        )

    return {
        "entry": {
            "title": entry.title,
            "server_url": entry.data.get("server_url"),
            "subentries": [
                {
                    "subentry_type": sub.subentry_type,
                    "title": sub.title,
                    "data": sub.data,
                }
                for sub in entry.subentries.values()
            ],
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "devices": devices,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device_id: str
) -> dict[str, Any]:
    """Return diagnostics for a single device."""
    coordinator = entry.runtime_data.coordinator
    device = coordinator.get_device(device_id)
    if device is None:
        return {"error": "device_not_loaded"}
    return {
        "id": device.id,
        "code": device.code,
        "gen": device.gen,
        "type": device.type,
        "online": device.online,
        "raw_status": device.raw_status,
        "raw_settings": device.raw_settings,
    }
