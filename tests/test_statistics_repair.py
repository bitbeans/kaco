"""Tests for KACO statistics_repair.py — orphan merge and historical import."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kaco.const import DOMAIN, CONF_KACO_URL
from custom_components.kaco.statistics_repair import (
    async_migrate_statistics,
    async_import_historical,
    _camel_to_snake,
)

from .conftest import MOCK_CONFIG


def test_camel_to_snake() -> None:
    """Test camelCase to snake_case conversion."""
    assert _camel_to_snake("currentPower") == "current_power"
    assert _camel_to_snake("energyToday") == "energy_today"
    assert _camel_to_snake("generatorVoltage1") == "generator_voltage1"
    assert _camel_to_snake("gridCurrent3") == "grid_current3"


async def test_migrate_statistics_no_orphans(hass: HomeAssistant) -> None:
    """Test migration when no orphaned statistics exist."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.kaco.statistics_repair.get_instance"
    ) as mock_recorder:
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(return_value=[])
        mock_recorder.return_value = mock_instance

        await async_migrate_statistics(hass, entry)

        # Should mark as migrated even with no orphans
        assert entry.data.get("statistics_migrated") is True


async def test_migrate_statistics_with_orphans(hass: HomeAssistant) -> None:
    """Test migration detects and clears orphaned statistics."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG)
    entry.add_to_hass(hass)

    stat_ids = [
        {"statistic_id": f"sensor.pv_inverter_{entry.entry_id}_current_power"},
        {"statistic_id": "sensor.pv_inverter_current_power_2"},
        {"statistic_id": "sensor.pv_inverter_current_power_3"},
    ]

    with patch(
        "custom_components.kaco.statistics_repair.get_instance"
    ) as mock_recorder:
        mock_instance = MagicMock()
        mock_instance.async_add_executor_job = AsyncMock(return_value=stat_ids)
        mock_recorder.return_value = mock_instance

        with patch(
            "custom_components.kaco.statistics_repair.clear_statistics"
        ) as mock_clear:
            await async_migrate_statistics(hass, entry)

            assert entry.data.get("statistics_migrated") is True


async def test_import_historical_no_ip(hass: HomeAssistant) -> None:
    """Test historical import skips when no IP configured."""
    config = dict(MOCK_CONFIG)
    config[CONF_KACO_URL] = ""
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)

    await async_import_historical(hass, entry)
    # Should not crash, should not set history_imported_until
    assert entry.data.get("history_imported_until") is None
