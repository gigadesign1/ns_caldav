/**
 * NS Perronbord card for the "NS CalDAV Trip" integration.
 *
 * Renders the next NS trip (from sensor.ns_trip_next_trip_summary) as an
 * authentic NS departure-board (perronbord) widget. Two visual variants:
 *   - "board": the calm, on-time NS-blue departure screen (default).
 *   - "alert": an emphasised NS-yellow pop-out used when the trip is delayed
 *     or disrupted.
 *
 * No build step / no Lit dependency: a plain custom element that swaps its
 * innerHTML when `hass` updates.
 */

const NS_BLUE = "#003082";
const NS_YELLOW = "#ffc917";
const NS_RED = "#db0029";

const STYLES = `
  :host { display: block; }
  .ns-card {
    box-sizing: border-box;
    border-radius: var(--ha-card-border-radius, 12px);
    overflow: hidden;
    font-family: var(--paper-font-body1_-_font-family, "Roboto", "Helvetica Neue", Arial, sans-serif);
    -webkit-font-smoothing: antialiased;
  }

  /* ---------- shared bits ---------- */
  .ns-time { font-variant-numeric: tabular-nums; font-weight: 800; line-height: 1; }
  .ns-strike { text-decoration: line-through; opacity: 0.55; }
  .ns-spoor {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    border-radius: 8px; padding: 6px 12px; min-width: 64px;
  }
  .ns-spoor .ns-spoor-label { font-size: 0.8rem; font-weight: 700; text-transform: lowercase; letter-spacing: 0.02em; }
  .ns-spoor .ns-spoor-value { font-weight: 800; line-height: 1; }

  /* ---------- board (on time) ---------- */
  .ns-board {
    background: ${NS_BLUE};
    color: #fff;
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 18px;
    align-items: center;
    padding: 18px 20px;
  }
  .ns-board .ns-time { color: ${NS_YELLOW}; font-size: 2.9rem; }
  .ns-board .ns-countdown { color: #fff; font-size: 0.95rem; margin-top: 6px; opacity: 0.9; }
  .ns-board .ns-dest { color: ${NS_YELLOW}; font-size: 1.7rem; font-weight: 800; line-height: 1.1; }
  .ns-board .ns-train { color: #fff; font-size: 1rem; margin-top: 4px; opacity: 0.95; }
  .ns-board .ns-via { color: #cdd9ef; font-size: 0.9rem; margin-top: 2px; }
  .ns-board .ns-foot { display: flex; align-items: center; gap: 12px; margin-top: 10px; color: #cdd9ef; font-size: 0.85rem; }
  .ns-board .ns-foot ha-icon { --mdc-icon-size: 18px; }
  .ns-board .ns-delay { color: ${NS_YELLOW}; font-weight: 700; }
  .ns-board .ns-spoor { background: ${NS_YELLOW}; color: ${NS_BLUE}; }
  .ns-board .ns-spoor .ns-spoor-value { font-size: 2rem; }
  .ns-board .ns-divider { width: 1px; align-self: stretch; background: rgba(255,255,255,0.18); }

  /* ---------- alert (delayed / disrupted) ---------- */
  .ns-alert {
    background: ${NS_YELLOW};
    color: ${NS_BLUE};
  }
  .ns-alert .ns-topbar {
    background: ${NS_RED}; color: #fff;
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 16px; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase;
  }
  .ns-alert .ns-topbar .ns-tag { display: flex; align-items: center; gap: 8px; font-size: 0.95rem; }
  .ns-alert .ns-topbar ha-icon { --mdc-icon-size: 20px; }
  .ns-alert .ns-body { padding: 16px 20px 18px; }
  .ns-alert .ns-dest { font-size: 2rem; font-weight: 800; line-height: 1.05; }
  .ns-alert .ns-train { font-size: 1.05rem; margin-top: 2px; font-weight: 600; }
  .ns-alert hr { border: none; border-top: 2px solid rgba(0,48,130,0.25); margin: 14px 0; }
  .ns-alert .ns-times { display: flex; align-items: flex-end; gap: 18px; flex-wrap: wrap; }
  .ns-alert .ns-col-label { font-size: 0.8rem; font-weight: 700; text-transform: none; }
  .ns-alert .ns-planned .ns-time { font-size: 1.6rem; color: ${NS_BLUE}; }
  .ns-alert .ns-new .ns-time { font-size: 2.6rem; }
  .ns-alert .ns-badge {
    background: ${NS_RED}; color: #fff; border-radius: 8px; padding: 6px 12px;
    font-weight: 800; line-height: 1.1; text-align: center; align-self: center;
  }
  .ns-alert .ns-badge small { display: block; font-weight: 700; font-size: 0.7rem; }
  .ns-alert .ns-spoor { background: ${NS_BLUE}; color: ${NS_YELLOW}; margin-left: auto; }
  .ns-alert .ns-spoor .ns-spoor-value { font-size: 1.9rem; }
  .ns-alert .ns-message {
    display: flex; align-items: center; gap: 12px;
    background: rgba(219,0,41,0.12); border: 2px solid rgba(219,0,41,0.45);
    border-radius: 10px; padding: 10px 14px; margin-top: 14px; color: #8a0019;
  }
  .ns-alert .ns-message ha-icon { --mdc-icon-size: 26px; color: ${NS_RED}; flex: 0 0 auto; }
  .ns-alert .ns-message .ns-msg-title { font-weight: 800; }

  /* ---------- empty ---------- */
  .ns-empty {
    background: ${NS_BLUE}; color: #cdd9ef;
    display: flex; align-items: center; gap: 12px; padding: 18px 20px; font-size: 1rem;
  }
  .ns-empty ha-icon { --mdc-icon-size: 24px; color: ${NS_YELLOW}; }
`;

function pad2(n) {
  return String(n).padStart(2, "0");
}

function hhmm(iso) {
  if (!iso) return "--:--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--";
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function minutesUntil(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return Math.max(0, Math.round((d.getTime() - Date.now()) / 60000));
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

class NsPerronbordCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = undefined;
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Invalid configuration");
    }
    const variant = config.variant || "board";
    if (variant !== "board" && variant !== "alert") {
      throw new Error('variant must be "board" or "alert"');
    }
    this._config = {
      // null => auto-discover the trip summary entity (language-independent).
      entity: config.entity || null,
      variant,
    };
    this._autoEntity = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._config.variant === "alert" ? 4 : 2;
  }

  static getStubConfig() {
    return { variant: "board" };
  }

  _resolveEntityId() {
    // Explicitly configured entity always wins.
    if (this._config.entity) return this._config.entity;
    if (!this._hass) return null;

    // Cached auto-discovery still valid?
    if (this._autoEntity && this._hass.states[this._autoEntity]) {
      return this._autoEntity;
    }

    // The trip summary sensor is the only entity exposing `summary_text`,
    // so we can find it regardless of the (localized) entity_id.
    const found = Object.keys(this._hass.states).find((id) => {
      if (!id.startsWith("sensor.")) return false;
      const attrs = this._hass.states[id].attributes;
      return attrs && Object.prototype.hasOwnProperty.call(attrs, "summary_text");
    });
    this._autoEntity = found || null;
    return this._autoEntity;
  }

  _trip() {
    if (!this._hass) return null;
    const entityId = this._resolveEntityId();
    if (!entityId) return null;
    const state = this._hass.states[entityId];
    if (!state || state.state === "unavailable" || state.state === "unknown") {
      return null;
    }
    return state;
  }

  _render() {
    if (!this.shadowRoot) return;
    const trip = this._trip();

    let inner;
    if (!trip) {
      inner = this._renderEmpty();
    } else {
      const a = trip.attributes || {};
      const delayed = Number(a.departure_delay_minutes || 0) > 0 ||
        Number(a.arrival_delay_minutes || 0) > 0 || Boolean(a.is_delayed);
      const disrupted = Boolean(a.is_disrupted) ||
        (a.status && a.status !== "NORMAL");
      const useAlert = this._config.variant === "alert" || delayed || disrupted;
      inner = useAlert
        ? this._renderAlert(a, { delayed, disrupted })
        : this._renderBoard(a);
    }

    this.shadowRoot.innerHTML = `<style>${STYLES}</style>${inner}`;
  }

  _legInfo(a) {
    const legs = Array.isArray(a.legs) ? a.legs : [];
    const transit = legs.find((l) => l && l.type === "PUBLIC_TRANSIT") || legs[0] || {};
    return {
      train: transit.name || null,
      direction: transit.direction || null,
    };
  }

  _renderBoard(a) {
    const dep = a.departure_station || {};
    const arr = a.arrival_station || {};
    const { train, direction } = this._legInfo(a);
    const depDelay = Number(a.departure_delay_minutes || 0);
    const depTime = hhmm(a.actual_departure);
    const planned = hhmm(a.planned_departure);
    const until = minutesUntil(a.actual_departure);
    const transfers = a.transfers;
    const track = dep.track || a.departure_track;

    const delayHtml = depDelay > 0
      ? `<span class="ns-strike">${planned}</span> <span class="ns-delay">+${depDelay}</span>`
      : "";

    const footParts = [];
    if (until !== null) footParts.push(`<span>over ${until} min</span>`);
    if (delayHtml) footParts.push(delayHtml);
    if (transfers !== null && transfers !== undefined) {
      footParts.push(`<span><ha-icon icon="mdi:transit-transfer"></ha-icon> ${transfers}</span>`);
    }
    if (a.crowd_forecast && a.crowd_forecast !== "UNKNOWN") {
      footParts.push(`<span><ha-icon icon="mdi:account-group"></ha-icon> ${escapeHtml(this._crowdLabel(a.crowd_forecast))}</span>`);
    }

    const spoor = track
      ? `<div class="ns-spoor"><span class="ns-spoor-label">spoor</span><span class="ns-spoor-value">${escapeHtml(track)}</span></div>`
      : "";

    return `
      <div class="ns-card ns-board">
        <div class="ns-left">
          <div class="ns-time">${depTime}</div>
        </div>
        <div class="ns-center">
          <div class="ns-dest">${escapeHtml(arr.name || "—")}</div>
          ${train ? `<div class="ns-train">${escapeHtml(train)}${direction ? ` ri. ${escapeHtml(direction)}` : ""}</div>` : ""}
          <div class="ns-foot">${footParts.join("")}</div>
        </div>
        ${spoor}
      </div>
    `;
  }

  _renderAlert(a, { disrupted }) {
    const arr = a.arrival_station || {};
    const dep = a.departure_station || {};
    const { train } = this._legInfo(a);
    const depDelay = Number(a.departure_delay_minutes || 0);
    const planned = hhmm(a.planned_departure);
    const actual = hhmm(a.actual_departure);
    const track = dep.track || a.departure_track;
    const status = a.status && a.status !== "NORMAL" ? a.status : null;
    const tag = disrupted ? this._statusLabel(status || "DISRUPTION") : "Vertraging";
    const icon = disrupted ? "mdi:alert-octagon" : "mdi:alert";

    const spoor = track
      ? `<div class="ns-spoor"><span class="ns-spoor-label">spoor</span><span class="ns-spoor-value">${escapeHtml(track)}</span></div>`
      : "";

    let timesBlock;
    if (depDelay > 0) {
      timesBlock = `
        <div class="ns-times">
          <div class="ns-planned">
            <div class="ns-col-label">Gepland</div>
            <div class="ns-time ns-strike">${planned}</div>
          </div>
          <div class="ns-new">
            <div class="ns-col-label">Nieuwe vertrektijd</div>
            <div class="ns-time">${actual}</div>
          </div>
          <div class="ns-badge">+${depDelay} min<small>vertraging</small></div>
          ${spoor}
        </div>`;
    } else {
      timesBlock = `
        <div class="ns-times">
          <div class="ns-new">
            <div class="ns-col-label">Vertrek</div>
            <div class="ns-time">${actual}</div>
          </div>
          ${spoor}
        </div>`;
    }

    const messages = Array.isArray(a.messages) ? a.messages : [];
    const messageHtml = this._renderMessage(messages, status);

    return `
      <div class="ns-card ns-alert">
        <div class="ns-topbar">
          <span></span>
          <span class="ns-tag"><ha-icon icon="${icon}"></ha-icon> ${tag}</span>
        </div>
        <div class="ns-body">
          <div class="ns-dest">${escapeHtml(arr.name || "—")}</div>
          ${train ? `<div class="ns-train">${escapeHtml(train)}</div>` : ""}
          <hr />
          ${timesBlock}
          ${messageHtml}
        </div>
      </div>
    `;
  }

  _renderMessage(messages, status) {
    let title = null;
    let text = null;
    if (messages.length) {
      const m = messages[0];
      title = m.title || m.head || null;
      text = m.text || m.message || m.body || null;
    }
    if (!title && !text && status) {
      title = this._statusLabel(status);
    }
    if (!title && !text) return "";
    return `
      <div class="ns-message">
        <ha-icon icon="mdi:alert"></ha-icon>
        <div>
          ${title ? `<div class="ns-msg-title">${escapeHtml(title)}</div>` : ""}
          ${text ? `<div class="ns-msg-text">${escapeHtml(text)}</div>` : ""}
        </div>
      </div>`;
  }

  _statusLabel(status) {
    switch (status) {
      case "CANCELLED": return "Rit vervallen";
      case "DISRUPTION": return "Verstoring";
      case "MAINTENANCE": return "Werkzaamheden";
      case "ALTERNATIVE_TRANSPORT": return "Vervangend vervoer";
      default: return status;
    }
  }

  _crowdLabel(value) {
    switch (value) {
      case "LOW": return "rustig";
      case "MEDIUM": return "gemiddeld";
      case "HIGH": return "druk";
      default: return value;
    }
  }

  _renderEmpty() {
    return `
      <div class="ns-card ns-empty">
        <ha-icon icon="mdi:train"></ha-icon>
        <span>Geen reis gepland</span>
      </div>`;
  }
}

if (!customElements.get("ns-perronbord-card")) {
  customElements.define("ns-perronbord-card", NsPerronbordCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "ns-perronbord-card")) {
  window.customCards.push({
    type: "ns-perronbord-card",
    name: "NS Perronbord",
    description: "NS departure-board style card for the next NS trip.",
    preview: false,
  });
}

console.info(
  "%c NS-PERRONBORD-CARD %c loaded ",
  `background:${NS_BLUE};color:${NS_YELLOW};font-weight:700;border-radius:3px 0 0 3px;padding:2px 6px`,
  `background:${NS_YELLOW};color:${NS_BLUE};font-weight:700;border-radius:0 3px 3px 0;padding:2px 6px`
);
