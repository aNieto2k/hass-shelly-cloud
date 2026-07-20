"""Shelly Cloud API client.

Wraps both the v2 (beta) communication API and the legacy v1 endpoints, since
Gen 1 devices still need v1 to expose their full status (relay:0, light:0 with
gain/brightness, roller:0, meter:0, etc.).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp import ClientError, ClientResponseError, ClientTimeout
from yarl import URL

from .const import (
    BATCH_SIZE,
    CONF_AUTH_KEY,
    CONF_SERVER_URL,
    RATE_LIMIT_PER_SECOND,
    REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class ShellyCloudError(Exception):
    """Base error."""


class ShellyCloudCannotConnect(ShellyCloudError):
    """Network / connection error."""


class ShellyCloudAuthError(ShellyCloudError):
    """Invalid or expired auth key."""


class ShellyCloudDeviceNotFound(ShellyCloudError):
    """The device id does not exist on the account."""


class ShellyCloudRateLimited(ShellyCloudError):
    """Hit the 1 req/sec limit anyway."""


class ShellyCloudApiClient:
    """Thin async client around the Shelly Cloud HTTP API."""

    def __init__(
        self,
        server_url: str,
        auth_key: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._base = server_url.rstrip("/")
        self._auth_key = auth_key
        self._session = session
        self._lock = asyncio.Lock()

    @property
    def server_url(self) -> str:
        return self._base

    @property
    def auth_key(self) -> str:
        return self._auth_key

    async def async_validate(self) -> bool:
        """Quick connectivity check used by the config flow.

        Uses the v1 ``/device/all_status`` endpoint because it requires no
        device id and exposes the full account, so we get both a connectivity
        test and an auth check in one call. Auth key is passed in the query
        string — without it the cloud returns 401 even though the docs don't
        mention it for this particular endpoint.
        """
        result = await self._request(
            "POST",
            "/device/all_status",
            params={
                "auth_key": self._auth_key,
                "show_info": "true",
                "no_shared": "true",
            },
        )
        return bool(result.get("isok"))

    async def async_list_devices_v1(self) -> dict[str, dict[str, Any]]:
        """Return ``{device_id: _dev_info}`` for every device on the account."""
        payload = await self._request(
            "POST",
            "/device/all_status",
            params={
                "auth_key": self._auth_key,
                "show_info": "true",
                "no_shared": "true",
            },
        )
        devices_status = payload.get("data", {}).get("devices_status", {})
        result: dict[str, dict[str, Any]] = {}
        for key, value in devices_status.items():
            info = value.get("_dev_info")
            if info and "id" in info:
                result[str(info["id"])] = info
        return result

    async def async_get_devices_state(
        self,
        ids: list[str],
        select: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """POST /v2/devices/api/get — up to ``BATCH_SIZE`` ids per call."""
        if not ids:
            return []

        results: list[dict[str, Any]] = []
        for chunk in (ids[i : i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)):
            body: dict[str, Any] = {"ids": chunk}
            if select:
                body["select"] = select
            payload = await self._request(
                "POST",
                "/v2/devices/api/get",
                params={"auth_key": self._auth_key},
                json=body,
            )
            if isinstance(payload, list):
                results.extend(payload)
        return results

    async def async_get_v1_status(self, device_id: str) -> dict[str, Any]:
        """POST /device/status — Gen1 fallback with full device_status body."""
        payload = await self._request(
            "POST",
            "/device/status",
            params={"auth_key": self._auth_key},
            form={"id": device_id},
        )
        if not payload.get("isok"):
            raise ShellyCloudDeviceNotFound(device_id)
        return payload

    async def async_set_switch(
        self,
        device_id: str,
        channel: int,
        on: bool,
        toggle_after: float | None = None,
    ) -> None:
        body: dict[str, Any] = {"id": device_id, "channel": channel, "on": on}
        if toggle_after is not None:
            body["toggle_after"] = toggle_after
        await self._request(
            "POST",
            "/v2/devices/api/set/switch",
            params={"auth_key": self._auth_key},
            json=body,
        )

    async def async_set_cover(
        self,
        device_id: str,
        channel: int,
        *,
        position: int | str | None = None,
        relative: int | None = None,
        duration: int | None = None,
        slat_position: int | None = None,
        slat_relative: int | None = None,
    ) -> None:
        body: dict[str, Any] = {"id": device_id, "channel": channel}
        if position is not None:
            body["position"] = position
        if relative is not None:
            body["relative"] = relative
        if duration is not None:
            body["duration"] = duration
        if slat_position is not None:
            body["slatPosition"] = slat_position
        if slat_relative is not None:
            body["slatRelative"] = slat_relative
        await self._request(
            "POST",
            "/v2/devices/api/set/cover",
            params={"auth_key": self._auth_key},
            json=body,
        )

    async def async_set_light(
        self,
        device_id: str,
        channel: int,
        *,
        on: bool | None = None,
        toggle_after: float | None = None,
        mode: str | None = None,
        brightness: int | None = None,
        temperature: int | None = None,
        red: int | None = None,
        green: int | None = None,
        blue: int | None = None,
        white: int | None = None,
        gain: int | None = None,
        effect: int | None = None,
    ) -> None:
        body: dict[str, Any] = {"id": device_id, "channel": channel}
        if on is not None:
            body["on"] = on
        if toggle_after is not None:
            body["toggle_after"] = toggle_after
        if mode is not None:
            body["mode"] = mode
        if brightness is not None:
            body["brightness"] = brightness
        if temperature is not None:
            body["temperature"] = temperature
        if red is not None:
            body["red"] = red
        if green is not None:
            body["green"] = green
        if blue is not None:
            body["blue"] = blue
        if white is not None:
            body["white"] = white
        if gain is not None:
            body["gain"] = gain
        if effect is not None:
            body["effect"] = effect
        await self._request(
            "POST",
            "/v2/devices/api/set/light",
            params={"auth_key": self._auth_key},
            json=body,
        )

    async def async_set_roller_v1(
        self,
        device_id: str,
        direction: str,
    ) -> None:
        """Gen 1 cover control (open/close/stop)."""
        await self._request(
            "POST",
            "/device/relay/roller/control",
            params={"auth_key": self._auth_key},
            form={"direction": direction, "id": device_id},
        )

    async def async_set_roller_pos_v1(self, device_id: str, position: int) -> None:
        """Gen 1 cover position control (0..100)."""
        await self._request(
            "POST",
            "/device/relay/roller/control",
            params={"auth_key": self._auth_key},
            form={"pos": str(position), "id": device_id},
        )

    async def async_set_relay_v1(
        self,
        device_id: str,
        channel: int,
        turn: str,
    ) -> None:
        """Gen 1 relay control (on/off)."""
        await self._request(
            "POST",
            "/device/relay/control",
            params={"auth_key": self._auth_key},
            form={"channel": str(channel), "turn": turn, "id": device_id},
        )

    async def async_set_light_v1(
        self,
        device_id: str,
        channel: int,
        turn: str | None = None,
        brightness: int | None = None,
        white: int | None = None,
        red: int | None = None,
        green: int | None = None,
        blue: int | None = None,
        gain: int | None = None,
    ) -> None:
        """Gen 1 light control."""
        params: dict[str, str] = {"channel": str(channel), "id": device_id}
        if turn is not None:
            params["turn"] = turn
        if brightness is not None:
            params["brightness"] = str(brightness)
        if white is not None:
            params["white"] = str(white)
        if red is not None:
            params["red"] = str(red)
        if green is not None:
            params["green"] = str(green)
        if blue is not None:
            params["blue"] = str(blue)
        if gain is not None:
            params["gain"] = str(gain)
        await self._request(
            "POST",
            "/device/light/control",
            params={"auth_key": self._auth_key},
            form=params,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
    ) -> Any:
        """Make an HTTP request with a process-wide rate limiter."""
        url = URL(self._base + path)
        timeout = ClientTimeout(total=REQUEST_TIMEOUT)

        async with self._lock:
            # Serialise calls ourselves; the cloud endpoint is limited to
            # 1 req/s globally per account. Sleep at least that long between
            # two consecutive calls.
            try:
                async with self._session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    data=form,
                    timeout=timeout,
                ) as response:
                    if response.status == 401 or response.status == 403:
                        body_preview = (await response.text())[:200]
                        _LOGGER.debug(
                            "Auth rejected on %s %s (status=%s, body=%s)",
                            method,
                            path,
                            response.status,
                            body_preview,
                        )
                        raise ShellyCloudAuthError(
                            f"Auth rejected ({response.status}) on {method} {path}"
                        )
                    if response.status == 404 and "device" in path.lower():
                        raise ShellyCloudDeviceNotFound(path)
                    if response.status == 429:
                        raise ShellyCloudRateLimited("Rate limited by cloud")
                    response.raise_for_status()
                    if response.content_type == "application/json":
                        return await response.json()
                    text = await response.text()
                    return {"raw": text}
            except ClientResponseError as err:
                if err.status == 401 or err.status == 403:
                    raise ShellyCloudAuthError(str(err)) from err
                if err.status == 404:
                    raise ShellyCloudDeviceNotFound(str(err)) from err
                raise ShellyCloudCannotConnect(str(err)) from err
            except (ClientError, asyncio.TimeoutError) as err:
                raise ShellyCloudCannotConnect(str(err)) from err
            finally:
                # Always wait at least the rate-limit window before releasing
                # the lock so the next caller cannot burst.
                await asyncio.sleep(1.0 / RATE_LIMIT_PER_SECOND)


def build_client_from_entry_data(
    entry_data: dict[str, Any],
    session: aiohttp.ClientSession,
) -> ShellyCloudApiClient:
    """Helper used everywhere we need a client from a config entry dict."""
    return ShellyCloudApiClient(
        server_url=entry_data[CONF_SERVER_URL],
        auth_key=entry_data[CONF_AUTH_KEY],
        session=session,
    )
