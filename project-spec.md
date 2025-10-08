# Mini Split Climate Groups - Implementation Specification

## Project Overview

A Home Assistant custom integration that manages multiple mini-split climate zones with priority-based orchestration. Prevents simultaneous heating and cooling across zones while allowing independent temperature control.

## Quick Start

See `setup-workspace.sh` to initialize the project structure.

For the UI reference implementation, see `UI_MOCKUP.md` (React code to convert to Lit Element).

## Repository Structure

```
mini-split-climate-groups/
├── custom_components/
│   └── mini_split_climate_groups/
│       ├── __init__.py
│       ├── manifest.json
│       ├── const.py
│       ├── config_flow.py
│       ├── climate.py
│       ├── coordinator.py
│       ├── services.yaml
│       └── strings.json
├── www/
│   └── mini-split-climate-card.js
├── README.md
├── LICENSE
├── hacs.json
└── .gitignore
```

## Edge Cases & Error Handling

### Critical: Robust Error Handling Required

This integration MUST handle real-world issues gracefully and NEVER crash.

### Edge Case 1: Initializing on Existing Running System

**Problem:** Adding integration to a system where mini splits are already running in various states.

**Solution:**
```python
async def async_added_to_hass(self):
    """Initialize member state from existing system."""
    # Read current climate entity state
    climate_state = self.hass.states.get(self.climate_entity_id)
    if climate_state and climate_state.state != STATE_UNAVAILABLE:
        # Detect current mode
        current_mode = climate_state.state
        if current_mode in (HVACMode.HEAT, HVACMode.COOL):
            self.mode = current_mode.lower()
            self.is_on = True
            _LOGGER.info(
                "[%s] Initialized from existing state: %s, currently %s",
                self.name,
                current_mode,
                "ON" if self.is_on else "OFF"
            )
        else:
            self.is_on = False
            _LOGGER.info("[%s] Initialized: entity is OFF", self.name)
    
    # Restore previous runtime state if available
    old_state = await self.async_get_last_state()
    if old_state and old_state.attributes.get("target_temp"):
        self.current_target_temp = old_state.attributes["target_temp"]
        _LOGGER.info(
            "[%s] Restored target temperature: %.1f°F",
            self.name,
            self.current_target_temp
        )
```

### Edge Case 2: Unavailable Climate Entities

**Problem:** Kumo integration sometimes makes entities unavailable (requires reload).

**Solution:**
```python
def update_climate_state(self):
    """Update state from climate entity with error handling."""
    climate_state = self.hass.states.get(self.climate_entity_id)
    
    if climate_state is None:
        _LOGGER.error(
            "[%s] Climate entity not found: %s",
            self.name,
            self.climate_entity_id
        )
        return False
    
    if climate_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        _LOGGER.warning(
            "[%s] Climate entity unavailable (state: %s). "
            "Skipping control this cycle. "
            "If persistent, try reloading the Kumo integration.",
            self.name,
            climate_state.state
        )
        # Mark as unavailable but don't crash
        self.is_available = False
        return False
    
    # Entity is available
    self.is_available = True
    hvac_mode = climate_state.state
    self.is_on = hvac_mode in (HVACMode.HEAT, HVACMode.COOL)
    return True

async def async_turn_on(self):
    """Turn on climate entity with error handling."""
    if not self.is_available:
        _LOGGER.debug(
            "[%s] Skipping turn_on: entity unavailable",
            self.name
        )
        return
    
    try:
        await self.hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {
                "entity_id": self.climate_entity_id,
                "hvac_mode": self.mode,
            },
            blocking=True,
        )
        _LOGGER.info(
            "[%s] Turned ON (mode: %s, reason: working toward target %.1f°F, current %.1f°F)",
            self.name,
            self.mode,
            self.current_target_temp,
            self.current_temp
        )
    except Exception as err:
        _LOGGER.error(
            "[%s] Failed to turn on: %s. Entity may be unavailable.",
            self.name,
            err
        )
```

### Edge Case 3: Missing HVAC Modes (Kumo Device Registry Bug)

**Problem:** Sometimes Kumo reloads an entity without cool/heat support.

**Solution:**
```python
def validate_hvac_modes(self):
    """Check if entity supports required modes."""
    climate_state = self.hass.states.get(self.climate_entity_id)
    if not climate_state:
        return False
    
    supported_modes = climate_state.attributes.get("hvac_modes", [])
    
    missing_modes = []
    if HVACMode.HEAT not in supported_modes:
        missing_modes.append("heat")
    if HVACMode.COOL not in supported_modes:
        missing_modes.append("cool")
    
    if missing_modes:
        _LOGGER.warning(
            "[%s] Climate entity is missing HVAC modes: %s. "
            "Supported modes: %s. "
            "This is a known Kumo bug. Fix: "
            "1) Go to Settings → Devices & Services → Devices "
            "2) Find '%s' "
            "3) Click device → ... → Edit → Check 'Cool' and 'Heat' support "
            "The integration will only use available modes until fixed.",
            self.name,
            ", ".join(missing_modes),
            ", ".join(supported_modes),
            self.name
        )
        return False
    
    return True

async def async_set_hvac_mode_safe(self, mode: str):
    """Set HVAC mode with validation."""
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
        return True
    except Exception as err:
        _LOGGER.error("[%s] Failed to set mode: %s", self.name, err)
        return False
```

## Logging Strategy: Explain WHY, Not Just WHAT

Every significant action must be logged with context explaining WHY it happened.

### Logging Levels

**INFO:** Normal operation that users might want to know about
```python
_LOGGER.info(
    "[%s] Mode change: %s → %s (reason: %s outside tolerance %.1f°F and has priority)",
    self.group_name,
    old_mode,
    new_mode,
    member.name,
    abs(member.current_temp - member.current_target_temp)
)
```

**DEBUG:** Detailed state for troubleshooting
```python
_LOGGER.debug(
    "[%s] Priority evaluation: %s (priority #%d) delta=%.1f°F, aligned=%s, wants=%s",
    self.group_name,
    member.name,
    member.current_priority,
    abs(member.current_temp - member.current_target_temp),
    member.is_aligned,
    member.wanted_mode
)
```

**WARNING:** Issues that don't break functionality
```python
_LOGGER.warning(
    "[%s] Temperature sensor unavailable for %s. Using last known value %.1f°F from %s ago.",
    self.group_name,
    member.name,
    member.current_temp,
    time_since_update
)
```

**ERROR:** Failures that prevent operation
```python
_LOGGER.error(
    "[%s] Cannot control %s: climate entity unavailable. Check Kumo integration status.",
    self.group_name,
    member.name
)
```

### Required Log Messages

**On Startup:**
```python
_LOGGER.info(
    "[%s] Initialized with %d members. Priority order: %s. "
    "Detected existing group mode: %s. Update interval: %d seconds.",
    self.group_name,
    len(self.members),
    ", ".join([m.name for m in self.members]),
    self.current_mode,
    UPDATE_INTERVAL
)
```

**On Mode Change:**
```python
_LOGGER.info(
    "[%s] Mode change: %s → %s. "
    "Reason: %s (priority #%d) is %.1f°F outside tolerance (target: %.1f°F, current: %.1f°F), wants %s",
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
```

**On Member Control:**
```python
# Turning ON
_LOGGER.info(
    "[%s] Turning ON (mode: %s). "
    "Reason: not aligned with target (target: %.1f°F, current: %.1f°F, delta: %.1f°F)",
    member.name,
    member.mode,
    member.current_target_temp,
    member.current_temp,
    abs(member.current_temp - member.current_target_temp)
)

# Turning OFF
_LOGGER.info(
    "[%s] Turning OFF. "
    "Reason: aligned with target (target: %.1f°F, current: %.1f°F, within hysteresis %.1f°F)",
    member.name,
    member.current_target_temp,
    member.current_temp,
    self.hysteresis
)

# Staying OFF (conflicted)
_LOGGER.debug(
    "[%s] Staying OFF despite being %.1f°F from target. "
    "Reason: wants %s but group is in %s mode (priority #%d, not high enough to change group)",
    member.name,
    abs(member.current_temp - member.current_target_temp),
    member.wanted_mode,
    self.current_mode,
    member.current_priority
)
```

**On Priority Evaluation:**
```python
_LOGGER.debug(
    "[%s] Priority evaluation: checking members in order %s",
    self.group_name,
    ", ".join([f"{m.name}(#{m.current_priority})" for m in priority_sorted])
)

for member in priority_sorted:
    if member.wants_mode_change:
        _LOGGER.debug(
            "[%s]   → %s: WANTS CHANGE (%.1f°F outside tolerance, wants %s)",
            self.group_name,
            member.name,
            abs(member.current_temp - member.current_target_temp),
            member.wanted_mode
        )
    else:
        _LOGGER.debug(
            "[%s]   → %s: satisfied (%.1f°F from target, within tolerance)",
            self.group_name,
            member.name,
            abs(member.current_temp - member.current_target_temp)
        )
```

**On Temperature Adjustment:**
```python
_LOGGER.info(
    "[%s] Target temperature adjusted: %.1f°F → %.1f°F (changed by user via UI)",
    member.name,
    old_temp,
    new_temp
)
```

**On Entity Issues:**
```python
_LOGGER.warning(
    "[%s] Climate entity %s is unavailable (state: %s). "
    "Skipping control this cycle. If this persists, reload the Kumo integration. "
    "Other members will continue to operate normally.",
    member.name,
    member.climate_entity_id,
    state
)
```

### Log Formatting Standards

- **Always use member/group name in brackets:** `[Living Room]` or `[Living Area]`
- **Always include relevant values:** temperatures, deltas, priorities
- **Always explain the reason:** "Reason: X because Y"
- **Use consistent terminology:** "aligned", "wants change", "outside tolerance"
- **Include actionable guidance:** "Try reloading Kumo integration"

### Example Complete Update Cycle Log

```
[Living Area] Starting update cycle
[Living Area] Member states:
  → Living Room: 73.2°F / target 74.0°F, aligned=True, wants=None
  → Bedroom: 76.8°F / target 72.0°F, aligned=False, wants=heat
[Living Area] Priority evaluation: checking members in order Bedroom(#1), Living Room(#2)
[Living Area]   → Bedroom: WANTS CHANGE (4.8°F outside tolerance, wants heat)
[Living Area] Mode change: cool → heat. Reason: Bedroom (priority #1) is 4.8°F outside tolerance (target: 72.0°F, current: 76.8°F), wants heat
[Living Room] Turning OFF. Reason: aligned with target (target: 74.0°F, current: 73.2°F, within hysteresis 0.1°F)
[Bedroom] Turning ON (mode: heat). Reason: not aligned with target (target: 72.0°F, current: 76.8°F, delta: 4.8°F)
[Living Area] Update cycle complete
```

This verbosity allows your wife to look at logs and see exactly:
1. What happened ("Mode changed to heat")
2. Why it happened ("Bedroom was 4.8°F too hot and has priority")
3. What to do if something is wrong ("Reload Kumo integration")

### Priority-Based Control
Each group has a priority order that determines which zone's needs take precedence. The highest priority zone that is outside its tolerance window gets to request a mode change.

### Aligned vs Conflicted States
- **Aligned**: Zone temperature is within hysteresis of target
- **Conflicted**: Zone is outside tolerance window and wants opposite mode

### Key Variables
- `default_target_temp`: Initial target from config (immutable)
- `current_target_temp`: Runtime target (user adjustable)
- `tolerance`: Degrees outside target before requesting mode change (default: 1.5°F)
- `hysteresis`: Deadband for on/off cycling (default: 0.1°F)

## Backend Integration (Python)

### File: `manifest.json`
```json
{
  "domain": "mini_split_climate_groups",
  "name": "Mini Split Climate Groups",
  "version": "1.0.0",
  "documentation": "https://github.com/yourusername/mini-split-climate-groups",
  "issue_tracker": "https://github.com/yourusername/mini-split-climate-groups/issues",
  "requirements": [],
  "codeowners": ["@yourusername"],
  "config_flow": true,
  "dependencies": [],
  "iot_class": "calculated",
  "integration_type": "device"
}
```

### File: `const.py`
Define all constants including:
- `DOMAIN = "mini_split_climate_groups"`
- Config keys: `CONF_MEMBERS`, `CONF_CLIMATE_ENTITY`, `CONF_TEMP_SENSOR`, etc.
- Defaults: `DEFAULT_TOLERANCE = 1.5`, `DEFAULT_HYSTERESIS = 0.1`, `DEFAULT_TARGET_TEMP = 72`
- Update interval: `UPDATE_INTERVAL = 30` seconds
- Service names and attribute keys

### File: `__init__.py`
Responsibilities:
- Set up entry point for integration
- Register climate platform
- Handle entry reload and unload
- Store config data in `hass.data[DOMAIN]`

### File: `config_flow.py`
Multi-step configuration flow:

**Step 1: `async_step_user`**
- Group name (string, required)
- Tolerance (float, 0.5-5.0, default 1.5)
- Hysteresis (float, 0.1-1.0, default 0.1)

**Step 2: `async_step_add_member`**
- Climate entity (selector from all climate entities)
- Temperature sensor (selector from sensors with device_class=temperature)
- Target temperature (int, 60-85, default 72)
- Add another? (bool, default True)
- Loop until user says no

**Step 3: `async_step_priority`**
- Show summary of members
- Create default priority schedule (all members in order added)
- Create entry with all data

**Options Flow: `OptionsFlowHandler`**
- Allow editing tolerance and hysteresis
- Update config entry data

### File: `climate.py`
**Class: `PriorityClimateGroup(ClimateEntity, RestoreEntity)`**

Properties:
- `hvac_mode`: Returns current group mode (cool/heat/off)
- `current_temperature`: Average of all member temps
- `target_temperature`: Average of all member targets
- `extra_state_attributes`: Full member details for card consumption

Methods:
- `async_set_hvac_mode`: Change group mode
- `async_set_temperature`: Set target for all members
- `async_added_to_hass`: Restore last state, register coordinator callback

Attributes exposed:
```python
{
  "members": [
    {
      "id": "living_room",
      "name": "Living Room",
      "climate_entity": "climate.living_room_mini_split",
      "temp_sensor": "sensor.living_room_accurate_temp",
      "current_temp": 73.2,
      "target_temp": 74,
      "is_on": true,
      "mode": "cool",
      "is_aligned": true,
      "wants_change": false,
      "priority": 1
    }
  ],
  "tolerance": 1.5,
  "hysteresis": 0.1,
  "current_priority": ["living_room", "bedroom"]
}
```

### File: `coordinator.py`

**Class: `PriorityClimateMember`**

State:
- `default_target_temp`: From config (immutable)
- `current_target_temp`: User-adjustable runtime value
- `current_temp`: From temperature sensor
- `is_on`: Climate entity power state
- `mode`: Current mode (cool/heat)
- `is_aligned`: Within hysteresis of target
- `wants_mode_change`: Outside tolerance window
- `wanted_mode`: Which mode it wants (if conflicted)
- `current_priority`: Position in priority order

Methods:
- `update_current_temp()`: Read from temp sensor
- `update_climate_state()`: Read from climate entity
- `calculate_alignment(hysteresis)`: Check if on/off needed
- `calculate_wants(tolerance)`: Check if mode change desired
- `should_be_on()`: Determine if split should run
- `async_set_target_temperature(temp)`: Update target
- `async_turn_on()`: Turn on climate entity
- `async_turn_off()`: Turn off climate entity

**Class: `PriorityClimateCoordinator`**

Core Logic:
```python
async def async_update(self):
    """Main control loop - runs every UPDATE_INTERVAL seconds."""
    
    # 1. Update all member states from sensors
    for member in self.members:
        member.update_current_temp()
        member.update_climate_state()
        member.calculate_alignment(self.hysteresis)
        member.calculate_wants(self.tolerance)
    
    # 2. Get current priority order (time-based)
    current_priority = self.get_current_priority_order()
    
    # 3. Determine desired group mode using priority
    desired_mode = self.calculate_group_mode(current_priority)
    
    # 4. Apply mode change if needed
    if desired_mode != self.current_mode:
        await self.async_set_group_mode(desired_mode)
    
    # 5. Control individual splits (turn on/off)
    await self.control_individual_splits()
```

Priority Logic:
```python
def calculate_group_mode(self, priority_order):
    """Apply priority logic to determine group mode."""
    for member_id in priority_order:
        member = self.get_member(member_id)
        
        # If high-priority member wants something, grant it
        if member.wants_mode_change and member.wanted_mode:
            return member.wanted_mode
    
    # No one outside window, maintain current mode
    return self.current_mode
```

Member Control:
```python
async def control_individual_splits(self):
    """Turn splits on/off based on alignment."""
    for member in self.members:
        if member.should_be_on():
            await member.async_turn_on()
        else:
            await member.async_turn_off()
```

### File: `services.yaml`
Define services:
- `set_target_temperature`: Set target for specific member
- `set_tolerance`: Adjust tolerance for group
- `set_priority_order`: Change priority ordering
- `reset_to_default`: Reset member to default target

### File: `strings.json`
UI strings for config flow:
```json
{
  "config": {
    "step": {
      "user": {
        "title": "Create Climate Group",
        "description": "Set up a new mini split climate group",
        "data": {
          "name": "Group Name",
          "tolerance": "Tolerance (°F)",
          "hysteresis": "Hysteresis (°F)"
        }
      },
      "add_member": {
        "title": "Add Climate Zone",
        "description": "{description}",
        "data": {
          "climate_entity": "Climate Entity",
          "temp_sensor": "Temperature Sensor",
          "target_temp": "Default Target (°F)",
          "add_another": "Add Another Zone?"
        }
      }
    }
  }
}
```

## Frontend Card (JavaScript)

### File: `www/mini-split-climate-card.js`

Built using Lit Element (Home Assistant standard).

**Structure:**
```javascript
class MiniSplitClimateCard extends LitElement {
  static get properties() {
    return {
      hass: {},
      config: {},
      _expandedUnits: { state: true },
      _showSettings: { state: true },
    };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('You need to define an entity');
    }
    this.config = config;
  }

  render() {
    const entity = this.hass.states[this.config.entity];
    const members = entity.attributes.members || [];
    const groups = this._groupEntities();
    
    return html`
      ${groups.map(group => this._renderGroup(group))}
    `;
  }

  _renderGroup(group) {
    return html`
      <div class="group-container">
        ${this._renderGroupHeader(group)}
        ${group.members.map(m => this._renderMember(m))}
      </div>
    `;
  }

  _renderGroupHeader(group) {
    // Mode slider switch, settings button
  }

  _renderMember(member) {
    const isExpanded = this._expandedUnits[member.id];
    return html`
      <div class="member-compact">
        ${this._renderCompactView(member)}
      </div>
      ${isExpanded ? this._renderExpandedView(member) : ''}
    `;
  }

  _togglePower(memberId) {
    // Call service to toggle on/off
    this.hass.callService('climate', 'turn_on', {
      entity_id: member.climate_entity
    });
  }

  _adjustTemp(memberId, delta) {
    const member = this._getMember(memberId);
    const newTemp = member.target_temp + delta;
    
    this.hass.callService('mini_split_climate_groups', 'set_target_temperature', {
      entity_id: this.config.entity,
      member_id: memberId,
      temperature: newTemp,
    });
  }

  _toggleGroupMode(mode) {
    this.hass.callService('climate', 'set_hvac_mode', {
      entity_id: this.config.entity,
      hvac_mode: mode,
    });
  }

  _showEntityPopup(entityId) {
    const event = new Event('hass-more-info', {
      bubbles: true,
      composed: true,
    });
    event.detail = { entityId };
    this.dispatchEvent(event);
  }
}

customElements.define('mini-split-climate-card', MiniSplitClimateCard);
```

**UI Components (from our React mockup):**

1. **Group Header**
   - Mode slider switch (cool/heat icons)
   - Group name
   - Settings button

2. **Compact Member View**
   - Expand chevron
   - Mode icon button (toggles on/off)
   - Name and priority
   - Current temp → Target temp
   - Conflicted icon (if applicable)

3. **Expanded Member View**
   - Large target adjustment (up/down buttons)
   - Current temp display
   - Status grid (running/off, mode, priority)
   - Entities section (Temperature sensor button, Climate entity button)

**Styling:**
- Parent groups: gradient background, thick colored border
- Child members: indented, color-coded icons
- Responsive: works on mobile, tablet, desktop

## Installation Instructions

### For Development:
1. Clone repo
2. Create symlinks:
   ```bash
   ln -s /path/to/repo/custom_components/mini_split_climate_groups ~/.homeassistant/custom_components/
   ln -s /path/to/repo/www/mini-split-climate-card.js ~/.homeassistant/www/community/
   ```
3. Restart Home Assistant
4. Add integration via UI

### For Users (via HACS):
1. Add custom repository in HACS
2. Install "Mini Split Climate Groups"
3. Restart Home Assistant
4. Add integration: Settings → Integrations → Add Integration
5. Install card from HACS Frontend
6. Add card to dashboard

## Testing Scenarios

1. **Basic Operation**
   - Create group with 2 members
   - Set different target temps
   - Verify priority-based mode switching

2. **Conflicted State**
   - Set one zone to 80°, one to 65°
   - In cool mode, verify warm zone shows conflicted
   - Check priority determines when mode switches

3. **State Persistence**
   - Adjust temps via UI
   - Restart Home Assistant
   - Verify temps persist

4. **Priority Schedule**
   - Configure day/night priorities
   - Verify priority changes at scheduled times

5. **Entity Popup**
   - Click entity buttons
   - Verify correct entity history shown

## Future Enhancements

- Adaptive tolerance based on outdoor temp
- Learning mode for preferred temps
- Energy usage tracking
- Integration with weather forecast
- Advanced scheduling (per-day, vacation mode)
- Zone occupancy detection
- Visual floor plan view

## Technical Notes

- Update interval: 30 seconds (configurable in const.py)
- Uses Home Assistant's climate platform
- All state stored in `.storage/core.restore_state`
- No external dependencies
- Fully local operation
- Compatible with Home Assistant 2024.1+

## Error Handling

- Entity not found: Log warning, skip member
- Invalid temperature: Use last known good value
- Sensor unavailable: Maintain last state
- Climate entity unavailable: Don't control
- Service call failures: Retry on next cycle

## Logging

Use standard Python logging:
```python
_LOGGER.debug("Member %s aligned: %s", member.id, member.is_aligned)
_LOGGER.info("Group mode changed: %s → %s", old_mode, new_mode)
_LOGGER.warning("Temperature sensor %s unavailable", sensor_id)
_LOGGER.error("Failed to control climate entity %s", entity_id)
```
