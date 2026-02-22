"""Statistics repair: merge orphaned statistics and import historical CSV data."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_list_statistic_ids,
    statistics_during_period,
    async_import_statistics,
    clear_statistics,
)
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.persistent_notification import async_create

from .const import (
    DOMAIN,
    CONF_KACO_URL,
    MEAS_CURRENT_POWER,
    MEAS_ENERGY_TODAY,
    MEAS_GEN_VOLT1,
    MEAS_GEN_VOLT2,
    MEAS_GEN_CURR1,
    MEAS_GEN_CURR2,
    MEAS_GRID_VOLT1,
    MEAS_GRID_VOLT2,
    MEAS_GRID_VOLT3,
    MEAS_GRID_CURR1,
    MEAS_GRID_CURR2,
    MEAS_GRID_CURR3,
    MEAS_VALUES,
)

_LOGGER = logging.getLogger(__name__)

# Sensor value keys used to match orphaned statistic_ids
_SENSOR_SUFFIXES = [m.valueKey for m in MEAS_VALUES]

# How far back to scan for historical CSV files (days)
_MAX_HISTORY_DAYS = 5 * 365

# In-memory flags to avoid re-running on each reload (persisted via hass.data)
_REPAIR_FLAGS_KEY = f"{DOMAIN}_repair_flags"


def _get_flags(hass: HomeAssistant) -> dict:
    """Get repair flags from hass.data (survives reloads, not restarts)."""
    hass.data.setdefault(_REPAIR_FLAGS_KEY, {})
    return hass.data[_REPAIR_FLAGS_KEY]


async def async_migrate_statistics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Phase A: Find and merge orphaned statistics from duplicate entities."""
    flags = _get_flags(hass)
    flag_key = f"{config_entry.entry_id}_migrated"
    if flags.get(flag_key):
        return

    _LOGGER.info("KACO: Starting statistics migration check")

    try:
        stat_ids_list = await get_instance(hass).async_add_executor_job(
            _list_statistic_ids_sync, hass
        )
    except Exception:
        _LOGGER.warning("Could not list statistic IDs, skipping migration")
        return

    # Build lookup: suffix -> list of statistic_ids
    kaco_stats: dict[str, list[str]] = {}
    for stat_info in stat_ids_list:
        stat_id = stat_info.get("statistic_id", "")
        if not stat_id.startswith("sensor."):
            continue
        # Check if this looks like a kaco sensor
        for suffix in _SENSOR_SUFFIXES:
            camel_lower = suffix.lower()
            snake = _camel_to_snake(suffix)
            if camel_lower in stat_id.lower() or snake in stat_id.lower():
                kaco_stats.setdefault(suffix, []).append(stat_id)
                break

    # Find orphaned ones (more than 1 statistic per suffix = duplicates exist)
    merged_count = 0
    orphan_count = 0
    for suffix, stat_id_list in kaco_stats.items():
        if len(stat_id_list) <= 1:
            continue

        _LOGGER.info(
            "KACO: Found %d statistics for sensor suffix '%s': %s",
            len(stat_id_list),
            suffix,
            stat_id_list,
        )

        # The "current" one is the one matching our config entry
        entry_id = config_entry.entry_id
        current_id = None
        orphans = []
        for sid in stat_id_list:
            if entry_id in sid:
                current_id = sid
            else:
                orphans.append(sid)

        if not current_id:
            if orphans:
                _LOGGER.info(
                    "KACO: No current statistic for '%s', will attempt rename of first orphan",
                    suffix,
                )
            continue

        for orphan_id in orphans:
            orphan_count += 1
            try:
                await get_instance(hass).async_add_executor_job(
                    clear_statistics, get_instance(hass), [orphan_id]
                )
                merged_count += 1
                _LOGGER.info(
                    "KACO: Cleared orphaned statistic '%s' (superseded by '%s')",
                    orphan_id,
                    current_id,
                )
            except Exception as ex:
                _LOGGER.warning(
                    "KACO: Failed to clear orphaned statistic '%s': %s",
                    orphan_id,
                    ex,
                )

    # Mark migration as done (in-memory only, no config_entry update)
    flags[flag_key] = True

    if merged_count > 0:
        async_create(
            hass,
            f"KACO: Cleaned up {merged_count} orphaned statistics entries "
            f"from {orphan_count} duplicate entities.",
            title="KACO Statistics Migration",
            notification_id="kaco_statistics_migration",
        )
    _LOGGER.info(
        "KACO: Statistics migration complete. Cleaned %d orphaned entries.",
        merged_count,
    )


async def async_import_historical(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Phase B: Import historical energy data from inverter daily CSV files."""
    flags = _get_flags(hass)
    flag_key = f"{config_entry.entry_id}_history"
    if flags.get(flag_key):
        return

    ip = config_entry.data.get(CONF_KACO_URL)
    if not ip:
        return

    _LOGGER.info("KACO: Starting historical data import from %s", ip)
    session = async_get_clientsession(hass)

    # Find the energy entity's statistic_id
    energy_stat_id = f"sensor.{config_entry.data.get('name', 'kaco')}_{MEAS_ENERGY_TODAY.description.lower().replace(' ', '_')}"

    today = datetime.date.today()
    imported_days = 0
    cumulative_sum = 0.0

    # First verify inverter is reachable at all
    test_url = f"http://{ip}/realtime.csv"
    try:
        async with asyncio.timeout(15):
            resp = await session.get(test_url)
            if resp.status != 200:
                _LOGGER.info("KACO: Inverter not reachable, skipping historical import")
                return
    except Exception:
        _LOGGER.info("KACO: Inverter not reachable, skipping historical import")
        return

    # Probe yearly boundaries to find earliest available date (gentle: 5s between)
    earliest_available = None
    for months_back in range(0, 60, 6):  # probe every 6 months, max 5 years
        probe_date = today - datetime.timedelta(days=months_back * 30)
        url = f"http://{ip}/{probe_date.strftime('%Y%m%d')}.csv"
        try:
            async with asyncio.timeout(15):
                resp = await session.get(url)
                if resp.status == 200:
                    text = await resp.text(encoding="ISO-8859-1")
                    if len(text) > 10:
                        earliest_available = probe_date
                        _LOGGER.info(
                            "KACO: Found CSV at %s, probing further back...",
                            probe_date.isoformat(),
                        )
        except Exception:
            pass
        await asyncio.sleep(5)

    if earliest_available is None:
        _LOGGER.info("KACO: No historical CSV files found on inverter")
        flags[flag_key] = True
        return

    _LOGGER.info(
        "KACO: Scanning day-by-day from %s to %s (%d days)",
        earliest_available.isoformat(),
        today.isoformat(),
        (today - earliest_available).days,
    )

    # Scan day by day from earliest to today (gentle: 5s between requests)
    statistics_data = []
    scan_date = earliest_available
    total_days = (today - earliest_available).days + 1
    while scan_date <= today:
        url = f"http://{ip}/{scan_date.strftime('%Y%m%d')}.csv"
        try:
            async with asyncio.timeout(15):
                resp = await session.get(url)
                if resp.status == 200:
                    text = await resp.text(encoding="ISO-8859-1")
                    if len(text) > 10:
                        lines = text.strip().split("\r")
                        if len(lines) > 1:
                            last_line = lines[-1].strip()
                            if last_line:
                                cols = last_line.split(";")
                                if len(cols) > 4:
                                    energy_kwh = float(cols[4])
                                    cumulative_sum += energy_kwh
                                    dt = datetime.datetime.combine(
                                        scan_date,
                                        datetime.time(12, 0),
                                        tzinfo=datetime.timezone.utc,
                                    )
                                    statistics_data.append(
                                        StatisticData(
                                            start=dt,
                                            state=energy_kwh,
                                            sum=cumulative_sum,
                                        )
                                    )
                                    imported_days += 1
        except Exception:
            pass

        # Log progress every 30 days
        days_done = (scan_date - earliest_available).days + 1
        if days_done % 30 == 0:
            _LOGGER.info(
                "KACO: Historical import progress: %d/%d days scanned, %d imported",
                days_done,
                total_days,
                imported_days,
            )

        scan_date += datetime.timedelta(days=1)
        # 5s between requests to not overwhelm the inverter
        await asyncio.sleep(5)

    if statistics_data:
        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"{config_entry.data.get('name', 'kaco')} Energy Today",
            source="recorder",
            statistic_id=energy_stat_id,
            unit_of_measurement="kWh",
        )
        try:
            async_import_statistics(hass, metadata, statistics_data)
            _LOGGER.info(
                "KACO: Imported %d days of historical energy data (earliest: %s)",
                imported_days,
                earliest_available.isoformat(),
            )
        except Exception as ex:
            _LOGGER.error("KACO: Failed to import historical statistics: %s", ex)

    # Mark import as done (in-memory only)
    flags[flag_key] = True

    if imported_days > 0:
        async_create(
            hass,
            f"KACO: Imported {imported_days} days of historical energy data "
            f"(earliest: {earliest_available.isoformat()}).",
            title="KACO Historical Data Import",
            notification_id="kaco_historical_import",
        )


async def async_repair_statistics_service(call: ServiceCall) -> None:
    """Service handler for kaco.repair_statistics."""
    hass = call.hass
    # Reset flags to force re-run
    hass.data.pop(_REPAIR_FLAGS_KEY, None)

    entries = hass.config_entries.async_entries(DOMAIN)
    for entry in entries:
        await async_migrate_statistics(hass, entry)
        await async_import_historical(hass, entry)


def _camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    result = []
    for char in name:
        if char.isupper() and result:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def _list_statistic_ids_sync(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Wrapper for sync context."""
    import homeassistant.components.recorder.statistics as stats

    return stats.list_statistic_ids(hass)
