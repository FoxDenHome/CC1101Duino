"""Sensors for values received from wireless sensors (e.g. LaCrosse TX), and hub diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    LIGHT_LUX,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UV_INDEX,
    EntityCategory,
    Platform,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CC1101DuinoConfigEntry
from .const import DOMAIN, signal_diagnostics
from .hub import HubDiagnostics, ReceivedSignal
from .remote import RemoteEntity, async_setup_remote_entities


def _measurement(
    key: str,
    device_class: SensorDeviceClass | None,
    unit: str | None,
    precision: int,
    translation_key: str | None = None,
    state_class: SensorStateClass = SensorStateClass.MEASUREMENT,
) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=translation_key,
        device_class=device_class,
        state_class=state_class,
        native_unit_of_measurement=unit,
        suggested_display_precision=precision,
    )


def _temperature(key: str, translation_key: str | None = None) -> SensorEntityDescription:
    return _measurement(
        key, SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 1, translation_key
    )


def _wind(key: str, translation_key: str | None = None) -> SensorEntityDescription:
    return _measurement(
        key, SensorDeviceClass.WIND_SPEED, UnitOfSpeed.METERS_PER_SECOND, 1, translation_key
    )


# Values of wireless sensors, by the subtype of the decoded signal
SENSOR_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    description.key: description
    for description in (
        _temperature("temperature"),
        _temperature("temperature_2", "temperature_2"),
        _temperature("temperature_3", "temperature_3"),
        _temperature("temperature_4", "temperature_4"),
        _temperature("temperature_food", "temperature_food"),
        _temperature("temperature_bbq", "temperature_bbq"),
        _temperature("wind_chill", "wind_chill"),
        _measurement("humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE, 0),
        _measurement("pressure", SensorDeviceClass.ATMOSPHERIC_PRESSURE, UnitOfPressure.HPA, 0),
        _wind("wind_speed"),
        _wind("wind_speed_average", "wind_speed_average"),
        _wind("wind_gust", "wind_gust"),
        _measurement(
            "wind_direction",
            SensorDeviceClass.WIND_DIRECTION,
            DEGREE,
            0,
            state_class=SensorStateClass.MEASUREMENT_ANGLE,
        ),
        _measurement(
            "rain",
            SensorDeviceClass.PRECIPITATION,
            UnitOfPrecipitationDepth.MILLIMETERS,
            1,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        _measurement(
            "rain_rate",
            SensorDeviceClass.PRECIPITATION_INTENSITY,
            UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
            1,
        ),
        _measurement("battery", SensorDeviceClass.BATTERY, PERCENTAGE, 0),
        _measurement("battery_voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 1),
        _measurement("illuminance", SensorDeviceClass.ILLUMINANCE, LIGHT_LUX, 0),
        _measurement("uv_index", None, UV_INDEX, 1, "uv_index"),
        _measurement("distance", SensorDeviceClass.DISTANCE, UnitOfLength.CENTIMETERS, 0),
    )
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CC1101DuinoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Recreate previously seen sensors and add new ones as they are heard."""
    async_add_entities(
        CC1101DuinoHubSensor(entry, description) for description in HUB_SENSOR_DESCRIPTIONS
    )

    async_setup_remote_entities(
        hass, entry, async_add_entities, Platform.SENSOR, SENSOR_DESCRIPTIONS, CC1101DuinoSensor
    )


class CC1101DuinoSensor(RemoteEntity, RestoreSensor):
    """A single value reported by a wireless sensor."""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._attr_native_value is None and (last := await self.async_get_last_sensor_data()):
            self._attr_native_value = last.native_value

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
