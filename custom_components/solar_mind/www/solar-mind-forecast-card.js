/**
 * Solar Mind Forecast Card
 * Displays price and generation forecasts with charts
 */

class SolarMindForecastCard extends HTMLElement {
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
      title: config.title || 'Energy Forecast',
      show_prices: config.show_prices !== false,
      show_generation: config.show_generation !== false,
      show_load: config.show_load !== false,
      hours: config.hours || 24,
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
    const plan = attrs.plan || [];
    const summary = attrs.summary || {};
    
    const hours = Math.min(this.config.hours, plan.length);
    const chartData = plan.slice(0, hours);

    this.shadowRoot.innerHTML = `
      <style>
        .card-content {
          padding: 16px;
        }
        .summary-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 12px;
          margin-bottom: 16px;
        }
        .summary-item {
          text-align: center;
          padding: 12px;
          background: var(--card-background-color, #1c1c1c);
          border-radius: 8px;
        }
        .summary-value {
          font-size: 20px;
          font-weight: bold;
          color: var(--primary-text-color);
        }
        .summary-label {
          font-size: 11px;
          color: var(--secondary-text-color);
          margin-top: 4px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          max-width: 100%;
        }
        .summary-item.positive .summary-value { color: #4caf50; }
        .summary-item.negative .summary-value { color: #f44336; }
        
        .chart-container {
          position: relative;
          height: 200px;
          margin: 16px 0;
        }
        .chart-svg {
          width: 100%;
          height: 100%;
        }
        .chart-grid-line {
          stroke: var(--divider-color, #424242);
          stroke-width: 1;
          stroke-dasharray: 4;
        }
        .chart-axis-label {
          font-size: 10px;
          fill: var(--secondary-text-color);
          max-width: 3em;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .chart-section-title {
          font-size: 12px;
          font-weight: 600;
          color: var(--primary-text-color);
          margin: 16px 0 8px 0;
        }
        .chart-section-title:first-of-type { margin-top: 0; }
        .chart-line-soc {
          stroke: #9c27b0;
        }
        .chart-area-soc {
          fill: rgba(156, 39, 176, 0.2);
        }
        .legend-color.soc { background: #9c27b0; }
        .chart-line {
          fill: none;
          stroke-width: 2;
        }
        .chart-line-pv {
          stroke: #ffc107;
        }
        .chart-line-load {
          stroke: #2196f3;
        }
        .chart-line-price {
          stroke: #4caf50;
        }
        .chart-area-pv {
          fill: rgba(255, 193, 7, 0.2);
        }
        .chart-area-load {
          fill: rgba(33, 150, 243, 0.1);
        }
        .chart-bar {
          fill: var(--primary-color);
          opacity: 0.7;
        }
        .chart-bar.charge { fill: #4caf50; }
        .chart-bar.discharge { fill: #ff9800; }
        .chart-bar.self_use { fill: #2196f3; }
        .chart-bar.idle { fill: #9e9e9e; }
        
        .legend {
          display: flex;
          justify-content: center;
          gap: 16px;
          margin-top: 8px;
          flex-wrap: wrap;
        }
        .legend-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
          color: var(--secondary-text-color);
        }
        .legend-color {
          width: 12px;
          height: 12px;
          border-radius: 2px;
        }
        .legend-color.pv { background: #ffc107; }
        .legend-color.load { background: #2196f3; }
        .legend-color.price { background: #4caf50; }
        .legend-color.charge { background: #4caf50; }
        .legend-color.discharge { background: #ff9800; }
        
        .action-timeline {
          display: flex;
          gap: 2px;
          margin-top: 16px;
          height: 24px;
          border-radius: 4px;
          overflow: hidden;
        }
        .action-block {
          flex: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 8px;
          color: white;
          text-transform: uppercase;
        }
        .action-block.charge { background: #4caf50; }
        .action-block.discharge { background: #ff9800; }
        .action-block.self_use { background: #2196f3; }
        .action-block.idle { background: #9e9e9e; }
        
        .time-labels {
          display: flex;
          justify-content: space-between;
          margin-top: 4px;
        }
        .time-label {
          font-size: 10px;
          color: var(--secondary-text-color);
          max-width: 4em;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        
        .no-data {
          text-align: center;
          padding: 40px;
          color: var(--secondary-text-color);
        }
      </style>
      
      <ha-card header="${this.config.title}">
        <div class="card-content">
          ${chartData.length === 0 ? `
            <div class="no-data">No forecast data available</div>
          ` : `
            <!-- Summary -->
            <div class="summary-grid">
              <div class="summary-item positive">
                <div class="summary-value">${(summary.total_pv_kwh || 0).toFixed(1)}</div>
                <div class="summary-label">☀️ PV Forecast (kWh)</div>
              </div>
              <div class="summary-item">
                <div class="summary-value">${(summary.total_load_kwh || 0).toFixed(1)}</div>
                <div class="summary-label">🏠 Load Forecast (kWh)</div>
              </div>
              <div class="summary-item ${(summary.estimated_cost || 0) > (summary.estimated_revenue || 0) ? 'negative' : 'positive'}">
                <div class="summary-value">${((summary.estimated_revenue || 0) - (summary.estimated_cost || 0)).toFixed(1)}</div>
                <div class="summary-label">💰 Net (CZK)</div>
              </div>
            </div>
            
            <!-- Expected generation & load -->
            <div class="chart-section-title">Expected PV &amp; load (W)</div>
            ${this._renderChart(chartData)}
            
            <!-- Expected battery level -->
            <div class="chart-section-title">Expected battery level (%)</div>
            ${this._renderSocChart(chartData)}
            
            <!-- Legend -->
            <div class="legend">
              ${this.config.show_generation ? '<div class="legend-item"><div class="legend-color pv"></div>PV generation</div>' : ''}
              ${this.config.show_load ? '<div class="legend-item"><div class="legend-color load"></div>House load</div>' : ''}
              <div class="legend-item"><div class="legend-color soc"></div>Battery %</div>
              <div class="legend-item"><div class="legend-color charge"></div>Charge</div>
              <div class="legend-item"><div class="legend-color discharge"></div>Discharge</div>
            </div>
            
            <!-- Action Timeline -->
            <div class="action-timeline">
              ${chartData.map(entry => `
                <div class="action-block ${entry.action}" title="${entry.hour}: ${entry.action}"></div>
              `).join('')}
            </div>
            <div class="time-labels">
              <span class="time-label">Now</span>
              <span class="time-label">+${Math.floor(hours/2)}h</span>
              <span class="time-label">+${hours}h</span>
            </div>
          `}
        </div>
      </ha-card>
    `;
  }

  _renderChart(data) {
    if (data.length === 0) return '';
    
    const width = 100; // Percentage
    const height = 200;
    const padding = { top: 10, right: 10, bottom: 20, left: 40 };
    const chartWidth = width;
    const chartHeight = height - padding.top - padding.bottom;
    
    // Calculate scales
    const maxPV = Math.max(...data.map(d => d.pv_forecast_wh || 0), 1);
    const maxLoad = Math.max(...data.map(d => d.load_forecast_wh || 0), 1);
    const maxValue = Math.max(maxPV, maxLoad);
    
    const xStep = chartWidth / data.length;
    
    // Generate paths
    const pvPath = data.map((d, i) => {
      const x = (i / data.length) * 100;
      const y = chartHeight - ((d.pv_forecast_wh || 0) / maxValue * chartHeight);
      return `${i === 0 ? 'M' : 'L'} ${x}% ${y}`;
    }).join(' ');
    
    const loadPath = data.map((d, i) => {
      const x = (i / data.length) * 100;
      const y = chartHeight - ((d.load_forecast_wh || 0) / maxValue * chartHeight);
      return `${i === 0 ? 'M' : 'L'} ${x}% ${y}`;
    }).join(' ');
    
    // Area path for PV
    const pvAreaPath = pvPath + ` L 100% ${chartHeight} L 0% ${chartHeight} Z`;
    
    return `
      <div class="chart-container">
        <svg class="chart-svg" viewBox="0 0 100 ${height}" preserveAspectRatio="none">
          <!-- Grid lines -->
          <line class="chart-grid-line" x1="0" y1="${chartHeight * 0.25}" x2="100%" y2="${chartHeight * 0.25}" />
          <line class="chart-grid-line" x1="0" y1="${chartHeight * 0.5}" x2="100%" y2="${chartHeight * 0.5}" />
          <line class="chart-grid-line" x1="0" y1="${chartHeight * 0.75}" x2="100%" y2="${chartHeight * 0.75}" />
          
          <!-- PV area and line -->
          ${this.config.show_generation ? `
            <path class="chart-area-pv" d="${pvAreaPath}" />
            <path class="chart-line chart-line-pv" d="${pvPath}" />
          ` : ''}
          
          <!-- Load line -->
          ${this.config.show_load ? `
            <path class="chart-line chart-line-load" d="${loadPath}" />
          ` : ''}
          
          <!-- Axis labels -->
          <text class="chart-axis-label" x="2" y="15">${(maxValue / 1000).toFixed(1)}kW</text>
          <text class="chart-axis-label" x="2" y="${chartHeight / 2}">${(maxValue / 2000).toFixed(1)}kW</text>
          <text class="chart-axis-label" x="2" y="${chartHeight - 5}">0</text>
        </svg>
      </div>
    `;
  }

  _renderSocChart(data) {
    if (data.length === 0) return '';
    const height = 120;
    const padding = { top: 8, right: 8, bottom: 16, left: 28 };
    const chartHeight = height - padding.top - padding.bottom;
    const socValues = data.map(d => d.predicted_soc != null ? Number(d.predicted_soc) : 0);
    const minSoc = Math.min(...socValues, 0);
    const maxSoc = Math.max(...socValues, 100);
    const range = maxSoc - minSoc || 100;
    const w = 100;
    const socPath = data.map((d, i) => {
      const x = (data.length <= 1 ? 0 : (i / (data.length - 1)) * w);
      const v = d.predicted_soc != null ? Number(d.predicted_soc) : 0;
      const y = chartHeight - ((v - minSoc) / range * chartHeight);
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    }).join(' ');
    const socAreaPath = socPath + ` L ${w} ${chartHeight} L 0 ${chartHeight} Z`;
    return `
      <div class="chart-container" style="height: ${height}px;">
        <svg class="chart-svg" viewBox="0 0 100 ${height}" preserveAspectRatio="none">
          <line class="chart-grid-line" x1="0" y1="${chartHeight * 0.5}" x2="100%" y2="${chartHeight * 0.5}" />
          <path class="chart-area-soc" d="${socAreaPath}" />
          <path class="chart-line chart-line-soc" d="${socPath}" />
          <text class="chart-axis-label" x="2" y="10">${Math.round(maxSoc)}%</text>
          <text class="chart-axis-label" x="2" y="${chartHeight - 4}">${Math.round(minSoc)}%</text>
        </svg>
      </div>
    `;
  }

  getCardSize() {
    return 5;
  }

  static getStubConfig() {
    return {
      entity: 'sensor.solar_mind_hourly_plan',
      title: 'Energy Forecast',
      hours: 24
    };
  }
}

customElements.define('solar-mind-forecast-card', SolarMindForecastCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'solar-mind-forecast-card',
  name: 'Solar Mind Forecast',
  description: 'Displays price and generation forecasts with charts'
});
