"""Connection state of the CC1101Duino, and battery warnings of wireless sensors."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import CC1101DuinoConfigEntry
from .const import DOMAIN, signal_connection
from .remote import RemoteEntity, async_setup_remote_entities

BINARY_SENSOR_DESCRIPTIONS: dict[str, BinarySensorEntityDescription] = {
    "battery_low": BinarySensorEntityDescription(
        key="battery_low",
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CC1101DuinoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([CC1101DuinoConnectedSensor(entry)])
    async_setup_remote_entities(
        hass,
        entry,
        async_add_entities,
        Platform.BINARY_SENSOR,
        BINARY_SENSOR_DESCRIPTIONS,
        CC1101DuinoBinarySensor,
    )


class CC1101DuinoConnectedSensor(BinarySensorEntity):
    """Whether the serial connection is open."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: CC1101DuinoConfigEntry) -> None:
        self._hub = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}-connected"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool:
        return self._hub.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_connection(self._hub.entry_id), self.async_write_ha_state
            )
        )


class CC1101DuinoBinarySensor(RemoteEntity, BinarySensorEntity, RestoreEntity):
    """A state reported by a wireless sensor, such as a low battery."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._attr_is_on is None and (last := await self.async_get_last_state()):
            self._attr_is_on = {"on": True, "off": False}.get(last.state)

    @callback
    def handle_value(self, value: bool) -> None:
        self._attr_is_on = value
        if self.hass is not None:
            self.async_write_ha_state()
