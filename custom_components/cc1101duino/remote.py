"""Entities for wireless sensors, created as they are heard and restored from the registry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, NamedTuple

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CC1101DuinoConfigEntry
from .const import CONF_AUTOMATIC_ADD, DOMAIN, signal_connection, signal_decoded
from .protocol import Signal

CODER_NAMES = {
    "lacrosse": "LaCrosse",
    "nexus": "Nexus",
}


class RemoteKey(NamedTuple):
    coder: str
    id: str
    subtype: str

    @classmethod
    def from_signal(cls, signal: Signal, subtypes: Mapping[str, Any]) -> RemoteKey | None:
        if signal.get("type") != "sensor" or signal.get("subtype") not in subtypes:
            return None
        return cls(signal["coder"], signal["id"], signal["subtype"])

    def unique_id(self, entry_id: str) -> str:
        return "-".join((entry_id, *self))

    @classmethod
    def from_unique_id(
        cls, entry_id: str, unique_id: str, subtypes: Mapping[str, Any]
    ) -> RemoteKey | None:
        parts = unique_id.removeprefix(f"{entry_id}-").split("-")
        if len(parts) != 3 or parts[2] not in subtypes:
            return None
        return cls(*parts)


def device_info(entry_id: str, key: RemoteKey, signal: Signal | None) -> DeviceInfo:
    info = DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}-{key.coder}-{key.id}")},
        via_device=(DOMAIN, entry_id),
    )
    if signal is None:
        # Restored from the registry, which already knows the name and model
        return info
    if "protocol" in signal:
        # SIGNALduino sensors are named by their FHEM device code, e.g. SD_WS_27_TH_2
        info.update(
            name=key.id,
            model=signal.get("model"),
            model_id=f"SIGNALduino protocol {signal['protocol']}",
        )
    else:
        coder_name = CODER_NAMES.get(key.coder, key.coder)
        info.update(name=f"{coder_name} {key.id}", model=coder_name, serial_number=key.id)
    return info


class RemoteEntity(Entity):
    """A single value reported by a wireless sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry: CC1101DuinoConfigEntry,
        key: RemoteKey,
        description: EntityDescription,
        signal: Signal | None,
    ) -> None:
        self.key = key
        self._hub = entry.runtime_data
        self.entity_description = description
        self._attr_unique_id = key.unique_id(entry.entry_id)
        self._attr_device_info = device_info(entry.entry_id, key, signal)

    @property
    def available(self) -> bool:
        return self._hub.connected

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_connection(self._hub.entry_id), self.async_write_ha_state
            )
        )

    @callback
    def handle_value(self, value: Any) -> None:
        raise NotImplementedError


@callback
def async_setup_remote_entities(
    hass: HomeAssistant,
    entry: CC1101DuinoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    domain: str,
    descriptions: Mapping[str, EntityDescription],
    entity_factory: Callable[
        [CC1101DuinoConfigEntry, RemoteKey, EntityDescription, Signal | None], RemoteEntity
    ],
) -> None:
    """Recreate previously seen entities of a platform, and add new ones as they are heard."""
    hub = entry.runtime_data
    entities: dict[RemoteKey, RemoteEntity] = {}

    def add(keys: list[tuple[RemoteKey, Signal | None]]) -> None:
        new = [
            entity_factory(entry, key, descriptions[key.subtype], signal)
            for key, signal in keys
            if key not in entities
        ]
        entities.update((entity.key, entity) for entity in new)
        async_add_entities(new)

    registry = er.async_get(hass)
    add(
        [
            (key, None)
            for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
            if reg_entry.domain == domain
            and (key := RemoteKey.from_unique_id(entry.entry_id, reg_entry.unique_id, descriptions))
        ]
    )

    automatic_add = entry.options.get(CONF_AUTOMATIC_ADD, True)

    @callback
    def handle_signal(signal: Signal) -> None:
        key = RemoteKey.from_signal(signal, descriptions)
        if key is None:
            return
        entity = entities.get(key)
        if entity is None:
            if not automatic_add or not hub.is_confirmed(signal):
                return
            add([(key, signal)])
            entity = entities[key]
        entity.handle_value(signal["value"])

    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_decoded(entry.entry_id), handle_signal)
    )
