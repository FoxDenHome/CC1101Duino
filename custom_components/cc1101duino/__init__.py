"""The CC1101Duino integration."""

from __future__ import annotations

from typing import Any

import serial
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .classifier import STORAGE_VERSION, UnknownSignalClassifier
from .const import (
    ATTR_CODER,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_LINE,
    ATTR_SIGNAL_ID,
    DOMAIN,
    SERVICE_CLASSIFY_UNKNOWN_SIGNAL,
    SERVICE_FORGET_UNKNOWN_SIGNAL,
    SERVICE_LIST_UNKNOWN_SIGNALS,
    SERVICE_SEND_RAW,
    SERVICE_SEND_SIGNAL,
)
from .hub import CC1101DuinoHub
from .protocol.signalduino import load_protocols

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.UPDATE]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type CC1101DuinoConfigEntry = ConfigEntry[CC1101DuinoHub]

SEND_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_CODER): cv.string,
    },
    # Remaining fields are coder specific, e.g. id / command for minka_aire
    extra=vol.ALLOW_EXTRA,
)

SEND_RAW_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_LINE): cv.string,
    }
)

LIST_UNKNOWN_SIGNALS_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})

CLASSIFY_UNKNOWN_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_SIGNAL_ID): cv.string,
    }
)

FORGET_UNKNOWN_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        # All of them if left out
        vol.Optional(ATTR_SIGNAL_ID): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services, shared by all CC1101Duino config entries."""

    async def send_signal(call: ServiceCall) -> None:
        data = dict(call.data)
        hub = _get_hub(hass, data.pop(ATTR_CONFIG_ENTRY_ID, None))
        await hub.async_send_signal(data)

    async def send_raw(call: ServiceCall) -> None:
        hub = _get_hub(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        await hub.async_send_line(call.data[ATTR_LINE])

    async def list_unknown_signals(call: ServiceCall) -> ServiceResponse:
        classifier = _get_classifier(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        signals: list[Any] = classifier.confirmed()
        return {"signals": signals}

    async def classify_unknown_signal(call: ServiceCall) -> ServiceResponse:
        classifier = _get_classifier(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        return await classifier.async_classify(call.data[ATTR_SIGNAL_ID])

    async def forget_unknown_signal(call: ServiceCall) -> None:
        classifier = _get_classifier(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        classifier.async_forget(call.data.get(ATTR_SIGNAL_ID))

    hass.services.async_register(DOMAIN, SERVICE_SEND_SIGNAL, send_signal, SEND_SIGNAL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SEND_RAW, send_raw, SEND_RAW_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_UNKNOWN_SIGNALS,
        list_unknown_signals,
        LIST_UNKNOWN_SIGNALS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLASSIFY_UNKNOWN_SIGNAL,
        classify_unknown_signal,
        CLASSIFY_UNKNOWN_SIGNAL_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FORGET_UNKNOWN_SIGNAL,
        forget_unknown_signal,
        FORGET_UNKNOWN_SIGNAL_SCHEMA,
    )
    return True


def _get_hub(hass: HomeAssistant, entry_id: str | None) -> CC1101DuinoHub:
    entries: list[CC1101DuinoConfigEntry] = [
        entry
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if entry_id is None or entry.entry_id == entry_id
    ]
    if entry_id is None and len(entries) > 1:
        raise ServiceValidationError(
            "Multiple CC1101Duino devices are set up, specify config_entry_id"
        )
    if not entries:
        raise ServiceValidationError("No matching CC1101Duino device is loaded")
    return entries[0].runtime_data


def _get_classifier(hass: HomeAssistant, entry_id: str | None) -> UnknownSignalClassifier:
    classifier = _get_hub(hass, entry_id).classifier
    assert classifier is not None
    return classifier


async def async_setup_entry(hass: HomeAssistant, entry: CC1101DuinoConfigEntry) -> bool:
    """Set up a CC1101Duino from a config entry."""
    # Reading the SIGNALduino protocol list is file I/O; it is cached afterwards
    await hass.async_add_executor_job(load_protocols)
    hub = CC1101DuinoHub(hass, entry.entry_id, entry.data[CONF_DEVICE])
    classifier = UnknownSignalClassifier(hass, entry.entry_id, entry.options)
    await classifier.async_load()
    try:
        await hub.async_connect()
    except (OSError, serial.SerialException) as err:
        raise ConfigEntryNotReady(f"Unable to open {hub.device}: {err}") from err

    hub.classifier = classifier
    entry.runtime_data = hub
    # Unload callbacks run last first, so the hub stops before the classifier saves
    entry.async_on_unload(classifier.async_unload)
    entry.async_on_unload(hub.async_close)

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="CC1101Duino",
        name=f"CC1101Duino {hub.device}",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    hub.start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: CC1101DuinoConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CC1101DuinoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: CC1101DuinoConfigEntry) -> None:
    """Delete the unknown signals collected for a removed entry."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.unknown_signals.{entry.entry_id}").async_remove()


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: CC1101DuinoConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing remote sensors (e.g. a neighbour's), but not the hub itself."""
    return (DOMAIN, entry.entry_id) not in device.identifiers
