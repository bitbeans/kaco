"""Shared fixtures for KACO integration tests."""

from __future__ import annotations

import sys
import asyncio
import socket as _socket_module
import pytest
from unittest.mock import patch
from homeassistant.core import HomeAssistant

# On Windows, pytest-homeassistant-custom-component uses pytest_socket which
# blocks ALL socket creation, but both ProactorEventLoop and SelectorEventLoop
# need socket.socketpair() for their self-pipe. We must disable the socket
# blocker and use SelectorEventLoop for Windows compatibility.
if sys.platform == "win32":
    # 1. Neutralize pytest_socket's blocking before it activates
    import pytest_socket

    # Save original socket class
    _OrigSocket = pytest_socket._true_socket

    # Override disable/enable to never actually block
    pytest_socket.disable_socket = (
        lambda allow_unix_socket=False, allow_hosts=None: None
    )
    pytest_socket.enable_socket = lambda: None
    # Ensure socket class is always the real one
    _socket_module.socket = _OrigSocket

    # 2. Patch HassEventLoopPolicy to use SelectorEventLoop
    _policy = asyncio.get_event_loop_policy()
    _orig_new_loop = _policy.new_event_loop

    def _selector_new_event_loop():
        """Create a SelectorEventLoop instead of ProactorEventLoop."""
        loop = asyncio.SelectorEventLoop()
        try:
            from homeassistant.runner import _async_loop_exception_handler

            loop.set_exception_handler(_async_loop_exception_handler)
        except ImportError:
            pass
        return loop

    _policy.new_event_loop = _selector_new_event_loop

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
)

# Sample realtime.csv response (14 semicolon-separated fields)
# Fields: unknown;genV1;genV2;gridV1;gridV2;gridV3;genC1;genC2;gridC1;gridC2;gridC3;power;temp;status
SAMPLE_REALTIME_CSV = (
    "0;32768;32768;32768;32768;32768;16384;16384;16384;16384;16384;32768;2500;4"
)

# Sample daily CSV (model;serial;date;time;energy_kwh;...)
SAMPLE_DAILY_CSV = (
    "blueplanet 10.0 TL3;BPI123456789;20260222;120000;5.432;0;0\r"
    "blueplanet 10.0 TL3;BPI123456789;20260222;121000;5.567;0;0"
)

# Empty/short response for "no data" scenarios
EMPTY_CSV = ""

MOCK_CONFIG = {
    CONF_NAME: "PV Inverter",
    CONF_KACO_URL: "192.168.178.112",
    CONF_INTERVAL: "20",
    CONF_KWH_INTERVAL: "120",
    CONF_GENERATOR_VOLTAGE: True,
    CONF_GENERATOR_CURRENT: True,
    CONF_GRID_VOLTAGE: True,
    CONF_GRID_CURRENT: True,
}

MOCK_CONFIG_MINIMAL = {
    CONF_NAME: "PV Inverter",
    CONF_KACO_URL: "192.168.178.112",
    CONF_INTERVAL: "20",
    CONF_KWH_INTERVAL: "120",
    CONF_GENERATOR_VOLTAGE: False,
    CONF_GENERATOR_CURRENT: False,
    CONF_GRID_VOLTAGE: False,
    CONF_GRID_CURRENT: False,
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    yield
