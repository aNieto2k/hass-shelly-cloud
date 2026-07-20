"""Device model.

Normalises Gen 1 and Gen 2+ device state into a single shape that platform
code can introspect without caring about the generation.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .const import (
    GEN_1,
    GEN_2,
    GEN_BLE,
    KEY_COVER,
    KEY_DEVICE_POWER,
    KEY_EM,
    KEY_LIGHT,
    KEY_SWITCH,
)

# Gen 1 keys that map to a Gen 2 equivalent. All other keys are passed through.
_GEN1_TO_GEN2 = {
    "relay": KEY_SWITCH,
    "roller": KEY_COVER,
}


def _normalise_status_keys(status: dict[str, Any] | None) -> dict[str, Any]:
    """Rename Gen1 ``relay:0`` / ``roller:0`` to ``switch:0`` / ``cover:0``."""
    if not status:
        return {}
    out: dict[str, Any] = {}
    for key, value in status.items():
        if ":" in key:
            kind, _, index = key.partition(":")
            kind = _GEN1_TO_GEN2.get(kind, kind)
            out[f"{kind}:{index}"] = value
        else:
            out[key] = value
    return out


def _detect_channels(status: dict[str, Any], kind: str) -> list[int]:
    """Return sorted list of channel indices for ``kind`` in status."""
    prefix = f"{kind}:"
    return sorted(
        int(key[len(prefix) :])
        for key in status
        if key.startswith(prefix)
    )


def _safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class ChannelInfo:
    """A single addressable channel on a device."""

    kind: str  # 'switch' | 'cover' | 'light' | 'input' | 'devicepower' | 'em'
    index: int
    state: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    @property
    def is_on(self) -> bool | None:
        return self.state.get("output")

    @property
    def is_light(self) -> bool | None:
        """Whether the appliance is configured as a light (vs a generic switch)."""
        for src in (self.settings, self.state):
            if not src:
                continue
            if src.get("appliance_type") == "light":
                return True
            if src.get("consumption_type") == "light":
                return True
        return None


@dataclass
class ShellyCloudDevice:
    """Normalised representation of a Shelly device."""

    id: str
    code: str
    gen: str
    type: str
    online: bool
    raw_status: dict[str, Any] = field(default_factory=dict)
    raw_settings: dict[str, Any] = field(default_factory=dict)
    raw_v1_status: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    channels: dict[str, list[ChannelInfo]] = field(default_factory=dict)

    @property
    def model(self) -> str:
        return self.code or self.type or "Shelly"

    @property
    def is_gen1(self) -> bool:
        return self.gen == GEN_1

    @property
    def is_gen2(self) -> bool:
        return self.gen == GEN_2

    @property
    def supports_color(self) -> bool:
        for ch in self.iter_channels(KEY_LIGHT):
            st = ch.state
            for color_key in ("red", "green", "blue"):
                if color_key in st:
                    return True
        return False

    @property
    def supports_white_temperature(self) -> bool:
        for ch in self.iter_channels(KEY_LIGHT):
            if "temp" in ch.state or "ct" in ch.state or "temperature" in ch.state:
                return True
        return False

    @property
    def has_power_metering(self) -> bool:
        for kind in (KEY_SWITCH, KEY_DEVICE_POWER, KEY_EM):
            if any(self.iter_channels(kind)):
                return True
        return False

    @property
    def has_battery(self) -> bool:
        if isinstance(self.raw_status.get("devicepower:0"), dict):
            return True
        if "bat" in self.raw_status or "battery" in self.raw_status:
            return True
        return False

    @property
    def firmware_version(self) -> str | None:
        sys_info = self.raw_status.get("sys") or self.raw_settings.get("sys") or {}
        if isinstance(sys_info, dict):
            fw = sys_info.get("firmware") or sys_info.get("fw")
            if isinstance(fw, str):
                return fw
        return None

    def iter_channels(self, kind: str) -> Iterator[ChannelInfo]:
        yield from self.channels.get(kind, [])

    def get_channel(self, kind: str, index: int) -> ChannelInfo | None:
        for ch in self.channels.get(kind, []):
            if ch.index == index:
                return ch
        return None

    def get_status(self, kind: str, index: int) -> dict[str, Any]:
        key = f"{kind}:{index}"
        return self.raw_status.get(key, {})

    def get_v1_status(self, kind: str, index: int) -> dict[str, Any]:
        key = f"{kind}:{index}"
        return self.raw_v1_status.get(key, {})

    # ------------------------------------------------------------------
    # Constructors / updates
    # ------------------------------------------------------------------

    @classmethod
    def from_v2_response(cls, data: dict[str, Any]) -> ShellyCloudDevice:
        """Build a device from a single item of ``/v2/devices/api/get``."""
        device_id = str(data.get("id", "")).lower()
        gen = str(data.get("gen", GEN_2)).upper()
        if gen not in (GEN_1, GEN_2, GEN_BLE):
            gen = GEN_2

        raw_status = _normalise_status_keys(data.get("status") or {})
        raw_settings = data.get("settings") or {}

        return cls(
            id=device_id,
            code=str(data.get("code") or ""),
            gen=gen,
            type=str(data.get("type") or ""),
            online=bool(data.get("online")),
            raw_status=raw_status,
            raw_settings=raw_settings,
            channels=cls._build_channels(raw_status, raw_settings),
        )

    def update_from_v2(self, data: dict[str, Any]) -> None:
        """Merge a v2 poll result into this device in-place."""
        self.code = str(data.get("code") or self.code)
        if "gen" in data:
            self.gen = str(data["gen"]).upper()
        if "type" in data:
            self.type = str(data["type"])
        if "online" in data:
            self.online = bool(data["online"])
        new_status = _normalise_status_keys(data.get("status") or {})
        self.raw_status.update(new_status)
        if "settings" in data and data["settings"]:
            self.raw_settings.update(data["settings"])
        self.channels = self._build_channels(self.raw_status, self.raw_settings)

    def merge_v1_status(self, v1_data: dict[str, Any]) -> None:
        """Merge the legacy v1 ``device_status`` body for richer G1 data."""
        device_status = v1_data.get("data", {}).get("device_status", {})
        if not isinstance(device_status, dict):
            return
        normalised = _normalise_status_keys(device_status)
        self.raw_v1_status.update(normalised)
        # For Gen1 devices the v1 status often contains the most complete
        # picture, so it becomes the primary source for switches / lights /
        # meters / rollers.
        if self.is_gen1:
            self.raw_status.update(normalised)
        else:
            # Only fill keys we don't already have from v2.
            for key, value in normalised.items():
                self.raw_status.setdefault(key, value)
        self.channels = self._build_channels(self.raw_status, self.raw_settings)

    # ------------------------------------------------------------------
    # Channel construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_channels(
        status: dict[str, Any],
        settings: dict[str, Any],
    ) -> dict[str, list[ChannelInfo]]:
        result: dict[str, list[ChannelInfo]] = {}
        # Discover channel kinds from both status and settings. Only keys of
        # the form ``kind:index`` represent addressable channels; top-level
        # keys like ``sys``, ``wifi``, ``cloud``, ``mqtt``, ``ble``,
        # ``devicepower``, ``em`` are device-wide state and must be skipped.
        candidates: set[str] = set()
        for source in (status, settings):
            for key in source:
                if ":" in key:
                    candidates.add(key.split(":", 1)[0])

        for kind in candidates:
            indices: set[int] = set()
            for source in (status, settings):
                for key in source:
                    if not key.startswith(f"{kind}:"):
                        continue
                    index = _safe_int(key.split(":", 1)[1])
                    if index is not None:
                        indices.add(index)

            channels: list[ChannelInfo] = []
            for index in sorted(indices):
                state_key = f"{kind}:{index}"
                ch = ChannelInfo(
                    kind=kind,
                    index=index,
                    state=status.get(state_key, {}) or {},
                    settings=settings.get(state_key, {}) or {},
                )
                channels.append(ch)
            if channels:
                result[kind] = channels
        return result
