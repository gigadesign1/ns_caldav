"""Config and options flow for NS CalDAV Trip."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .caldav_client import async_validate_connection
from .const import (
    CONF_DELAY_THRESHOLD_MINUTES,
    CONF_LOOK_AHEAD_DAYS,
    CONF_NOTIFY_LEAD_MINUTES,
    CONF_SCAN_INTERVAL_HOURS,
    CONF_SUBSCRIPTION_KEY,
    DEFAULT_DELAY_THRESHOLD_MINUTES,
    DEFAULT_LOOK_AHEAD_DAYS,
    DEFAULT_NOTIFY_LEAD_MINUTES,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_SUBSCRIPTION_KEY): cv.string,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): cv.boolean,
    }
)


class NsCaldavConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for NS CalDAV Trip."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match(
                {
                    CONF_URL: user_input[CONF_URL],
                    CONF_USERNAME: user_input[CONF_USERNAME],
                }
            )
            error = await async_validate_connection(
                self.hass,
                user_input[CONF_URL],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_VERIFY_SSL],
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm re-authentication with updated credentials/key."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            new_data = {**reauth_entry.data, **user_input}
            error = await async_validate_connection(
                self.hass,
                new_data[CONF_URL],
                new_data[CONF_USERNAME],
                new_data[CONF_PASSWORD],
                new_data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry, data=new_data
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): cv.string,
                    vol.Required(CONF_SUBSCRIPTION_KEY): cv.string,
                }
            ),
            description_placeholders={CONF_USERNAME: reauth_entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NsCaldavOptionsFlow:
        """Return the options flow handler."""
        return NsCaldavOptionsFlow()


class NsCaldavOptionsFlow(OptionsFlow):
    """Handle options for NS CalDAV Trip."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage tunable options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL_HOURS,
                    default=options.get(
                        CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                vol.Optional(
                    CONF_LOOK_AHEAD_DAYS,
                    default=options.get(
                        CONF_LOOK_AHEAD_DAYS, DEFAULT_LOOK_AHEAD_DAYS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                vol.Optional(
                    CONF_NOTIFY_LEAD_MINUTES,
                    default=options.get(
                        CONF_NOTIFY_LEAD_MINUTES, DEFAULT_NOTIFY_LEAD_MINUTES
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=240)),
                vol.Optional(
                    CONF_DELAY_THRESHOLD_MINUTES,
                    default=options.get(
                        CONF_DELAY_THRESHOLD_MINUTES,
                        DEFAULT_DELAY_THRESHOLD_MINUTES,
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
