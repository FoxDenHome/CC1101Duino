"""Config flow for CC1101Duino."""

from __future__ import annotations

import logging
from typing import Any

import serial
import serial.tools.list_ports
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_DEVICE
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_AUTOMATIC_ADD, DOMAIN
from .hub import async_open

_LOGGER = logging.getLogger(__name__)


def _list_ports() -> list[str]:
    return [port.device for port in serial.tools.list_ports.comports()]


class CC1101DuinoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a CC1101Duino by serial port or pyserial URL."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            device = user_input[CONF_DEVICE]
            await self.async_set_unique_id(device)
            self._abort_if_unique_id_configured()
            try:
                _, writer = await async_open(device)
                writer.close()
            except (OSError, serial.SerialException):
                _LOGGER.exception("Unable to open %s", device)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=device,
                    data={CONF_DEVICE: device},
                    options={CONF_AUTOMATIC_ADD: user_input[CONF_AUTOMATIC_ADD]},
                )

        ports = await self.hass.async_add_executor_job(_list_ports)
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE): SelectSelector(
                    SelectSelectorConfig(
                        options=ports, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Required(CONF_AUTOMATIC_ADD, default=True): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
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
