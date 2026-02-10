/**
 * Solar Mind Events Timeline Card
 * Displays system events in a timeline format
 */

class SolarMindEventsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('Please define an entity');
    }
    this.config = {
      entity: config.entity,
      title: config.title || 'System Events',
      max_events: config.max_events || 10,
      show_time: config.show_time !== false,
      ...config
    };
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  render() {
    if (!this._hass || !this.config) return;

    const entityId = this.config.entity;
    const state = this._hass.states[entityId];
    
    if (!state) {
      this.shadowRoot.innerHTML = `
        <ha-card header="${this.config.title}">
          <div class="card-content">Entity not found: ${entityId}</div>
        </ha-card>
      `;
      return;
    }

    const attrs = state.attributes || {};
    const events = Array.isArray(attrs.events) ? attrs.events.slice(0, this.config.max_events) : [];

    this.shadowRoot.innerHTML = `
      <style>
        .card-content {
          padding: 0 16px 16px;
        }
        .events-timeline {
          position: relative;
          padding-left: 24px;
        }
        .events-timeline::before {
          content: '';
          position: absolute;
          left: 8px;
          top: 0;
          bottom: 0;
          width: 2px;
          background: var(--divider-color, #424242);
        }
        .event-item {
          position: relative;
          padding: 12px 0;
          border-bottom: 1px solid var(--divider-color, #424242);
        }
        .event-item:last-child {
          border-bottom: none;
        }
        .event-dot {
          position: absolute;
          left: -20px;
          top: 16px;
          width: 12px;
          height: 12px;
          border-radius: 50%;
          background: var(--primary-color);
          border: 2px solid var(--card-background-color, #1c1c1c);
        }
        .event-dot.info { background: #2196f3; }
        .event-dot.success { background: #4caf50; }
        .event-dot.warning { background: #ff9800; }
        .event-dot.error { background: #f44336; }
        
        .event-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          margin-bottom: 4px;
        }
        .event-title {
          font-weight: 500;
          font-size: 14px;
          color: var(--primary-text-color);
        }
        .event-time {
          font-size: 11px;
          color: var(--secondary-text-color);
          white-space: nowrap;
          margin-left: 8px;
        }
        .event-description {
          font-size: 12px;
          color: var(--secondary-text-color);
          line-height: 1.4;
        }
        .event-type-badge {
          display: inline-block;
          padding: 2px 8px;
          border-radius: 10px;
          font-size: 10px;
          font-weight: 500;
          text-transform: uppercase;
          margin-top: 4px;
        }
        .badge-strategy_changed { background: #9c27b0; color: white; }
        .badge-battery_full { background: #4caf50; color: white; }
        .badge-battery_low { background: #ff9800; color: white; }
        .badge-charge_started { background: #2196f3; color: white; }
        .badge-charge_completed { background: #4caf50; color: white; }
        .badge-discharge_started { background: #ff5722; color: white; }
        .badge-discharge_completed { background: #4caf50; color: white; }
        .badge-weather_changed { background: #00bcd4; color: white; }
        .badge-price_spike { background: #f44336; color: white; }
        .badge-price_drop { background: #4caf50; color: white; }
        .badge-system_error { background: #f44336; color: white; }
        .badge-system_warning { background: #ff9800; color: white; }
        
        .no-events {
          text-align: center;
          padding: 24px;
          color: var(--secondary-text-color);
        }
        .no-events-icon {
          font-size: 48px;
          margin-bottom: 8px;
        }
      </style>
      
      <ha-card header="${this.config.title}">
        <div class="card-content">
          ${events.length === 0 ? `
            <div class="no-events">
              <div class="no-events-icon">📋</div>
              <div>No events yet</div>
            </div>
          ` : `
            <div class="events-timeline">
              ${events.map(event => this._renderEvent(event)).join('')}
            </div>
          `}
        </div>
      </ha-card>
    `;
  }

  _renderEvent(event) {
    const timestamp = new Date(event.timestamp);
    const timeStr = this._formatTime(timestamp);
    const severity = event.severity || 'info';
    const eventType = event.event_type || 'unknown';
    
    return `
      <div class="event-item">
        <div class="event-dot ${severity}"></div>
        <div class="event-header">
          <span class="event-title">${this._escapeHtml(event.title)}</span>
          ${this.config.show_time ? `<span class="event-time">${timeStr}</span>` : ''}
        </div>
        <div class="event-description">${this._escapeHtml(event.description)}</div>
        <span class="event-type-badge badge-${eventType}">${this._formatEventType(eventType)}</span>
      </div>
    `;
  }

  _formatTime(date) {
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString();
  }

  _formatEventType(type) {
    return type.replace(/_/g, ' ');
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  getCardSize() {
    return 4;
  }

  static getStubConfig() {
    return {
      entity: 'sensor.solar_mind_recent_events',
      title: 'System Events',
      max_events: 10
    };
  }
}

customElements.define('solar-mind-events-card', SolarMindEventsCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'solar-mind-events-card',
  name: 'Solar Mind Events Timeline',
  description: 'Displays system events in a timeline format'
});
