"""The CC1101Duino integration."""

from __future__ import annotations

import serial
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CODER,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_LINE,
    DOMAIN,
    SERVICE_SEND_RAW,
    SERVICE_SEND_SIGNAL,
)
from .hub import CC1101DuinoHub

PLATFORMS = [Platform.SENSOR]

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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services, shared by all CC1101Duino config entries."""

    async def send_signal(call: ServiceCall) -> None:
        data = dict(call.data)
        hub = _get_hub(hass, data.pop(ATTR_CONFIG_ENTRY_ID, None))
        await hub.async_send_signal(data)

    async def send_raw(call: ServiceCall) -> None:
        hub = _get_hub(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        await hub.async_send_line(call.data[ATTR_LINE])

    hass.services.async_register(DOMAIN, SERVICE_SEND_SIGNAL, send_signal, SEND_SIGNAL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SEND_RAW, send_raw, SEND_RAW_SCHEMA)
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


async def async_setup_entry(hass: HomeAssistant, entry: CC1101DuinoConfigEntry) -> bool:
    """Set up a CC1101Duino from a config entry."""
    hub = CC1101DuinoHub(hass, entry.entry_id, entry.data[CONF_DEVICE])
    try:
        await hub.async_connect()
    except (OSError, serial.SerialException) as err:
        raise ConfigEntryNotReady(f"Unable to open {hub.device}: {err}") from err

    entry.runtime_data = hub
    entry.async_on_unload(hub.async_close)

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="CC1101Duino",
        name=f"CC1101Duino {hub.device}",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_create_background_task(hass, hub.async_run(), f"{DOMAIN} {hub.device}")
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: CC1101DuinoConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CC1101DuinoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: CC1101DuinoConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing remote sensors (e.g. a neighbour's), but not the hub itself."""
    return (DOMAIN, entry.entry_id) not in device.identifiers
