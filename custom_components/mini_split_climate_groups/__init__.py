"""The Mini Split Climate Groups integration."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_ENABLED,
    ATTR_HYSTERESIS,
    ATTR_MEMBER_ID,
    ATTR_MODE,
    ATTR_ON,
    ATTR_PRIORITY_ORDER,
    ATTR_SCHEDULES,
    ATTR_TEMPERATURE,
    ATTR_TOLERANCE,
    CONF_CLIMATE_ENTITY,
    CONF_HYSTERESIS,
    CONF_MEMBER_NAME,
    CONF_MEMBERS,
    CONF_TARGET_TEMP,
    CONF_TEMP_SENSOR,
    CONF_TOLERANCE,
    DEFAULT_HYSTERESIS,
    DEFAULT_TARGET_TEMP,
    DEFAULT_TOLERANCE,
    DOMAIN,
    MAX_TARGET_TEMP,
    MIN_TARGET_TEMP,
    MODES,
    SERVICE_RESET_TO_DEFAULT,
    SERVICE_SET_AUTOMATION,
    SERVICE_SET_HYSTERESIS,
    SERVICE_SET_MEMBER_POWER,
    SERVICE_SET_MODE,
    SERVICE_SET_PRIORITY_ORDER,
    SERVICE_SET_SCHEDULES,
    SERVICE_SET_TARGET_TEMPERATURE,
    SERVICE_SET_TOLERANCE,
    STORAGE_KEY,
    STORAGE_VERSION,
    WEEKDAYS,
)
from .coordinator import PriorityClimateCoordinator, PriorityClimateMember

PLATFORMS = [Platform.CLIMATE, Platform.SWITCH]

_LOGGER = logging.getLogger(__name__)

_ENTITY = {vol.Required("entity_id"): cv.entity_id}

SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Optional("id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Required("start"): cv.string,
        vol.Required("end"): cv.string,
        vol.Optional("days", default=list(WEEKDAYS)): [vol.In(WEEKDAYS)],
        vol.Optional("priority_order", default=[]): [cv.string],
    }
)

SERVICE_SCHEMAS = {
    SERVICE_SET_TARGET_TEMPERATURE: vol.Schema(
        {
            **_ENTITY,
            vol.Required(ATTR_MEMBER_ID): cv.string,
            vol.Required(ATTR_TEMPERATURE): vol.All(
                vol.Coerce(float), vol.Range(min=MIN_TARGET_TEMP, max=MAX_TARGET_TEMP)
            ),
        }
    ),
    SERVICE_SET_TOLERANCE: vol.Schema(
        {
            **_ENTITY,
            vol.Required(ATTR_TOLERANCE): vol.All(
                vol.Coerce(float), vol.Range(min=0.5, max=5.0)
            ),
        }
    ),
    SERVICE_SET_HYSTERESIS: vol.Schema(
        {
            **_ENTITY,
            vol.Required(ATTR_HYSTERESIS): vol.All(
                vol.Coerce(float), vol.Range(min=0.0, max=2.0)
            ),
        }
    ),
    SERVICE_SET_PRIORITY_ORDER: vol.Schema(
        {**_ENTITY, vol.Required(ATTR_PRIORITY_ORDER): [cv.string]}
    ),
    SERVICE_RESET_TO_DEFAULT: vol.Schema(
        {**_ENTITY, vol.Required(ATTR_MEMBER_ID): cv.string}
    ),
    SERVICE_SET_AUTOMATION: vol.Schema(
        {**_ENTITY, vol.Required(ATTR_ENABLED): cv.boolean}
    ),
    SERVICE_SET_MODE: vol.Schema({**_ENTITY, vol.Required(ATTR_MODE): vol.In(MODES)}),
    SERVICE_SET_MEMBER_POWER: vol.Schema(
        {
            **_ENTITY,
            vol.Required(ATTR_MEMBER_ID): cv.string,
            vol.Required(ATTR_ON): cv.boolean,
        }
    ),
    SERVICE_SET_SCHEDULES: vol.Schema(
        {**_ENTITY, vol.Required(ATTR_SCHEDULES): [SCHEDULE_SCHEMA]}
    ),
}


def _entry_value(entry: ConfigEntry, key: str, default: Any) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a climate group from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    members = [
        PriorityClimateMember(
            hass=hass,
            member_id=member_config["id"],
            name=member_config.get(CONF_MEMBER_NAME, member_config["id"]),
            climate_entity_id=member_config[CONF_CLIMATE_ENTITY],
            temp_sensor_id=member_config[CONF_TEMP_SENSOR],
            default_target_temp=member_config.get(
                CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP
            ),
        )
        for member_config in entry.data.get(CONF_MEMBERS, [])
    ]

    coordinator = PriorityClimateCoordinator(
        hass=hass,
        name=entry.title,
        members=members,
        tolerance=_entry_value(entry, CONF_TOLERANCE, DEFAULT_TOLERANCE),
        hysteresis=_entry_value(entry, CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
        store=Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}"),
    )
    await coordinator.async_load()
    await coordinator.async_initialize()
    await coordinator.async_refresh()

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    _async_register_services(hass)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply tolerance/hysteresis changed in the options dialog."""
    coordinator: PriorityClimateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    if CONF_TOLERANCE in entry.options:
        await coordinator.async_set_tolerance(entry.options[CONF_TOLERANCE])
    if CONF_HYSTERESIS in entry.options:
        await coordinator.async_set_hysteresis(entry.options[CONF_HYSTERESIS])


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)["coordinator"]
        await coordinator.async_flush()
        if not hass.data[DOMAIN]:
            for service in SERVICE_SCHEMAS:
                hass.services.async_remove(DOMAIN, service)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete saved settings when a group is removed."""
    await Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}").async_remove()


def _coordinator_for(hass: HomeAssistant, entity_id: str) -> PriorityClimateCoordinator:
    """Find the group behind a climate (or automation switch) entity."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    groups = hass.data.get(DOMAIN, {})
    if registry_entry and registry_entry.config_entry_id in groups:
        return groups[registry_entry.config_entry_id]["coordinator"]
    raise ServiceValidationError(f"{entity_id} is not a mini split climate group")


def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services (once)."""

    handlers: dict[
        str, Callable[[PriorityClimateCoordinator, dict], Awaitable[None]]
    ] = {
        SERVICE_SET_TARGET_TEMPERATURE: lambda c, d: (
            c.async_set_member_target_temperature(
                d[ATTR_MEMBER_ID], d[ATTR_TEMPERATURE]
            )
        ),
        SERVICE_SET_TOLERANCE: lambda c, d: c.async_set_tolerance(d[ATTR_TOLERANCE]),
        SERVICE_SET_HYSTERESIS: lambda c, d: c.async_set_hysteresis(d[ATTR_HYSTERESIS]),
        SERVICE_SET_PRIORITY_ORDER: lambda c, d: (
            c.async_set_priority_order(d[ATTR_PRIORITY_ORDER])
        ),
        SERVICE_RESET_TO_DEFAULT: lambda c, d: (
            c.async_reset_member_to_default(d[ATTR_MEMBER_ID])
        ),
        SERVICE_SET_AUTOMATION: lambda c, d: c.async_set_automation(d[ATTR_ENABLED]),
        SERVICE_SET_MODE: lambda c, d: c.async_set_mode(d[ATTR_MODE]),
        SERVICE_SET_MEMBER_POWER: lambda c, d: (
            c.async_set_member_power(d[ATTR_MEMBER_ID], d[ATTR_ON])
        ),
        SERVICE_SET_SCHEDULES: lambda c, d: c.async_set_schedules(d[ATTR_SCHEDULES]),
    }

    def make_handler(service: str):
        async def handle(call: ServiceCall) -> None:
            coordinator = _coordinator_for(hass, call.data["entity_id"])
            try:
                await handlers[service](coordinator, dict(call.data))
            except ValueError as err:
                raise ServiceValidationError(str(err)) from err

        return handle

    for service, schema in SERVICE_SCHEMAS.items():
        if not hass.services.has_service(DOMAIN, service):
            hass.services.async_register(
                DOMAIN, service, make_handler(service), schema=schema
            )
