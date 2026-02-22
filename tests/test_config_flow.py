"""Tests for KACO config_flow.py — user step, options step, duplicate IP abort."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kaco.const import (
    DOMAIN,
    CONF_NAME,
    CONF_KACO_URL,
    CONF_INTERVAL,
    CONF_KWH_INTERVAL,
    CONF_GENERATOR_VOLTAGE,
    CONF_GENERATOR_CURRENT,
    CONF_GRID_VOLTAGE,
    CONF_GRID_CURRENT,
    CONF_SERIAL_NUMBER,
    CONF_MAC_ADDRESS,
)

from .conftest import MOCK_CONFIG


async def test_user_step_creates_entry(hass: HomeAssistant) -> None:
    """Test successful config flow user step."""
    with patch(
        "custom_components.kaco.const.check_data",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CONFIG,
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == MOCK_CONFIG[CONF_NAME]
        assert result["data"][CONF_KACO_URL] == MOCK_CONFIG[CONF_KACO_URL]


async def test_user_step_duplicate_ip_aborts(hass: HomeAssistant) -> None:
    """Test that configuring the same IP twice is aborted."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG,
        unique_id="192.168.178.112",
    )
    existing.add_to_hass(hass)

    with patch(
        "custom_components.kaco.const.check_data",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input=MOCK_CONFIG,
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"


async def test_import_step(hass: HomeAssistant) -> None:
    """Test import from YAML."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "import"}, data=MOCK_CONFIG
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test options flow updates config."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.kaco.async_setup_entry",
        new_callable=AsyncMock,
        return_value=True,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with patch(
        "custom_components.kaco.const.check_data",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM

        updated_config = dict(MOCK_CONFIG)
        updated_config[CONF_INTERVAL] = "30"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=updated_config,
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
