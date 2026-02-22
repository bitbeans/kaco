# Kaco

Home Assistant integration for KACO / Schueco solar inverters (e.g. blueplanet 10.0 TL3, SGI-9k and similar models with a local web interface).

**This component will set up the following platforms.**

| Platform | Description                                    |
| -------- | ---------------------------------------------- |
| `sensor` | Power, energy, voltage, current and status data |

![Example](kaco.png)


## Features

- Shows all values from the inverter's web interface
- Status is parsed and shown as text
- Tracks maximal seen power
- Configurable update interval
- Fully async (aiohttp) — no blocking executor threads
- Exponential backoff on timeouts (important for slow inverters like the TL3)
- Last-known-state: sensors keep their last value when the inverter is offline (night, reboot) instead of going "unavailable"
- Connection status sensor (Online/Offline)
- Stable entity IDs across restarts — no more duplicate entities
- Statistics repair service for recovering orphaned data and importing historical energy from the inverter
- German and English translations

## What's new in v0.7.0

- **Fixed duplicate entities on restart** (Issue #23): Entity IDs are now based on the config entry, not the serial number. Previously the serial was read from the daily CSV which isn't available right after a restart, causing HA to create new entities each time.
- **Migrated from `requests` to `aiohttp`**: No more blocking executor threads. Uses HA's native async HTTP client.
- **Increased timeouts**: 10s for realtime data (was 5s), 15s for daily CSV (was 10s). The blueplanet TL3 is slow.
- **Last-known-state persistence**: When the inverter is offline, sensors show the last known value instead of "unavailable". Useful for the energy dashboard.
- **Connection status sensor**: New binary-style sensor showing Online/Offline based on actual connectivity.
- **Statistics repair service** (`kaco.repair_statistics`): Cleans up orphaned statistics from the duplicate entity bug and can import historical energy data from the inverter's daily CSV files.
- **Removed external dependencies**: No more `requests`, `integrationhelper`, `python-dateutil`, `tzlocal` or `voluptuous` in requirements — everything is HA-bundled.
- **Fixed HA deprecation warnings**: Removed `CONNECTION_CLASS`, fixed `OptionsFlowHandler`, fixed direct `entry.data` mutation, use enum `SensorStateClass`/`SensorDeviceClass` instead of strings.
- **Proper device classes**: Voltage and current sensors now have `SensorDeviceClass.VOLTAGE` / `SensorDeviceClass.CURRENT`.
- **Auto-persist serial number**: The serial number from the daily CSV is automatically saved to the config entry — no manual input needed.

### Upgrading from older versions

After updating to v0.7.0, entity IDs will change once because the unique_id scheme changed. You may need to update your dashboards, automations and energy configuration to use the new entity names.

If you had duplicate entities from the old bug, you can clean up orphaned statistics by calling the `kaco.repair_statistics` service under Developer Tools > Services.

# Installation

## HACS

The easiest way to add this to your Home Assistant installation is using [HACS](https://hacs.xyz/).

It's recommended to restart Home Assistant directly after the installation without any change to the configuration.

## Manual

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
2. If you do not have a `custom_components` directory (folder) there, you need to create it.
3. In the `custom_components` directory (folder) create a new folder called `kaco`.
4. Download _all_ the files from the `custom_components/kaco/` directory (folder) in this repository.
5. Place the files you downloaded in the new directory (folder) you created.
6. Follow the instructions under [Configuration](#Configuration) below.

Using your HA configuration directory (folder) as a starting point you should now also have this:

```text
custom_components/kaco/translations/en.json
custom_components/kaco/translations/de.json
custom_components/kaco/__init__.py
custom_components/kaco/manifest.json
custom_components/kaco/sensor.py
custom_components/kaco/config_flow.py
custom_components/kaco/const.py
custom_components/kaco/services.yaml
custom_components/kaco/statistics_repair.py
```

# Setup

All you need is the IP address of the inverter. This is shown on the actual device display.

## Configuration options

| Key                 | Type     | Required | Default | Description                                                                                     |
| ------------------- | -------- | -------- | ------- | ----------------------------------------------------------------------------------------------- |
| `url`               | `string` | `true`   | `None`  | The IP of the inverter, e.g. 192.168.2.194                                                      |
| `name`              | `string` | `false`  | `kaco`  | The friendly name of the sensor                                                                 |
| `kwh_interval`      | `int`    | `false`  | `120`   | The interval of the kWh update in seconds                                                       |
| `interval`          | `int`    | `false`  | `20`    | The interval of all other updates in seconds (my inverter crashes if I set it below 5 for more than a day) |
| `generator_voltage` | `bool`   | `false`  | `false` | Import generator voltage as entity                                                              |
| `generator_current` | `bool`   | `false`  | `false` | Import generator current as entity                                                              |
| `grid_voltage`      | `bool`   | `false`  | `false` | Import grid voltage as entity                                                                   |
| `grid_current`      | `bool`   | `false`  | `false` | Import grid current as entity                                                                   |
| `serial_number`     | `string` | `false`  | `None`  | Serial number (optional, auto-detected from inverter)                                           |
| `mac_address`       | `string` | `false`  | `None`  | MAC address (optional, for HA device matching)                                                  |

## GUI configuration (recommended)

Config flow is supported and is the preferred way to setup the integration. (No need to restart Home Assistant)

## Services

### `kaco.repair_statistics`

Cleans up orphaned statistics from duplicate entities and imports historical energy data from the inverter's daily CSV files. The inverter must be online. Can take a few minutes depending on how much history is available.

Call via Developer Tools > Services.

## Running tests

The test suite runs in Docker:

```bash
docker compose -f docker-compose.test.yml up --build
```

Or locally with pytest (requires Python 3.13 and `pytest-homeassistant-custom-component`):

```bash
pip install -r requirements_test.txt
pytest tests/ -v
```