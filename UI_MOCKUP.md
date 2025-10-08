# UI Mockup - React Reference Implementation

This is the reference UI implementation in React. Convert this to Lit Element for the actual card.

## Key UI Patterns

### Hierarchical Display
- **Groups** have gradient backgrounds and thick colored left borders
- **Members** are indented and nested under their group
- Clear visual parent-child relationship

### Mode Indication
- **Slider Switch** in group header to toggle cool/heat
- **Mode Icons** on each member (snowflake for cool, flame for heat)
- **Color Coding**:
  - Blue = cooling (active)
  - Orange = heating (active)
  - Gray = off

### Expand/Collapse
- Chevron button on each member (right arrow = collapsed, down arrow = expanded)
- Expanded view shows temperature controls and entity buttons
- Expansion state maintained locally (not saved)

### Power Control
- Mode icon acts as power button in compact view
- Click to toggle between active mode and off
- Visual feedback: colored background when on, gray when off

### Conflicted State
- Red triangle icon on far right when member wants mode change
- Fixed position so doesn't shift other elements
- Only visible when outside tolerance window

## React Code (Convert to Lit Element)

```javascript
import React, { useState } from 'react';
import { Thermometer, Flame, Snowflake, Power, ChevronUp, ChevronDown, ChevronRight, Settings, TrendingUp, AlertTriangle } from 'lucide-react';

const MiniSplitClimateCard = () => {
  const [expandedUnits, setExpandedUnits] = useState({});
  const [showSettings, setShowSettings] = useState({});
  
  const groups = [
    {
      id: "living_area",
      name: "Living Area",
      mode: "cool",
      tolerance: 1.5,
      members: [
        {
          id: "living_room",
          name: "Living Room",
          current_temp: 73.2,
          target_temp: 74,
          is_on: true,
          mode: "cool",
          wants_change: false,
          priority: 1
        },
        {
          id: "bedroom",
          name: "Bedroom",
          current_temp: 76.8,
          target_temp: 72,
          is_on: true,
          mode: "cool",
          wants_change: true,
          priority: 2
        }
      ]
    },
    {
      id: "kids_area",
      name: "Kids Area",
      mode: "heat",
      tolerance: 1.5,
      members: [
        {
          id: "kid1",
          name: "Kid 1",
          current_temp: 69.5,
          target_temp: 70,
          is_on: true,
          mode: "heat",
          wants_change: false,
          priority: 1
        },
        {
          id: "kid2",
          name: "Kid 2",
          current_temp: 70.8,
          target_temp: 71,
          is_on: false,
          mode: "heat",
          wants_change: false,
          priority: 2
        }
      ]
    }
  ];

  const toggleExpand = (unitId) => {
    setExpandedUnits(prev => ({ ...prev, [unitId]: !prev[unitId] }));
  };

  const toggleSettings = (groupId) => {
    setShowSettings(prev => ({ ...prev, [groupId]: !prev[groupId] }));
  };

  const getModeColor = (mode, is_on) => {
    if (!is_on) return 'text-gray-400 bg-gray-100';
    return mode === 'cool' ? 'text-blue-600 bg-blue-100' : 'text-orange-600 bg-orange-100';
  };

  const getGroupBorderColor = (mode) => {
    return mode === 'cool' ? 'border-l-blue-500' : 'border-l-orange-500';
  };

  return (
    <div className="max-w-3xl mx-auto p-4 bg-gray-50 space-y-4">
      {groups.map((group) => (
        <div key={group.id} className={`bg-white rounded-lg shadow-lg border-l-4 ${getGroupBorderColor(group.mode)} overflow-hidden`}>
          {/* GROUP HEADER */}
          <div className="bg-gradient-to-r from-gray-50 to-white p-4 border-b-2 border-gray-200">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {/* Mode Slider Switch */}
                <div className="relative bg-gray-200 rounded-full p-1 flex items-center gap-1">
                  <button
                    onClick={() => console.log('Switch to cool')}
                    className={`p-2 rounded-full transition-all ${
                      group.mode === 'cool'
                        ? 'bg-blue-500 shadow-md'
                        : 'bg-transparent hover:bg-gray-300'
                    }`}
                  >
                    <Snowflake className={`w-5 h-5 ${group.mode === 'cool' ? 'text-white' : 'text-gray-600'}`} />
                  </button>
                  <button
                    onClick={() => console.log('Switch to heat')}
                    className={`p-2 rounded-full transition-all ${
                      group.mode === 'heat'
                        ? 'bg-orange-500 shadow-md'
                        : 'bg-transparent hover:bg-gray-300'
                    }`}
                  >
                    <Flame className={`w-5 h-5 ${group.mode === 'heat' ? 'text-white' : 'text-gray-600'}`} />
                  </button>
                </div>
                
                <div>
                  <h2 className="text-xl font-bold text-gray-800">{group.name}</h2>
                  <div className="text-sm text-gray-600">
                    Group Mode: <span className={`font-semibold ${group.mode === 'cool' ? 'text-blue-600' : 'text-orange-600'}`}>
                      {group.mode === 'cool' ? 'Cooling' : 'Heating'}
                    </span>
                  </div>
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => toggleSettings(group.id)}
                  className="p-2 hover:bg-gray-100 rounded-lg transition"
                >
                  <Settings className={`w-5 h-5 ${showSettings[group.id] ? 'text-blue-600' : 'text-gray-600'}`} />
                </button>
              </div>
            </div>

            {/* SETTINGS PANEL */}
            {showSettings[group.id] && (
              <div className="mt-4 pt-4 border-t border-gray-200">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium text-gray-700 block mb-2">
                      Tolerance: {group.tolerance}°F
                    </label>
                    <input type="range" min="0.5" max="3" step="0.5" value={group.tolerance} className="w-full" />
                  </div>
                  <div>
                    <label className="text-sm font-medium text-gray-700 block mb-2">
                      Priority Order
                    </label>
                    <div className="flex flex-col gap-1">
                      {group.members.map((m, idx) => (
                        <div key={m.id} className="text-sm flex items-center gap-2">
                          <span className="font-mono bg-gray-200 px-2 py-0.5 rounded text-xs">{idx + 1}</span>
                          <span>{m.name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* MEMBER UNITS */}
          <div className="divide-y divide-gray-200">
            {group.members.map((member) => {
              const isExpanded = expandedUnits[member.id];
              
              return (
                <div key={member.id} className="bg-white">
                  {/* COMPACT VIEW */}
                  <div className="pl-8 pr-4 py-3 hover:bg-gray-50 transition">
                    <div className="flex items-center justify-between">
                      {/* Left: Expand + Power/Mode Icon + Name */}
                      <div className="flex items-center gap-3 flex-1">
                        <button 
                          onClick={() => toggleExpand(member.id)}
                          className="p-1 hover:bg-gray-200 rounded transition"
                        >
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-gray-600" />
                          ) : (
                            <ChevronRight className="w-4 h-4 text-gray-600" />
                          )}
                        </button>
                        
                        <button
                          onClick={() => console.log('Toggle power', member.id)}
                          className={`p-2 rounded-lg transition border-2 ${getModeColor(member.mode, member.is_on)} ${
                            member.is_on 
                              ? 'border-transparent hover:border-gray-300' 
                              : 'border-gray-300 hover:border-gray-400'
                          }`}
                        >
                          {member.mode === 'cool' ? (
                            <Snowflake className="w-5 h-5" />
                          ) : (
                            <Flame className="w-5 h-5" />
                          )}
                        </button>
                        
                        <div>
                          <div className="font-semibold text-gray-800">{member.name}</div>
                          <div className="text-xs text-gray-500">Priority #{member.priority}</div>
                        </div>
                      </div>

                      {/* Center: Temps */}
                      <div className="flex items-center gap-3 mx-4">
                        <div className="text-right">
                          <div className="text-xs text-gray-500">Current</div>
                          <div className="text-lg font-bold text-gray-800">
                            {member.current_temp.toFixed(1)}°
                          </div>
                        </div>
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                        <div>
                          <div className="text-xs text-gray-500">Target</div>
                          <div className={`text-lg font-bold ${member.mode === 'cool' ? 'text-blue-600' : 'text-orange-600'}`}>
                            {member.target_temp}°
                          </div>
                        </div>
                      </div>

                      {/* Right: Conflicted Icon */}
                      <div className="w-8 flex justify-center">
                        {member.wants_change && (
                          <AlertTriangle className="w-5 h-5 text-red-500" />
                        )}
                      </div>
                    </div>
                  </div>

                  {/* EXPANDED VIEW */}
                  {isExpanded && (
                    <div className="pl-16 pr-4 pb-4 bg-gray-50 border-t border-gray-200">
                      <div className="flex items-center justify-between pt-4">
                        {/* Temperature Controls */}
                        <div className="flex items-center gap-4">
                          <div>
                            <div className="text-xs text-gray-600 mb-1">Adjust Target</div>
                            <div className="flex items-center gap-2">
                              <button className="p-2 bg-white hover:bg-blue-50 border border-gray-300 rounded-lg transition">
                                <ChevronDown className="w-5 h-5 text-blue-600" />
                              </button>
                              <div className={`text-3xl font-bold px-4 ${member.mode === 'cool' ? 'text-blue-600' : 'text-orange-600'}`}>
                                {member.target_temp}°
                              </div>
                              <button className="p-2 bg-white hover:bg-blue-50 border border-gray-300 rounded-lg transition">
                                <ChevronUp className="w-5 h-5 text-blue-600" />
                              </button>
                            </div>
                          </div>

                          {/* Current Temp Display */}
                          <div className="pl-4 border-l border-gray-300">
                            <div className="text-xs text-gray-600">Current</div>
                            <div className="text-xl font-semibold text-gray-700">
                              {member.current_temp.toFixed(1)}°
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Status Info */}
                      <div className="mt-3 p-3 bg-white rounded-lg border border-gray-200">
                        <div className="grid grid-cols-3 gap-4 text-sm">
                          <div>
                            <span className="text-gray-600">Status: </span>
                            <span className="font-semibold text-gray-800">
                              {member.is_on ? 'Running' : 'Off'}
                            </span>
                          </div>
                          <div>
                            <span className="text-gray-600">Mode: </span>
                            <span className={`font-semibold ${member.mode === 'cool' ? 'text-blue-600' : 'text-orange-600'}`}>
                              {member.mode === 'cool' ? 'Cooling' : 'Heating'}
                            </span>
                          </div>
                          <div>
                            <span className="text-gray-600">Priority: </span>
                            <span className="font-semibold text-gray-800">#{member.priority}</span>
                          </div>
                        </div>
                      </div>

                      {/* Entities */}
                      <div className="mt-3 p-3 bg-white rounded-lg border border-gray-200">
                        <div className="text-xs text-gray-600 mb-2">Entities</div>
                        <div className="flex gap-2">
                          <button 
                            onClick={() => console.log('Show temperature sensor entity for', member.id)}
                            className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 hover:bg-gray-100 border border-gray-300 rounded text-sm transition"
                          >
                            <Thermometer className="w-4 h-4 text-gray-600" />
                            <span className="text-gray-700">Temperature</span>
                          </button>
                          <button 
                            onClick={() => console.log('Show climate entity for', member.id)}
                            className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 hover:bg-gray-100 border border-gray-300 rounded text-sm transition"
                          >
                            {member.mode === 'cool' ? (
                              <Snowflake className="w-4 h-4 text-gray-600" />
                            ) : (
                              <Flame className="w-4 h-4 text-gray-600" />
                            )}
                            <span className="text-gray-700">Climate</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};

export default MiniSplitClimateCard;
```

## Conversion Notes for Lit Element

### State Management
Replace `useState` with Lit's reactive properties:
```javascript
static get properties() {
  return {
    _expandedUnits: { state: true },
    _showSettings: { state: true },
  };
}
```

### Event Handlers
Replace `onClick` with `@click`:
```javascript
<button @click=${() => this._toggleExpand(memberId)}>
```

### Data Binding
Read from Home Assistant entity:
```javascript
const entity = this.hass.states[this.config.entity];
const groups = entity.attributes.members || [];
```

### Service Calls
```javascript
this.hass.callService('mini_split_climate_groups', 'set_target_temperature', {
  entity_id: this.config.entity,
  member_id: memberId,
  temperature: newTemp,
});
```

### Entity Popups
```javascript
_showEntityPopup(entityId) {
  const event = new Event('hass-more-info', {
    bubbles: true,
    composed: true,
  });
  event.detail = { entityId };
  this.dispatchEvent(event);
}
```
