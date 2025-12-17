
"""Config flow for the KACO custom component."""
from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

# Wir verwenden nur die benötigten Symbole aus const.py
from .const import (
    DOMAIN,
    CONF_NAME,
    create_form,
    check_data,
    ensure_config,
)

_LOGGER = logging.getLogger(__name__)


class KacoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for KACO."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

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
            # Best‑Effort‑Validierung – darf die Einrichtung NICHT blockieren.
            try:
                self._errors = await check_data(
                    user_input, self.hass.async_add_executor_job
                )
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
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for the KACO integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store initial config for later updates."""
        self.config_entry = config_entry
        self.data: Dict[str, Any] = dict(config_entry.data.items())
        self._errors: Dict[str, str] = {}

    async def async_step_init(self, user_input: Dict[str, Any] | None = None):
        """Show and process the options form."""
        self._errors = {}

        if user_input is not None:
            try:
                self._errors = await check_data(
                    user_input, self.hass.async_add_executor_job
                )
            except Exception:
                _LOGGER.warning(
                    "Skipping online validation in options due to exception.",
                    exc_info=True,
                )
                self._errors = {}

            if not self._errors:
                updated = ensure_config(user_input)
                self.data.update(updated)
                return self.async_create_entry(
                    title=self.data.get(CONF_NAME, "kaco"),
                    data=self.data,
                )

        defaults = ensure_config(self.data)
        schema = vol.Schema(create_form(defaults))
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=self._errors,
        )
