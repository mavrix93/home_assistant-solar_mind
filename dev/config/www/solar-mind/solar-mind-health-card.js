/**
 * Solar Mind System Health Card
 * Displays system health, diagnostics, and warnings
 */

class SolarMindHealthCard extends HTMLElement {
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
      title: config.title || 'System Health',
      show_temperatures: config.show_temperatures !== false,
      show_cycles: config.show_cycles !== false,
      show_warnings: config.show_warnings !== false,
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

    const healthScore = parseFloat(state.state) || 0;
    const attrs = state.attributes || {};

    this.shadowRoot.innerHTML = `
      <style>
        .card-content {
          padding: 16px;
        }
        
        .health-score-container {
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 20px;
        }
        .health-score-ring {
          position: relative;
          width: 120px;
          height: 120px;
        }
        .health-score-ring svg {
          transform: rotate(-90deg);
        }
        .health-score-ring circle {
          fill: none;
          stroke-width: 10;
        }
        .health-score-ring .bg {
          stroke: var(--divider-color, #424242);
        }
        .health-score-ring .fg {
          stroke-linecap: round;
          transition: stroke-dashoffset 0.5s ease;
        }
        .health-score-ring .fg.excellent { stroke: #4caf50; }
        .health-score-ring .fg.good { stroke: #8bc34a; }
        .health-score-ring .fg.fair { stroke: #ff9800; }
        .health-score-ring .fg.poor { stroke: #f44336; }
        
        .health-score-value {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          text-align: center;
        }
        .health-score-number {
          font-size: 32px;
          font-weight: bold;
          color: var(--primary-text-color);
        }
        .health-score-label {
          font-size: 12px;
          color: var(--secondary-text-color);
        }
        
        .metrics-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
          margin-bottom: 16px;
        }
        .metric-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px;
          background: var(--card-background-color, #1c1c1c);
          border-radius: 8px;
        }
        .metric-icon {
          font-size: 24px;
          min-width: 32px;
          text-align: center;
        }
        .metric-content {
          flex: 1;
        }
        .metric-value {
          font-size: 18px;
          font-weight: bold;
          color: var(--primary-text-color);
        }
        .metric-label {
          font-size: 11px;
          color: var(--secondary-text-color);
        }
        .metric-value.warning { color: #ff9800; }
        .metric-value.danger { color: #f44336; }
        
        .warnings-section {
          margin-top: 16px;
        }
        .section-title {
          font-size: 12px;
          font-weight: 600;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          margin-bottom: 8px;
        }
        .warning-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 12px;
          background: rgba(255, 152, 0, 0.1);
          border-left: 3px solid #ff9800;
          border-radius: 4px;
          margin-bottom: 8px;
          font-size: 13px;
          color: var(--primary-text-color);
        }
        .warning-item.error {
          background: rgba(244, 67, 54, 0.1);
          border-left-color: #f44336;
        }
        .warning-icon {
          font-size: 16px;
        }
        
        .no-warnings {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px;
          background: rgba(76, 175, 80, 0.1);
          border-radius: 8px;
          color: #4caf50;
          font-size: 14px;
        }
        
        .errors-section {
          margin-top: 16px;
        }
        .error-item {
          padding: 8px 12px;
          background: rgba(244, 67, 54, 0.1);
          border-radius: 4px;
          margin-bottom: 4px;
          font-size: 12px;
        }
        .error-time {
          color: var(--secondary-text-color);
          font-size: 10px;
        }
        .error-message {
          color: var(--primary-text-color);
        }
        
        .cycles-bar {
          display: flex;
          gap: 8px;
          margin-top: 12px;
        }
        .cycle-stat {
          flex: 1;
          text-align: center;
          padding: 8px;
          background: var(--card-background-color, #1c1c1c);
          border-radius: 8px;
        }
        .cycle-value {
          font-size: 20px;
          font-weight: bold;
          color: var(--primary-text-color);
        }
        .cycle-label {
          font-size: 10px;
          color: var(--secondary-text-color);
        }
      </style>
      
      <ha-card header="${this.config.title}">
        <div class="card-content">
          <!-- Health Score Ring -->
          <div class="health-score-container">
            <div class="health-score-ring">
              <svg width="120" height="120">
                <circle class="bg" cx="60" cy="60" r="50" />
                <circle class="fg ${this._getHealthClass(healthScore)}" cx="60" cy="60" r="50"
                  stroke-dasharray="${Math.PI * 100}"
                  stroke-dashoffset="${Math.PI * 100 * (1 - healthScore / 100)}" />
              </svg>
              <div class="health-score-value">
                <div class="health-score-number">${Math.round(healthScore)}</div>
                <div class="health-score-label">${this._getHealthLabel(healthScore)}</div>
              </div>
            </div>
          </div>
          
          <!-- Temperature Metrics -->
          ${this.config.show_temperatures ? `
            <div class="metrics-grid">
              <div class="metric-item">
                <div class="metric-icon">🔋</div>
                <div class="metric-content">
                  <div class="metric-value ${this._getTempClass(attrs.battery_temperature)}">
                    ${attrs.battery_temperature !== null ? `${attrs.battery_temperature}°C` : 'N/A'}
                  </div>
                  <div class="metric-label">Battery Temp</div>
                </div>
              </div>
              <div class="metric-item">
                <div class="metric-icon">⚡</div>
                <div class="metric-content">
                  <div class="metric-value ${this._getTempClass(attrs.inverter_temperature, 50, 60)}">
                    ${attrs.inverter_temperature !== null ? `${attrs.inverter_temperature}°C` : 'N/A'}
                  </div>
                  <div class="metric-label">Inverter Temp</div>
                </div>
              </div>
            </div>
          ` : ''}
          
          <!-- Cycle Counts -->
          ${this.config.show_cycles ? `
            <div class="cycles-bar">
              <div class="cycle-stat">
                <div class="cycle-value">${attrs.charge_cycles_today || 0}</div>
                <div class="cycle-label">Charge Cycles</div>
              </div>
              <div class="cycle-stat">
                <div class="cycle-value">${attrs.discharge_cycles_today || 0}</div>
                <div class="cycle-label">Discharge Cycles</div>
              </div>
              <div class="cycle-stat">
                <div class="cycle-value">${attrs.mode_changes_today || 0}</div>
                <div class="cycle-label">Mode Changes</div>
              </div>
            </div>
          ` : ''}
          
          <!-- Warnings -->
          ${this.config.show_warnings ? `
            <div class="warnings-section">
              <div class="section-title">System Status</div>
              ${(attrs.active_warnings || []).length === 0 ? `
                <div class="no-warnings">
                  <span>✅</span>
                  <span>All systems operating normally</span>
                </div>
              ` : `
                ${(attrs.active_warnings || []).map(w => `
                  <div class="warning-item">
                    <span class="warning-icon">⚠️</span>
                    <span>${this._escapeHtml(w)}</span>
                  </div>
                `).join('')}
              `}
            </div>
          ` : ''}
          
          <!-- Recent Errors -->
          ${(attrs.recent_errors || []).length > 0 ? `
            <div class="errors-section">
              <div class="section-title">Recent Errors</div>
              ${(attrs.recent_errors || []).slice(0, 3).map(e => `
                <div class="error-item">
                  <div class="error-time">${this._formatTime(e.timestamp)}</div>
                  <div class="error-message">${this._escapeHtml(e.error)}</div>
                </div>
              `).join('')}
            </div>
          ` : ''}
        </div>
      </ha-card>
    `;
  }

  _getHealthClass(score) {
    if (score >= 90) return 'excellent';
    if (score >= 70) return 'good';
    if (score >= 50) return 'fair';
    return 'poor';
  }

  _getHealthLabel(score) {
    if (score >= 90) return 'Excellent';
    if (score >= 70) return 'Good';
    if (score >= 50) return 'Fair';
    return 'Needs Attention';
  }

  _getTempClass(temp, warnThreshold = 40, dangerThreshold = 50) {
    if (temp === null || temp === undefined) return '';
    if (temp >= dangerThreshold) return 'danger';
    if (temp >= warnThreshold) return 'warning';
    return '';
  }

  _formatTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  getCardSize() {
    return 5;
  }

  static getStubConfig() {
    return {
      entity: 'sensor.solar_mind_system_health',
      title: 'System Health'
    };
  }
}

customElements.define('solar-mind-health-card', SolarMindHealthCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'solar-mind-health-card',
  name: 'Solar Mind Health',
  description: 'Displays system health, diagnostics, and warnings'
});
