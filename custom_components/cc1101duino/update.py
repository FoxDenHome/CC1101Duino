"""Updates the CC1101Duino to the firmware bundled with the integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CC1101DuinoConfigEntry
from .const import DOMAIN, signal_diagnostics
from .firmware import Firmware, load_firmware


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CC1101DuinoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    firmware = await hass.async_add_executor_job(load_firmware)
    async_add_entities([CC1101DuinoFirmwareUpdate(entry, firmware)])


class CC1101DuinoFirmwareUpdate(UpdateEntity):
    """The firmware running on the device, and the one bundled with the integration."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_title = "CC1101Duino firmware"

    def __init__(self, entry: CC1101DuinoConfigEntry, firmware: Firmware) -> None:
        self._hub = entry.runtime_data
        self._firmware = firmware
        self._attr_unique_id = f"{entry.entry_id}-firmware"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_latest_version = firmware.version
        self._attr_supported_features = UpdateEntityFeature.PROGRESS
        if self._hub.can_flash:
            self._attr_supported_features |= UpdateEntityFeature.INSTALL

    @property
    def installed_version(self) -> str | None:
        return self._hub.firmware_version

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_diagnostics(self._hub.entry_id), self.async_write_ha_state
            )
        )

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        def progress(percentage: int) -> None:
            self.hass.loop.call_soon_threadsafe(self._async_set_progress, percentage)

        self._async_set_progress(0)
        try:
            await self._hub.async_install_firmware(self._firmware.image, progress)
        finally:
            self._attr_in_progress = False
            self._attr_update_percentage = None
            self.async_write_ha_state()

    def _async_set_progress(self, percentage: int) -> None:
        self._attr_in_progress = True
        self._attr_update_percentage = percentage
        self.async_write_ha_state()
