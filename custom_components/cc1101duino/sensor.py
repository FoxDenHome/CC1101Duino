"""Sensors for values received from wireless sensors (e.g. LaCrosse TX)."""

from __future__ import annotations

from typing import NamedTuple

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CC1101DuinoConfigEntry
from .const import CONF_AUTOMATIC_ADD, DOMAIN, signal_connection, signal_decoded
from .protocol import Signal

SENSOR_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    "temperature": SensorEntityDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    "humidity": SensorEntityDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
    ),
}

CODER_NAMES = {
    "lacrosse": "LaCrosse",
}


class SensorKey(NamedTuple):
    coder: str
    id: str
    subtype: str

    @classmethod
    def from_signal(cls, signal: Signal) -> SensorKey | None:
        if signal.get("type") != "sensor" or signal.get("subtype") not in SENSOR_DESCRIPTIONS:
            return None
        return cls(signal["coder"], signal["id"], signal["subtype"])

    def unique_id(self, entry_id: str) -> str:
        return "-".join((entry_id, *self))

    @classmethod
    def from_unique_id(cls, entry_id: str, unique_id: str) -> SensorKey | None:
        parts = unique_id.removeprefix(f"{entry_id}-").split("-")
        if len(parts) != 3 or parts[2] not in SENSOR_DESCRIPTIONS:
            return None
        return cls(*parts)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CC1101DuinoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Recreate previously seen sensors and add new ones as they are heard."""
    entities: dict[SensorKey, CC1101DuinoSensor] = {}

    def add(keys: list[SensorKey]) -> None:
        new = [CC1101DuinoSensor(entry, key) for key in keys if key not in entities]
        entities.update((entity.key, entity) for entity in new)
        async_add_entities(new)

    registry = er.async_get(hass)
    add(
        [
            key
            for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
            if reg_entry.domain == "sensor"
            and (key := SensorKey.from_unique_id(entry.entry_id, reg_entry.unique_id))
        ]
    )

    automatic_add = entry.options.get(CONF_AUTOMATIC_ADD, True)

    @callback
    def handle_signal(signal: Signal) -> None:
        key = SensorKey.from_signal(signal)
        if key is None:
            return
        entity = entities.get(key)
        if entity is None:
            if not automatic_add:
                return
            add([key])
            entity = entities[key]
        entity.handle_value(signal["value"])

    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_decoded(entry.entry_id), handle_signal)
    )


class CC1101DuinoSensor(RestoreSensor):
    """A single value reported by a wireless sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: CC1101DuinoConfigEntry, key: SensorKey) -> None:
        self.key = key
        self._hub = entry.runtime_data
        self.entity_description = SENSOR_DESCRIPTIONS[key.subtype]
        self._attr_unique_id = key.unique_id(entry.entry_id)
        coder_name = CODER_NAMES.get(key.coder, key.coder)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}-{key.coder}-{key.id}")},
            name=f"{coder_name} {key.id}",
            model=coder_name,
            serial_number=key.id,
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def available(self) -> bool:
        return self._hub.connected

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._attr_native_value is None and (last := await self.async_get_last_sensor_data()):
            self._attr_native_value = last.native_value
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_connection(self._hub.entry_id), self.async_write_ha_state
            )
        )

    @callback
    def handle_value(self, value: float) -> None:
        self._attr_native_value = value
        if self.hass is not None:
            self.async_write_ha_state()
