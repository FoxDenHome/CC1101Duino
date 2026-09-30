"""Constants for the CC1101Duino integration."""

from typing import Final

DOMAIN: Final = "cc1101duino"

CONF_AUTOMATIC_ADD: Final = "automatic_add"
CONF_API_KEY: Final = "api_key"
CONF_MODEL: Final = "model"
CONF_CLASSIFY_AUTOMATICALLY: Final = "classify_automatically"
CONF_MAX_CLASSIFICATIONS_PER_DAY: Final = "max_classifications_per_day"
CONF_MIN_TRANSMISSIONS: Final = "min_transmissions"

DEFAULT_MODEL: Final = "claude-opus-5-5"
DEFAULT_MAX_CLASSIFICATIONS_PER_DAY: Final = 10
DEFAULT_MIN_TRANSMISSIONS: Final = 3

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
EVENT_UNKNOWN_SIGNAL_CLASSIFIED: Final = f"{DOMAIN}_unknown_signal_classified"

SERVICE_SEND_SIGNAL: Final = "send_signal"
SERVICE_SEND_RAW: Final = "send_raw"
SERVICE_LIST_UNKNOWN_SIGNALS: Final = "list_unknown_signals"
SERVICE_CLASSIFY_UNKNOWN_SIGNAL: Final = "classify_unknown_signal"
SERVICE_FORGET_UNKNOWN_SIGNAL: Final = "forget_unknown_signal"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_CODER: Final = "coder"
ATTR_LINE: Final = "line"
ATTR_SIGNAL_ID: Final = "signal_id"


def signal_decoded(entry_id: str) -> str:
    """Dispatcher signal carrying each decoded signal for a config entry."""
    return f"{DOMAIN}_decoded_{entry_id}"


def signal_connection(entry_id: str) -> str:
    """Dispatcher signal sent when the connection state of a config entry changes."""
    return f"{DOMAIN}_connection_{entry_id}"


def signal_diagnostics(entry_id: str) -> str:
    """Dispatcher signal sent when the hub's diagnostics change."""
    return f"{DOMAIN}_diagnostics_{entry_id}"


def signal_unknown(entry_id: str) -> str:
    """Dispatcher signal sent when the unknown signal types of a config entry change."""
    return f"{DOMAIN}_unknown_{entry_id}"
