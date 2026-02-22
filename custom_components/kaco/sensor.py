"""
Custom component to grab data from a kaco solar inverter.
@ Author : Kolja Windeler
@ Date : 2020/08/10
@ Description : Grabs and parses the data of a kaco inverter
"""

from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_NAME,
    UnitOfEnergy,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
)
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from custom_components.kaco import get_coordinator
from .const import (
    DOMAIN,
    DEFAULT_ICON,
    DEFAULT_NAME,
    CONF_KACO_URL,
    CONF_SERIAL_NUMBER,
    CONF_MAC_ADDRESS,
    MEAS_VALUES,
    MeasurementObj,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Run setup via YAML."""
    _LOGGER.debug("Config via YAML")
    if config is not None:
        coordinator = await get_coordinator(hass, config)
        async_add_entities(
            [
                KacoSensor(hass, config, coordinator, sensor_obj, entry_id=None)
                for sensor_obj in MEAS_VALUES
                if sensor_obj.checkEnabled(config)
            ],
            False,
        )


async def async_setup_entry(hass, config_entry: ConfigEntry, async_add_devices):
    """Run setup via Storage/UI."""
    _LOGGER.debug("Config via Storage/UI")
    if len(config_entry.data) > 0:
        coordinator = await get_coordinator(
            hass, config_entry.data, config_entry=config_entry
        )
        entities = [
            KacoSensor(
                hass,
                config_entry.data,
                coordinator,
                sensor_obj,
                entry_id=config_entry.entry_id,
            )
            for sensor_obj in MEAS_VALUES
            if sensor_obj.checkEnabled(config_entry.data)
        ]
        # Add connection status sensor
        entities.append(
            KacoConnectionSensor(
                hass,
                config_entry.data,
                coordinator,
                entry_id=config_entry.entry_id,
            )
        )
        async_add_devices(entities, False)


class KacoSensor(CoordinatorEntity, SensorEntity):
    """Representation of a KACO Sensor."""

    def __init__(
        self,
        hass,
        config: dict,
        coordinator: DataUpdateCoordinator,
        sensor_obj: MeasurementObj,
        entry_id: str | None = None,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.hass = hass
        self.coordinator = coordinator

        self._value_key = sensor_obj.valueKey
        self._unit = sensor_obj.unit
        self._description = sensor_obj.description
        self._url: str = config.get(CONF_KACO_URL) or ""
        self._name: str = config.get(CONF_NAME) or DEFAULT_NAME
        self._icon = DEFAULT_ICON
        self._entry_id = entry_id
        self._config = config
        self._last_known_state = None

        # Stable unique_id: derived from config entry, never from coordinator data
        if entry_id:
            self._attr_unique_id = f"{entry_id}_{self._value_key}"
        else:
            # YAML fallback: use IP-based ID
            try:
                fallback = (self._url.split(".")[-1] or self._url).strip()
            except Exception:
                fallback = (self._url or "unknown").strip()
            self._attr_unique_id = f"{DOMAIN}_{fallback}_{self._value_key}"

        _LOGGER.debug("KACO config:")
        _LOGGER.debug("\tname: %s", self._name)
        _LOGGER.debug("\turl: %s", self._url)
        _LOGGER.debug("\tvalueKey: %s", self._value_key)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._name} {self._description}"

    @property
    def icon(self) -> str:
        """Return the icon for the frontend."""
        return self._icon

    @property
    def device_info(self):
        """Device info using config entry for identity, coordinator for display."""
        # Identity is always based on config entry, never coordinator data
        if self._entry_id:
            identifiers = {(DOMAIN, self._entry_id)}
        else:
            identifiers = {(DOMAIN, self._url or "unknown")}

        info = {
            "identifiers": identifiers,
            "name": self._name,
            "configuration_url": f"http://{self._url}" if self._url else None,
            "manufacturer": "Kaco",
        }

        # Serial from config or coordinator (display only, not identity)
        serial = self._config.get(CONF_SERIAL_NUMBER)
        if not serial:
            try:
                if self.coordinator and self.coordinator.data:
                    serial = self.coordinator.data.get("extra", {}).get("serialno")
                    if serial == "no_serial":
                        serial = None
            except Exception:
                pass
        if serial:
            info["serial_number"] = serial

        # Model from coordinator (display only)
        try:
            if self.coordinator and self.coordinator.data:
                model = self.coordinator.data.get("extra", {}).get("model")
                if model and model != "no_model":
                    info["model"] = model
        except Exception:
            pass

        # MAC address for cross-integration device matching
        mac = self._config.get(CONF_MAC_ADDRESS)
        if mac:
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}

        return info

    @property
    def extra_state_attributes(self):
        """Return extra attributes if available."""
        try:
            if self.coordinator and self.coordinator.data:
                return self.coordinator.data.get("extra")
            return None
        except Exception:
            return None

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def native_value(self):
        """Return the sensor value, with last-known-state persistence."""
        try:
            if self.coordinator and self.coordinator.data:
                value = self.coordinator.data.get(self._value_key)
                if value is not None:
                    self._last_known_state = value
                    return value
        except Exception:
            pass
        return self._last_known_state

    @property
    def available(self) -> bool:
        """Available as long as we have a last known value."""
        if self._last_known_state is not None:
            return True
        return super().available

    @property
    def device_class(self):
        if self._unit == UnitOfEnergy.KILO_WATT_HOUR:
            return SensorDeviceClass.ENERGY
        if self._unit in (UnitOfPower.WATT, UnitOfPower.KILO_WATT):
            return SensorDeviceClass.POWER
        if self._unit == UnitOfElectricPotential.VOLT:
            return SensorDeviceClass.VOLTAGE
        if self._unit == UnitOfElectricCurrent.AMPERE:
            return SensorDeviceClass.CURRENT
        return None

    @property
    def state_class(self):
        if self._unit == UnitOfEnergy.KILO_WATT_HOUR:
            return SensorStateClass.TOTAL_INCREASING
        if self._unit in (
            UnitOfPower.WATT,
            UnitOfPower.KILO_WATT,
            UnitOfElectricPotential.VOLT,
            UnitOfElectricCurrent.AMPERE,
        ):
            return SensorStateClass.MEASUREMENT
        return None


class KacoConnectionSensor(CoordinatorEntity, SensorEntity):
    """Shows Online/Offline based on coordinator success."""

    def __init__(
        self,
        hass,
        config: dict,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
    ):
        """Initialize the connection status sensor."""
        super().__init__(coordinator)
        self.hass = hass
        self.coordinator = coordinator
        self._url: str = config.get(CONF_KACO_URL) or ""
        self._name: str = config.get(CONF_NAME) or DEFAULT_NAME
        self._entry_id = entry_id
        self._config = config
        self._attr_unique_id = f"{entry_id}_connection_status"

    @property
    def name(self) -> str:
        return f"{self._name} Connection Status"

    @property
    def icon(self) -> str:
        if self.coordinator.last_update_success:
            return "mdi:lan-connect"
        return "mdi:lan-disconnect"

    @property
    def device_info(self):
        info = {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": self._name,
            "configuration_url": f"http://{self._url}" if self._url else None,
            "manufacturer": "Kaco",
        }
        serial = self._config.get(CONF_SERIAL_NUMBER)
        if serial:
            info["serial_number"] = serial
        mac = self._config.get(CONF_MAC_ADDRESS)
        if mac:
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
        return info

    @property
    def native_value(self) -> str:
        if self.coordinator.last_update_success:
            return "Online"
        return "Offline"

    @property
    def available(self) -> bool:
        """Always available — shows connectivity state."""
        return True
