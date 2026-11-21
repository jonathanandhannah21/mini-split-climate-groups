"""Coordinator for Mini Split Climate Groups.

The group always has a single mode (heat or cool) that every running unit
follows. On top of that, automation can be on or off:

* Automation on: the priority order (optionally replaced by a schedule)
  decides the group mode, and each room's unit is switched on or off to
  reach that room's own target. A room can be paused, which leaves it off
  and out of the decision until it is resumed.
* Automation off: nothing is switched on or off automatically. The group
  only keeps every running unit in the group mode, and each unit's own
  thermostat holds its room at the room's target.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.components.climate import HVACMode
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_HYSTERESIS,
    DEFAULT_TARGET_TEMP,
    DEFAULT_TOLERANCE,
    MAX_TARGET_TEMP,
    MIN_TARGET_TEMP,
    MODE_COOL,
    MODE_HEAT,
    MODES,
    STATUS_AT_TARGET,
    STATUS_DRIVING,
    STATUS_IDLE,
    STATUS_MANUAL_OFF,
    STATUS_MANUAL_ON,
    STATUS_PAUSED,
    STATUS_RUNNING,
    STATUS_UNAVAILABLE,
    STATUS_WANTS_COOL,
    STATUS_WANTS_HEAT,
    UPDATE_INTERVAL,
    WEEKDAYS,
)

_LOGGER = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(:[0-5]\d)?$")


def parse_time(value: str) -> time:
    """Parse an HH:MM (or HH:MM:SS) string."""
    match = _TIME_RE.match(str(value).strip())
    if not match:
        raise ValueError(f"Invalid time: {value!r} (expected HH:MM)")
    return time(int(match.group(1)), int(match.group(2)))


def schedule_is_active(schedule: Dict[str, Any], now: datetime) -> bool:
    """Return True if a schedule applies at the given local time.

    A window whose end is earlier than its start runs overnight: it belongs
    to the day it starts on, so a Friday 22:00-07:00 window also covers
    Saturday until 07:00.
    """
    days = schedule.get("days") or list(WEEKDAYS)
    start = parse_time(schedule["start"])
    end = parse_time(schedule["end"])
    current = now.time().replace(second=0, microsecond=0)
    today = WEEKDAYS[now.weekday()]
    yesterday = WEEKDAYS[(now.weekday() - 1) % 7]

    if start == end:
        return today in days
    if start < end:
        return today in days and start <= current < end
    return (today in days and current >= start) or (yesterday in days and current < end)


class PriorityClimateMember:
    """A room in a climate group: one mini split unit.

    Decisions use the unit's own temperature reading, unless the room has a
    separate temperature sensor configured (optional), in which case that
    sensor is used instead.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        member_id: str,
        name: str,
        climate_entity_id: str,
        temp_sensor_id: Optional[str],
        default_target_temp: float,
    ) -> None:
        """Initialize the member."""
        self.hass = hass
        self.member_id = member_id
        self.name = name
        self.climate_entity_id = climate_entity_id
        self.temp_sensor_id = temp_sensor_id or None
        self.default_target_temp = float(default_target_temp)

        # Runtime state
        self.current_target_temp = float(default_target_temp)
        self.current_temp: Optional[float] = None
        self.is_on = False
        self.unit_mode: Optional[str] = None
        self.is_aligned = True
        self.wanted_mode: Optional[str] = None
        self.wants_mode_change = False
        self.current_priority = 1
        self.is_available = True
        self.supported_modes: List[str] = []
        self.paused = False
        self.status = STATUS_IDLE
        self._warned_missing_modes = False
        self._warned_no_unit_temp = False

    @property
    def temp_source(self) -> str:
        """Where decisions read the room temperature from."""
        return "sensor" if self.temp_sensor_id else "unit"

    def update_current_temp(self) -> bool:
        """Update the room temperature from its sensor or the unit."""
        if not self.temp_sensor_id:
            return self._update_temp_from_unit()

        temp_state = self.hass.states.get(self.temp_sensor_id)

        if temp_state is None:
            _LOGGER.error(
                "[%s] Temperature sensor not found: %s",
                self.name,
                self.temp_sensor_id,
            )
            return False

        if temp_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning(
                "[%s] Temperature sensor unavailable (state: %s). "
                "Using last known value %s.",
                self.name,
                temp_state.state,
                self.current_temp,
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
                err,
            )
            return False

    def _update_temp_from_unit(self) -> bool:
        """Use the unit's own current_temperature reading."""
        climate_state = self.hass.states.get(self.climate_entity_id)
        if climate_state is None or climate_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            return False

        value = climate_state.attributes.get("current_temperature")
        if value is None:
            if self._warned_no_unit_temp:
                return False
            self._warned_no_unit_temp = True
            _LOGGER.warning(
                "[%s] %s reports no current temperature. "
                "Add a temperature sensor for this room in the group's options.",
                self.name,
                self.climate_entity_id,
            )
            return False
        self._warned_no_unit_temp = False
        try:
            self.current_temp = float(value)
            return True
        except (ValueError, TypeError):
            _LOGGER.error(
                "[%s] Invalid current temperature '%s' from %s",
                self.name,
                value,
                self.climate_entity_id,
            )
            return False

    def update_climate_state(self) -> bool:
        """Update on/off state and mode from the unit's climate entity."""
        climate_state = self.hass.states.get(self.climate_entity_id)

        if climate_state is None:
            _LOGGER.error(
                "[%s] Climate entity not found: %s",
                self.name,
                self.climate_entity_id,
            )
            self.is_available = False
            return False

        if climate_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            _LOGGER.warning(
                "[%s] Climate entity unavailable (state: %s). "
                "Skipping control this cycle. "
                "If persistent, try reloading the Kumo integration.",
                self.name,
                climate_state.state,
            )
            self.is_available = False
            return False

        self.is_available = True
        state = str(climate_state.state).lower()
        self.is_on = state in MODES
        self.unit_mode = state if self.is_on else None
        self.supported_modes = list(climate_state.attributes.get("hvac_modes", []))
        return True

    def validate_hvac_modes(self) -> bool:
        """Check the unit supports heat and cool (warns once)."""
        missing = [m for m in MODES if m not in self.supported_modes]
        if not missing:
            self._warned_missing_modes = False
            return True

        if not self._warned_missing_modes:
            self._warned_missing_modes = True
            _LOGGER.warning(
                "[%s] Climate entity is missing HVAC modes: %s. "
                "Supported modes: %s. This is a known Kumo bug. Fix: "
                "Settings > Devices & Services > Devices > '%s' > Edit, "
                "and enable Cool and Heat. Only available modes will be used.",
                self.name,
                ", ".join(missing),
                ", ".join(self.supported_modes) or "none",
                self.name,
            )
        return False

    def evaluate(self, group_mode: str, tolerance: float, hysteresis: float) -> None:
        """Work out what this room wants and whether it is at target.

        `wanted_mode` is the mode the room asks for once it drifts outside
        the tolerance window. `is_aligned` says whether the room is
        satisfied in the current group mode.
        """
        self.wanted_mode = None
        self.wants_mode_change = False
        self.is_aligned = True

        if self.current_temp is None:
            return

        delta = self.current_temp - self.current_target_temp
        if delta > tolerance:
            self.wanted_mode = MODE_COOL
        elif delta < -tolerance:
            self.wanted_mode = MODE_HEAT

        self.wants_mode_change = (
            self.wanted_mode is not None and self.wanted_mode != group_mode
        )

        if group_mode == MODE_COOL:
            self.is_aligned = self.current_temp <= (
                self.current_target_temp + hysteresis
            )
        else:
            self.is_aligned = self.current_temp >= (
                self.current_target_temp - hysteresis
            )

    @property
    def needs_running(self) -> bool:
        """True when the room needs its unit running in the group mode."""
        return self.is_available and not self.is_aligned

    async def async_run_in_mode(self, mode: str, reason: str = "") -> bool:
        """Turn the unit on in the given mode (or switch a running unit)."""
        if not self.is_available:
            return False
        if self.is_on and self.unit_mode == mode:
            return True

        target_mode = HVACMode.HEAT if mode == MODE_HEAT else HVACMode.COOL
        if self.supported_modes and target_mode not in self.supported_modes:
            _LOGGER.warning(
                "[%s] Cannot set mode to %s: not supported (available: %s)",
                self.name,
                mode,
                ", ".join(self.supported_modes),
            )
            return False

        try:
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": self.climate_entity_id, "hvac_mode": target_mode},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - keep the loop running
            _LOGGER.error("[%s] Failed to set mode to %s: %s", self.name, mode, err)
            return False

        was_on = self.is_on
        self.is_on = True
        self.unit_mode = mode
        _LOGGER.info(
            "[%s] %s (%s). Reason: %s",
            self.name,
            "Switched mode" if was_on else "Turned ON",
            mode,
            reason or "requested",
        )
        return True

    async def async_turn_off(self, reason: str = "") -> bool:
        """Turn the unit off."""
        if not self.is_available or not self.is_on:
            return False

        try:
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": self.climate_entity_id, "hvac_mode": HVACMode.OFF},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - keep the loop running
            _LOGGER.error("[%s] Failed to turn off: %s", self.name, err)
            return False

        self.is_on = False
        self.unit_mode = None
        _LOGGER.info("[%s] Turned OFF. Reason: %s", self.name, reason or "requested")
        return True

    async def async_push_setpoint(self) -> None:
        """Copy the room's target to the unit's own thermostat."""
        if not self.is_available:
            return
        try:
            await self.hass.services.async_call(
                "climate",
                "set_temperature",
                {
                    "entity_id": self.climate_entity_id,
                    "temperature": self.current_target_temp,
                },
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 - not every unit accepts it
            _LOGGER.warning(
                "[%s] Could not set unit setpoint to %.1f°F: %s",
                self.name,
                self.current_target_temp,
                err,
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert member to a dictionary for state attributes."""
        return {
            "id": self.member_id,
            "name": self.name,
            "climate_entity": self.climate_entity_id,
            "temp_sensor": self.temp_sensor_id,
            "temp_source": self.temp_source,
            "current_temp": (
                round(self.current_temp, 1) if self.current_temp is not None else None
            ),
            "target_temp": round(self.current_target_temp, 1),
            "default_target_temp": round(self.default_target_temp, 1),
            "is_on": self.is_on,
            "mode": self.unit_mode,
            "is_aligned": self.is_aligned,
            "wants_change": self.wants_mode_change,
            "wanted_mode": self.wanted_mode,
            "priority": self.current_priority,
            "is_available": self.is_available,
            "paused": self.paused,
            "status": self.status,
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
        store: Optional[Store] = None,
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
        self.tolerance = float(tolerance)
        self.hysteresis = float(hysteresis)
        self.current_mode = MODE_COOL
        self.automation = True
        self.default_priority: List[str] = [m.member_id for m in members]
        self.current_priority: List[str] = list(self.default_priority)
        self.schedules: List[Dict[str, Any]] = []
        self.active_schedule: Optional[Dict[str, Any]] = None
        self.driving_member_id: Optional[str] = None
        self.restored_from_store = False
        self._store = store

        self._apply_priority(self.default_priority)

        _LOGGER.info(
            "[%s] Initialized with %d members. Priority order: %s. "
            "Tolerance: %.1f°F, Hysteresis: %.1f°F.",
            self.group_name,
            len(self.members),
            ", ".join(m.name for m in self.members),
            self.tolerance,
            self.hysteresis,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_member(self, member_id: str) -> Optional[PriorityClimateMember]:
        """Get member by ID."""
        for member in self.members:
            if member.member_id == member_id:
                return member
        return None

    def sanitize_order(self, order: List[str]) -> List[str]:
        """Keep known ids once each; append any members the order left out."""
        known = {m.member_id for m in self.members}
        result: List[str] = []
        for member_id in order or []:
            if member_id in known and member_id not in result:
                result.append(member_id)
        for member in self.members:
            if member.member_id not in result:
                result.append(member.member_id)
        return result

    def _apply_priority(self, order: List[str]) -> None:
        """Make `order` the effective priority order."""
        self.current_priority = self.sanitize_order(order)
        for idx, member_id in enumerate(self.current_priority):
            member = self.get_member(member_id)
            if member:
                member.current_priority = idx + 1

    def _by_priority(self) -> List[PriorityClimateMember]:
        return sorted(self.members, key=lambda m: m.current_priority)

    def _normalize_schedule(self, raw: Dict[str, Any], index: int) -> Dict[str, Any]:
        """Validate one schedule and fill in defaults."""
        name = str(raw.get("name") or f"Schedule {index + 1}").strip()
        start = parse_time(raw.get("start", "22:00")).strftime("%H:%M")
        end = parse_time(raw.get("end", "07:00")).strftime("%H:%M")
        days = [
            d
            for d in WEEKDAYS
            if d in [str(x).lower()[:3] for x in raw.get("days", [])]
        ] or list(WEEKDAYS)
        schedule_id = str(raw.get("id") or "").strip()
        if not schedule_id:
            slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "schedule"
            schedule_id = f"{slug}_{index + 1}"
        return {
            "id": schedule_id,
            "name": name,
            "start": start,
            "end": end,
            "days": days,
            "priority_order": self.sanitize_order(raw.get("priority_order", [])),
        }

    def _resolve_active_schedule(self, now: datetime) -> Optional[Dict[str, Any]]:
        for schedule in self.schedules:
            try:
                if schedule_is_active(schedule, now):
                    return schedule
            except (KeyError, ValueError) as err:
                _LOGGER.warning(
                    "[%s] Ignoring invalid schedule %s: %s",
                    self.group_name,
                    schedule.get("name"),
                    err,
                )
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Load saved settings and runtime choices."""
        if self._store is None:
            return
        data = await self._store.async_load()
        if not data:
            return

        self.restored_from_store = True
        self.automation = bool(data.get("automation", True))
        if data.get("mode") in MODES:
            self.current_mode = data["mode"]
        self.tolerance = float(data.get("tolerance", self.tolerance))
        self.hysteresis = float(data.get("hysteresis", self.hysteresis))
        self.default_priority = self.sanitize_order(
            data.get("default_priority", self.default_priority)
        )
        schedules = []
        for idx, raw in enumerate(data.get("schedules", [])):
            try:
                schedules.append(self._normalize_schedule(raw, idx))
            except ValueError as err:
                _LOGGER.warning(
                    "[%s] Dropping saved schedule: %s", self.group_name, err
                )
        self.schedules = schedules
        for member_id, saved in (data.get("members") or {}).items():
            member = self.get_member(member_id)
            if not member:
                continue
            if saved.get("target") is not None:
                member.current_target_temp = float(saved["target"])
            member.paused = bool(saved.get("paused", False))
        self._apply_priority(self.default_priority)
        _LOGGER.info(
            "[%s] Restored settings: automation=%s, mode=%s, %d schedule(s)",
            self.group_name,
            self.automation,
            self.current_mode,
            len(self.schedules),
        )

    def _data_to_save(self) -> Dict[str, Any]:
        return {
            "automation": self.automation,
            "mode": self.current_mode,
            "tolerance": self.tolerance,
            "hysteresis": self.hysteresis,
            "default_priority": self.default_priority,
            "schedules": self.schedules,
            "members": {
                m.member_id: {"target": m.current_target_temp, "paused": m.paused}
                for m in self.members
            },
        }

    def async_save(self) -> None:
        """Schedule a save of settings."""
        if self._store is not None:
            self._store.async_delay_save(self._data_to_save, 1)

    async def async_flush(self) -> None:
        """Write settings now (used when unloading)."""
        if self._store is not None:
            await self._store.async_save(self._data_to_save())

    # ------------------------------------------------------------------
    # Control loop
    # ------------------------------------------------------------------

    async def async_initialize(self) -> None:
        """Read current unit state; adopt the mode of any running unit."""
        for member in self.members:
            member.update_current_temp()
            if member.update_climate_state():
                member.validate_hvac_modes()

        running = [m for m in self._by_priority() if m.is_on and m.unit_mode]
        if running and running[0].unit_mode != self.current_mode:
            _LOGGER.info(
                "[%s] Detected running mode from %s: %s",
                self.group_name,
                running[0].name,
                running[0].unit_mode,
            )
            self.current_mode = running[0].unit_mode

    def _evaluate_members(self) -> None:
        for member in self.members:
            if member.is_available:
                member.evaluate(self.current_mode, self.tolerance, self.hysteresis)

    def _decide_mode(self) -> str:
        """The highest-priority room outside its tolerance decides the mode.

        A room that is outside tolerance in the direction of the current
        mode keeps that mode, so lower-priority rooms cannot flip it.
        """
        for member in self._by_priority():
            if not member.is_available or member.paused:
                continue
            if member.wanted_mode:
                _LOGGER.debug(
                    "[%s] %s (#%d) wants %s",
                    self.group_name,
                    member.name,
                    member.current_priority,
                    member.wanted_mode,
                )
                return member.wanted_mode
        return self.current_mode

    async def _async_change_mode(self, new_mode: str, reason: str) -> None:
        old_mode = self.current_mode
        self.current_mode = new_mode
        _LOGGER.info(
            "[%s] Mode change: %s -> %s. Reason: %s",
            self.group_name,
            old_mode,
            new_mode,
            reason,
        )
        self.async_save()

    async def _async_control_members(self) -> None:
        """Automation on: run each room only while it needs the group mode."""
        mode = self.current_mode
        for member in self.members:
            if not member.is_available:
                continue

            if member.paused:
                # Paused rooms stay out of the decision, but a unit that was
                # switched on elsewhere must never fight the group mode.
                if member.is_on and member.unit_mode != mode:
                    await member.async_run_in_mode(mode, "keep paused room in sync")
                continue

            if member.needs_running:
                if not member.is_on or member.unit_mode != mode:
                    await member.async_run_in_mode(
                        mode,
                        f"{member.current_temp}°F vs target "
                        f"{member.current_target_temp}°F",
                    )
            elif member.is_on:
                if member.wanted_mode and member.wanted_mode != mode:
                    reason = (
                        f"wants {member.wanted_mode} but group is in {mode} "
                        f"(priority #{member.current_priority} is outranked)"
                    )
                else:
                    reason = f"reached target {member.current_target_temp}°F"
                await member.async_turn_off(reason)

    async def _async_sync_running_units(self) -> None:
        """Automation off: only keep running units in the group mode."""
        for member in self.members:
            if (
                member.is_available
                and member.is_on
                and member.unit_mode != (self.current_mode)
            ):
                await member.async_run_in_mode(
                    self.current_mode, "keep in sync with group mode"
                )

    def _update_statuses(self) -> None:
        self.driving_member_id = None
        if self.automation:
            for member in self._by_priority():
                if member.is_available and not member.paused and member.needs_running:
                    self.driving_member_id = member.member_id
                    break

        for member in self.members:
            if not member.is_available:
                member.status = STATUS_UNAVAILABLE
            elif not self.automation:
                member.status = STATUS_MANUAL_ON if member.is_on else STATUS_MANUAL_OFF
            elif member.paused:
                member.status = STATUS_PAUSED
            elif member.member_id == self.driving_member_id:
                member.status = STATUS_DRIVING
            elif member.wants_mode_change:
                member.status = (
                    STATUS_WANTS_HEAT
                    if member.wanted_mode == MODE_HEAT
                    else STATUS_WANTS_COOL
                )
            elif member.is_on:
                member.status = STATUS_RUNNING
            elif member.is_aligned:
                member.status = STATUS_AT_TARGET
            else:
                member.status = STATUS_IDLE

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "mode": self.current_mode,
            "automation": self.automation,
            "members": [m.to_dict() for m in self.members],
            "tolerance": self.tolerance,
            "hysteresis": self.hysteresis,
            "current_priority": self.current_priority,
            "driving_member": self.driving_member_id,
        }

    async def _async_update_data(self) -> Dict[str, Any]:
        """Main control loop - runs every UPDATE_INTERVAL seconds."""
        schedule = self._resolve_active_schedule(dt_util.now())
        old_id = self.active_schedule["id"] if self.active_schedule else None
        new_id = schedule["id"] if schedule else None
        if new_id != old_id:
            _LOGGER.info(
                "[%s] Priority order now from %s",
                self.group_name,
                f"schedule '{schedule['name']}'" if schedule else "the default",
            )
        self.active_schedule = schedule
        self._apply_priority(
            schedule["priority_order"] if schedule else self.default_priority
        )

        for member in self.members:
            member.update_current_temp()
            if member.update_climate_state():
                member.validate_hvac_modes()

        self._evaluate_members()

        if self.automation:
            new_mode = self._decide_mode()
            if new_mode != self.current_mode:
                decider = next(
                    (
                        m
                        for m in self._by_priority()
                        if m.is_available and not m.paused and m.wanted_mode == new_mode
                    ),
                    None,
                )
                reason = (
                    f"{decider.name} (priority #{decider.current_priority}) is "
                    f"{abs(decider.current_temp - decider.current_target_temp):.1f}°F "
                    f"from target"
                    if decider and decider.current_temp is not None
                    else "priority evaluation"
                )
                await self._async_change_mode(new_mode, reason)
                self._evaluate_members()
            await self._async_control_members()
        else:
            await self._async_sync_running_units()

        self._update_statuses()
        return self._snapshot()

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    async def async_set_automation(self, enabled: bool) -> None:
        """Turn automation on or off."""
        if self.automation == enabled:
            return
        self.automation = enabled
        _LOGGER.info(
            "[%s] Automation turned %s",
            self.group_name,
            "ON" if enabled else "OFF",
        )
        if not enabled:
            # Units now hold their rooms with their own thermostats.
            for member in self.members:
                await member.async_push_setpoint()
        self.async_save()
        await self.async_refresh()

    async def async_set_mode(self, mode: str, turn_on_if_all_off: bool = False) -> None:
        """Choose the group mode by hand. This turns automation off."""
        if mode not in MODES:
            raise ValueError(f"Unsupported mode: {mode}")
        if self.automation:
            self.automation = False
            _LOGGER.info(
                "[%s] Automation turned OFF (mode chosen by hand)", self.group_name
            )
            for member in self.members:
                await member.async_push_setpoint()
        if mode != self.current_mode:
            await self._async_change_mode(mode, "chosen by user")
        await self._async_sync_running_units()
        if turn_on_if_all_off and not any(m.is_on for m in self.members):
            for member in self.members:
                await member.async_run_in_mode(mode, "group turned on")
        self.async_save()
        await self.async_refresh()

    async def async_turn_group_off(self) -> None:
        """Turn automation off and every unit off."""
        self.automation = False
        _LOGGER.info("[%s] Group turned OFF by user", self.group_name)
        for member in self.members:
            await member.async_turn_off("group turned off by user")
        self.async_save()
        await self.async_refresh()

    async def async_set_member_power(self, member_id: str, on: bool) -> None:
        """Power button for one room.

        With automation on this pauses or resumes the room. With automation
        off it simply turns the unit on (in the group mode) or off.
        """
        member = self._require_member(member_id)
        if self.automation:
            member.paused = not on
            _LOGGER.info(
                "[%s] %s by user",
                member.name,
                "Resumed" if on else "Paused",
            )
            if not on:
                await member.async_turn_off("paused by user")
        elif on:
            await member.async_push_setpoint()
            await member.async_run_in_mode(self.current_mode, "turned on by user")
        else:
            await member.async_turn_off("turned off by user")
        self.async_save()
        await self.async_refresh()

    async def async_set_member_target_temperature(
        self, member_id: str, temperature: float
    ) -> None:
        """Set one room's target."""
        member = self._require_member(member_id)
        temperature = max(MIN_TARGET_TEMP, min(MAX_TARGET_TEMP, float(temperature)))
        old = member.current_target_temp
        member.current_target_temp = temperature
        _LOGGER.info(
            "[%s] Target changed: %.1f°F -> %.1f°F", member.name, old, temperature
        )
        if not self.automation:
            await member.async_push_setpoint()
        self.async_save()
        await self.async_refresh()

    async def async_reset_member_to_default(self, member_id: str) -> None:
        """Reset a room's target to its configured default."""
        member = self._require_member(member_id)
        await self.async_set_member_target_temperature(
            member_id, member.default_target_temp
        )

    async def async_set_tolerance(self, tolerance: float) -> None:
        """Set how far a room may drift before it asks for the other mode."""
        self.tolerance = float(tolerance)
        _LOGGER.info("[%s] Tolerance set to %.1f°F", self.group_name, self.tolerance)
        self.async_save()
        await self.async_refresh()

    async def async_set_hysteresis(self, hysteresis: float) -> None:
        """Set the buffer used to decide a room is back on target."""
        self.hysteresis = float(hysteresis)
        _LOGGER.info("[%s] Hysteresis set to %.1f°F", self.group_name, self.hysteresis)
        self.async_save()
        await self.async_refresh()

    async def async_set_priority_order(self, priority_order: List[str]) -> None:
        """Set the default priority order (used when no schedule is active)."""
        self.default_priority = self.sanitize_order(priority_order)
        _LOGGER.info(
            "[%s] Default priority order: %s",
            self.group_name,
            ", ".join(
                f"{self.get_member(mid).name}(#{idx + 1})"
                for idx, mid in enumerate(self.default_priority)
            ),
        )
        self.async_save()
        await self.async_refresh()

    async def async_set_schedules(self, schedules: List[Dict[str, Any]]) -> None:
        """Replace all priority schedules."""
        normalized = [
            self._normalize_schedule(raw, idx) for idx, raw in enumerate(schedules)
        ]
        ids = [s["id"] for s in normalized]
        if len(ids) != len(set(ids)):
            raise ValueError("Schedule ids must be unique")
        self.schedules = normalized
        _LOGGER.info(
            "[%s] Schedules updated: %s",
            self.group_name,
            ", ".join(f"{s['name']} {s['start']}-{s['end']}" for s in normalized)
            or "none",
        )
        self.async_save()
        await self.async_refresh()

    def _require_member(self, member_id: str) -> PriorityClimateMember:
        member = self.get_member(member_id)
        if member is None:
            raise ValueError(f"Unknown member id: {member_id}")
        return member

    # ------------------------------------------------------------------
    # Aggregates for the group entity
    # ------------------------------------------------------------------

    def get_average_current_temperature(self) -> Optional[float]:
        """Average current temperature of available rooms."""
        temps = [
            m.current_temp
            for m in self.members
            if m.is_available and m.current_temp is not None
        ]
        if not temps:
            return None
        return sum(temps) / len(temps)

    def get_average_target_temperature(self) -> float:
        """Average target temperature of all rooms."""
        if not self.members:
            return float(DEFAULT_TARGET_TEMP)
        return sum(m.current_target_temp for m in self.members) / len(self.members)
