"""Sensors for values received from wireless sensors (e.g. LaCrosse TX), and hub diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CC1101DuinoConfigEntry
from .const import (
    CONF_AUTOMATIC_ADD,
    DOMAIN,
    signal_connection,
    signal_decoded,
    signal_diagnostics,
)
from .hub import HubDiagnostics, ReceivedSignal
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


@dataclass(frozen=True, kw_only=True)
class HubSensorDescription(SensorEntityDescription):
    value_fn: Callable[[HubDiagnostics], Any]
    attrs_fn: Callable[[HubDiagnostics], dict[str, Any] | None] = lambda _: None


def _signal_attrs(received: ReceivedSignal | None) -> dict[str, Any] | None:
    if received is None:
        return None
    return {"line": received.line, "rssi": received.rssi, "signals": received.signals}


HUB_SENSOR_DESCRIPTIONS: tuple[HubSensorDescription, ...] = (
    HubSensorDescription(
        key="last_signal",
        translation_key="last_signal",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda diag: diag.last_received and diag.last_received.time,
        attrs_fn=lambda diag: _signal_attrs(diag.last_received),
    ),
    HubSensorDescription(
        key="last_decoded_signal",
        translation_key="last_decoded_signal",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda diag: diag.last_decoded and diag.last_decoded.time,
        attrs_fn=lambda diag: _signal_attrs(diag.last_decoded),
    ),
    HubSensorDescription(
        key="last_unrecognized_signal",
        translation_key="last_unrecognized_signal",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda diag: diag.last_unrecognized and diag.last_unrecognized.time,
        attrs_fn=lambda diag: _signal_attrs(diag.last_unrecognized),
    ),
    HubSensorDescription(
        key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        value_fn=lambda diag: diag.last_received and diag.last_received.rssi,
    ),
    HubSensorDescription(
        key="signals_received",
        translation_key="signals_received",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda diag: diag.received,
    ),
    HubSensorDescription(
        key="signals_decoded",
        translation_key="signals_decoded",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda diag: diag.decoded,
    ),
    HubSensorDescription(
        key="signals_unrecognized",
        translation_key="signals_unrecognized",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda diag: diag.unrecognized,
    ),
    HubSensorDescription(
        key="firmware_message",
        translation_key="firmware_message",
        value_fn=lambda diag: diag.firmware_message,
    ),
)

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
    async_add_entities(
        CC1101DuinoHubSensor(entry, description) for description in HUB_SENSOR_DESCRIPTIONS
    )

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


class CC1101DuinoHubSensor(SensorEntity):
    """A diagnostic value about the signals the hub itself has received."""

    entity_description: HubSensorDescription

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # The raw lines change with every signal and are only useful live
    _unrecorded_attributes = frozenset({"line", "rssi", "signals"})

    def __init__(self, entry: CC1101DuinoConfigEntry, description: HubSensorDescription) -> None:
        self.entity_description = description
        self._hub = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}-{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._hub.diagnostics)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self._hub.diagnostics)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_diagnostics(self._hub.entry_id), self.async_write_ha_state
            )
        )
