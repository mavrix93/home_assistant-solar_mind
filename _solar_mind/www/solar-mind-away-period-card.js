/**
 * Solar Mind Away Period Form Card
 * Form to add an "away from home" period from the dashboard
 */

class SolarMindAwayPeriodCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  setConfig(config) {
    this.config = {
      title: config.title || 'Add Away Period',
      default_reduce_percent: config.default_reduce_percent ?? 50,
      ...config
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._root) this.render();
  }

  render() {
    if (!this.shadowRoot) return;

    const start = new Date();
    start.setMinutes(0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + 2);
    end.setHours(18, 0, 0, 0);

    const fmt = (d) => d.toISOString().slice(0, 16);

    this.shadowRoot.innerHTML = `
      <style>
        .card-content {
          padding: 16px;
        }
        .form-row {
          margin-bottom: 16px;
        }
        .form-row label {
          display: block;
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
        }
        .form-row input, .form-row input[type="range"] {
          width: 100%;
          box-sizing: border-box;
        }
        .form-row input[type="range"] {
          max-width: 100%;
        }
        .form-row input[type="datetime-local"] {
          padding: 8px 12px;
          border-radius: 8px;
          border: 1px solid var(--divider-color, #424242);
          background: var(--card-background-color, #1c1c1c);
          color: var(--primary-text-color);
          font-size: 14px;
        }
        .form-row input[type="text"] {
          padding: 8px 12px;
          border-radius: 8px;
          border: 1px solid var(--divider-color, #424242);
          background: var(--card-background-color, #1c1c1c);
          color: var(--primary-text-color);
          font-size: 14px;
        }
        .reduce-row {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .reduce-row input[type="range"] {
          flex: 1;
        }
        .submit-btn {
          width: 100%;
          margin-top: 12px;
          padding: 12px 16px;
          border-radius: 8px;
          border: none;
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
        }
        .submit-btn:hover {
          opacity: 0.9;
        }
        .reduce-value {
          font-size: 14px;
          font-weight: 500;
          min-width: 3em;
        }
        mwc-button {
          width: 100%;
          margin-top: 8px;
        }
        .hint {
          font-size: 11px;
          color: var(--secondary-text-color);
          margin-top: 4px;
        }
      </style>
      <ha-card header="${this.config.title}">
        <div class="card-content">
          <div class="form-row">
            <label>Start</label>
            <input type="datetime-local" id="start" value="${fmt(start)}" />
          </div>
          <div class="form-row">
            <label>End</label>
            <input type="datetime-local" id="end" value="${fmt(end)}" />
          </div>
          <div class="form-row">
            <label>Label (optional)</label>
            <input type="text" id="label" placeholder="e.g. Vacation, Business trip" />
          </div>
          <div class="form-row">
            <label>Expected load reduction during away period</label>
            <div class="reduce-row">
              <input type="range" id="reduce" min="0" max="100" value="${this.config.default_reduce_percent}" />
              <span class="reduce-value" id="reduceValue">${this.config.default_reduce_percent}%</span>
            </div>
            <div class="hint">System will assume lower consumption and optimize accordingly.</div>
          </div>
          <button id="submitBtn" class="submit-btn">Add away period</button>
        </div>
      </ha-card>
    `;

    this._root = this.shadowRoot;
    const reduceEl = this._root.querySelector('#reduce');
    const reduceValueEl = this._root.querySelector('#reduceValue');
    if (reduceEl && reduceValueEl) {
      reduceEl.addEventListener('input', () => {
        reduceValueEl.textContent = reduceEl.value + '%';
      });
    }
    const btn = this._root.querySelector('#submitBtn');
    if (btn) btn.addEventListener('click', () => this._onSubmit());
  }

  _onSubmit() {
    const startInput = this.shadowRoot.querySelector('#start');
    const endInput = this.shadowRoot.querySelector('#end');
    const labelInput = this.shadowRoot.querySelector('#label');
    const reduceInput = this.shadowRoot.querySelector('#reduce');

    if (!startInput?.value || !endInput?.value) return;

    const startStr = startInput.value.replace('T', ' ') + ':00';
    const endStr = endInput.value.replace('T', ' ') + ':00';
    const startDate = new Date(startInput.value);
    const endDate = new Date(endInput.value);
    if (endDate <= startDate) {
      alert('End must be after start');
      return;
    }

    this._hass.callService('solar_mind', 'add_away_period', {
      start: startDate.toISOString().slice(0, 19),
      end: endDate.toISOString().slice(0, 19),
      label: (labelInput?.value || '').trim(),
      reduce_load_percent: parseFloat(reduceInput?.value ?? 50)
    }).then(() => {
      if (labelInput) labelInput.value = '';
    }).catch(err => {
      console.error('solar_mind.add_away_period failed', err);
      alert('Failed to add away period: ' + (err.message || err));
    });
  }

  getCardSize() {
    return 4;
  }

  static getStubConfig() {
    return { title: 'Add Away Period' };
  }
}

customElements.define('solar-mind-away-period-card', SolarMindAwayPeriodCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'solar-mind-away-period-card',
  name: 'Solar Mind Away Period',
  description: 'Form to add an away-from-home period from the dashboard'
});
