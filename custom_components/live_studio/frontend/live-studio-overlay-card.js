/* Live Studio: per-live overlay controls using the authenticated HA connection. */
const LS_LABELS = {
  es: {
    design: 'Diseño', element: 'Elemento', band: 'Franja', ticker: 'Marquesina', sensor: 'Información',
    title: 'Título', source: 'Cámara', date: 'Fecha', clock: 'Hora', cta: 'Llamada a la acción',
    visible: 'Mostrar', text: 'Texto', position: 'Posición', top: 'Arriba', bottom: 'Abajo',
    size: 'Tamaño del texto', height: 'Altura', opacity: 'Opacidad', style: 'Color y fondo',
    color: 'Color del texto', background_color: 'Color del fondo', background_opacity: 'Opacidad del fondo',
    shadow: 'Sombra del texto', anchor: 'Ubicación', auto: 'Automática',
    top_left: 'Arriba · izquierda', top_center: 'Arriba · centro', top_right: 'Arriba · derecha',
    middle_left: 'Centro · izquierda', middle_center: 'Centro', middle_right: 'Centro · derecha',
    bottom_left: 'Abajo · izquierda', bottom_center: 'Abajo · centro', bottom_right: 'Abajo · derecha',
    offsets: 'Ajustar posición', x: 'Separación horizontal', y: 'Separación vertical',
    movement: 'Movimiento', scroll: 'Desplazamiento', off: 'Sin desplazamiento', overflow: 'Solo si no cabe',
    always: 'Continuo', speed: 'Velocidad', direction: 'Dirección', left: 'Hacia la izquierda', right: 'Hacia la derecha',
    format: 'Formato', loading: 'Cargando…', saving: 'Aplicando…', saved: 'Actualizado',
    error: 'No se pudo aplicar el cambio. Reintenta.', unavailable: 'El motor necesita Live Studio 0.5.0 o posterior.',
    connect: 'No se pudo conectar con Live Studio.', timeZone: 'Zona horaria',
  },
  en: {
    design: 'Layout', element: 'Element', band: 'Bar', ticker: 'Ticker', sensor: 'Information',
    title: 'Title', source: 'Camera', date: 'Date', clock: 'Time', cta: 'Call to action',
    visible: 'Show', text: 'Text', position: 'Position', top: 'Top', bottom: 'Bottom',
    size: 'Text size', height: 'Height', opacity: 'Opacity', style: 'Color and background',
    color: 'Text color', background_color: 'Background color', background_opacity: 'Background opacity',
    shadow: 'Text shadow', anchor: 'Placement', auto: 'Automatic',
    top_left: 'Top · left', top_center: 'Top · center', top_right: 'Top · right',
    middle_left: 'Middle · left', middle_center: 'Center', middle_right: 'Middle · right',
    bottom_left: 'Bottom · left', bottom_center: 'Bottom · center', bottom_right: 'Bottom · right',
    offsets: 'Fine position', x: 'Horizontal offset', y: 'Vertical offset',
    movement: 'Movement', scroll: 'Scrolling', off: 'No scrolling', overflow: 'When too long',
    always: 'Continuous', speed: 'Speed', direction: 'Direction', left: 'Left', right: 'Right',
    format: 'Format', loading: 'Loading…', saving: 'Applying…', saved: 'Updated',
    error: 'Could not apply the change. Try again.', unavailable: 'The engine needs Live Studio 0.5.0 or later.',
    connect: 'Could not connect to Live Studio.', timeZone: 'Time zone',
  },
};
const lsEscape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
class LiveStudioOverlayCard extends HTMLElement {
  constructor() {
    super(); this.attachShadow({mode: 'open'}); this._element = 'ticker'; this._pending = {};
    this.shadowRoot.addEventListener('change', event => this._change(event));
    this.shadowRoot.addEventListener('input', event => {
      if (event.target.type === 'range') {
        const label = event.target.closest('label').querySelector('output');
        if (label) label.textContent = event.target.value;
      }
    });
  }
  setConfig(config) {
    if (!config.entity) throw new Error('Choose a Live Studio status entity');
    this._config = config; this._data = null; this._state = null;
    if (this._hass) this._load();
  }
  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._config?.entity];
    if (state !== this._state && !this._busy && !this._loading && !Object.keys(this._pending).length) {
      this._state = state; this._load();
    }
  }
  getCardSize() { return 8; }
  disconnectedCallback() { clearTimeout(this._timer); clearTimeout(this._pollTimer); this._flush(); }
  connectedCallback() { if (this._hass && this._config) this._load(); }
  static getStubConfig(hass) {
    return {entity: Object.keys(hass.states).find(id => id.startsWith('sensor.live_studio') && hass.states[id].attributes.version) || 'sensor.live_studio_status'};
  }
  get _t() { return LS_LABELS[this._hass?.language?.startsWith('es') ? 'es' : 'en']; }
  async _load() {
    if (!this._config || this._loading) return;
    this._loading = true;
    try {
      const data = await this._hass.callWS({type: 'live_studio/overlay/get', entity_id: this._config.entity});
      if (!this._busy && !Object.keys(this._pending).length) {
        this._data = data;
        if (!this.shadowRoot.activeElement) this._render();
        this._setStatus(data.pending ? this._t.saving : '');
        this._refreshPreview();
        if (data.pending) this._pollTimer = setTimeout(()=>this._load(),700);
      }
    } catch (_) {
      if (!this._data) this.shadowRoot.innerHTML = `<ha-card><p class="error">${this._t.connect}</p></ha-card>`;
    } finally { this._loading = false; }
  }
  _select(key, value, choices, section = this._element) {
    return `<label>${this._t[key] || key}<select data-key="${key}" data-section="${section}">${choices.map(([id, label]) => `<option value="${id}"${id === value ? ' selected' : ''}>${lsEscape(label)}</option>`).join('')}</select></label>`;
  }
  _range(key, value, min, max, label, section = this._element) {
    return `<label>${label || this._t[key]} <output>${value}</output><input type="range" min="${min}" max="${max}" value="${value}" data-key="${key}" data-section="${section}"></label>`;
  }
  _color(key, value, label, section = this._element) {
    return `<label class="color">${label || this._t[key]}<input type="color" value="${lsEscape(value)}" data-key="${key}" data-section="${section}"></label>`;
  }
  _check(key, value, label, section = this._element) {
    return `<label class="check"><input type="checkbox"${value ? ' checked' : ''} data-key="${key}" data-section="${section}">${label || this._t[key]}</label>`;
  }
  _render() {
    const t = this._t, config = this._data?.config, layout = config?.overlay_layout;
    if (!layout) { this.shadowRoot.innerHTML = `<ha-card><p>${t.unavailable}</p></ha-card>`; return; }
    const name = this._element, e = layout[name];
    const position = () => this._select('position', layout.band.position, ['top','bottom'].map(k => [k,t[k]]), 'band');
    let body;
    if (name === 'band') {
      body = `${position()}${this._range('height',e.height,40,400)}<div class="row">${this._color('color',e.color,t.band)}${this._range('opacity',e.opacity,0,100)}</div>`;
    } else {
      const content = ['title','ticker','cta'].includes(name) ? `<label>${t.text}<textarea rows="3" maxlength="${{title:100,ticker:1200,cta:200}[name]}" data-content="${name}">${lsEscape(config[name])}</textarea></label>` : '';
      const formats = name === 'date' ? [['iso','2026-10-17'],['day_first','17/10/2026'],['month_first','10/17/2026']] : [['24h_seconds','23:05:30'],['24h','23:05'],['12h','11:05 PM']];
      body = `${content}${['sensor','ticker'].includes(name) ? position() : ''}
        ${['date','clock'].includes(name) ? this._select('format',e.format,formats) + `<label>${t.timeZone}<input type="text" value="${lsEscape(config.timezone)}" data-content="timezone"></label>` : ''}
        ${this._select('anchor',e.anchor,['auto','top_left','top_center','top_right','middle_left','middle_center','middle_right','bottom_left','bottom_center','bottom_right'].map(k=>[k,t[k]]))}
        ${this._range('font_size',e.font_size,8,120,t.size)}
        <details><summary>${t.offsets}</summary><div class="row">${['x','y'].map(k=>`<label>${t[k]}<input type="number" min="0" max="${k==='x'?3840:2160}" value="${e[k]}" data-key="${k}" data-section="${name}"></label>`).join('')}</div></details>
        <details${e.scroll !== 'off' ? ' open' : ''}><summary>${t.movement}</summary>
          ${this._select('scroll',e.scroll,['off','overflow','always'].map(k=>[k,t[k]]))}
          ${this._range('speed',e.speed,0,400)}${this._select('direction',e.direction,['left','right'].map(k=>[k,t[k]]))}
        </details>
        <details><summary>${t.style}</summary><div class="row">${this._color('color',e.color)}${this._color('background_color',e.background_color)}</div>
          ${this._range('background_opacity',e.background_opacity,0,100)}${this._check('shadow',e.shadow)}
        </details>`;
    }
    const cta = name === 'cta' ? `<div class="row">${['cta_period','cta_duration'].map(k=>`<label>${t===LS_LABELS.es?(k==='cta_period'?'Cada (segundos)':'Duración (segundos)'):(k==='cta_period'?'Every (seconds)':'Duration (seconds)')}<input type="number" min="${k==='cta_period'?60:3}" max="${k==='cta_period'?7200:60}" value="${config[k] || (k==='cta_period'?600:12)}" data-content="${k}"></label>`).join('')}</div>` : '';
    this.shadowRoot.innerHTML = `<style>
      :host{display:block}ha-card{padding:20px;overflow:hidden}h2{font-size:20px;margin:0 0 16px}.row{display:flex;gap:16px;align-items:center}.row>*{flex:1;min-width:0}.quick{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:18px;padding-bottom:16px;border-bottom:1px solid var(--divider-color)}
      label{display:block;font-size:14px;margin:12px 0;color:var(--primary-text-color)}select,textarea,input[type=number]{display:block;box-sizing:border-box;width:100%;margin-top:6px;padding:10px;border:1px solid var(--divider-color);border-radius:8px;color:var(--primary-text-color);background:var(--card-background-color);font:inherit}textarea{resize:vertical}
      input[type=range]{display:block;width:100%;margin:12px 0 16px;accent-color:var(--primary-color)}output{float:right;font-variant-numeric:tabular-nums;color:var(--secondary-text-color)}input[type=checkbox]{accent-color:var(--primary-color);width:18px;height:18px}.check{display:flex;gap:8px;align-items:center;cursor:pointer}.color{display:flex;align-items:center;justify-content:space-between;gap:8px}input[type=color]{width:44px;height:34px;border:0;padding:0;background:none;cursor:pointer}
      details{border-top:1px solid var(--divider-color);padding-top:12px;margin-top:12px}summary{cursor:pointer;font-size:14px;font-weight:500;padding:4px 0}#status{min-height:18px;margin-top:12px;font-size:12px;color:var(--secondary-text-color)}.error{color:var(--error-color);padding:16px}.preview{display:block;width:100%;border-radius:8px;margin-bottom:16px}
    </style><ha-card><h2>${lsEscape(this._config.title || t.design)}</h2>
      ${this._config.preview ? `<img id="preview" class="preview" alt="${t.design}">` : ''}<div class="quick">${['source','date','clock'].map(k=>this._check('visible',layout[k].visible,t[k],k)).join('')}</div>
      <div class="row">${this._select('element',name,['ticker','sensor','title','source','date','clock','cta','band'].map(k=>[k,t[k]]),'editor')}${this._check('visible',e.visible)}</div>
      ${body}${cta}<div id="status" role="status" aria-live="polite"></div></ha-card>`;
  }
  _change(event) {
    const input = event.target, key = input.dataset.key;
    if (input.dataset.section === 'editor') { this._element = input.value; this._render(); return; }
    if (!this._data) return;
    let changes;
    if (input.dataset.content) {
      const field = input.dataset.content;
      const value = field.startsWith('cta_') ? Number(input.value) : input.value;
      changes = {[field]:value}; this._data.config[field] = value;
    } else if (key) {
      if (!input.checkValidity()) return;
      const section = input.dataset.section;
      const value = input.type === 'checkbox' ? input.checked : ['range','number'].includes(input.type) ? Number(input.value) : input.value;
      changes = {overlay_layout:{[section]:{[key]:value}}};
      Object.assign(this._data.config.overlay_layout[section], changes.overlay_layout[section]);
      if (key === 'scroll' || (key === 'visible' && ['source','date','clock'].includes(section))) this._render();
    } else return;
    this._merge(this._pending,changes); this._setStatus(this._t.saving);
    clearTimeout(this._timer); this._timer = setTimeout(()=>this._flush(),250);
  }
  _merge(target, changes) {
    for (const [key,value] of Object.entries(changes)) {
      if (key === 'overlay_layout') {
        target[key] ||= {};
        for (const [name,fields] of Object.entries(value)) target[key][name] = {...target[key][name],...fields};
      } else target[key] = value;
    }
  }
  async _flush() {
    if (this._busy || !Object.keys(this._pending).length) return;
    this._busy = true; const changes = this._pending; this._pending = {};
    try {
      const data = await this._hass.callWS({type:'live_studio/overlay/update',entity_id:this._config.entity,changes});
      this._merge(data.config,this._pending); this._data = data; this._setStatus(data.pending ? this._t.saving : this._t.saved);
      if (data.pending) this._pollTimer = setTimeout(()=>this._load(),700);
    } catch (_) { this._setStatus(this._t.error,true); }
    finally { this._busy = false; if (Object.keys(this._pending).length) this._flush(); }
  }
  _refreshPreview() {
    const image = this.shadowRoot.getElementById('preview');
    const path = this._hass.states?.[this._data?.preview_entity]?.attributes.entity_picture;
    if (image && path) image.src = path + (path.includes('?') ? '&' : '?') + 't=' + Date.now();
  }
  _setStatus(text,error=false) { const el=this.shadowRoot.getElementById('status'); if(el){el.textContent=text;el.style.color=error?'var(--error-color)':'';} }
}
if (!customElements.get('live-studio-overlay-card')) customElements.define('live-studio-overlay-card',LiveStudioOverlayCard);
window.customCards ||= [];
if (!window.customCards.some(c=>c.type==='live-studio-overlay-card')) window.customCards.push({type:'live-studio-overlay-card',name:'Live Studio · Overlay',description:'Configure the overlay of one live independently.'});
