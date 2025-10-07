# Mini Split Climate Groups

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

A Home Assistant custom integration for managing multiple mini-split climate zones with priority-based orchestration.

## Features

- 🎯 **Priority-Based Control** - Highest priority zone that needs it determines the group mode
- 🔄 **Prevents Mode Conflicts** - Never heat and cool simultaneously
- 🌡️ **Independent Temperatures** - Each zone maintains its own target
- ⏰ **Time-Based Priorities** - Different priorities for day/night
- 📊 **Rich Diagnostics** - Detailed logging explains every decision
- 🛡️ **Robust Error Handling** - Gracefully handles unavailable entities and missing modes

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
