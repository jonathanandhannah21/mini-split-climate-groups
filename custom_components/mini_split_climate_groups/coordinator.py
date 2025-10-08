"""Coordinator for Mini Split Climate Groups."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import HVACMode
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    ATTR_TEMPERATURE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    UPDATE_INTERVAL,
    DEFAULT_TOLERANCE,
    DEFAULT_HYSTERESIS,
    DEFAULT_TARGET_TEMP,
)

_LOGGER = logging.getLogger(__name__)


class PriorityClimateMember:
    """Represents a member of a priority climate group."""

    def __init__(
        self,
        hass: HomeAssistant,
        member_id: str,
        name: str,
        climate_entity_id: str,
        temp_sensor_id: str,
        default_target_temp: float,
    ) -> None:
        """Initialize the member."""
        self.hass = hass
        self.member_id = member_id
        self.name = name
        self.climate_entity_id = climate_entity_id
        self.temp_sensor_id = temp_sensor_id
        self.default_target_temp = default_target_temp
        
        # Runtime state
        self.current_target_temp = default_target_temp
        self.current_temp = default_target_temp
        self.is_on = False
        self.mode = "cool"
        self.is_aligned = True
        self.wants_mode_change = False
        self.wanted_mode = None
        self.current_priority = 1
        self.is_available = True
        self.supported_modes = []

    def update_current_temp(self) -> bool:
        """Update current temperature from sensor with error handling."""
        temp_state = self.hass.states.get(self.temp_sensor_id)
        
        if temp_state is None:
            _LOGGER.error(
                "[%s] Temperature sensor not found: %s",
                self.name,
                self.temp_sensor_id
            )
            return False
            
        if temp_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning(
                "[%s] Temperature sensor unavailable (state: %s). "
                "Using last known value %.1f�F. "
                "If persistent, check sensor connectivity.",
                self.name,
                temp_state.state,
                self.current_temp
            )
            return False
            
        try:
            self.current_temp = float(temp_state.state)
            return True
        except (ValueError, TypeError) as err:
            _LOGGER.error(
                "[%s] Invalid temperature value '%s' from sensor %s: %s",
                self.name,
                temp_state.state,
                self.temp_sensor_id,
                err
            )
            return False

    def update_climate_state(self) -> bool:
        """Update state from climate entity with error handling."""
        climate_state = self.hass.states.get(self.climate_entity_id)
        
        if climate_state is None:
            _LOGGER.error(
                "[%s] Climate entity not found: %s",
                self.name,
                self.climate_entity_id
            )
            self.is_available = False
            return False
            
        if climate_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning(
                "[%s] Climate entity unavailable (state: %s). "
                "Skipping control this cycle. "
                "If persistent, try reloading the Kumo integration.",
                self.name,
                climate_state.state
            )
            self.is_available = False
            return False
            
        # Entity is available
        self.is_available = True
        hvac_mode = climate_state.state
        self.is_on = hvac_mode in (HVACMode.HEAT, HVACMode.COOL)
        
        # Update supported modes
        self.supported_modes = climate_state.attributes.get("hvac_modes", [])
        
        # Update current mode if entity is on
        if self.is_on:
            self.mode = hvac_mode.lower()
            
        return True

    def validate_hvac_modes(self) -> bool:
        """Check if entity supports required modes."""
        if not self.supported_modes:
            climate_state = self.hass.states.get(self.climate_entity_id)
            if climate_state:
                self.supported_modes = climate_state.attributes.get("hvac_modes", [])
                
        missing_modes = []
        if HVACMode.HEAT not in self.supported_modes:
            missing_modes.append("heat")
        if HVACMode.COOL not in self.supported_modes:
            missing_modes.append("cool")
            
        if missing_modes:
            _LOGGER.warning(
                "[%s] Climate entity is missing HVAC modes: %s. "
                "Supported modes: %s. "
                "This is a known Kumo bug. Fix: "
                "1) Go to Settings � Devices & Services � Devices "
                "2) Find '%s' "
                "3) Click device � ... � Edit � Check 'Cool' and 'Heat' support "
                "The integration will only use available modes until fixed.",
                self.name,
                ", ".join(missing_modes),
                ", ".join(self.supported_modes) if self.supported_modes else "none",
                self.name
            )
            return False
            
        return True

    def calculate_alignment(self, hysteresis: float) -> None:
        """Calculate if member is aligned with target temperature."""
        if self.mode == "cool":
            # In cooling mode, aligned if current temp is at or below target + hysteresis
            self.is_aligned = self.current_temp <= (self.current_target_temp + hysteresis)
        else:  # heat
            # In heating mode, aligned if current temp is at or above target - hysteresis
            self.is_aligned = self.current_temp >= (self.current_target_temp - hysteresis)
            
        _LOGGER.debug(
            "[%s] Alignment check: current=%.1f�F, target=%.1f�F, mode=%s, aligned=%s",
            self.name,
            self.current_temp,
            self.current_target_temp,
            self.mode,
            self.is_aligned
        )

    def calculate_wants(self, tolerance: float) -> None:
        """Calculate if member wants a mode change."""
        delta = self.current_temp - self.current_target_temp
        abs_delta = abs(delta)
        
        # Reset wants
        self.wants_mode_change = False
        self.wanted_mode = None
        
        if abs_delta > tolerance:
            # Outside tolerance window
            if delta > 0:
                # Too hot, wants cooling
                self.wanted_mode = "cool"
            else:
                # Too cold, wants heating
                self.wanted_mode = "heat"
                
            # Check if current mode matches wanted mode
            if self.mode != self.wanted_mode:
                self.wants_mode_change = True
                _LOGGER.debug(
                    "[%s] Wants mode change: %.1f�F outside tolerance, wants %s but in %s mode",
                    self.name,
                    abs_delta,
                    self.wanted_mode,
                    self.mode
                )
        else:
            _LOGGER.debug(
                "[%s] Within tolerance: %.1f�F from target (tolerance: %.1f�F)",
                self.name,
                abs_delta,
                tolerance
            )

    def should_be_on(self, group_mode: str) -> bool:
        """Determine if this member should be running."""
        # Don't run if not available
        if not self.is_available:
            return False
            
        # Must match group mode
        if self.mode != group_mode:
            return False
            
        # Run if not aligned with target
        return not self.is_aligned

    async def async_set_hvac_mode_safe(self, mode: str) -> bool:
        """Set HVAC mode with validation."""
        if not self.is_available:
            _LOGGER.debug(
                "[%s] Skipping mode change: entity unavailable",
                self.name
            )
            return False
            
        climate_state = self.hass.states.get(self.climate_entity_id)
        if not climate_state:
            return False
            
        supported_modes = climate_state.attributes.get("hvac_modes", [])
        target_mode = HVACMode.HEAT if mode == "heat" else HVACMode.COOL
        
        if target_mode not in supported_modes:
            _LOGGER.warning(
                "[%s] Cannot set mode to %s: not supported by entity. "
                "Available modes: %s. Skipping.",
                self.name,
                mode,
                ", ".join(supported_modes)
            )
            return False
            
        try:
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {
                    "entity_id": self.climate_entity_id,
                    "hvac_mode": target_mode,
                },
                blocking=True,
            )
            self.mode = mode
            _LOGGER.info(
                "[%s] Mode set to %s",
                self.name,
                mode
            )
            return True
        except Exception as err:
            _LOGGER.error(
                "[%s] Failed to set mode to %s: %s",
                self.name,
                mode,
                err
            )
            return False

    async def async_turn_on(self, reason: str = "") -> None:
        """Turn on climate entity with error handling."""
        if not self.is_available:
            _LOGGER.debug(
                "[%s] Skipping turn_on: entity unavailable",
                self.name
            )
            return
            
        if self.is_on:
            return  # Already on
            
        try:
            # First set the mode
            success = await self.async_set_hvac_mode_safe(self.mode)
            if success:
                self.is_on = True
                _LOGGER.info(
                    "[%s] Turned ON (mode: %s). Reason: %s",
                    self.name,
                    self.mode,
                    reason or f"working toward target {self.current_target_temp:.1f}�F, current {self.current_temp:.1f}�F"
                )
        except Exception as err:
            _LOGGER.error(
                "[%s] Failed to turn on: %s. Entity may be unavailable.",
                self.name,
                err
            )

    async def async_turn_off(self, reason: str = "") -> None:
        """Turn off climate entity with error handling."""
        if not self.is_available:
            _LOGGER.debug(
                "[%s] Skipping turn_off: entity unavailable",
                self.name
            )
            return
            
        if not self.is_on:
            return  # Already off
            
        try:
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {
                    "entity_id": self.climate_entity_id,
                    "hvac_mode": HVACMode.OFF,
                },
                blocking=True,
            )
            self.is_on = False
            _LOGGER.info(
                "[%s] Turned OFF. Reason: %s",
                self.name,
                reason or f"aligned with target (target: {self.current_target_temp:.1f}�F, current: {self.current_temp:.1f}�F)"
            )
        except Exception as err:
            _LOGGER.error(
                "[%s] Failed to turn off: %s. Entity may be unavailable.",
                self.name,
                err
            )

    async def async_set_target_temperature(self, temperature: float) -> None:
        """Set target temperature for the member."""
        old_temp = self.current_target_temp
        self.current_target_temp = temperature
        
        _LOGGER.info(
            "[%s] Target temperature adjusted: %.1f�F � %.1f�F (changed by user via UI)",
            self.name,
            old_temp,
            temperature
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert member to dictionary for attributes."""
        return {
            "id": self.member_id,
            "name": self.name,
            "climate_entity": self.climate_entity_id,
            "temp_sensor": self.temp_sensor_id,
            "current_temp": round(self.current_temp, 1),
            "target_temp": round(self.current_target_temp, 1),
            "default_target_temp": round(self.default_target_temp, 1),
            "is_on": self.is_on,
            "mode": self.mode,
            "is_aligned": self.is_aligned,
            "wants_change": self.wants_mode_change,
            "wanted_mode": self.wanted_mode,
            "priority": self.current_priority,
            "is_available": self.is_available,
        }


class PriorityClimateCoordinator(DataUpdateCoordinator):
    """Coordinator for priority-based climate control."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        members: List[PriorityClimateMember],
        tolerance: float = DEFAULT_TOLERANCE,
        hysteresis: float = DEFAULT_HYSTERESIS,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        
        self.group_name = name
        self.members = members
        self.tolerance = tolerance
        self.hysteresis = hysteresis
        self.current_mode = "cool"
        self.current_priority = [m.member_id for m in members]
        
        # Update member priorities based on order
        for idx, member_id in enumerate(self.current_priority):
            member = self.get_member(member_id)
            if member:
                member.current_priority = idx + 1
        
        # Log initialization
        _LOGGER.info(
            "[%s] Initialized with %d members. Priority order: %s. "
            "Tolerance: %.1f�F, Hysteresis: %.1f�F. Update interval: %d seconds.",
            self.group_name,
            len(self.members),
            ", ".join([m.name for m in self.members]),
            self.tolerance,
            self.hysteresis,
            UPDATE_INTERVAL
        )

    def get_member(self, member_id: str) -> Optional[PriorityClimateMember]:
        """Get member by ID."""
        for member in self.members:
            if member.member_id == member_id:
                return member
        return None

    async def async_initialize(self) -> None:
        """Initialize the coordinator and detect existing state."""
        _LOGGER.debug("[%s] Starting initialization", self.group_name)
        
        # Update all member states
        for member in self.members:
            member.update_current_temp()
            if member.update_climate_state():
                member.validate_hvac_modes()
                
                # Detect existing mode from running members
                if member.is_on and member.mode in ("heat", "cool"):
                    self.current_mode = member.mode
                    _LOGGER.info(
                        "[%s] Detected existing group mode from %s: %s",
                        self.group_name,
                        member.name,
                        self.current_mode
                    )
                    
        _LOGGER.info(
            "[%s] Initialization complete. Current mode: %s",
            self.group_name,
            self.current_mode
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Main control loop - runs every UPDATE_INTERVAL seconds."""
        _LOGGER.debug("[%s] Starting update cycle", self.group_name)
        
        # 1. Update all member states
        for member in self.members:
            member.update_current_temp()
            if not member.update_climate_state():
                # Entity unavailable, skip but don't crash
                continue
            member.validate_hvac_modes()
            member.calculate_alignment(self.hysteresis)
            member.calculate_wants(self.tolerance)
        
        # 2. Log member states
        _LOGGER.debug("[%s] Member states:", self.group_name)
        for member in self.members:
            if member.is_available:
                _LOGGER.debug(
                    "  � %s: %.1f�F / target %.1f�F, aligned=%s, wants=%s",
                    member.name,
                    member.current_temp,
                    member.current_target_temp,
                    member.is_aligned,
                    member.wanted_mode
                )
            else:
                _LOGGER.debug(
                    "  � %s: UNAVAILABLE",
                    member.name
                )
        
        # 3. Evaluate priority and determine mode
        old_mode = self.current_mode
        new_mode = await self.calculate_group_mode_with_logging()
        
        # 4. Apply mode change if needed
        if new_mode != old_mode:
            await self.async_set_group_mode(new_mode, old_mode)
        
        # 5. Control individual splits
        await self.control_individual_splits()
        
        _LOGGER.debug("[%s] Update cycle complete", self.group_name)
        
        # Return current state
        return {
            "mode": self.current_mode,
            "members": [m.to_dict() for m in self.members],
            "tolerance": self.tolerance,
            "hysteresis": self.hysteresis,
            "current_priority": self.current_priority,
        }

    async def calculate_group_mode_with_logging(self) -> str:
        """Apply priority logic to determine group mode with detailed logging."""
        # Sort members by priority
        priority_sorted = sorted(self.members, key=lambda m: m.current_priority)
        
        _LOGGER.debug(
            "[%s] Priority evaluation: checking members in order %s",
            self.group_name,
            ", ".join([f"{m.name}(#{m.current_priority})" for m in priority_sorted])
        )
        
        deciding_member = None
        for member in priority_sorted:
            if not member.is_available:
                _LOGGER.debug(
                    "[%s]   � %s: UNAVAILABLE (skipping)",
                    self.group_name,
                    member.name
                )
                continue
                
            if member.wants_mode_change and member.wanted_mode:
                _LOGGER.debug(
                    "[%s]   � %s: WANTS CHANGE (%.1f�F outside tolerance, wants %s)",
                    self.group_name,
                    member.name,
                    abs(member.current_temp - member.current_target_temp),
                    member.wanted_mode
                )
                deciding_member = member
                break
            else:
                _LOGGER.debug(
                    "[%s]   � %s: satisfied (%.1f�F from target, within tolerance)",
                    self.group_name,
                    member.name,
                    abs(member.current_temp - member.current_target_temp)
                )
        
        if deciding_member:
            return deciding_member.wanted_mode
            
        # No one wants change, maintain current mode
        return self.current_mode

    async def async_set_group_mode(self, new_mode: str, old_mode: str) -> None:
        """Set the group mode with detailed logging."""
        # Find the member that caused the change
        deciding_member = None
        for member in sorted(self.members, key=lambda m: m.current_priority):
            if member.is_available and member.wanted_mode == new_mode:
                deciding_member = member
                break
        
        if deciding_member:
            _LOGGER.info(
                "[%s] Mode change: %s � %s. "
                "Reason: %s (priority #%d) is %.1f�F outside tolerance "
                "(target: %.1f�F, current: %.1f�F), wants %s",
                self.group_name,
                old_mode,
                new_mode,
                deciding_member.name,
                deciding_member.current_priority,
                abs(deciding_member.current_temp - deciding_member.current_target_temp),
                deciding_member.current_target_temp,
                deciding_member.current_temp,
                new_mode
            )
        else:
            _LOGGER.info(
                "[%s] Mode change: %s � %s",
                self.group_name,
                old_mode,
                new_mode
            )
        
        self.current_mode = new_mode
        
        # Update all member modes
        for member in self.members:
            if member.is_available:
                member.mode = new_mode

    async def control_individual_splits(self) -> None:
        """Turn splits on/off based on alignment."""
        for member in self.members:
            if not member.is_available:
                continue
                
            should_run = member.should_be_on(self.current_mode)
            
            if should_run and not member.is_on:
                # Turn on
                reason = (
                    f"not aligned with target (target: {member.current_target_temp:.1f}�F, "
                    f"current: {member.current_temp:.1f}�F, delta: "
                    f"{abs(member.current_temp - member.current_target_temp):.1f}�F)"
                )
                await member.async_turn_on(reason)
                
            elif not should_run and member.is_on:
                # Turn off
                if member.is_aligned:
                    reason = (
                        f"aligned with target (target: {member.current_target_temp:.1f}�F, "
                        f"current: {member.current_temp:.1f}�F, within hysteresis {self.hysteresis:.1f}�F)"
                    )
                else:
                    # Conflicted - wants different mode
                    reason = (
                        f"wants {member.wanted_mode} but group is in {self.current_mode} mode "
                        f"(priority #{member.current_priority} not high enough to change group)"
                    )
                await member.async_turn_off(reason)
                
            elif not should_run and not member.is_on:
                # Log why it's staying off if conflicted
                if member.wanted_mode and member.wanted_mode != self.current_mode:
                    _LOGGER.debug(
                        "[%s] Staying OFF despite being %.1f�F from target. "
                        "Reason: wants %s but group is in %s mode "
                        "(priority #%d not high enough to change group)",
                        member.name,
                        abs(member.current_temp - member.current_target_temp),
                        member.wanted_mode,
                        self.current_mode,
                        member.current_priority
                    )

    async def async_set_member_target_temperature(
        self, member_id: str, temperature: float
    ) -> None:
        """Set target temperature for a specific member."""
        member = self.get_member(member_id)
        if not member:
            _LOGGER.error(
                "[%s] Member not found: %s",
                self.group_name,
                member_id
            )
            return
        
        await member.async_set_target_temperature(temperature)
        
        # Trigger immediate update
        await self.async_refresh()

    async def async_set_tolerance(self, tolerance: float) -> None:
        """Set the tolerance for the group."""
        old_tolerance = self.tolerance
        self.tolerance = tolerance
        
        _LOGGER.info(
            "[%s] Tolerance adjusted: %.1f�F � %.1f�F",
            self.group_name,
            old_tolerance,
            tolerance
        )
        
        # Trigger immediate update
        await self.async_refresh()

    async def async_set_priority_order(self, priority_order: List[str]) -> None:
        """Set the priority order for members."""
        self.current_priority = priority_order
        
        # Update member priorities
        for idx, member_id in enumerate(priority_order):
            member = self.get_member(member_id)
            if member:
                member.current_priority = idx + 1
        
        _LOGGER.info(
            "[%s] Priority order updated: %s",
            self.group_name,
            ", ".join([f"{self.get_member(mid).name}(#{idx+1})" 
                      for idx, mid in enumerate(priority_order) 
                      if self.get_member(mid)])
        )
        
        # Trigger immediate update
        await self.async_refresh()

    async def async_reset_member_to_default(self, member_id: str) -> None:
        """Reset a member's target temperature to default."""
        member = self.get_member(member_id)
        if not member:
            _LOGGER.error(
                "[%s] Member not found: %s",
                self.group_name,
                member_id
            )
            return
        
        old_temp = member.current_target_temp
        member.current_target_temp = member.default_target_temp
        
        _LOGGER.info(
            "[%s] Reset to default temperature: %.1f�F � %.1f�F",
            member.name,
            old_temp,
            member.default_target_temp
        )
        
        # Trigger immediate update
        await self.async_refresh()

    def get_average_current_temperature(self) -> float:
        """Get the average current temperature of all available members."""
        available_members = [m for m in self.members if m.is_available]
        if not available_members:
            return DEFAULT_TARGET_TEMP
        
        return sum(m.current_temp for m in available_members) / len(available_members)

    def get_average_target_temperature(self) -> float:
        """Get the average target temperature of all members."""
        if not self.members:
            return DEFAULT_TARGET_TEMP
        
        return sum(m.current_target_temp for m in self.members) / len(self.members)