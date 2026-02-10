/**
 * Solar Mind Energy Flow Card
 * Visualizes energy flow between solar panels, battery, grid, and house
 */

class SolarMindEnergyFlowCard extends HTMLElement {
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
      title: config.title || 'Energy Flow',
      show_values: config.show_values !== false,
      animate: config.animate !== false,
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
    const batterySOC = attrs.battery_soc || 0;
    const status = attrs.status || 'unknown';
    const gridImport = attrs.grid_import || 0;
    const gridExport = attrs.grid_export || 0;
    const houseLoad = attrs.house_load || 0;
    const currentPrice = attrs.current_price;

    // Determine flow directions
    const isCharging = status === 'charging';
    const isDischarging = status === 'discharging';
    const isSelfUse = status === 'self_use';
    const isGridToHouse = status === 'house_from_grid';

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --flow-color-solar: #ffc107;
          --flow-color-battery: #4caf50;
          --flow-color-grid: #2196f3;
          --flow-color-house: #ff9800;
          --flow-color-inactive: #424242;
        }
        .card-content {
          padding: 16px;
        }
        .energy-flow-container {
          display: grid;
          grid-template-columns: 1fr 1fr 1fr;
          grid-template-rows: auto auto auto;
          gap: 8px;
          text-align: center;
          min-height: 280px;
        }
        .node {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 12px;
          border-radius: 12px;
          background: var(--card-background-color, #1c1c1c);
          border: 2px solid var(--divider-color, #424242);
          transition: all 0.3s ease;
        }
        .node.active {
          border-color: var(--primary-color);
          box-shadow: 0 0 20px rgba(var(--rgb-primary-color), 0.3);
        }
        .node-icon {
          font-size: 32px;
          margin-bottom: 8px;
        }
        .node-value {
          font-size: 18px;
          font-weight: bold;
          color: var(--primary-text-color);
        }
        .node-label {
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-top: 4px;
        }
        .node-solar { grid-column: 2; grid-row: 1; }
        .node-battery { grid-column: 1; grid-row: 2; }
        .node-house { grid-column: 3; grid-row: 2; }
        .node-grid { grid-column: 2; grid-row: 3; }
        
        .flow-lines {
          grid-column: 1 / 4;
          grid-row: 1 / 4;
          position: relative;
          pointer-events: none;
        }
        .flow-line {
          position: absolute;
          background: linear-gradient(90deg, var(--flow-color-inactive), var(--flow-color-inactive));
          height: 4px;
          border-radius: 2px;
          transition: all 0.3s ease;
        }
        .flow-line.active {
          animation: flow-pulse 1.5s ease-in-out infinite;
        }
        .flow-line.solar-battery {
          top: 40%;
          left: 20%;
          width: 30%;
          transform: rotate(45deg);
        }
        .flow-line.solar-house {
          top: 40%;
          right: 20%;
          width: 30%;
          transform: rotate(-45deg);
        }
        .flow-line.grid-battery {
          bottom: 30%;
          left: 25%;
          width: 25%;
          transform: rotate(-45deg);
        }
        .flow-line.grid-house {
          bottom: 30%;
          right: 25%;
          width: 25%;
          transform: rotate(45deg);
        }
        .flow-line.battery-house {
          top: 50%;
          left: 30%;
          width: 40%;
        }
        
        @keyframes flow-pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
        
        .status-bar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 16px;
          padding: 12px;
          background: var(--card-background-color, #1c1c1c);
          border-radius: 8px;
        }
        .status-text {
          font-size: 14px;
          font-weight: 500;
        }
        .status-charging { color: #4caf50; }
        .status-discharging { color: #ff9800; }
        .status-self_use { color: #2196f3; }
        .status-house_from_grid { color: #9c27b0; }
        
        .price-tag {
          padding: 4px 12px;
          border-radius: 16px;
          font-size: 12px;
          font-weight: bold;
        }
        .price-low { background: #4caf50; color: white; }
        .price-medium { background: #ff9800; color: white; }
        .price-high { background: #f44336; color: white; }
        
        .battery-indicator {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .battery-bar {
          width: 40px;
          height: 16px;
          border: 2px solid var(--primary-text-color);
          border-radius: 4px;
          position: relative;
          overflow: hidden;
        }
        .battery-bar::after {
          content: '';
          position: absolute;
          right: -4px;
          top: 4px;
          width: 4px;
          height: 8px;
          background: var(--primary-text-color);
          border-radius: 0 2px 2px 0;
        }
        .battery-fill {
          height: 100%;
          transition: width 0.3s ease;
        }
        .battery-fill.low { background: #f44336; }
        .battery-fill.medium { background: #ff9800; }
        .battery-fill.high { background: #4caf50; }
      </style>
      
      <ha-card header="${this.config.title}">
        <div class="card-content">
          <div class="energy-flow-container">
            <!-- Solar Node -->
            <div class="node node-solar ${isSelfUse ? 'active' : ''}">
              <div class="node-icon">☀️</div>
              <div class="node-label">Solar</div>
            </div>
            
            <!-- Battery Node -->
            <div class="node node-battery ${isCharging || isDischarging ? 'active' : ''}">
              <div class="node-icon">🔋</div>
              <div class="battery-indicator">
                <div class="battery-bar">
                  <div class="battery-fill ${batterySOC < 20 ? 'low' : batterySOC < 50 ? 'medium' : 'high'}" 
                       style="width: ${batterySOC}%"></div>
                </div>
                <span class="node-value">${Math.round(batterySOC)}%</span>
              </div>
              <div class="node-label">Battery</div>
            </div>
            
            <!-- House Node -->
            <div class="node node-house active">
              <div class="node-icon">🏠</div>
              <div class="node-value">${Math.round(houseLoad)}W</div>
              <div class="node-label">House</div>
            </div>
            
            <!-- Grid Node -->
            <div class="node node-grid ${isCharging || isGridToHouse ? 'active' : ''}">
              <div class="node-icon">⚡</div>
              <div class="node-value">${gridImport > 0 ? `↓${Math.round(gridImport)}W` : gridExport > 0 ? `↑${Math.round(gridExport)}W` : '0W'}</div>
              <div class="node-label">Grid</div>
            </div>
          </div>
          
          <div class="status-bar">
            <span class="status-text status-${status}">
              ${this._getStatusText(status)}
            </span>
            ${currentPrice !== undefined ? `
              <span class="price-tag ${currentPrice < 0.05 ? 'price-low' : currentPrice < 0.10 ? 'price-medium' : 'price-high'}">
                ${currentPrice.toFixed(3)} CZK/kWh
              </span>
            ` : ''}
          </div>
        </div>
      </ha-card>
    `;
  }

  _getStatusText(status) {
    const statusTexts = {
      'charging': '⚡ Charging from Grid',
      'discharging': '📤 Discharging to Grid',
      'self_use': '☀️ Self Use Mode',
      'house_from_grid': '🔌 House from Grid',
      'idle': '💤 Idle',
      'error': '⚠️ Error'
    };
    return statusTexts[status] || status;
  }

  getCardSize() {
    return 4;
  }

  static getConfigElement() {
    return document.createElement('solar-mind-energy-flow-card-editor');
  }

  static getStubConfig() {
    return {
      entity: 'sensor.solar_mind_energy_flow',
      title: 'Energy Flow'
    };
  }
}

customElements.define('solar-mind-energy-flow-card', SolarMindEnergyFlowCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'solar-mind-energy-flow-card',
  name: 'Solar Mind Energy Flow',
  description: 'Visualizes energy flow between solar, battery, grid, and house'
});
