"""Automation switch for Mini Split Climate Groups.

On: the priority order decides the group mode and turns rooms on and off.
Off: you choose the mode and power; the group only keeps units in sync.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .climate import group_device_info
from .const import DOMAIN
from .coordinator import PriorityClimateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the automation switch."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities([AutomationSwitch(coordinator, config_entry)])


class AutomationSwitch(CoordinatorEntity, SwitchEntity):
    """Turns priority automation on or off for a group."""

    _attr_icon = "mdi:auto-mode"

    coordinator: PriorityClimateCoordinator

    def __init__(
        self, coordinator: PriorityClimateCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{config_entry.entry_id}_automation"
        self._attr_name = f"{config_entry.title} Automation"
        self._attr_device_info = group_device_info(config_entry)

    @property
    def is_on(self) -> bool:
        """Whether automation is on."""
        return self.coordinator.automation

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn automation on."""
        await self.coordinator.async_set_automation(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn automation off."""
        await self.coordinator.async_set_automation(False)
