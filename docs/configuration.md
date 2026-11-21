# Configuration Guide

## Adding a Climate Group

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "Mini Split Climate Groups"
4. Follow the configuration wizard: name the group, then add each room (its
   mini split climate entity, a default target, and optionally a separate
   temperature sensor)

### Room temperature source

By default, each room's decisions use the unit's own temperature reading
(the climate entity's current temperature). For a room where that reading is
misleading (for example a unit mounted high on a wall), pick a separate
temperature sensor and decisions for that room use the sensor instead.

You can set or clear a room's sensor later: Settings → Devices & Services →
Mini Split Climate Groups → Configure → **Room temperature source**. The group
reloads with the new source. Each room's `temp_source` (`unit` or `sensor`)
is shown in the group's `members` attribute.

Each group creates two entities:

| Entity | What it does |
| --- | --- |
| `climate.<group>` | The group. State is `heat` or `cool` (the group mode), or `off` when automation is off and every unit is off. Setting heat/cool chooses the mode by hand (and turns automation off). Setting off turns everything off. Turning it on hands control back to automation. |
| `switch.<group>_automation` | Automation on/off. Use it in automations, for example "turn automation off while the windows are open". |

## Automation

**On** — the group runs itself:

1. The active priority order is the default order, or the order of the
   schedule active right now.
2. Rooms are checked in that order. The first room that is outside its
   tolerance (target ± tolerance) decides the group mode.
3. Each room's unit runs while the room needs the group mode and turns off
   once the room is back within hysteresis of its target.
4. Paused rooms are left off and ignored when deciding the mode.

**Off** — you are in control:

- Nothing is turned on or off for you.
- Any unit that is running is kept in the group mode (a unit switched on in the
  other mode from its remote or app is switched back).
- When automation turns off, each room's target is copied to its unit, so the
  unit's own thermostat holds the room at that target. Changing a room's target
  while automation is off updates the unit too.

## Settings

All of these are available from the card's settings button, and as services:

- **Tolerance** — how far a room can drift before it asks for heat or cool.
- **Hysteresis** — buffer before a room counts as back on target and turns off.
- **Default priority** — the order used whenever no schedule is active.
- **Schedules** — a name, start and end time, days, and a priority order. An end
  time earlier than the start runs overnight and belongs to the day it starts
  (Friday 22:00–07:00 also covers Saturday until 07:00). If schedules overlap,
  the first one in the list wins.

Settings, automation, room targets and paused rooms are saved and survive restarts.

## Services

All services take `entity_id` (the group's climate entity).

| Service | Fields | Notes |
| --- | --- | --- |
| `mini_split_climate_groups.set_target_temperature` | `member_id`, `temperature` | One room's target. |
| `mini_split_climate_groups.set_member_power` | `member_id`, `on` | Automation on: off pauses the room, on resumes it. Automation off: turns the unit on (in the group mode) or off. |
| `mini_split_climate_groups.set_automation` | `enabled` | |
| `mini_split_climate_groups.set_mode` | `mode` (`heat`/`cool`) | Chooses the mode by hand and turns automation off. Running units switch; idle units stay off. |
| `mini_split_climate_groups.set_tolerance` | `tolerance` | |
| `mini_split_climate_groups.set_hysteresis` | `hysteresis` | |
| `mini_split_climate_groups.set_priority_order` | `priority_order` | Default order, highest first. |
| `mini_split_climate_groups.set_schedules` | `schedules` | Replaces all schedules. |
| `mini_split_climate_groups.reset_to_default` | `member_id` | Resets a room's target to its configured default. |

Example schedule:

```yaml
service: mini_split_climate_groups.set_schedules
data:
  entity_id: climate.living_area
  schedules:
    - name: Night
      start: "22:00"
      end: "07:00"
      days: [mon, tue, wed, thu, fri, sat, sun]
      priority_order: [bedroom, living_room]
```

Room ids (`member_id`) are listed in the group's `members` attribute.

## The Card

```yaml
type: custom:mini-split-climate-card
entity: climate.living_area
```

One card per group. The card has a fixed height (header plus one row per room),
so it never changes size as states change.

- **Header:** the Auto switch, the heat/cool toggle (tapping the other mode
  turns Auto off and switches the mode), and the settings button.
- **Each room:** its priority rank (filled for the room in charge), a status
  (Driving, Wants heat/cool, At target, Paused), the current temperature, a
  − / target / + control, and a power button.
- **With Auto off,** ranks and statuses are hidden and the power buttons turn
  units on and off directly.

## Edge Cases Handled

### Initializing on Existing System
On startup the group adopts the mode of any unit that is already running.

### Unavailable Climate Entities
If a climate entity becomes unavailable, the integration will:
- Log a warning
- Skip controlling that member
- Continue operating other members
- Auto-recover when entity becomes available

### Missing HVAC Modes
If a climate entity is missing cool/heat modes (Kumo bug), the integration will:
- Log the issue once
- Only use available modes
- Suggest manual device registry fix in logs

## Troubleshooting

Check logs at Settings → System → Logs, filter by "mini_split_climate_groups"
