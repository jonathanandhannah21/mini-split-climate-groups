import { LitElement, html, css } from "https://unpkg.com/lit@3.1.0/index.js?module";

class MiniSplitClimateCard extends LitElement {
  static properties = {
    hass: {},
    config: {},
    _expandedUnits: { state: true },
    _showSettings: { state: true },
  };

  constructor() {
    super();
    this._expandedUnits = {};
    this._showSettings = {};
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('You need to define an entity');
    }
    this.config = config;
  }

  render() {
    if (!this.hass || !this.config) {
      return html`<div>Loading...</div>`;
    }

    const entity = this.hass.states[this.config.entity];
    if (!entity) {
      return html`<div>Entity ${this.config.entity} not found</div>`;
    }

    const members = entity.attributes.members || [];
    const groups = this._groupEntities(members, entity);

    return html`
      <div class="card-container">
        ${groups.map(group => this._renderGroup(group, entity))}
      </div>
    `;
  }

  _groupEntities(members, entity) {
    // For now, create a single group with all members
    return [{
      id: entity.entity_id,
      name: entity.attributes.friendly_name || this.config.entity,
      mode: entity.state === 'cool' ? 'cool' : 'heat',
      tolerance: entity.attributes.tolerance || 1.5,
      members: members
    }];
  }

  _renderGroup(group, entity) {
    const isSettingsExpanded = this._showSettings[group.id];

    return html`
      <div class="group-container ${this._getGroupBorderClass(group.mode)}">
        <!-- GROUP HEADER -->
        <div class="group-header">
          <div class="header-content">
            <div class="mode-controls">
              <!-- Mode Slider Switch -->
              <div class="mode-slider">
                <button
                  class="mode-button ${group.mode === 'cool' ? 'active-cool' : ''}"
                  @click=${() => this._toggleGroupMode('cool')}
                >
                  <ha-icon icon="mdi:snowflake"></ha-icon>
                </button>
                <button
                  class="mode-button ${group.mode === 'heat' ? 'active-heat' : ''}"
                  @click=${() => this._toggleGroupMode('heat')}
                >
                  <ha-icon icon="mdi:fire"></ha-icon>
                </button>
              </div>
              
              <div class="group-info">
                <h2 class="group-name">${group.name}</h2>
                <div class="group-status">
                  Group Mode: <span class="mode-text ${group.mode}">
                    ${group.mode === 'cool' ? 'Cooling' : 'Heating'}
                  </span>
                </div>
              </div>
            </div>
            
            <div class="header-actions">
              <button 
                class="settings-button ${isSettingsExpanded ? 'active' : ''}"
                @click=${() => this._toggleSettings(group.id)}
              >
                <ha-icon icon="mdi:cog"></ha-icon>
              </button>
            </div>
          </div>

          <!-- SETTINGS PANEL -->
          ${isSettingsExpanded ? html`
            <div class="settings-panel">
              <div class="settings-grid">
                <div class="setting-item">
                  <label class="setting-label">
                    Tolerance: ${group.tolerance}�F
                  </label>
                  <input 
                    type="range" 
                    min="0.5" 
                    max="3" 
                    step="0.5" 
                    .value=${group.tolerance.toString()}
                    @input=${(e) => this._updateTolerance(e.target.value)}
                    class="tolerance-slider"
                  />
                </div>
                <div class="setting-item">
                  <label class="setting-label">
                    Priority Order
                  </label>
                  <div class="priority-list">
                    ${group.members.map((m, idx) => html`
                      <div class="priority-item">
                        <span class="priority-number">${idx + 1}</span>
                        <span class="priority-name">${m.name}</span>
                      </div>
                    `)}
                  </div>
                </div>
              </div>
            </div>
          ` : ''}
        </div>

        <!-- MEMBER UNITS -->
        <div class="members-container">
          ${group.members.map(member => this._renderMember(member))}
        </div>
      </div>
    `;
  }

  _renderMember(member) {
    const isExpanded = this._expandedUnits[member.id];

    return html`
      <div class="member-container">
        <!-- COMPACT VIEW -->
        <div class="member-compact" @click=${() => this._toggleExpand(member.id)}>
          <div class="member-content">
            <!-- Left: Expand + Power/Mode Icon + Name -->
            <div class="member-left">
              <button class="expand-button">
                <ha-icon icon=${isExpanded ? "mdi:chevron-down" : "mdi:chevron-right"}></ha-icon>
              </button>
              
              <button
                class="power-button ${this._getModeClass(member.mode, member.is_on)}"
                @click=${(e) => { e.stopPropagation(); this._togglePower(member.id); }}
              >
                <ha-icon icon=${member.mode === 'cool' ? "mdi:snowflake" : "mdi:fire"}></ha-icon>
              </button>
              
              <div class="member-info">
                <div class="member-name">${member.name}</div>
                <div class="member-priority">Priority #${member.priority}</div>
              </div>
            </div>

            <!-- Center: Temps -->
            <div class="temp-display">
              <div class="temp-item">
                <div class="temp-label">Current</div>
                <div class="temp-value current">${member.current_temp.toFixed(1)}�</div>
              </div>
              <ha-icon icon="mdi:chevron-right" class="temp-arrow"></ha-icon>
              <div class="temp-item">
                <div class="temp-label">Target</div>
                <div class="temp-value target ${member.mode}">${member.target_temp}�</div>
              </div>
            </div>

            <!-- Right: Conflicted Icon -->
            <div class="conflict-indicator">
              ${member.wants_change ? html`
                <ha-icon icon="mdi:alert-triangle" class="conflict-icon"></ha-icon>
              ` : ''}
            </div>
          </div>
        </div>

        <!-- EXPANDED VIEW -->
        ${isExpanded ? html`
          <div class="member-expanded">
            <div class="expanded-content">
              <!-- Temperature Controls -->
              <div class="temp-controls">
                <div class="temp-control-section">
                  <div class="control-label">Adjust Target</div>
                  <div class="temp-adjustment">
                    <button 
                      class="temp-button"
                      @click=${() => this._adjustTemp(member.id, -1)}
                    >
                      <ha-icon icon="mdi:chevron-down"></ha-icon>
                    </button>
                    <div class="target-display ${member.mode}">
                      ${member.target_temp}�
                    </div>
                    <button 
                      class="temp-button"
                      @click=${() => this._adjustTemp(member.id, 1)}
                    >
                      <ha-icon icon="mdi:chevron-up"></ha-icon>
                    </button>
                  </div>
                </div>

                <!-- Current Temp Display -->
                <div class="current-temp-section">
                  <div class="control-label">Current</div>
                  <div class="current-temp-value">
                    ${member.current_temp.toFixed(1)}�
                  </div>
                </div>
              </div>

              <!-- Status Info -->
              <div class="status-info">
                <div class="status-grid">
                  <div class="status-item">
                    <span class="status-label">Status:</span>
                    <span class="status-value">${member.is_on ? 'Running' : 'Off'}</span>
                  </div>
                  <div class="status-item">
                    <span class="status-label">Mode:</span>
                    <span class="status-value ${member.mode}">
                      ${member.mode === 'cool' ? 'Cooling' : 'Heating'}
                    </span>
                  </div>
                  <div class="status-item">
                    <span class="status-label">Priority:</span>
                    <span class="status-value">#${member.priority}</span>
                  </div>
                </div>
              </div>

              <!-- Entities -->
              <div class="entities-section">
                <div class="entities-label">Entities</div>
                <div class="entity-buttons">
                  <button 
                    class="entity-button"
                    @click=${() => this._showEntityPopup(member.temp_sensor)}
                  >
                    <ha-icon icon="mdi:thermometer"></ha-icon>
                    <span>Temperature</span>
                  </button>
                  <button 
                    class="entity-button"
                    @click=${() => this._showEntityPopup(member.climate_entity)}
                  >
                    <ha-icon icon=${member.mode === 'cool' ? "mdi:snowflake" : "mdi:fire"}></ha-icon>
                    <span>Climate</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        ` : ''}
      </div>
    `;
  }

  _getGroupBorderClass(mode) {
    return mode === 'cool' ? 'border-cool' : 'border-heat';
  }

  _getModeClass(mode, isOn) {
    if (!isOn) return 'power-off';
    return mode === 'cool' ? 'power-cool' : 'power-heat';
  }

  _toggleExpand(memberId) {
    this._expandedUnits = {
      ...this._expandedUnits,
      [memberId]: !this._expandedUnits[memberId]
    };
  }

  _toggleSettings(groupId) {
    this._showSettings = {
      ...this._showSettings,
      [groupId]: !this._showSettings[groupId]
    };
  }

  _togglePower(memberId) {
    const entity = this.hass.states[this.config.entity];
    const member = entity.attributes.members.find(m => m.id === memberId);
    
    if (!member) return;
    
    // Use set_hvac_mode which is universally supported
    const targetMode = member.is_on ? 'off' : member.mode;
    
    this.hass.callService('climate', 'set_hvac_mode', {
      entity_id: member.climate_entity,
      hvac_mode: targetMode
    });
  }

  _adjustTemp(memberId, delta) {
    const entity = this.hass.states[this.config.entity];
    const member = entity.attributes.members.find(m => m.id === memberId);
    
    if (!member) return;
    
    const newTemp = member.target_temp + delta;
    
    this.hass.callService('mini_split_climate_groups', 'set_target_temperature', {
      entity_id: this.config.entity,
      member_id: memberId,
      temperature: newTemp,
    });
  }

  _toggleGroupMode(mode) {
    const targetMode = mode === 'cool' ? 'cool' : 'heat';
    
    this.hass.callService('climate', 'set_hvac_mode', {
      entity_id: this.config.entity,
      hvac_mode: targetMode,
    });
  }

  _updateTolerance(value) {
    this.hass.callService('mini_split_climate_groups', 'set_tolerance', {
      entity_id: this.config.entity,
      tolerance: parseFloat(value),
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

  static styles = css`
    .card-container {
      max-width: 800px;
      margin: 0 auto;
      padding: 16px;
      background: var(--primary-background-color);
      border-radius: 8px;
    }

    .group-container {
      background: var(--card-background-color);
      border-radius: 12px;
      box-shadow: var(--ha-card-box-shadow);
      border-left: 4px solid;
      overflow: hidden;
      margin-bottom: 16px;
    }

    .group-container.border-cool {
      border-left-color: var(--info-color, #2196F3);
    }

    .group-container.border-heat {
      border-left-color: var(--warning-color, #FF9800);
    }

    .group-header {
      background: linear-gradient(to right, var(--secondary-background-color), var(--card-background-color));
      padding: 16px;
      border-bottom: 2px solid var(--divider-color);
    }

    .header-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .mode-controls {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .mode-slider {
      background: var(--divider-color);
      border-radius: 24px;
      padding: 4px;
      display: flex;
      gap: 4px;
    }

    .mode-button {
      padding: 8px;
      border-radius: 20px;
      border: none;
      background: transparent;
      cursor: pointer;
      transition: all 0.3s ease;
      color: var(--secondary-text-color);
    }

    .mode-button.active-cool {
      background: var(--info-color, #2196F3);
      color: white;
      box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    .mode-button.active-heat {
      background: var(--warning-color, #FF9800);
      color: white;
      box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    }

    .mode-button:hover:not(.active-cool):not(.active-heat) {
      background: var(--secondary-background-color);
    }

    .group-info h2 {
      margin: 0;
      font-size: 20px;
      font-weight: bold;
      color: var(--primary-text-color);
    }

    .group-status {
      font-size: 14px;
      color: var(--secondary-text-color);
    }

    .mode-text.cool {
      color: var(--info-color, #2196F3);
      font-weight: 600;
    }

    .mode-text.heat {
      color: var(--warning-color, #FF9800);
      font-weight: 600;
    }

    .settings-button {
      padding: 8px;
      border: none;
      background: transparent;
      border-radius: 8px;
      cursor: pointer;
      color: var(--secondary-text-color);
      transition: all 0.3s ease;
    }

    .settings-button:hover,
    .settings-button.active {
      background: var(--secondary-background-color);
      color: var(--accent-color);
    }

    .settings-panel {
      margin-top: 16px;
      padding-top: 16px;
      border-top: 1px solid var(--divider-color);
    }

    .settings-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }

    .setting-label {
      display: block;
      font-size: 14px;
      font-weight: 500;
      color: var(--primary-text-color);
      margin-bottom: 8px;
    }

    .tolerance-slider {
      width: 100%;
      margin: 8px 0;
    }

    .priority-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .priority-item {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
    }

    .priority-number {
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
      padding: 2px 8px;
      border-radius: 12px;
      font-family: monospace;
      font-size: 12px;
      min-width: 24px;
      text-align: center;
    }

    .members-container {
      divide-y: 1px solid var(--divider-color);
    }

    .member-container {
      border-bottom: 1px solid var(--divider-color);
    }

    .member-container:last-child {
      border-bottom: none;
    }

    .member-compact {
      padding: 12px 16px 12px 32px;
      cursor: pointer;
      transition: background-color 0.3s ease;
    }

    .member-compact:hover {
      background: var(--secondary-background-color);
    }

    .member-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .member-left {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;
    }

    .expand-button {
      padding: 4px;
      border: none;
      background: transparent;
      color: var(--secondary-text-color);
      cursor: pointer;
      border-radius: 4px;
      transition: background-color 0.3s ease;
    }

    .expand-button:hover {
      background: var(--secondary-background-color);
    }

    .power-button {
      padding: 8px;
      border: 2px solid var(--divider-color);
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.3s ease;
    }

    .power-button.power-off {
      background: var(--secondary-background-color);
      color: var(--secondary-text-color);
    }

    .power-button.power-cool {
      background: var(--info-color, #2196F3);
      border-color: var(--info-color, #2196F3);
      color: white;
    }

    .power-button.power-heat {
      background: var(--warning-color, #FF9800);
      border-color: var(--warning-color, #FF9800);
      color: white;
    }

    .power-button:hover {
      opacity: 0.8;
    }

    .member-info {
      flex: 1;
    }

    .member-name {
      font-weight: 600;
      color: var(--primary-text-color);
    }

    .member-priority {
      font-size: 12px;
      color: var(--secondary-text-color);
    }

    .temp-display {
      display: flex;
      align-items: center;
      gap: 12px;
      margin: 0 16px;
    }

    .temp-item {
      text-align: center;
    }

    .temp-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-bottom: 2px;
    }

    .temp-value {
      font-size: 18px;
      font-weight: bold;
    }

    .temp-value.current {
      color: var(--primary-text-color);
    }

    .temp-value.target.cool {
      color: var(--info-color, #2196F3);
    }

    .temp-value.target.heat {
      color: var(--warning-color, #FF9800);
    }

    .temp-arrow {
      color: var(--secondary-text-color);
    }

    .conflict-indicator {
      width: 32px;
      display: flex;
      justify-content: center;
    }

    .conflict-icon {
      color: var(--error-color, #F44336);
    }

    .member-expanded {
      padding: 16px 64px 16px 64px;
      background: var(--secondary-background-color);
      border-top: 1px solid var(--divider-color);
    }

    .temp-controls {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }

    .control-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-bottom: 8px;
    }

    .temp-adjustment {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .temp-button {
      padding: 8px;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      cursor: pointer;
      color: var(--info-color, #2196F3);
      transition: all 0.3s ease;
    }

    .temp-button:hover {
      background: var(--info-color, #2196F3);
      color: white;
    }

    .target-display {
      font-size: 32px;
      font-weight: bold;
      padding: 0 16px;
    }

    .target-display.cool {
      color: var(--info-color, #2196F3);
    }

    .target-display.heat {
      color: var(--warning-color, #FF9800);
    }

    .current-temp-section {
      padding-left: 16px;
      border-left: 1px solid var(--divider-color);
    }

    .current-temp-value {
      font-size: 20px;
      font-weight: 600;
      color: var(--primary-text-color);
    }

    .status-info {
      padding: 12px;
      background: var(--card-background-color);
      border-radius: 8px;
      border: 1px solid var(--divider-color);
      margin-bottom: 12px;
    }

    .status-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
      font-size: 14px;
    }

    .status-label {
      color: var(--secondary-text-color);
    }

    .status-value {
      font-weight: 600;
      color: var(--primary-text-color);
    }

    .status-value.cool {
      color: var(--info-color, #2196F3);
    }

    .status-value.heat {
      color: var(--warning-color, #FF9800);
    }

    .entities-section {
      padding: 12px;
      background: var(--card-background-color);
      border-radius: 8px;
      border: 1px solid var(--divider-color);
    }

    .entities-label {
      font-size: 12px;
      color: var(--secondary-text-color);
      margin-bottom: 8px;
    }

    .entity-buttons {
      display: flex;
      gap: 8px;
    }

    .entity-button {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      background: var(--secondary-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      cursor: pointer;
      font-size: 14px;
      color: var(--primary-text-color);
      transition: all 0.3s ease;
    }

    .entity-button:hover {
      background: var(--accent-color);
      color: white;
    }

    @media (max-width: 768px) {
      .settings-grid {
        grid-template-columns: 1fr;
      }
      
      .temp-controls {
        flex-direction: column;
        align-items: flex-start;
        gap: 16px;
      }
      
      .status-grid {
        grid-template-columns: 1fr;
        gap: 8px;
      }
    }
  `;
}

customElements.define('mini-split-climate-card', MiniSplitClimateCard);

// Add to window for discovery
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'mini-split-climate-card',
  name: 'Mini Split Climate Card',
  description: 'A card for controlling mini split climate groups with priority-based orchestration'
});