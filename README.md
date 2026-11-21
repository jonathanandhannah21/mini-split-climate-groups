# Mini Split Climate Groups

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

A Home Assistant custom integration for managing multiple mini-split climate zones with priority-based orchestration.

## Features

- 🎯 **Priority-Based Control** - The highest-priority room outside its tolerance decides the group mode
- 🔄 **Prevents Mode Conflicts** - One shared heat/cool mode; units never heat and cool at once
- 🌡️ **Independent Temperatures** - Every room keeps its own target
- 🤖 **Automation On/Off** - Let priority run the rooms, or take over mode and power yourself
- ⏰ **Priority Schedules** - A different priority order by time of day and day of week
- ⏸️ **Pause a Room** - Leave one room off without fighting the automation
- 🃏 **Dashboard Card** - Fixed-size "priority ladder" card with per-room controls and settings
- 📊 **Rich Diagnostics** - Detailed logging explains every decision
- 🛡️ **Robust Error Handling** - Gracefully handles unavailable entities and missing modes

## How It Works

Each group has **one mode** (heat or cool) that every running unit follows, and
each room has **its own target**.

- **Automation on** (default): rooms are checked in priority order. The
  highest-priority room that is outside its tolerance decides the mode. Each
  room's unit runs only while that room needs the group mode, then turns off.
  A room that wants the other mode waits until it is the highest priority asking.
- **Automation off**: nothing is switched on or off for you. You choose the
  mode and turn rooms on and off; the group only keeps running units in the
  group mode, and each unit's own thermostat holds its room at the room's target.

Choosing heat or cool by hand (on the card or the thermostat) turns automation
off. Turning the group's climate entity **off** turns automation off and every
unit off, and they stay off.

## Installation

See [Installation Guide](docs/installation.md)

## Configuration

See [Configuration Guide](docs/configuration.md)

## Example Dashboard

See [Dashboard Examples](examples/dashboard.yaml)

## Debugging

This integration logs every decision with context. Check logs:
- Settings → System → Logs
- Filter by "mini_split_climate_groups"

Example log messages:
```
[Living Area] Priority evaluation: bedroom (priority #1) is 4.3°F outside tolerance, wants heat
[Living Area] Mode change: cool → heat (reason: bedroom outside tolerance and has priority)
[Living Room] Turning OFF (reason: aligned with target 74.0°F, current 73.9°F)
[Bedroom] Climate entity unavailable, skipping control this cycle
```

## Edge Cases Handled

### Existing System Initialization
When added to a running system, detects current state and initializes appropriately.

### Unavailable Entities
Gracefully handles Kumo integration reloads and entity unavailability.

### Missing HVAC Modes
Detects and logs when climate entities are missing expected modes (Kumo device registry bug).

## License

MIT License - see LICENSE file
