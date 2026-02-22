"""Tests for KACO __init__.py — coordinator, setup, unload, backoff."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kaco.const import DOMAIN, CONF_KACO_URL, CONF_SERIAL_NUMBER
from custom_components.kaco import (
    get_coordinator,
    _apply_backoff,
    _bootstrap_defaults,
    async_setup_entry,
    async_unload_entry,
)

from .conftest import MOCK_CONFIG, SAMPLE_REALTIME_CSV, SAMPLE_DAILY_CSV


async def test_setup_and_unload_entry(hass: HomeAssistant, aiohttp_client) -> None:
    """Test that setup and unload work correctly."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    with patch("custom_components.kaco.async_get_clientsession") as mock_session_fn:
        mock_session = MagicMock()
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value=SAMPLE_REALTIME_CSV)
        mock_resp.status = 200
        mock_session.get = AsyncMock(return_value=mock_resp)
        mock_session_fn.return_value = mock_session

        with (
            patch(
                "custom_components.kaco.statistics_repair.async_migrate_statistics",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.kaco.statistics_repair.async_import_historical",
                new_callable=AsyncMock,
            ),
        ):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state is ConfigEntryState.LOADED

            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state is ConfigEntryState.NOT_LOADED


def test_apply_backoff() -> None:
    """Test exponential backoff calculation."""
    # First failure: factor = 2^0 = 1
    result = _apply_backoff(20.0, 1)
    assert 5.0 <= result <= 120.0

    # Third failure: should increase significantly
    result = _apply_backoff(20.0, 3)
    assert result > 20.0

    # Large fail count: should cap at _MAX_INTERVAL
    result = _apply_backoff(20.0, 20)
    assert result <= 120.0


def test_bootstrap_defaults_none() -> None:
    """Test bootstrap with None input."""
    result = _bootstrap_defaults(None)
    assert result["extra"]["max_power"] == 0
    assert result["extra"]["serialno"] == "no_serial"
    assert result["extra"]["model"] == "no_model"


def test_bootstrap_defaults_existing() -> None:
    """Test bootstrap preserves existing values."""
    existing = {"extra": {"serialno": "BPI123", "max_power": 5000}}
    result = _bootstrap_defaults(existing)
    assert result["extra"]["serialno"] == "BPI123"
    assert result["extra"]["max_power"] == 5000
    assert result["extra"]["model"] == "no_model"


async def test_coordinator_creation(hass: HomeAssistant) -> None:
    """Test coordinator is created and reused."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    with patch("custom_components.kaco.async_get_clientsession") as mock_session_fn:
        mock_session = MagicMock()
        mock_resp = AsyncMock()
        mock_resp.text = AsyncMock(return_value=SAMPLE_REALTIME_CSV)
        mock_resp.status = 200
        mock_session.get = AsyncMock(return_value=mock_resp)
        mock_session_fn.return_value = mock_session

        coord1 = await get_coordinator(hass, MOCK_CONFIG, config_entry=entry)
        coord2 = await get_coordinator(hass, MOCK_CONFIG, config_entry=entry)
        assert coord1 is coord2


async def test_coordinator_no_ip(hass: HomeAssistant) -> None:
    """Test coordinator with no IP returns defaults."""
    config = dict(MOCK_CONFIG)
    config[CONF_KACO_URL] = ""

    with patch("custom_components.kaco.async_get_clientsession") as mock_session_fn:
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session

        coord = await get_coordinator(hass, config)
        assert coord.data is not None
        assert coord.data["extra"]["serialno"] == "no_serial"
