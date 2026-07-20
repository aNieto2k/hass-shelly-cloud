"""Config flow for the Shelly Cloud integration.

Step 1 (config flow):  ask for Server URL + Authorization Cloud Key.
Step 2 (subentry flow): ask for the device ID, validate it, and create the
device subentry. The user can keep adding devices via "+ Add device".
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_USER,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    FlowType,
    SubentryFlowContext,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    ShellyCloudApiClient,
    ShellyCloudAuthError,
    ShellyCloudCannotConnect,
    ShellyCloudDeviceNotFound,
    ShellyCloudError,
)
from .const import (
    CONF_AUTH_KEY,
    CONF_DEVICE_CODE,
    CONF_DEVICE_GEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_TYPE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required("server_url"): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Required(CONF_AUTH_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_ID): cv.string,
    }
)


def _entry_unique_id(auth_key: str) -> str:
    return hashlib.sha256(auth_key.encode("utf-8")).hexdigest()[:32]


async def _validate_credentials(
    hass, server_url: str, auth_key: str
) -> dict[str, Any]:
    """Validate server+auth and return a tiny summary dict."""
    client = ShellyCloudApiClient(
        server_url=server_url,
        auth_key=auth_key,
        session=async_get_clientsession(hass),
    )
    await client.async_validate()
    return {"client": client}


class ShellyCloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the main (hub) config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            server_url = user_input["server_url"].strip()
            auth_key = user_input[CONF_AUTH_KEY].strip()
            try:
                await _validate_credentials(self.hass, server_url, auth_key)
            except ShellyCloudAuthError:
                errors["base"] = "invalid_auth"
            except ShellyCloudCannotConnect:
                errors["base"] = "cannot_connect"
            except ShellyCloudError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(_entry_unique_id(auth_key))
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Shelly Cloud",
                    data={
                        "server_url": server_url,
                        CONF_AUTH_KEY: auth_key,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "docs_url": "https://shelly-api-docs.shelly.cloud/cloud-control-api/",
            },
        )

    async def async_on_create_entry(
        self, result: ConfigFlowResult
    ) -> ConfigFlowResult:
        """Right after creating the entry, open the subentry flow for devices.

        Implements the user requirement that the "add device" modal pops up
        immediately after credentials are validated.
        """
        entry_id = result["result"].entry_id
        subentry_result = await self.hass.config_entries.subentries.async_init(
            (entry_id, "device"),
            context=SubentryFlowContext(source=SOURCE_USER),
        )
        result["next_flow"] = (
            FlowType.CONFIG_SUBENTRIES_FLOW,
            subentry_result["flow_id"],
        )
        return result

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {"device": ShellyCloudDeviceSubentryFlow}


class ShellyCloudDeviceSubentryFlow(ConfigSubentryFlow):
    """Subentry flow that adds a single Shelly device."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID].strip().lower()
            client = ShellyCloudApiClient(
                server_url=self._get_entry().data["server_url"],
                auth_key=self._get_entry().data[CONF_AUTH_KEY],
                session=async_get_clientsession(self.hass),
            )
            try:
                states = await client.async_get_devices_state(
                    [device_id],
                    select=["status", "settings"],
                )
            except ShellyCloudDeviceNotFound:
                errors["base"] = "device_not_found"
            except ShellyCloudAuthError:
                errors["base"] = "invalid_auth"
            except ShellyCloudCannotConnect:
                errors["base"] = "cannot_connect"
            except ShellyCloudError:
                errors["base"] = "unknown"
            else:
                if not states:
                    errors["base"] = "device_not_found"
                else:
                    info = states[0]
                    await self.async_set_unique_id(device_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=info.get("code") or device_id,
                        data={
                            CONF_DEVICE_ID: device_id,
                            CONF_DEVICE_CODE: info.get("code") or "",
                            CONF_DEVICE_GEN: info.get("gen") or "G2",
                            CONF_DEVICE_TYPE: info.get("type") or "",
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=DEVICE_SCHEMA,
            errors=errors,
            description_placeholders={
                "howto": (
                    "Abre la app Shelly Cloud → Device → Settings → Device "
                    "Information → Device Id"
                )
            },
        )
