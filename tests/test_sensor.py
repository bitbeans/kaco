"""Tests for KACO sensor.py — entity creation, unique_id stability, last-known-state."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfElectricPotential
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.kaco.sensor import KacoSensor, KacoConnectionSensor
from custom_components.kaco.const import (
    DOMAIN,
    MEAS_CURRENT_POWER,
    MEAS_ENERGY_TODAY,
    MEAS_GEN_VOLT1,
    MEAS_GRID_CURR1,
)

from .conftest import MOCK_CONFIG


def _make_coordinator(hass, data=None):
    """Create a mock coordinator."""
    coord = MagicMock(spec=DataUpdateCoordinator)
    coord.data = data
    coord.last_update_success = True
    return coord


class TestKacoSensorUniqueId:
    """Test that unique_id is stable regardless of coordinator data."""

    def test_unique_id_with_entry_id(self, hass: HomeAssistant) -> None:
        """unique_id must be entry_id + value_key, never serial-based."""
        coord = _make_coordinator(hass, data=None)
        sensor = KacoSensor(
            hass, MOCK_CONFIG, coord, MEAS_CURRENT_POWER, entry_id="test_entry_123"
        )
        assert sensor.unique_id == "test_entry_123_currentPower"

    def test_unique_id_stable_across_data_changes(self, hass: HomeAssistant) -> None:
        """unique_id must NOT change when coordinator data changes."""
        coord = _make_coordinator(hass, data=None)
        sensor = KacoSensor(
            hass, MOCK_CONFIG, coord, MEAS_CURRENT_POWER, entry_id="test_entry_123"
        )
        uid_before = sensor.unique_id

        # Now coordinator gets data with serial
        coord.data = {
            "extra": {"serialno": "BPI123456", "model": "TL3"},
            "currentPower": 5000,
        }
        uid_after = sensor.unique_id

        assert uid_before == uid_after
        assert "BPI123456" not in uid_after

    def test_unique_id_yaml_fallback(self, hass: HomeAssistant) -> None:
        """YAML setup (no entry_id) falls back to IP-based ID."""
        coord = _make_coordinator(hass, data=None)
        sensor = KacoSensor(hass, MOCK_CONFIG, coord, MEAS_CURRENT_POWER, entry_id=None)
        assert sensor.unique_id == f"{DOMAIN}_112_currentPower"


class TestKacoSensorLastKnownState:
    """Test last-known-state persistence."""

    def test_returns_value_when_available(self, hass: HomeAssistant) -> None:
        """Sensor returns coordinator value when available."""
        coord = _make_coordinator(
            hass, data={"currentPower": 5000, "extra": {"serialno": "X"}}
        )
        sensor = KacoSensor(hass, MOCK_CONFIG, coord, MEAS_CURRENT_POWER, entry_id="e1")
        assert sensor.native_value == 5000

    def test_returns_last_known_when_no_data(self, hass: HomeAssistant) -> None:
        """Sensor returns last known value when coordinator has no data."""
        coord = _make_coordinator(
            hass, data={"currentPower": 5000, "extra": {"serialno": "X"}}
        )
        sensor = KacoSensor(hass, MOCK_CONFIG, coord, MEAS_CURRENT_POWER, entry_id="e1")
        # Read once to populate last known state
        _ = sensor.native_value

        # Simulate coordinator failure (data becomes None)
        coord.data = None
        coord.last_update_success = False
        assert sensor.native_value == 5000
        assert sensor.available is True

    def test_returns_none_when_never_had_data(self, hass: HomeAssistant) -> None:
        """Sensor returns None if it never had data."""
        coord = _make_coordinator(hass, data=None)
        sensor = KacoSensor(hass, MOCK_CONFIG, coord, MEAS_CURRENT_POWER, entry_id="e1")
        assert sensor.native_value is None


class TestKacoSensorDeviceClass:
    """Test device_class and state_class assignment."""

    def test_energy_sensor(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass, data=None)
        sensor = KacoSensor(hass, MOCK_CONFIG, coord, MEAS_ENERGY_TODAY, entry_id="e1")
        assert sensor.device_class == SensorDeviceClass.ENERGY
        assert sensor.state_class == SensorStateClass.TOTAL_INCREASING

    def test_power_sensor(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass, data=None)
        sensor = KacoSensor(hass, MOCK_CONFIG, coord, MEAS_CURRENT_POWER, entry_id="e1")
        assert sensor.device_class == SensorDeviceClass.POWER
        assert sensor.state_class == SensorStateClass.MEASUREMENT

    def test_voltage_sensor(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass, data=None)
        sensor = KacoSensor(hass, MOCK_CONFIG, coord, MEAS_GEN_VOLT1, entry_id="e1")
        assert sensor.device_class == SensorDeviceClass.VOLTAGE
        assert sensor.state_class == SensorStateClass.MEASUREMENT

    def test_current_sensor(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass, data=None)
        sensor = KacoSensor(hass, MOCK_CONFIG, coord, MEAS_GRID_CURR1, entry_id="e1")
        assert sensor.device_class == SensorDeviceClass.CURRENT
        assert sensor.state_class == SensorStateClass.MEASUREMENT


class TestKacoConnectionSensor:
    """Test connection status sensor."""

    def test_online_when_success(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass, data={"currentPower": 1000})
        coord.last_update_success = True
        sensor = KacoConnectionSensor(hass, MOCK_CONFIG, coord, entry_id="e1")
        assert sensor.native_value == "Online"
        assert sensor.available is True

    def test_offline_when_failed(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass, data=None)
        coord.last_update_success = False
        sensor = KacoConnectionSensor(hass, MOCK_CONFIG, coord, entry_id="e1")
        assert sensor.native_value == "Offline"
        assert sensor.available is True

    def test_unique_id(self, hass: HomeAssistant) -> None:
        coord = _make_coordinator(hass, data=None)
        sensor = KacoConnectionSensor(hass, MOCK_CONFIG, coord, entry_id="e1")
        assert sensor.unique_id == "e1_connection_status"
