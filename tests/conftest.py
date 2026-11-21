"""Shared fixtures: fake mini split units and a two-room group."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "mini_split_climate_groups"
GROUP = "climate.living_area"
SWITCH = "switch.living_area_automation"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load integrations from custom_components."""
    yield


class FakeUnits:
    """Fake mini split climate entities driven through climate services."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def add(self, entity_id: str, state: str = "off", temp: float = 72) -> None:
        self.hass.states.async_set(
            entity_id,
            state,
            {"hvac_modes": ["off", "cool", "heat"], "temperature": temp},
        )

    def room(self, sensor_id: str, temp: float) -> None:
        self.hass.states.async_set(
            sensor_id, str(temp), {"device_class": "temperature"}
        )

    def mode(self, entity_id: str) -> str:
        return self.hass.states.get(entity_id).state

    async def _set_hvac_mode(self, call: ServiceCall) -> None:
        for entity_id in _ids(call):
            self.calls.append(("set_hvac_mode", dict(call.data)))
            old = self.hass.states.get(entity_id)
            self.hass.states.async_set(
                entity_id, call.data["hvac_mode"], dict(old.attributes)
            )

    async def _set_temperature(self, call: ServiceCall) -> None:
        for entity_id in _ids(call):
            self.calls.append(("set_temperature", dict(call.data)))
            old = self.hass.states.get(entity_id)
            attrs = dict(old.attributes)
            attrs["temperature"] = call.data["temperature"]
            self.hass.states.async_set(entity_id, old.state, attrs)

    def setpoint(self, entity_id: str) -> float:
        return self.hass.states.get(entity_id).attributes["temperature"]


def _ids(call: ServiceCall) -> list[str]:
    ids = call.data["entity_id"]
    return [ids] if isinstance(ids, str) else list(ids)


@pytest.fixture
async def units(hass: HomeAssistant) -> FakeUnits:
    """Fake units; the climate component's services are replaced by fakes."""
    assert await async_setup_component(hass, "climate", {})
    fake = FakeUnits(hass)
    hass.services.async_register("climate", "set_hvac_mode", fake._set_hvac_mode)
    hass.services.async_register("climate", "set_temperature", fake._set_temperature)
    return fake


def make_entry(**extra: Any) -> MockConfigEntry:
    """Living Area: living_room (#1, 74°) and bedroom (#2, 72°)."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Living Area",
        data={
            "name": "Living Area",
            "tolerance": 1.5,
            "hysteresis": 0.1,
            "members": [
                {
                    "id": "living_room",
                    "name": "Living Room",
                    "climate_entity": "climate.living_room_unit",
                    "temp_sensor": "sensor.living_room_temp",
                    "target_temp": 74,
                },
                {
                    "id": "bedroom",
                    "name": "Bedroom",
                    "climate_entity": "climate.bedroom_unit",
                    "temp_sensor": "sensor.bedroom_temp",
                    "target_temp": 72,
                },
            ],
            **extra,
        },
    )


async def setup_group(
    hass: HomeAssistant,
    units: FakeUnits,
    living: float,
    bedroom: float,
    living_state: str = "off",
    bedroom_state: str = "off",
    entry: MockConfigEntry | None = None,
) -> MockConfigEntry:
    """Create room temps and unit states, then set up the group."""
    units.add("climate.living_room_unit", living_state)
    units.add("climate.bedroom_unit", bedroom_state)
    units.room("sensor.living_room_temp", living)
    units.room("sensor.bedroom_temp", bedroom)
    entry = entry or make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def members(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Group member attributes keyed by id."""
    return {m["id"]: m for m in hass.states.get(GROUP).attributes["members"]}


async def call(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call one of the integration's services on the group."""
    await hass.services.async_call(
        DOMAIN, service, {"entity_id": GROUP, **data}, blocking=True
    )
    await hass.async_block_till_done()


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Run one control cycle."""
    await hass.data[DOMAIN][entry.entry_id]["coordinator"].async_refresh()
    await hass.async_block_till_done()
