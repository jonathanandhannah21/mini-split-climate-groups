"""The Mini Split Climate Groups integration."""
from __future__ import annotations

import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_registry import async_get

from .const import (
    DOMAIN,
    CONF_MEMBERS,
    CONF_CLIMATE_ENTITY,
    CONF_TEMP_SENSOR,
    CONF_TARGET_TEMP,
    CONF_TOLERANCE,
    CONF_HYSTERESIS,
    CONF_CURRENT_PRIORITY,
    CONF_MEMBER_NAME,
    SERVICE_SET_TARGET_TEMPERATURE,
    SERVICE_SET_TOLERANCE,
    SERVICE_SET_PRIORITY_ORDER,
    SERVICE_RESET_TO_DEFAULT,
    ATTR_MEMBER_ID,
    ATTR_TEMPERATURE,
    ATTR_TOLERANCE,
    ATTR_PRIORITY_ORDER,
    DEFAULT_TOLERANCE,
    DEFAULT_HYSTERESIS,
    DEFAULT_TARGET_TEMP,
)
from .coordinator import PriorityClimateCoordinator, PriorityClimateMember

PLATFORMS = [Platform.CLIMATE]

_LOGGER = logging.getLogger(__name__)

# Service schemas
SET_TARGET_TEMPERATURE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required(ATTR_MEMBER_ID): cv.string,
        vol.Required(ATTR_TEMPERATURE): vol.Coerce(float),
    }
)

SET_TOLERANCE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required(ATTR_TOLERANCE): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=5.0)),
    }
)

SET_PRIORITY_ORDER_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required(ATTR_PRIORITY_ORDER): [cv.string],
    }
)

RESET_TO_DEFAULT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required(ATTR_MEMBER_ID): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mini Split Climate Groups from a config entry."""
    _LOGGER.info(
        "Setting up Mini Split Climate Groups integration: %s",
        entry.title
    )
    
    # Initialize domain data if not exists
    hass.data.setdefault(DOMAIN, {})
    
    # Create members from config
    members = []
    for member_config in entry.data.get(CONF_MEMBERS, []):
        member = PriorityClimateMember(
            hass=hass,
            member_id=member_config["id"],
            name=member_config.get(CONF_MEMBER_NAME, member_config["id"]),
            climate_entity_id=member_config[CONF_CLIMATE_ENTITY],
            temp_sensor_id=member_config[CONF_TEMP_SENSOR],
            default_target_temp=member_config.get(CONF_TARGET_TEMP, DEFAULT_TARGET_TEMP),
        )
        members.append(member)
    
    # Create coordinator
    coordinator = PriorityClimateCoordinator(
        hass=hass,
        name=entry.title,
        members=members,
        tolerance=entry.data.get(CONF_TOLERANCE, DEFAULT_TOLERANCE),
        hysteresis=entry.data.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS),
    )
    
    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await async_register_services(hass)
    
    _LOGGER.info(
        "Mini Split Climate Groups integration setup complete: %s",
        entry.title
    )
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(
        "Unloading Mini Split Climate Groups integration: %s",
        entry.title
    )
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Remove coordinator
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Remove services if no other instances
        if not hass.data[DOMAIN]:
            await async_unregister_services(hass)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_register_services(hass: HomeAssistant) -> None:
    """Register integration services."""
    
    async def handle_set_target_temperature(call: ServiceCall) -> None:
        """Handle set target temperature service call."""
        entity_id = call.data["entity_id"]
        member_id = call.data[ATTR_MEMBER_ID]
        temperature = call.data[ATTR_TEMPERATURE]
        
        # Find the coordinator for this entity
        coordinator = None
        for entry_id, data in hass.data[DOMAIN].items():
            # Check if this is the correct entity by matching the climate entity
            if entity_id in hass.states:
                entity_state = hass.states.get(entity_id)
                if entity_state and entity_state.attributes.get("unique_id") == f"{DOMAIN}_{entry_id}":
                    coordinator = data["coordinator"]
                    break
        
        # Fallback - try to match by unique ID pattern
        if not coordinator:
            for entry_id, data in hass.data[DOMAIN].items():
                if entity_id.endswith(entry_id) or entry_id in entity_id:
                    coordinator = data["coordinator"]
                    break
        
        if not coordinator:
            _LOGGER.error(
                "Climate group entity not found: %s",
                entity_id
            )
            return
        
        await coordinator.async_set_member_target_temperature(member_id, temperature)
    
    async def handle_set_tolerance(call: ServiceCall) -> None:
        """Handle set tolerance service call."""
        entity_id = call.data["entity_id"]
        tolerance = call.data[ATTR_TOLERANCE]
        
        # Find the coordinator for this entity
        coordinator = None
        for entry_id, data in hass.data[DOMAIN].items():
            # Check if this is the correct entity by matching the climate entity
            if entity_id in hass.states:
                entity_state = hass.states.get(entity_id)
                if entity_state and entity_state.attributes.get("unique_id") == f"{DOMAIN}_{entry_id}":
                    coordinator = data["coordinator"]
                    break
        
        # Fallback - try to match by unique ID pattern
        if not coordinator:
            for entry_id, data in hass.data[DOMAIN].items():
                if entity_id.endswith(entry_id) or entry_id in entity_id:
                    coordinator = data["coordinator"]
                    break
        
        if not coordinator:
            _LOGGER.error(
                "Climate group entity not found: %s",
                entity_id
            )
            return
        
        await coordinator.async_set_tolerance(tolerance)
    
    async def handle_set_priority_order(call: ServiceCall) -> None:
        """Handle set priority order service call."""
        entity_id = call.data["entity_id"]
        priority_order = call.data[ATTR_PRIORITY_ORDER]
        
        # Find the coordinator for this entity
        coordinator = None
        for entry_id, data in hass.data[DOMAIN].items():
            # Check if this is the correct entity by matching the climate entity
            if entity_id in hass.states:
                entity_state = hass.states.get(entity_id)
                if entity_state and entity_state.attributes.get("unique_id") == f"{DOMAIN}_{entry_id}":
                    coordinator = data["coordinator"]
                    break
        
        # Fallback - try to match by unique ID pattern
        if not coordinator:
            for entry_id, data in hass.data[DOMAIN].items():
                if entity_id.endswith(entry_id) or entry_id in entity_id:
                    coordinator = data["coordinator"]
                    break
        
        if not coordinator:
            _LOGGER.error(
                "Climate group entity not found: %s",
                entity_id
            )
            return
        
        await coordinator.async_set_priority_order(priority_order)
    
    async def handle_reset_to_default(call: ServiceCall) -> None:
        """Handle reset to default service call."""
        entity_id = call.data["entity_id"]
        member_id = call.data[ATTR_MEMBER_ID]
        
        # Find the coordinator for this entity
        coordinator = None
        for entry_id, data in hass.data[DOMAIN].items():
            # Check if this is the correct entity by matching the climate entity
            if entity_id in hass.states:
                entity_state = hass.states.get(entity_id)
                if entity_state and entity_state.attributes.get("unique_id") == f"{DOMAIN}_{entry_id}":
                    coordinator = data["coordinator"]
                    break
        
        # Fallback - try to match by unique ID pattern
        if not coordinator:
            for entry_id, data in hass.data[DOMAIN].items():
                if entity_id.endswith(entry_id) or entry_id in entity_id:
                    coordinator = data["coordinator"]
                    break
        
        if not coordinator:
            _LOGGER.error(
                "Climate group entity not found: %s",
                entity_id
            )
            return
        
        await coordinator.async_reset_member_to_default(member_id)
    
    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TARGET_TEMPERATURE,
        handle_set_target_temperature,
        schema=SET_TARGET_TEMPERATURE_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TOLERANCE,
        handle_set_tolerance,
        schema=SET_TOLERANCE_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PRIORITY_ORDER,
        handle_set_priority_order,
        schema=SET_PRIORITY_ORDER_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_TO_DEFAULT,
        handle_reset_to_default,
        schema=RESET_TO_DEFAULT_SCHEMA,
    )
    
    _LOGGER.debug("Registered services for Mini Split Climate Groups")


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister integration services."""
    services = [
        SERVICE_SET_TARGET_TEMPERATURE,
        SERVICE_SET_TOLERANCE,
        SERVICE_SET_PRIORITY_ORDER,
        SERVICE_RESET_TO_DEFAULT,
    ]
    
    for service in services:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    
    _LOGGER.debug("Unregistered services for Mini Split Climate Groups")