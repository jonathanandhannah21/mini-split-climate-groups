"""Climate platform for Mini Split Climate Groups.

The group entity reports the group mode (heat or cool), or off when
automation is off and every unit is off. Room targets are set per room
(see the `set_target_temperature` service), so the group has no single
target temperature of its own.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ACTIVE_SCHEDULE,
    ATTR_AUTOMATION,
    ATTR_CURRENT_PRIORITY,
    ATTR_DEFAULT_PRIORITY,
    ATTR_DRIVING_MEMBER,
    ATTR_GROUP_MODE,
    ATTR_MEMBERS,
    ATTR_SCHEDULES,
    DOMAIN,
    MIN_TARGET_TEMP,
    MAX_TARGET_TEMP,
    MODE_HEAT,
    MODES,
    UPDATE_INTERVAL,
)
from .coordinator import PriorityClimateCoordinator

_LOGGER = logging.getLogger(__name__)


def group_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Device shared by the group's entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Mini Split Climate Groups",
        model="Priority Climate Group",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the group climate entity."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities([PriorityClimateGroup(coordinator, config_entry)])


class PriorityClimateGroup(CoordinatorEntity, ClimateEntity, RestoreEntity):
    """A group of mini splits that share one heat/cool mode."""

    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = MIN_TARGET_TEMP
    _attr_max_temp = MAX_TARGET_TEMP
    _attr_target_temperature_step = 1
    _attr_icon = "mdi:hvac"

    coordinator: PriorityClimateCoordinator

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
        self._attr_device_info = group_device_info(config_entry)

    async def async_added_to_hass(self) -> None:
        """Migrate state saved by older versions, then start listening."""
        await super().async_added_to_hass()

        if self.coordinator.restored_from_store:
            return

        last_state = await self.async_get_last_state()
        if not last_state:
            return

        coordinator = self.coordinator
        if last_state.state in MODES:
            coordinator.current_mode = last_state.state
        for member_data in last_state.attributes.get(ATTR_MEMBERS, []) or []:
            member = coordinator.get_member(member_data.get("id"))
            target = member_data.get("target_temp")
            if member and target:
                member.current_target_temp = float(target)
        priority = last_state.attributes.get(ATTR_CURRENT_PRIORITY)
        if isinstance(priority, list):
            coordinator.default_priority = coordinator.sanitize_order(priority)
        coordinator.async_save()
        _LOGGER.info("[%s] Migrated settings from previous state", self.name)
        await coordinator.async_request_refresh()

    @property
    def hvac_mode(self) -> HVACMode:
        """Group mode, or off when automation is off and nothing runs."""
        coordinator = self.coordinator
        if not coordinator.automation and not any(
            m.is_on for m in coordinator.members if m.is_available
        ):
            return HVACMode.OFF
        return (
            HVACMode.HEAT if coordinator.current_mode == MODE_HEAT else (HVACMode.COOL)
        )

    @property
    def hvac_action(self) -> HVACAction:
        """What the group is doing right now."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if any(m.is_on for m in self.coordinator.members if m.is_available):
            return (
                HVACAction.HEATING
                if self.coordinator.current_mode == MODE_HEAT
                else HVACAction.COOLING
            )
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Average room temperature."""
        value = self.coordinator.get_average_current_temperature()
        return round(value, 1) if value is not None else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Off turns everything off; heat/cool sets the mode by hand."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_turn_group_off()
        elif hvac_mode in (HVACMode.COOL, HVACMode.HEAT):
            await self.coordinator.async_set_mode(
                str(hvac_mode), turn_on_if_all_off=True
            )
        else:
            _LOGGER.warning("[%s] Unsupported HVAC mode: %s", self.name, hvac_mode)

    async def async_turn_on(self) -> None:
        """Turning the group on hands control back to automation."""
        await self.coordinator.async_set_automation(True)

    async def async_turn_off(self) -> None:
        """Turn every unit off and stop automation."""
        await self.coordinator.async_turn_group_off()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Everything the card needs."""
        coordinator = self.coordinator
        active = coordinator.active_schedule
        return {
            ATTR_GROUP_MODE: coordinator.current_mode,
            ATTR_AUTOMATION: coordinator.automation,
            ATTR_MEMBERS: [m.to_dict() for m in coordinator.members],
            ATTR_DRIVING_MEMBER: coordinator.driving_member_id,
            "tolerance": coordinator.tolerance,
            "hysteresis": coordinator.hysteresis,
            ATTR_CURRENT_PRIORITY: coordinator.current_priority,
            ATTR_DEFAULT_PRIORITY: coordinator.default_priority,
            ATTR_SCHEDULES: coordinator.schedules,
            ATTR_ACTIVE_SCHEDULE: (
                {k: active[k] for k in ("id", "name", "start", "end")}
                if active
                else None
            ),
            "update_interval": UPDATE_INTERVAL,
        }

    @property
    def available(self) -> bool:
        """Available while at least one unit is."""
        return any(m.is_available for m in self.coordinator.members)
