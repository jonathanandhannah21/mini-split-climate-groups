"""Config flow for Mini Split Climate Groups integration."""

from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_MEMBERS,
    CONF_CLIMATE_ENTITY,
    CONF_TEMP_SENSOR,
    CONF_TARGET_TEMP,
    CONF_TOLERANCE,
    CONF_HYSTERESIS,
    CONF_CURRENT_PRIORITY,
    CONF_ADD_ANOTHER,
    CONF_MEMBER_NAME,
    DEFAULT_TOLERANCE,
    DEFAULT_HYSTERESIS,
    DEFAULT_TARGET_TEMP,
    MIN_TARGET_TEMP,
    MAX_TARGET_TEMP,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    # Validate that entities exist
    if CONF_CLIMATE_ENTITY in data:
        if not hass.states.get(data[CONF_CLIMATE_ENTITY]):
            raise ValueError(f"Climate entity {data[CONF_CLIMATE_ENTITY]} not found")

    if CONF_TEMP_SENSOR in data:
        if not hass.states.get(data[CONF_TEMP_SENSOR]):
            raise ValueError(f"Temperature sensor {data[CONF_TEMP_SENSOR]} not found")

    return {"title": data.get(CONF_NAME, "Climate Group")}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mini Split Climate Groups."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.data: Dict[str, Any] = {}
        self.members: list[Dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
                self.data = {
                    CONF_NAME: user_input[CONF_NAME],
                    CONF_TOLERANCE: user_input.get(CONF_TOLERANCE, DEFAULT_TOLERANCE),
                    CONF_HYSTERESIS: user_input.get(
                        CONF_HYSTERESIS, DEFAULT_HYSTERESIS
                    ),
                }

                # Move to adding members
                return await self.async_step_add_member()

            except Exception as err:
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Optional(
                        CONF_TOLERANCE, default=DEFAULT_TOLERANCE
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.5,
                            max=5.0,
                            step=0.5,
                            mode=selector.NumberSelectorMode.SLIDER,
                            unit_of_measurement="°F",
                        )
                    ),
                    vol.Optional(
                        CONF_HYSTERESIS, default=DEFAULT_HYSTERESIS
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1,
                            max=1.0,
                            step=0.1,
                            mode=selector.NumberSelectorMode.SLIDER,
                            unit_of_measurement="°F",
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_add_member(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding climate zone members."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Validate the input
                await validate_input(self.hass, user_input)

                # Get the name of the climate entity for display
                climate_state = self.hass.states.get(user_input[CONF_CLIMATE_ENTITY])
                member_name = climate_state.attributes.get(
                    "friendly_name", user_input[CONF_CLIMATE_ENTITY]
                )

                # Create member ID from entity name
                member_id = user_input[CONF_CLIMATE_ENTITY].split(".")[-1]

                # Add member to list
                self.members.append(
                    {
                        "id": member_id,
                        CONF_MEMBER_NAME: member_name,
                        CONF_CLIMATE_ENTITY: user_input[CONF_CLIMATE_ENTITY],
                        CONF_TEMP_SENSOR: user_input[CONF_TEMP_SENSOR],
                        CONF_TARGET_TEMP: user_input.get(
                            CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP
                        ),
                    }
                )

                # Check if user wants to add another
                if user_input.get(CONF_ADD_ANOTHER, True):
                    return await self.async_step_add_member()

                # Move to priority setup
                return await self.async_step_priority()

            except ValueError as err:
                errors["base"] = str(err)
            except Exception as err:
                _LOGGER.exception("Unexpected exception: %s", err)
                errors["base"] = "unknown"

        # Build description with member count
        description = f"Add zone #{len(self.members) + 1}"
        if self.members:
            added = ", ".join(m[CONF_MEMBER_NAME] for m in self.members)
            description += f" (Already added: {added})"

        return self.async_show_form(
            step_id="add_member",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLIMATE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=CLIMATE_DOMAIN,
                        )
                    ),
                    vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=SENSOR_DOMAIN,
                            device_class="temperature",
                        )
                    ),
                    vol.Optional(
                        CONF_TARGET_TEMP, default=DEFAULT_TARGET_TEMP
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_TARGET_TEMP,
                            max=MAX_TARGET_TEMP,
                            step=1,
                            mode=selector.NumberSelectorMode.SLIDER,
                            unit_of_measurement="°F",
                        )
                    ),
                    vol.Optional(CONF_ADD_ANOTHER, default=True): bool,
                }
            ),
            description_placeholders={"description": description},
            errors=errors,
        )

    async def async_step_priority(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle priority order configuration."""
        if user_input is not None or not self.members:
            # Create config entry
            self.data[CONF_MEMBERS] = self.members
            self.data[CONF_CURRENT_PRIORITY] = [m["id"] for m in self.members]

            return self.async_create_entry(
                title=self.data[CONF_NAME],
                data=self.data,
            )

        # Show summary of members and their default priority
        member_list = "\n".join(
            [
                f"{idx + 1}. {member[CONF_MEMBER_NAME]}"
                for idx, member in enumerate(self.members)
            ]
        )

        return self.async_show_form(
            step_id="priority",
            data_schema=vol.Schema({}),
            description_placeholders={
                "members": member_list,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for the integration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self.config_entry
        current_tolerance = entry.options.get(
            CONF_TOLERANCE, entry.data.get(CONF_TOLERANCE, DEFAULT_TOLERANCE)
        )
        current_hysteresis = entry.options.get(
            CONF_HYSTERESIS, entry.data.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_TOLERANCE, default=current_tolerance
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.5,
                            max=5.0,
                            step=0.5,
                            mode=selector.NumberSelectorMode.SLIDER,
                            unit_of_measurement="°F",
                        )
                    ),
                    vol.Optional(
                        CONF_HYSTERESIS, default=current_hysteresis
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.1,
                            max=1.0,
                            step=0.1,
                            mode=selector.NumberSelectorMode.SLIDER,
                            unit_of_measurement="°F",
                        )
                    ),
                }
            ),
        )
