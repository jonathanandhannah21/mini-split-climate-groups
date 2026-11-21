import { LitElement, html, css, nothing } from "https://unpkg.com/lit@3.1.0/index.js?module";

/*
 * Mini Split Climate Card — "Priority Ladder"
 *
 * One card per climate group entity. Fixed height: a 44px header plus one
 * 64px row per room, whatever the state, so the dashboard never reflows.
 *
 *   header: name · [Auto switch] [cool | heat] [settings]
 *   row:    rank · name + badge / current temp · [− target +] · power
 */

const DOMAIN = "mini_split_climate_groups";
const MIN_TEMP = 60;
const MAX_TEMP = 85;
const TARGET_DEBOUNCE_MS = 700;
const DAYS = [
  ["mon", "M", "Monday"],
  ["tue", "T", "Tuesday"],
  ["wed", "W", "Wednesday"],
  ["thu", "T", "Thursday"],
  ["fri", "F", "Friday"],
  ["sat", "S", "Saturday"],
  ["sun", "S", "Sunday"],
];

const BADGES = {
  driving: { label: "Driving", tone: "mode" },
  wants_heat: { label: "Wants heat", tone: "danger" },
  wants_cool: { label: "Wants cool", tone: "danger" },
  at_target: { label: "At target", tone: "success" },
  paused: { label: "Paused", tone: "neutral" },
};

const fmtTime = (hhmm) => {
  const [h, m] = String(hhmm || "00:00").split(":").map(Number);
  const suffix = h >= 12 ? "PM" : "AM";
  const hour = h % 12 === 0 ? 12 : h % 12;
  return `${hour}:${String(m).padStart(2, "0")} ${suffix}`;
};

const fmtDays = (days) => {
  const set = new Set(days || []);
  if (set.size === 7) return "Every day";
  const weekdays = ["mon", "tue", "wed", "thu", "fri"];
  if (set.size === 5 && weekdays.every((d) => set.has(d))) return "Weekdays";
  if (set.size === 2 && set.has("sat") && set.has("sun")) return "Weekends";
  return DAYS.filter(([d]) => set.has(d))
    .map(([, , name]) => name.slice(0, 3))
    .join(", ");
};

const move = (list, index, delta) => {
  const next = [...list];
  const target = index + delta;
  if (target < 0 || target >= next.length) return next;
  [next[index], next[target]] = [next[target], next[index]];
  return next;
};

class MiniSplitClimateCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    _config: { state: true },
    _pending: { state: true },
    _settings: { state: true },
  };

  constructor() {
    super();
    this._pending = {};
    this._timers = {};
    this._settings = null;
  }

  // ---------------------------------------------------------------- config

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Set 'entity' to a mini split climate group (climate.*)");
    }
    this._config = config;
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("climate.") && Array.isArray(hass.states[id].attributes.members)
    );
    return { entity: entity || "climate.living_area" };
  }

  get _stateObj() {
    return this.hass && this._config ? this.hass.states[this._config.entity] : undefined;
  }

  get _memberCount() {
    const members = this._stateObj?.attributes?.members;
    return Array.isArray(members) ? members.length : 2;
  }

  getCardSize() {
    return Math.ceil((92 + this._memberCount * 64) / 50);
  }

  getGridOptions() {
    const rows = this._memberCount + 2;
    return { columns: 12, min_columns: 6, rows, min_rows: rows };
  }

  // Only redraw when this group's state (or the theme) changes.
  shouldUpdate(changed) {
    if (changed.size === 1 && changed.has("hass")) {
      const old = changed.get("hass");
      if (!old || !this._config) return true;
      return (
        old.states[this._config.entity] !== this.hass.states[this._config.entity] ||
        old.themes !== this.hass.themes
      );
    }
    return true;
  }

  updated(changed) {
    if (changed.has("hass") && Object.keys(this._pending).length) {
      // Drop pending targets once Home Assistant reports them.
      const members = this._members();
      const pending = { ...this._pending };
      let dirty = false;
      for (const [id, value] of Object.entries(pending)) {
        const member = members.find((m) => m.id === id);
        if (!this._timers[id] && member && member.target_temp === value) {
          delete pending[id];
          dirty = true;
        }
      }
      if (dirty) this._pending = pending;
    }
    const dialog = this.renderRoot.querySelector("dialog");
    if (dialog) {
      if (this._settings && !dialog.open) dialog.showModal();
      if (!this._settings && dialog.open) dialog.close();
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    Object.values(this._timers).forEach(clearTimeout);
    this._timers = {};
  }

  // ---------------------------------------------------------------- data

  _members() {
    const attrs = this._stateObj?.attributes || {};
    const members = Array.isArray(attrs.members) ? [...attrs.members] : [];
    return members.sort((a, b) => (a.priority || 0) - (b.priority || 0));
  }

  _name() {
    return this._config.name || this._stateObj?.attributes?.friendly_name || this._config.entity;
  }

  _call(service, data) {
    return this.hass
      .callService(DOMAIN, service, { entity_id: this._config.entity, ...data })
      .catch((err) => {
        this.dispatchEvent(
          new CustomEvent("hass-notification", {
            detail: { message: `${this._name()}: ${err?.message || err}` },
            bubbles: true,
            composed: true,
          })
        );
        throw err;
      });
  }

  // ---------------------------------------------------------------- actions

  _toggleAutomation() {
    this._call("set_automation", { enabled: !this._stateObj.attributes.automation }).catch(() => {});
  }

  _setMode(mode) {
    const attrs = this._stateObj.attributes;
    if (attrs.group_mode === mode) return;
    this._call("set_mode", { mode }).catch(() => {});
  }

  _togglePower(member) {
    const automation = this._stateObj.attributes.automation;
    // Auto: the button pauses/resumes the room. Manual: plain on/off.
    const on = automation ? member.paused : !member.is_on;
    this._call("set_member_power", { member_id: member.id, on }).catch(() => {});
  }

  _step(member, delta) {
    const current = this._pending[member.id] ?? member.target_temp;
    const value = Math.max(MIN_TEMP, Math.min(MAX_TEMP, Math.round(current) + delta));
    this._pending = { ...this._pending, [member.id]: value };
    clearTimeout(this._timers[member.id]);
    this._timers[member.id] = setTimeout(() => {
      delete this._timers[member.id];
      this._call("set_target_temperature", { member_id: member.id, temperature: value })
        .catch(() => {
          const pending = { ...this._pending };
          delete pending[member.id];
          this._pending = pending;
        });
    }, TARGET_DEBOUNCE_MS);
  }

  // ---------------------------------------------------------------- render

  render() {
    if (!this._config || !this.hass) return nothing;
    const stateObj = this._stateObj;
    if (!stateObj) {
      return html`<ha-card><div class="missing">Entity not found: ${this._config.entity}</div></ha-card>`;
    }

    const attrs = stateObj.attributes;
    const automation = attrs.automation !== false;
    const mode = attrs.group_mode === "heat" ? "heat" : "cool";
    const members = this._members();

    return html`
      <ha-card class="mode-${mode} ${automation ? "auto" : "manual"}">
        <div class="header">
          <div class="title">
            <h2>${this._name()}</h2>
            <div class="sub">${members.length} ${members.length === 1 ? "room" : "rooms"}</div>
          </div>
          <div class="controls">
            <button
              class="auto-switch"
              role="switch"
              aria-checked=${automation ? "true" : "false"}
              aria-label="Automation"
              title=${automation ? "Priority decides mode and power" : "You control mode and power"}
              @click=${this._toggleAutomation}
            >
              Auto<span class="track"><span class="knob"></span></span>
            </button>
            <div class="mode-pill" role="group" aria-label="Group mode">
              ${this._modeButton("cool", mode, "mdi:snowflake", "Cool")}
              ${this._modeButton("heat", mode, "mdi:fire", "Heat")}
            </div>
            <button class="icon-btn" aria-label="Group settings" @click=${this._openSettings}>
              <ha-icon icon="mdi:tune-variant"></ha-icon>
            </button>
          </div>
        </div>
        <div class="rows">${members.map((m) => this._renderRow(m, automation, mode))}</div>
        ${this._renderDialog(members)}
      </ha-card>
    `;
  }

  _modeButton(value, mode, icon, label) {
    return html`
      <button
        class="mode-btn ${value} ${mode === value ? "active" : ""}"
        aria-label=${label}
        aria-pressed=${mode === value ? "true" : "false"}
        @click=${() => this._setMode(value)}
      >
        <ha-icon icon=${icon}></ha-icon>
      </button>
    `;
  }

  _renderRow(member, automation, mode) {
    const available = member.is_available !== false;
    const running = available && member.is_on;
    const target = this._pending[member.id] ?? member.target_temp;
    const status = member.status;
    const badge = automation && available ? BADGES[status] : undefined;
    const now = member.current_temp == null ? "—" : `${Number(member.current_temp).toFixed(1)}°`;

    let sub = `${now} now`;
    if (!available) sub = automation ? "Unavailable · skipped" : "Unavailable";
    else if (!automation) sub += running ? " · on" : " · off";
    else if (!running && status !== "paused") sub += " · off";

    const powerLabel = automation
      ? `${member.paused ? "Resume" : "Pause"} ${member.name}`
      : `Turn ${member.name} ${running ? "off" : "on"}`;

    return html`
      <div class="row ${available ? "" : "unavailable"}">
        ${automation
          ? html`<div class="rank ${status === "driving" ? "lead" : ""}" aria-label="Priority ${member.priority}">
              ${member.priority}
            </div>`
          : nothing}
        <div class="info">
          <div class="name-line">
            <span class="name">${member.name}</span>
            ${badge ? html`<span class="badge ${badge.tone}">${badge.label}</span>` : nothing}
          </div>
          <div class="sub">
            <span class="wide">${sub}</span>
            <span class="narrow"
              >${available ? now : sub}${badge
                ? html`<span class="tone-${badge.tone}"> · ${badge.label}</span>`
                : available && !running && status !== "paused"
                  ? " · off"
                  : nothing}</span
            >
          </div>
        </div>
        <div class="stepper ${running ? "on" : ""}">
          <button
            aria-label="Lower ${member.name} target"
            ?disabled=${!available || target <= MIN_TEMP}
            @click=${() => this._step(member, -1)}
          >
            <ha-icon icon="mdi:minus"></ha-icon>
          </button>
          <div class="value" aria-live="polite">${available ? `${Math.round(target)}°` : "—"}</div>
          <button
            aria-label="Raise ${member.name} target"
            ?disabled=${!available || target >= MAX_TEMP}
            @click=${() => this._step(member, 1)}
          >
            <ha-icon icon="mdi:plus"></ha-icon>
          </button>
        </div>
        <button
          class="power ${running ? "on" : ""}"
          aria-label=${powerLabel}
          aria-pressed=${running ? "true" : "false"}
          ?disabled=${!available}
          @click=${() => this._togglePower(member)}
        >
          <ha-icon icon="mdi:power"></ha-icon>
        </button>
      </div>
    `;
  }

  // ---------------------------------------------------------------- settings

  _openSettings() {
    const attrs = this._stateObj.attributes;
    this._settings = {
      view: "main",
      tolerance: Number(attrs.tolerance ?? 1.5),
      hysteresis: Number(attrs.hysteresis ?? 0.1),
      priority: [...(attrs.default_priority || this._members().map((m) => m.id))],
      schedules: JSON.parse(JSON.stringify(attrs.schedules || [])),
      editing: null,
      editIndex: -1,
      error: "",
      saving: false,
    };
  }

  _closeSettings() {
    this._settings = null;
  }

  _patch(changes) {
    this._settings = { ...this._settings, ...changes };
  }

  _patchSchedule(changes) {
    this._patch({ editing: { ...this._settings.editing, ...changes }, error: "" });
  }

  _editSchedule(index) {
    const s = this._settings;
    const editing =
      index >= 0
        ? JSON.parse(JSON.stringify(s.schedules[index]))
        : {
            name: "",
            start: "22:00",
            end: "07:00",
            days: DAYS.map(([d]) => d),
            priority_order: [...s.priority],
          };
    const ids = this._members().map((m) => m.id);
    editing.priority_order = [
      ...editing.priority_order.filter((id) => ids.includes(id)),
      ...ids.filter((id) => !editing.priority_order.includes(id)),
    ];
    this._patch({ view: "schedule", editing, editIndex: index, error: "" });
  }

  _finishSchedule() {
    const s = this._settings;
    const editing = { ...s.editing, name: (s.editing.name || "").trim() };
    if (!editing.name) return this._patch({ error: "Give the schedule a name." });
    if (!editing.days.length) return this._patch({ error: "Pick at least one day." });
    if (!editing.start || !editing.end) return this._patch({ error: "Set a start and end time." });
    const schedules = [...s.schedules];
    if (s.editIndex >= 0) schedules[s.editIndex] = editing;
    else schedules.push(editing);
    this._patch({ schedules, view: "main", editing: null, editIndex: -1, error: "" });
  }

  _deleteSchedule() {
    const s = this._settings;
    const schedules = s.schedules.filter((_, i) => i !== s.editIndex);
    this._patch({ schedules, view: "main", editing: null, editIndex: -1 });
  }

  async _saveSettings() {
    const s = this._settings;
    const attrs = this._stateObj.attributes;
    this._patch({ saving: true, error: "" });
    try {
      if (s.tolerance !== Number(attrs.tolerance)) {
        await this._call("set_tolerance", { tolerance: s.tolerance });
      }
      if (s.hysteresis !== Number(attrs.hysteresis)) {
        await this._call("set_hysteresis", { hysteresis: s.hysteresis });
      }
      if (JSON.stringify(s.priority) !== JSON.stringify(attrs.default_priority)) {
        await this._call("set_priority_order", { priority_order: s.priority });
      }
      if (JSON.stringify(s.schedules) !== JSON.stringify(attrs.schedules || [])) {
        await this._call("set_schedules", {
          schedules: s.schedules.map(({ id, name, start, end, days, priority_order }) => ({
            ...(id ? { id } : {}),
            name,
            start,
            end,
            days,
            priority_order,
          })),
        });
      }
      this._closeSettings();
    } catch (err) {
      this._patch({ saving: false, error: err?.message || String(err) });
    }
  }

  _renderOrder(order, onChange) {
    const byId = Object.fromEntries(this._members().map((m) => [m.id, m]));
    return html`
      <ol class="order">
        ${order.map(
          (id, i) => html`
            <li>
              <span class="rank ${i === 0 ? "lead" : ""}">${i + 1}</span>
              <span class="order-name">${byId[id]?.name || id}</span>
              <button
                class="square"
                aria-label="Move ${byId[id]?.name || id} up"
                ?disabled=${i === 0}
                @click=${() => onChange(move(order, i, -1))}
              >
                <ha-icon icon="mdi:chevron-up"></ha-icon>
              </button>
              <button
                class="square"
                aria-label="Move ${byId[id]?.name || id} down"
                ?disabled=${i === order.length - 1}
                @click=${() => onChange(move(order, i, 1))}
              >
                <ha-icon icon="mdi:chevron-down"></ha-icon>
              </button>
            </li>
          `
        )}
      </ol>
    `;
  }

  _renderDialog(members) {
    const s = this._settings;
    return html`
      <dialog
        aria-label="${this._name()} settings"
        @cancel=${(e) => {
          e.preventDefault();
          if (s?.view === "schedule") this._patch({ view: "main", editing: null });
          else this._closeSettings();
        }}
        @click=${(e) => {
          if (e.target !== e.currentTarget) return;
          const r = e.currentTarget.getBoundingClientRect();
          const inside =
            e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
          if (!inside) this._closeSettings();
        }}
      >
        ${!s ? nothing : s.view === "schedule" ? this._renderScheduleView(s) : this._renderMainView(s, members)}
      </dialog>
    `;
  }

  _renderMainView(s, members) {
    const byId = Object.fromEntries(members.map((m) => [m.id, m]));
    return html`
      <div class="dialog-head">
        <h2>${this._name()} settings</h2>
        <button class="icon-btn" aria-label="Close" @click=${this._closeSettings}>
          <ha-icon icon="mdi:close"></ha-icon>
        </button>
      </div>

      <section>
        <h3>Comfort</h3>
        <div class="field">
          <div class="field-head">
            <label for="tolerance">Tolerance</label><span>±${s.tolerance.toFixed(1)}°F</span>
          </div>
          <input
            id="tolerance"
            type="range"
            min="0.5"
            max="5"
            step="0.5"
            .value=${String(s.tolerance)}
            @input=${(e) => this._patch({ tolerance: Number(e.target.value) })}
          />
          <p class="help">How far a room can drift before it asks for heat or cool.</p>
        </div>
        <div class="field">
          <div class="field-head">
            <label for="hysteresis">Hysteresis</label><span>${s.hysteresis.toFixed(1)}°F</span>
          </div>
          <input
            id="hysteresis"
            type="range"
            min="0"
            max="1"
            step="0.1"
            .value=${String(s.hysteresis)}
            @input=${(e) => this._patch({ hysteresis: Number(e.target.value) })}
          />
          <p class="help">Buffer before a room counts as back on target and turns off.</p>
        </div>
      </section>

      <section>
        <h3>Default priority</h3>
        <p class="help">Used whenever no schedule is active.</p>
        ${this._renderOrder(s.priority, (priority) => this._patch({ priority }))}
      </section>

      <section>
        <h3>Schedules</h3>
        ${s.schedules.map(
          (sched, i) => html`
            <button class="schedule" @click=${() => this._editSchedule(i)}>
              <span class="schedule-icon"><ha-icon icon="mdi:clock-outline"></ha-icon></span>
              <span class="schedule-text">
                <span class="schedule-name">${sched.name}</span>
                <span class="help">
                  ${fmtTime(sched.start)} – ${fmtTime(sched.end)} · ${fmtDays(sched.days)} ·
                  ${byId[sched.priority_order[0]]?.name || "?"} first
                </span>
              </span>
              <ha-icon icon="mdi:chevron-right"></ha-icon>
            </button>
          `
        )}
        <button class="add" @click=${() => this._editSchedule(-1)}>
          <ha-icon icon="mdi:plus"></ha-icon>Add schedule
        </button>
      </section>

      ${s.error ? html`<p class="error" role="alert">${s.error}</p>` : nothing}
      <div class="dialog-foot">
        <button class="secondary" @click=${this._closeSettings}>Cancel</button>
        <button class="primary" ?disabled=${s.saving} @click=${this._saveSettings}>
          ${s.saving ? "Saving…" : "Save"}
        </button>
      </div>
    `;
  }

  _renderScheduleView(s) {
    const e = s.editing;
    const back = () => this._patch({ view: "main", editing: null, editIndex: -1, error: "" });
    return html`
      <div class="dialog-head">
        <button class="icon-btn back" aria-label="Back to settings" @click=${back}>
          <ha-icon icon="mdi:chevron-left"></ha-icon>
        </button>
        <h2>${s.editIndex >= 0 ? `${e.name || "Schedule"}` : "New schedule"}</h2>
        <button class="icon-btn" aria-label="Close" @click=${this._closeSettings}>
          <ha-icon icon="mdi:close"></ha-icon>
        </button>
      </div>

      <div class="field">
        <label for="sname">Name</label>
        <input
          id="sname"
          type="text"
          placeholder="Night"
          .value=${e.name}
          @input=${(ev) => this._patchSchedule({ name: ev.target.value })}
        />
      </div>

      <div class="two">
        <div class="field">
          <label for="sstart">Starts</label>
          <input
            id="sstart"
            type="time"
            .value=${e.start}
            @change=${(ev) => this._patchSchedule({ start: ev.target.value })}
          />
        </div>
        <div class="field">
          <label for="send">Ends</label>
          <input
            id="send"
            type="time"
            .value=${e.end}
            @change=${(ev) => this._patchSchedule({ end: ev.target.value })}
          />
        </div>
      </div>
      ${e.end <= e.start && e.end !== e.start
        ? html`<p class="help">Runs overnight, ending the next morning.</p>`
        : nothing}

      <div class="field">
        <span class="label">Days</span>
        <div class="days">
          ${DAYS.map(([day, letter, full]) => {
            const on = e.days.includes(day);
            return html`
              <button
                class="day ${on ? "on" : ""}"
                aria-label=${full}
                aria-pressed=${on ? "true" : "false"}
                @click=${() =>
                  this._patchSchedule({
                    days: on
                      ? e.days.filter((d) => d !== day)
                      : DAYS.map(([d]) => d).filter((d) => d === day || e.days.includes(d)),
                  })}
              >
                ${letter}
              </button>
            `;
          })}
        </div>
      </div>

      <section>
        <h3>Priority during this schedule</h3>
        ${this._renderOrder(e.priority_order, (priority_order) => this._patchSchedule({ priority_order }))}
      </section>

      ${s.error ? html`<p class="error" role="alert">${s.error}</p>` : nothing}
      <div class="dialog-foot">
        ${s.editIndex >= 0
          ? html`<button class="danger-text" @click=${this._deleteSchedule}>Delete schedule</button>`
          : nothing}
        <span class="spacer"></span>
        <button class="secondary" @click=${back}>Cancel</button>
        <button class="primary" @click=${this._finishSchedule}>Done</button>
      </div>
    `;
  }

  // ---------------------------------------------------------------- styles

  static styles = css`
    :host {
      --msc-cool: var(--state-climate-cool-color, #2563eb);
      --msc-heat: var(--state-climate-heat-color, #ea580c);
      --msc-danger: var(--error-color, #dc2626);
      --msc-success: var(--success-color, #16a34a);
      --msc-text: var(--primary-text-color, #1c1917);
      --msc-muted: var(--secondary-text-color, #57534e);
      --msc-line: var(--divider-color, rgba(127, 127, 127, 0.25));
      --msc-surface: var(--secondary-background-color, rgba(127, 127, 127, 0.12));
      --msc-card: var(--card-background-color, var(--ha-card-background, #fff));
      display: block;
      height: 100%;
    }
    ha-card {
      --msc-mode: var(--msc-cool);
      height: 100%;
      box-sizing: border-box;
      padding: 14px 16px 6px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      overflow: hidden;
    }
    ha-card.mode-heat {
      --msc-mode: var(--msc-heat);
    }
    button {
      font: inherit;
      color: inherit;
      cursor: pointer;
    }
    button:disabled {
      cursor: not-allowed;
    }
    button:focus-visible,
    input:focus-visible {
      outline: 2px solid var(--primary-color, #2563eb);
      outline-offset: 2px;
    }
    ha-icon {
      --mdc-icon-size: 20px;
      display: flex;
    }
    .missing {
      padding: 16px;
      color: var(--msc-danger);
    }

    /* header */
    .header {
      height: 44px;
      flex: none;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .title {
      flex: 1;
      min-width: 0;
    }
    h2 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
      line-height: 1.25;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .sub {
      font-size: 12px;
      color: var(--msc-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .controls {
      flex: none;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .auto-switch {
      height: 44px;
      padding: 0 6px;
      border: 0;
      background: none;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 600;
      color: var(--msc-muted);
    }
    .auto-switch[aria-checked="true"] {
      color: var(--msc-text);
    }
    .track {
      position: relative;
      width: 40px;
      height: 24px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--msc-muted) 55%, transparent);
      transition: background 0.15s;
    }
    .auto-switch[aria-checked="true"] .track {
      background: var(--msc-text);
    }
    .knob {
      position: absolute;
      top: 3px;
      left: 3px;
      width: 18px;
      height: 18px;
      border-radius: 999px;
      background: var(--msc-card);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
      transition: transform 0.15s;
    }
    .auto-switch[aria-checked="true"] .knob {
      transform: translateX(16px);
    }
    .mode-pill {
      display: flex;
      padding: 2px;
      border-radius: 999px;
      background: var(--msc-surface);
    }
    .mode-btn {
      width: 40px;
      height: 40px;
      border: 0;
      border-radius: 999px;
      background: transparent;
      color: var(--msc-muted);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .mode-btn ha-icon {
      --mdc-icon-size: 18px;
    }
    .mode-btn.cool.active {
      background: var(--msc-cool);
      color: #fff;
    }
    .mode-btn.heat.active {
      background: var(--msc-heat);
      color: #fff;
    }
    .icon-btn {
      width: 40px;
      height: 44px;
      border: 0;
      border-radius: 12px;
      background: none;
      color: var(--msc-muted);
      display: flex;
      align-items: center;
      justify-content: center;
    }

    /* rows */
    .rows {
      display: flex;
      flex-direction: column;
    }
    .row {
      height: 64px;
      flex: none;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .row + .row {
      border-top: 1px solid var(--msc-line);
    }
    .rank {
      width: 32px;
      height: 32px;
      flex: none;
      box-sizing: border-box;
      border-radius: 999px;
      border: 1.5px solid var(--msc-line);
      color: var(--msc-muted);
      font-size: 14px;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .rank.lead {
      border-color: var(--msc-text);
      background: var(--msc-text);
      color: var(--msc-card);
    }
    .info {
      flex: 1;
      min-width: 0;
      container-type: inline-size;
    }
    .name-line {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
    }
    .name {
      flex: 0 0 auto;
      max-width: 100%;
      font-size: 15px;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .info .sub {
      font-variant-numeric: tabular-nums;
    }
    .sub .narrow {
      display: none;
    }
    .tone-mode {
      color: var(--msc-mode);
    }
    .tone-danger {
      color: var(--msc-danger);
    }
    .tone-success {
      color: var(--msc-success);
    }
    /* Narrow rows: the status moves from a badge into the second line. */
    @container (max-width: 150px) {
      .badge,
      .sub .wide {
        display: none;
      }
      .sub .narrow {
        display: inline;
      }
    }
    .badge {
      flex: 0 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 999px;
      white-space: nowrap;
    }
    .badge.mode {
      color: var(--msc-mode);
      background: color-mix(in srgb, var(--msc-mode) 16%, transparent);
    }
    .badge.danger {
      color: var(--msc-danger);
      background: color-mix(in srgb, var(--msc-danger) 14%, transparent);
    }
    .badge.success {
      color: var(--msc-success);
      background: color-mix(in srgb, var(--msc-success) 14%, transparent);
    }
    .badge.neutral {
      color: var(--msc-muted);
      background: var(--msc-surface);
    }
    .stepper {
      flex: none;
      display: flex;
      align-items: center;
      border: 1px solid var(--msc-line);
      border-radius: 12px;
      color: var(--msc-muted);
    }
    .stepper.on {
      color: var(--msc-mode);
    }
    .stepper button {
      width: 36px;
      height: 44px;
      border: 0;
      background: none;
      color: inherit;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .stepper ha-icon {
      --mdc-icon-size: 18px;
    }
    .stepper button:disabled {
      opacity: 0.4;
    }
    .value {
      width: 44px;
      text-align: center;
      font-size: 18px;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .power {
      width: 44px;
      height: 44px;
      flex: none;
      box-sizing: border-box;
      border: 1.5px solid var(--msc-line);
      border-radius: 12px;
      background: none;
      color: var(--msc-muted);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .power.on {
      border-color: transparent;
      background: color-mix(in srgb, var(--msc-mode) 18%, transparent);
      color: var(--msc-mode);
    }
    .row.unavailable .name {
      color: var(--msc-muted);
    }
    .row.unavailable .rank,
    .row.unavailable .stepper,
    .row.unavailable .power {
      border-style: dashed;
      opacity: 0.6;
    }

    /* settings dialog */
    dialog {
      width: min(460px, calc(100vw - 32px));
      max-height: calc(100vh - 48px);
      box-sizing: border-box;
      padding: 18px 22px;
      border: 0;
      border-radius: 20px;
      background: var(--msc-card);
      color: var(--msc-text);
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
      font-family: var(--paper-font-body1_-_font-family, inherit);
    }
    dialog::backdrop {
      background: rgba(0, 0, 0, 0.5);
    }
    .dialog-head {
      display: flex;
      align-items: center;
      gap: 4px;
      margin-bottom: 8px;
    }
    .dialog-head h2 {
      flex: 1;
      font-size: 20px;
    }
    .back {
      margin-left: -12px;
    }
    section {
      border-top: 1px solid var(--msc-line);
      padding: 14px 0 6px;
    }
    h3 {
      margin: 0 0 8px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--msc-muted);
    }
    .field {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-bottom: 14px;
    }
    .field-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
    label,
    .label {
      font-size: 14px;
      font-weight: 600;
    }
    .help {
      margin: 0;
      font-size: 12px;
      color: var(--msc-muted);
    }
    input[type="range"] {
      width: 100%;
      margin: 0;
      height: 24px;
      accent-color: var(--primary-color, var(--msc-text));
    }
    input[type="text"],
    input[type="time"] {
      height: 44px;
      box-sizing: border-box;
      padding: 0 12px;
      border: 1px solid var(--msc-line);
      border-radius: 10px;
      background: transparent;
      color: inherit;
      font: inherit;
      font-size: 15px;
      color-scheme: light dark;
    }
    .two {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .days {
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 6px;
    }
    .day {
      height: 44px;
      border: 1px solid var(--msc-line);
      border-radius: 10px;
      background: none;
      font-size: 13px;
      font-weight: 600;
    }
    .day.on {
      border-color: var(--msc-text);
      background: var(--msc-text);
      color: var(--msc-card);
    }
    .order {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .order li {
      height: 52px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .order li + li {
      border-top: 1px solid var(--msc-line);
    }
    .order .rank {
      width: 28px;
      height: 28px;
      font-size: 13px;
    }
    .order-name {
      flex: 1;
      font-size: 15px;
      font-weight: 600;
    }
    .square {
      width: 44px;
      height: 44px;
      border: 1px solid var(--msc-line);
      border-radius: 10px;
      background: none;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .square:disabled {
      opacity: 0.35;
    }
    .schedule {
      width: 100%;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 8px 10px 12px;
      margin-bottom: 8px;
      border: 1px solid var(--msc-line);
      border-radius: 12px;
      background: none;
      text-align: left;
    }
    .schedule-icon {
      width: 36px;
      height: 36px;
      flex: none;
      border-radius: 10px;
      background: var(--msc-surface);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .schedule-text {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .schedule-name {
      font-size: 15px;
      font-weight: 600;
    }
    .add {
      width: 100%;
      height: 44px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      border: 1.5px dashed var(--msc-line);
      border-radius: 12px;
      background: none;
      font-size: 14px;
      font-weight: 600;
    }
    .add ha-icon {
      --mdc-icon-size: 18px;
    }
    .error {
      margin: 8px 0 0;
      font-size: 13px;
      color: var(--msc-danger);
    }
    .dialog-foot {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      border-top: 1px solid var(--msc-line);
      padding-top: 14px;
      margin-top: 8px;
    }
    .spacer {
      flex: 1;
    }
    .primary,
    .secondary {
      height: 44px;
      padding: 0 20px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
    }
    .primary {
      border: 0;
      background: var(--msc-text);
      color: var(--msc-card);
    }
    .secondary {
      border: 1px solid var(--msc-line);
      background: none;
    }
    .danger-text {
      height: 44px;
      padding: 0 4px;
      border: 0;
      background: none;
      color: var(--msc-danger);
      font-weight: 600;
    }
  `;
}

customElements.define("mini-split-climate-card", MiniSplitClimateCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "mini-split-climate-card",
  name: "Mini Split Climate Group",
  description: "Priority ladder for a mini split climate group: per-room targets, shared mode, automation.",
  preview: true,
});
