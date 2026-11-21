"""Behaviour of a two-room group against fake mini split units."""

from __future__ import annotations

from datetime import datetime

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.mini_split_climate_groups.coordinator import (
    schedule_is_active,
)

from .conftest import DOMAIN, GROUP, SWITCH, call, members, refresh, setup_group

LIVING = "climate.living_room_unit"
BEDROOM = "climate.bedroom_unit"


# --- Automation on -------------------------------------------------------


async def test_outranked_room_stays_off(hass: HomeAssistant, units) -> None:
    """#1 needs cooling, #2 wants heat: group cools, #2 waits."""
    await setup_group(hass, units, living=75.6, bedroom=70.1)

    state = hass.states.get(GROUP)
    assert state.state == "cool"
    assert state.attributes["automation"] is True
    assert units.mode(LIVING) == "cool"
    assert units.mode(BEDROOM) == "off"
    m = members(hass)
    assert m["living_room"]["status"] == "driving"
    assert m["bedroom"]["status"] == "wants_heat"
    assert state.attributes["driving_member"] == "living_room"


async def test_higher_priority_flips_mode_and_running_unit_switches(
    hass: HomeAssistant, units
) -> None:
    """When #1 wants heat the group heats, and a unit still cooling stops."""
    entry = await setup_group(
        hass, units, living=70.0, bedroom=75.0, bedroom_state="cool"
    )
    # Living room (#1) is 4° below target -> heat. Bedroom is fine in heat.
    assert hass.states.get(GROUP).state == "heat"
    assert units.mode(LIVING) == "heat"
    assert units.mode(BEDROOM) == "off"

    # Bedroom gets cold too: it runs, in heat, never in cool.
    units.room("sensor.bedroom_temp", 70.0)
    await refresh(hass, entry)
    assert units.mode(BEDROOM) == "heat"


async def test_handoff_when_first_room_reaches_target(
    hass: HomeAssistant, units
) -> None:
    """#1 at target turns off, #2 keeps running and becomes the driver."""
    entry = await setup_group(
        hass, units, living=71.0, bedroom=70.0, living_state="heat"
    )
    assert units.mode(LIVING) == "heat"
    assert units.mode(BEDROOM) == "heat"

    units.room("sensor.living_room_temp", 74.0)
    await refresh(hass, entry)
    assert units.mode(LIVING) == "off"
    assert units.mode(BEDROOM) == "heat"
    m = members(hass)
    assert m["living_room"]["status"] == "at_target"
    assert m["bedroom"]["status"] == "driving"


async def test_everyone_at_target_holds(hass: HomeAssistant, units) -> None:
    """All rooms satisfied: nothing runs but automation stays on."""
    await setup_group(hass, units, living=74.0, bedroom=72.0)
    state = hass.states.get(GROUP)
    assert state.state == "cool"
    assert state.attributes["hvac_action"] == "idle"
    assert {m["status"] for m in members(hass).values()} == {"at_target"}


async def test_paused_room_stays_off(hass: HomeAssistant, units) -> None:
    """Power off in Auto pauses the room until it is resumed."""
    entry = await setup_group(hass, units, living=74.0, bedroom=75.0)
    assert units.mode(BEDROOM) == "cool"

    await call(hass, "set_member_power", member_id="bedroom", on=False)
    assert units.mode(BEDROOM) == "off"
    await refresh(hass, entry)
    assert units.mode(BEDROOM) == "off"
    assert members(hass)["bedroom"]["status"] == "paused"

    await call(hass, "set_member_power", member_id="bedroom", on=True)
    assert units.mode(BEDROOM) == "cool"


async def test_paused_room_does_not_decide_mode(hass: HomeAssistant, units) -> None:
    """A paused #1 that wants heat does not flip the group."""
    entry = await setup_group(hass, units, living=74.0, bedroom=75.0)
    await call(hass, "set_member_power", member_id="living_room", on=False)
    units.room("sensor.living_room_temp", 70.0)
    await refresh(hass, entry)
    assert hass.states.get(GROUP).state == "cool"
    assert units.mode(LIVING) == "off"


async def test_unavailable_room_is_skipped(hass: HomeAssistant, units) -> None:
    """An unavailable unit does not stop the rest of the group."""
    entry = await setup_group(hass, units, living=75.6, bedroom=70.0)
    hass.states.async_set(BEDROOM, "unavailable")
    await refresh(hass, entry)
    assert members(hass)["bedroom"]["status"] == "unavailable"
    assert units.mode(LIVING) == "cool"


# --- Automation off --------------------------------------------------------


async def test_choosing_mode_turns_automation_off(hass: HomeAssistant, units) -> None:
    """Tapping heat locks the mode, syncs running units, starts nothing."""
    entry = await setup_group(hass, units, living=75.6, bedroom=72.0)
    assert units.mode(LIVING) == "cool"

    await call(hass, "set_mode", mode="heat")
    state = hass.states.get(GROUP)
    assert state.attributes["automation"] is False
    assert hass.states.get(SWITCH).state == "off"
    assert units.mode(LIVING) == "heat"  # running unit follows the group
    assert units.mode(BEDROOM) == "off"  # idle unit is left alone

    # Nothing is switched on or off automatically any more.
    units.room("sensor.bedroom_temp", 60.0)
    await refresh(hass, entry)
    assert units.mode(BEDROOM) == "off"
    assert members(hass)["bedroom"]["status"] == "off"


async def test_manual_power_and_setpoints(hass: HomeAssistant, units) -> None:
    """With automation off, power buttons and targets go straight to units."""
    entry = await setup_group(hass, units, living=74.0, bedroom=72.0)
    await call(hass, "set_automation", enabled=False)
    # Units take over with their own thermostats at the room targets.
    assert units.setpoint(LIVING) == 74
    assert units.setpoint(BEDROOM) == 72

    await call(hass, "set_member_power", member_id="bedroom", on=True)
    assert units.mode(BEDROOM) == "cool"
    await call(hass, "set_target_temperature", member_id="bedroom", temperature=70)
    assert units.setpoint(BEDROOM) == 70

    await call(hass, "set_member_power", member_id="bedroom", on=False)
    await refresh(hass, entry)
    assert units.mode(BEDROOM) == "off"


async def test_unit_turned_on_elsewhere_is_synced(hass: HomeAssistant, units) -> None:
    """A unit switched on in the other mode is brought into the group mode."""
    entry = await setup_group(hass, units, living=74.0, bedroom=72.0)
    await call(hass, "set_mode", mode="heat")
    units.add(BEDROOM, "cool")
    await refresh(hass, entry)
    assert units.mode(BEDROOM) == "heat"


async def test_group_off_stays_off(hass: HomeAssistant, units) -> None:
    """Off from the thermostat turns everything off and keeps it off."""
    entry = await setup_group(hass, units, living=76.0, bedroom=75.0)
    assert units.mode(LIVING) == "cool"

    # (climate.set_hvac_mode is faked for the units; turn_off takes the same
    # path in the group entity as hvac_mode "off".)
    await hass.services.async_call(
        "climate", "turn_off", {"entity_id": GROUP}, blocking=True
    )
    await hass.async_block_till_done()
    assert units.mode(LIVING) == "off"
    assert units.mode(BEDROOM) == "off"
    await refresh(hass, entry)
    assert units.mode(LIVING) == "off"
    assert hass.states.get(GROUP).state == "off"

    # Turning the switch back on hands control back to automation.
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": SWITCH}, blocking=True
    )
    await hass.async_block_till_done()
    assert units.mode(LIVING) == "cool"


# --- Targets, settings, schedules -----------------------------------------


async def test_room_targets_are_independent(hass: HomeAssistant, units) -> None:
    """Changing one room's target leaves the other alone."""
    await setup_group(hass, units, living=74.0, bedroom=72.0)
    await call(hass, "set_target_temperature", member_id="bedroom", temperature=69)
    m = members(hass)
    assert m["bedroom"]["target_temp"] == 69
    assert m["living_room"]["target_temp"] == 74
    # Automation keeps the unit's own setpoint untouched.
    assert units.setpoint(BEDROOM) == 72


async def test_group_has_no_shared_target(hass: HomeAssistant, units) -> None:
    """The group entity does not offer a single target temperature."""
    await setup_group(hass, units, living=74.0, bedroom=72.0)
    assert "temperature" not in hass.states.get(GROUP).attributes or (
        hass.states.get(GROUP).attributes["temperature"] is None
    )


async def test_priority_and_schedule(hass: HomeAssistant, units) -> None:
    """An active schedule replaces the default priority order."""
    await setup_group(hass, units, living=74.0, bedroom=72.0)
    await call(hass, "set_priority_order", priority_order=["bedroom", "living_room"])
    attrs = hass.states.get(GROUP).attributes
    assert attrs["default_priority"] == ["bedroom", "living_room"]

    await call(
        hass,
        "set_schedules",
        schedules=[
            {
                "name": "All day",
                "start": "00:00",
                "end": "00:00",
                "priority_order": ["living_room"],
            }
        ],
    )
    attrs = hass.states.get(GROUP).attributes
    assert attrs["active_schedule"]["name"] == "All day"
    assert attrs["current_priority"] == ["living_room", "bedroom"]
    assert attrs["schedules"][0]["days"] == [
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
    ]


async def test_invalid_input_is_rejected(hass: HomeAssistant, units) -> None:
    """Bad member ids and times raise a validation error."""
    await setup_group(hass, units, living=74.0, bedroom=72.0)
    with pytest.raises(ServiceValidationError):
        await call(hass, "set_member_power", member_id="garage", on=True)
    with pytest.raises(ServiceValidationError):
        await call(
            hass,
            "set_schedules",
            schedules=[{"name": "Bad", "start": "25:00", "end": "07:00"}],
        )


async def test_settings_survive_restart(hass: HomeAssistant, units) -> None:
    """Automation, targets, pauses and schedules are saved and restored."""
    entry = await setup_group(hass, units, living=74.0, bedroom=72.0)
    await call(hass, "set_target_temperature", member_id="bedroom", temperature=68)
    await call(hass, "set_member_power", member_id="living_room", on=False)
    await call(hass, "set_tolerance", tolerance=2.0)
    await call(
        hass,
        "set_schedules",
        schedules=[{"name": "Night", "start": "22:00", "end": "07:00"}],
    )
    await call(hass, "set_automation", enabled=False)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    attrs = hass.states.get(GROUP).attributes
    assert attrs["automation"] is False
    assert attrs["tolerance"] == 2.0
    assert attrs["schedules"][0]["name"] == "Night"
    m = members(hass)
    assert m["bedroom"]["target_temp"] == 68
    assert m["living_room"]["paused"] is True


# --- Schedule windows -------------------------------------------------------


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        (datetime(2026, 11, 20, 23, 0), True),  # Friday night
        (datetime(2026, 11, 21, 6, 59), True),  # Saturday early: Friday's window
        (datetime(2026, 11, 21, 7, 0), False),
        (datetime(2026, 11, 21, 23, 0), False),  # Saturday not listed
        (datetime(2026, 11, 16, 6, 0), False),  # Monday early: Sunday not listed
    ],
)
def test_overnight_schedule_window(when: datetime, expected: bool) -> None:
    """Overnight windows belong to the day they start."""
    schedule = {"start": "22:00", "end": "07:00", "days": ["mon", "tue", "fri"]}
    assert schedule_is_active(schedule, when) is expected


async def test_service_descriptions_match(hass: HomeAssistant, units) -> None:
    """services.yaml and translations describe every registered service."""
    import json
    from pathlib import Path

    from homeassistant.util.yaml import load_yaml

    await setup_group(hass, units, living=74.0, bedroom=72.0)
    base = Path(__file__).parent.parent / "custom_components" / DOMAIN
    described = set(load_yaml(str(base / "services.yaml")))
    translated = json.loads((base / "translations" / "en.json").read_text())
    registered = set(hass.services.async_services()[DOMAIN])
    assert described == registered
    assert set(translated["services"]) == registered
    for name, service in translated["services"].items():
        fields = set(load_yaml(str(base / "services.yaml"))[name]["fields"])
        assert set(service["fields"]) == fields, name
