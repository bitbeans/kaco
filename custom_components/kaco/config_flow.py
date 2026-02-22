"""Config flow for the KACO custom component."""

from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_KACO_URL,
    create_form,
    check_data,
    ensure_config,
)

_LOGGER = logging.getLogger(__name__)


class KacoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for KACO."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        self._errors: Dict[str, str] = {}
        self._defaults: Dict[str, Any] | None = None

    async def async_step_user(self, user_input: Dict[str, Any] | None = None):
        """Handle the initial step shown to the user."""
        self._errors = {}

        # Defaults für das Formular
        if self._defaults is None:
            self._defaults = ensure_config(user_input or {})

        if user_input is not None:
            # Prevent duplicate config entries for the same IP
            ip = user_input.get(CONF_KACO_URL)
            if ip:
                await self.async_set_unique_id(ip)
                self._abort_if_unique_id_configured()

            # Best-Effort-Validierung – darf die Einrichtung NICHT blockieren.
            try:
                self._errors = await check_data(user_input, self.hass)
            except Exception:
                _LOGGER.warning(
                    "Skipping online validation due to exception.",
                    exc_info=True,
                )
                self._errors = {}

            if not self._errors:
                data = ensure_config(user_input)
                return self.async_create_entry(
                    title=data[CONF_NAME],
                    data=data,
                )

        schema = vol.Schema(create_form(self._defaults))
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=self._errors,
        )

    async def async_step_import(self, user_input: Dict[str, Any]):
        """Handle import from configuration.yaml."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        data = ensure_config(user_input)
        return self.async_create_entry(title="configuration.yaml", data=data)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Return the options flow handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for the KACO integration."""

    async def async_step_init(self, user_input: Dict[str, Any] | None = None):
        """Show and process the options form."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            try:
                errors = await check_data(user_input, self.hass)
            except Exception:
                _LOGGER.warning(
                    "Skipping online validation in options due to exception.",
                    exc_info=True,
                )
                errors = {}

            if not errors:
                data = dict(self.config_entry.data.items())
                data.update(ensure_config(user_input))
                return self.async_create_entry(
                    title=data.get(CONF_NAME, "kaco"),
                    data=data,
                )

        defaults = ensure_config(dict(self.config_entry.data.items()))
        schema = vol.Schema(create_form(defaults))
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
