/**
 * Solar Mind Cheapest Hours & Price Forecast Card
 * Displays future data only: cheapest hours today and optional 24h price forecast.
 * Use this card instead of entity more-info to avoid history-stats for forecast data.
 */

class SolarMindCheapestHoursCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  setConfig(config) {
    const entity = config.entity || config.cheapest_hours_entity;
    if (!entity) {
      throw new Error('Please define entity (or cheapest_hours_entity)');
    }
    this.config = {
      entity,
      price_forecast_entity: config.price_forecast_entity || null,
      title: config.title || 'Cheapest Hours Today',
      show_prices: config.show_prices !== false,
      show_price_chart: config.show_price_chart !== false,
      ...config
    };
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  render() {
    if (!this._hass || !this.config) return;

    const state = this._hass.states[this.config.entity];
    const priceState = this.config.price_forecast_entity
      ? this._hass.states[this.config.price_forecast_entity]
      : null;

    if (!state) {
      this.shadowRoot.innerHTML = `
        <ha-card header="${this.config.title}">
          <div class="card-content">
            <div class="no-data">Entity not found: ${this.config.entity}</div>
          </div>
        </ha-card>
      `;
      return;
    }

    const attrs = state.attributes || {};
    const hours = Array.isArray(attrs.hours) ? attrs.hours : [];
    const priceAttrs = priceState && priceState.attributes ? priceState.attributes : {};
    const todayPrices = Array.isArray(priceAttrs.today) ? priceAttrs.today : [];
    const cheapestSet = new Set(hours.map(h => h.hour));

    const now = new Date();
    const currentHour = now.getHours();

    this.shadowRoot.innerHTML = `
      <style>
        .card-content { padding: 16px; }
        .section-title {
          font-size: 12px;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 8px;
        }
        .cheapest-hours-row {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: ${todayPrices.length && this.config.show_price_chart ? '16px' : '0'};
        }
        .hour-chip {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 6px 12px;
          border-radius: 16px;
          font-size: 13px;
          font-weight: 500;
          background: var(--ha-card-background, #1c1c1c);
          border: 1px solid var(--divider-color, #424242);
          color: var(--primary-text-color);
        }
        .hour-chip.cheapest {
          background: rgba(76, 175, 80, 0.2);
          border-color: #4caf50;
          color: #4caf50;
        }
        .hour-chip.past {
          opacity: 0.5;
        }
        .hour-chip .price {
          font-size: 11px;
          color: var(--secondary-text-color);
        }
        .price-chart {
          margin-top: 8px;
        }
        .chart-row {
          display: flex;
          align-items: flex-end;
          gap: 2px;
          height: 48px;
          margin-bottom: 4px;
        }
        .chart-bar-wrap {
          flex: 1;
          display: flex;
          align-items: flex-end;
          justify-content: center;
          min-width: 0;
        }
        .chart-bar {
          width: 100%;
          min-height: 4px;
          border-radius: 2px 2px 0 0;
          background: var(--divider-color, #424242);
          transition: height 0.2s;
        }
        .chart-bar.cheapest { background: #4caf50; }
        .chart-bar.current { background: var(--primary-color); opacity: 0.9; }
        .chart-labels {
          display: flex;
          justify-content: space-between;
          font-size: 10px;
          color: var(--secondary-text-color);
          padding: 0 2px;
        }
        .no-data {
          text-align: center;
          padding: 24px;
          color: var(--secondary-text-color);
        }
      </style>
      <ha-card header="${this.config.title}">
        <div class="card-content">
          <div class="section-title">Today's cheapest hours (forecast)</div>
          ${hours.length === 0 ? `
            <div class="no-data">${state.state || 'No data'}</div>
          ` : `
            <div class="cheapest-hours-row">
              ${hours.map(h => {
                const isPast = h.hour < currentHour;
                const priceStr = this.config.show_prices && h.price != null
                  ? ` <span class="price">${Number(h.price).toFixed(2)}</span>`
                  : '';
                return `<span class="hour-chip cheapest ${isPast ? 'past' : ''}" title="Hour ${h.hour}:00${h.price != null ? ' — ' + Number(h.price).toFixed(2) : ''}">${String(h.hour).padStart(2, '0')}:00${priceStr}</span>`;
              }).join('')}
            </div>
            ${todayPrices.length && this.config.show_price_chart ? `
              <div class="section-title">Price forecast (today)</div>
              <div class="price-chart">
                <div class="chart-row">
                  ${todayPrices.map((p, i) => {
                    const isCheapest = cheapestSet.has(p.hour);
                    const isCurrent = p.hour === currentHour;
                    const maxP = Math.max(...todayPrices.map(x => x.price), 0.01);
                    const heightPct = Math.max(4, (p.price / maxP) * 100);
                    return `<div class="chart-bar-wrap" title="${String(p.hour).padStart(2, '0')}:00 — ${Number(p.price).toFixed(2)}"><div class="chart-bar ${isCheapest ? 'cheapest' : ''} ${isCurrent ? 'current' : ''}" style="height: ${heightPct}%"></div></div>`;
                  }).join('')}
                </div>
                <div class="chart-labels">
                  <span>0h</span>
                  <span>12h</span>
                  <span>24h</span>
                </div>
              </div>
            ` : ''}
          `}
        </div>
      </ha-card>
    `;
  }

  getCardSize() {
    return 3;
  }

  static getStubConfig() {
    return {
      entity: 'sensor.solar_mind_cheapest_hours_today',
      title: 'Cheapest Hours Today',
      price_forecast_entity: 'sensor.solar_mind_price_forecast',
      show_prices: true,
      show_price_chart: true
    };
  }
}

customElements.define('solar-mind-cheapest-hours-card', SolarMindCheapestHoursCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'solar-mind-cheapest-hours-card',
  name: 'Solar Mind Cheapest Hours',
  description: 'Displays cheapest hours today and price forecast (future data only, no history)'
});
