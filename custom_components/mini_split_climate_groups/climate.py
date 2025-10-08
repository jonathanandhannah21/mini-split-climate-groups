"""Climate platform for Mini Split Climate Groups."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_MEMBERS,
    CONF_TOLERANCE,
    CONF_HYSTERESIS,
    ATTR_MEMBERS,
    ATTR_CURRENT_PRIORITY,
    MIN_TARGET_TEMP,
    MAX_TARGET_TEMP,
)
from .coordinator import PriorityClimateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mini Split Climate Groups from a config entry."""
    # Ensure coordinator exists
    if DOMAIN not in hass.data or config_entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error("Coordinator not found for entry %s", config_entry.entry_id)
        return
    
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    
    async_add_entities(
        [PriorityClimateGroup(coordinator, config_entry)],
        True
    )


class PriorityClimateGroup(CoordinatorEntity, ClimateEntity, RestoreEntity):
    """Representation of a Priority Climate Group."""

    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
    )
    _attr_min_temp = MIN_TARGET_TEMP
    _attr_max_temp = MAX_TARGET_TEMP
    _attr_target_temperature_step = 1

    def __init__(
        self,
        coordinator: PriorityClimateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the climate group."""
        super().__init__(coordinator)
        
        self._config_entry = config_entry
        self._attr_unique_id = f"{DOMAIN}_{config_entry.entry_id}"
        self._attr_name = config_entry.title
        
        # Device info for grouping in UI
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Mini Split Climate Groups",
            model="Priority Climate Group",
            sw_version="1.0.0",
        )
        
        # State tracking
        self._hvac_mode = HVACMode.OFF
        self._target_temperature = None
        self._current_temperature = None
        
        _LOGGER.info(
            "[%s] Climate entity initialized",
            self.name
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Initialize coordinator
        await self.coordinator.async_initialize()
        
        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state:
            # Restore HVAC mode
            if last_state.state in [HVACMode.COOL, HVACMode.HEAT]:
                self._hvac_mode = last_state.state
                self.coordinator.current_mode = last_state.state.lower()
                _LOGGER.info(
                    "[%s] Restored previous mode: %s",
                    self.name,
                    self._hvac_mode
                )
            
            # Restore target temperatures for members
            if last_state.attributes:
                members_data = last_state.attributes.get(ATTR_MEMBERS, [])
                for member_data in members_data:
                    member_id = member_data.get("id")
                    target_temp = member_data.get("target_temp")
                    if member_id and target_temp:
                        member = self.coordinator.get_member(member_id)
                        if member:
                            member.current_target_temp = target_temp
                            _LOGGER.info(
                                "[%s] Restored target temperature: %.1f°F",
                                member.name,
                                target_temp
                            )
                
                # Restore priority order
                priority_order = last_state.attributes.get(ATTR_CURRENT_PRIORITY)
                if priority_order:
                    await self.coordinator.async_set_priority_order(priority_order)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        if self.coordinator.current_mode == "cool":
            return HVACMode.COOL
        elif self.coordinator.current_mode == "heat":
            return HVACMode.HEAT
        return self._hvac_mode

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        return round(self.coordinator.get_average_current_temperature(), 1)

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        return round(self.coordinator.get_average_target_temperature(), 1)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        old_mode = self.coordinator.current_mode
        
        if hvac_mode == HVACMode.OFF:
            # Turn off all members
            _LOGGER.info(
                "[%s] Turning off all members",
                self.name
            )
            for member in self.coordinator.members:
                await member.async_turn_off("Group turned OFF by user")
            self._hvac_mode = HVACMode.OFF
            
        elif hvac_mode in [HVACMode.COOL, HVACMode.HEAT]:
            new_mode = hvac_mode.lower()
            await self.coordinator.async_set_group_mode(new_mode, old_mode)
            self._hvac_mode = hvac_mode
            
            # Trigger immediate update to apply new mode
            await self.coordinator.async_refresh()
            
        else:
            _LOGGER.warning(
                "[%s] Unsupported HVAC mode: %s",
                self.name,
                hvac_mode
            )

    async def async_set_temperature(self, **kwargs) -> None:
        """Set target temperature for all members."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
            
        _LOGGER.info(
            "[%s] Setting all members to %.1f�F",
            self.name,
            temperature
        )
        
        for member in self.coordinator.members:
            await member.async_set_target_temperature(temperature)
        
        # Trigger update
        await self.coordinator.async_refresh()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            ATTR_MEMBERS: [m.to_dict() for m in self.coordinator.members],
            "tolerance": self.coordinator.tolerance,
            "hysteresis": self.coordinator.hysteresis,
            ATTR_CURRENT_PRIORITY: self.coordinator.current_priority,
            "update_interval": 30,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Update our state from coordinator
        if self.coordinator.data:
            # Update temperatures
            self._current_temperature = self.coordinator.get_average_current_temperature()
            self._target_temperature = self.coordinator.get_average_target_temperature()
            
            # Update mode
            if self.coordinator.current_mode == "cool":
                self._hvac_mode = HVACMode.COOL
            elif self.coordinator.current_mode == "heat":
                self._hvac_mode = HVACMode.HEAT
                
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if at least one member is available
        return any(m.is_available for m in self.coordinator.members)