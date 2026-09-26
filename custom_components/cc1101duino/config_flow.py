"""Config flow for CC1101Duino."""

from __future__ import annotations

import logging
from typing import Any

import serial
import serial.tools.list_ports
import voluptuous as vol
from homeassistant.components import usb
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_DEVICE
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_AUTOMATIC_ADD, DOMAIN
from .hub import async_open

_LOGGER = logging.getLogger(__name__)


def _list_ports() -> list[SelectOptionDict]:
    """List serial ports by their stable /dev/serial/by-id path where one exists."""
    options = []
    for port in serial.tools.list_ports.comports():
        # Skip the legacy ttyS* placeholders Linux creates without any hardware behind them
        if port.vid is None and port.description in (None, "n/a"):
            continue
        path = usb.get_serial_by_id(port.device)
        label = usb.human_readable_device_name(
            path,
            port.serial_number,
            port.manufacturer,
            port.description,
            None if port.vid is None else f"{port.vid:04X}",
            None if port.pid is None else f"{port.pid:04X}",
        )
        options.append(SelectOptionDict(value=path, label=label))
    return options


def _stable_path(device: str) -> str:
    """Turn a typed /dev/ttyUSB0 into its /dev/serial/by-id path, leave URLs alone."""
    if device.startswith("/dev/"):
        return usb.get_serial_by_id(device)
    return device


class CC1101DuinoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a CC1101Duino by serial port or pyserial URL."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_step_device("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_step_device(
            "reconfigure",
            user_input,
            {CONF_DEVICE: self._get_reconfigure_entry().data[CONF_DEVICE]},
        )

    async def _async_step_device(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        suggested: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry() if self.source == SOURCE_RECONFIGURE else None
        errors: dict[str, str] = {}

        if user_input is not None:
            device = await self.hass.async_add_executor_job(_stable_path, user_input[CONF_DEVICE])
            await self.async_set_unique_id(device)
            if entry is not None:
                if any(
                    other.unique_id == device and other.entry_id != entry.entry_id
                    for other in self._async_current_entries(include_ignore=False)
                ):
                    return self.async_abort(reason="already_configured")
            else:
                self._abort_if_unique_id_configured()

            try:
                if entry is None or device != entry.data[CONF_DEVICE]:
                    # Reconfiguring to the port in use would fail, as it is open
                    _, writer = await async_open(device)
                    writer.close()
            except (OSError, serial.SerialException):
                _LOGGER.exception("Unable to open %s", device)
                errors["base"] = "cannot_connect"
            else:
                if entry is not None:
                    return self.async_update_reload_and_abort(
                        entry, unique_id=device, title=device, data={CONF_DEVICE: device}
                    )
                return self.async_create_entry(
                    title=device,
                    data={CONF_DEVICE: device},
                    options={CONF_AUTOMATIC_ADD: user_input[CONF_AUTOMATIC_ADD]},
                )

        ports = await self.hass.async_add_executor_job(_list_ports)
        fields: dict[Any, Any] = {
            vol.Required(CONF_DEVICE): SelectSelector(
                SelectSelectorConfig(
                    options=ports, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                )
            ),
        }
        if entry is None:
            fields[vol.Required(CONF_AUTOMATIC_ADD, default=True)] = BooleanSelector()
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(fields), user_input or suggested
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CC1101DuinoOptionsFlow()


class CC1101DuinoOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema({vol.Required(CONF_AUTOMATIC_ADD): BooleanSelector()})
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_AUTOMATIC_ADD: True, **self.config_entry.options}
            ),
        )
