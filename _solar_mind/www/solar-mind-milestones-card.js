/**
 * Solar Mind Milestones Card
 * Displays upcoming milestones and appliance recommendations
 */

class SolarMindMilestonesCard extends HTMLElement {
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
      title: config.title || 'Upcoming Milestones',
      max_milestones: config.max_milestones || 6,
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
    const milestones = (attrs.milestones || []).slice(0, this.config.max_milestones);

    this.shadowRoot.innerHTML = `
      <style>
        .card-content {
          padding: 0 16px 16px;
        }
        .milestones-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .milestone-item {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 12px;
          background: var(--card-background-color, #1c1c1c);
          border-radius: 12px;
          border-left: 4px solid var(--primary-color);
          transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .milestone-item:hover {
          transform: translateX(4px);
          box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }
        .milestone-item.high-priority {
          border-left-color: #f44336;
        }
        .milestone-item.medium-priority {
          border-left-color: #ff9800;
        }
        .milestone-item.low-priority {
          border-left-color: #4caf50;
        }
        
        .milestone-icon {
          font-size: 28px;
          min-width: 36px;
          text-align: center;
        }
        
        .milestone-content {
          flex: 1;
          min-width: 0;
        }
        .milestone-title {
          font-weight: 600;
          font-size: 14px;
          color: var(--primary-text-color);
          margin-bottom: 4px;
        }
        .milestone-description {
          font-size: 12px;
          color: var(--secondary-text-color);
          line-height: 1.4;
        }
        
        .milestone-time {
          text-align: right;
          min-width: 60px;
        }
        .milestone-time-value {
          font-size: 16px;
          font-weight: bold;
          color: var(--primary-text-color);
        }
        .milestone-time-label {
          font-size: 10px;
          color: var(--secondary-text-color);
        }
        
        .appliance-section {
          margin-top: 16px;
          padding-top: 16px;
          border-top: 1px solid var(--divider-color, #424242);
        }
        .appliance-section-title {
          font-size: 12px;
          font-weight: 600;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          margin-bottom: 12px;
        }
        .appliance-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 8px;
        }
        .appliance-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 12px;
          background: var(--card-background-color, #1c1c1c);
          border-radius: 8px;
          text-align: center;
        }
        .appliance-icon {
          font-size: 24px;
          margin-bottom: 4px;
        }
        .appliance-name {
          font-size: 11px;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
        }
        .appliance-time {
          font-size: 16px;
          font-weight: bold;
          color: var(--primary-color);
        }
        
        .no-milestones {
          text-align: center;
          padding: 32px;
          color: var(--secondary-text-color);
        }
        .no-milestones-icon {
          font-size: 48px;
          margin-bottom: 8px;
        }
      </style>
      
      <ha-card header="${this.config.title}">
        <div class="card-content">
          ${milestones.length === 0 ? `
            <div class="no-milestones">
              <div class="no-milestones-icon">🎯</div>
              <div>No upcoming milestones</div>
            </div>
          ` : `
            <div class="milestones-list">
              ${milestones.filter(m => m.milestone_type !== 'best_appliance_time').map(m => this._renderMilestone(m)).join('')}
            </div>
            
            ${this._renderApplianceRecommendations(milestones.filter(m => m.milestone_type === 'best_appliance_time'))}
          `}
        </div>
      </ha-card>
    `;
  }

  _renderMilestone(milestone) {
    const icon = this._getMilestoneIcon(milestone.milestone_type);
    const time = new Date(milestone.timestamp);
    const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const priority = milestone.priority >= 4 ? 'high' : milestone.priority >= 2 ? 'medium' : 'low';
    
    return `
      <div class="milestone-item ${priority}-priority">
        <div class="milestone-icon">${icon}</div>
        <div class="milestone-content">
          <div class="milestone-title">${this._escapeHtml(milestone.title)}</div>
          <div class="milestone-description">${this._escapeHtml(milestone.description)}</div>
        </div>
        <div class="milestone-time">
          <div class="milestone-time-value">${timeStr}</div>
          <div class="milestone-time-label">${this._getRelativeTime(time)}</div>
        </div>
      </div>
    `;
  }

  _renderApplianceRecommendations(appliances) {
    if (appliances.length === 0) return '';
    
    return `
      <div class="appliance-section">
        <div class="appliance-section-title">Best Times for Appliances</div>
        <div class="appliance-grid">
          ${appliances.map(a => {
            const icon = this._getApplianceIcon(a.data?.appliance || a.title);
            const time = new Date(a.timestamp);
            const timeStr = time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            return `
              <div class="appliance-item">
                <div class="appliance-icon">${icon}</div>
                <div class="appliance-name">${this._escapeHtml(a.data?.appliance || a.title)}</div>
                <div class="appliance-time">${timeStr}</div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }

  _getMilestoneIcon(type) {
    const icons = {
      'surplus_start': '☀️',
      'cheap_charge_time': '⚡',
      'battery_full': '🔋',
      'battery_low': '🪫',
      'best_appliance_time': '🔌',
      'price_spike': '📈',
      'price_drop': '📉'
    };
    return icons[type] || '🎯';
  }

  _getApplianceIcon(name) {
    const nameLower = (name || '').toLowerCase();
    if (nameLower.includes('water') || nameLower.includes('heater')) return '🚿';
    if (nameLower.includes('wash')) return '🧺';
    if (nameLower.includes('dish')) return '🍽️';
    if (nameLower.includes('dryer')) return '👕';
    if (nameLower.includes('car') || nameLower.includes('ev')) return '🚗';
    if (nameLower.includes('pool')) return '🏊';
    return '🔌';
  }

  _getRelativeTime(date) {
    const now = new Date();
    const diffMs = date - now;
    const diffMins = Math.round(diffMs / 60000);
    const diffHours = Math.round(diffMins / 60);
    
    if (diffMins < 0) return 'Now';
    if (diffMins < 60) return `in ${diffMins}m`;
    if (diffHours < 24) return `in ${diffHours}h`;
    return date.toLocaleDateString();
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
      entity: 'sensor.solar_mind_next_milestone',
      title: 'Upcoming Milestones',
      max_milestones: 6
    };
  }
}

customElements.define('solar-mind-milestones-card', SolarMindMilestonesCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'solar-mind-milestones-card',
  name: 'Solar Mind Milestones',
  description: 'Displays upcoming milestones and appliance recommendations'
});
