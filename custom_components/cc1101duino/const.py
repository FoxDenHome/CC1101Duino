"""Constants for the CC1101Duino integration."""

from typing import Final

DOMAIN: Final = "cc1101duino"

CONF_AUTOMATIC_ADD: Final = "automatic_add"

BAUDRATE: Final = 115200
RECONNECT_INTERVAL: Final = 10
COMMAND_TIMEOUT: Final = 5

# The firmware prints this after starting, followed by " V=<version>;" since versions exist
READY_MESSAGE: Final = "CC1101Duino ready"
# Reported for firmware that predates versions, so that any bundled version is newer
LEGACY_FIRMWARE_VERSION: Final = "0"
# Connections that do not reset the device (ser2net) see no ready message, so the version is
# asked for when none was reported this long after connecting
VERSION_QUERY_DELAY: Final = 3

# A new SIGNALduino sensor is added when heard twice within this many seconds (FHEM's 2:180),
# at least AUTOCREATE_MIN_GAP apart so the repeats of one transmission count once
AUTOCREATE_WINDOW: Final = 180
AUTOCREATE_MIN_GAP: Final = 2

EVENT_SIGNAL: Final = f"{DOMAIN}_signal"

SERVICE_SEND_SIGNAL: Final = "send_signal"
SERVICE_SEND_RAW: Final = "send_raw"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_CODER: Final = "coder"
ATTR_LINE: Final = "line"


def signal_decoded(entry_id: str) -> str:
    """Dispatcher signal carrying each decoded signal for a config entry."""
    return f"{DOMAIN}_decoded_{entry_id}"


def signal_connection(entry_id: str) -> str:
    """Dispatcher signal sent when the connection state of a config entry changes."""
    return f"{DOMAIN}_connection_{entry_id}"


def signal_diagnostics(entry_id: str) -> str:
    """Dispatcher signal sent when the hub's diagnostics change."""
    return f"{DOMAIN}_diagnostics_{entry_id}"
