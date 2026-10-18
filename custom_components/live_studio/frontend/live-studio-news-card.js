class LiveStudioNewsCard extends HTMLElement {
  setConfig(config) { if(this.config?.entity !== config.entity){this.loaded=false;this.news=null;this.loading=false;} this.config = config; this.draw(); if(this._hass && !this.loaded) this.load(); }
  set hass(hass) { this._hass = hass; if (!this.loaded && !this.loading) this.load(); }
  async load() {
    if (!this._hass || !this.config) return;
    this.loading = true;
    const owner = this.config.entity;
    try {
      const r = await this._hass.callWS({type:'live_studio/overlay/get',entity_id:this.config.entity});
      if(owner !== this.config.entity) return;
      this.layout = r.config.broadcast_layout || "classic";
      this.footer = r.config.weather_footer_enabled !== false;
      this.sidebarWidth = r.config.sidebar_width || 384;
      this.news = structuredClone(r.config.vertical_news || {enabled:false,speed_px_s:25,messages:[]});
      this.loaded = true; this.error = ''; this.draw();
    } catch(e) { this.error = e.message; this.draw(); }
    finally { this.loading = false; }
  }
  draw() {
    if (!this.shadowRoot) this.attachShadow({mode:'open'});
    const root = this.shadowRoot;
    root.replaceChildren();
    const style = document.createElement('style');
    style.textContent = `ha-card{padding:20px}h3{margin:0 0 16px}label{display:block;margin:10px 0;color:var(--primary-text-color)}input:not([type=checkbox]),textarea{box-sizing:border-box;width:100%;padding:9px;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:5px;font:inherit}textarea{min-height:58px;resize:vertical}article{border-top:1px solid var(--divider-color);padding-top:12px;margin-top:14px}button{padding:8px 14px;margin:8px 8px 0 0;border:1px solid var(--divider-color);border-radius:5px;color:var(--primary-text-color);background:var(--secondary-background-color);cursor:pointer}.error{color:var(--error-color)}small{color:var(--secondary-text-color)}`;
    root.append(style);
    const card = document.createElement('ha-card'); root.append(card);
    const heading = document.createElement('h3'); heading.textContent='Diseño y novedades';card.append(heading);
    if (!this.news) { const p=document.createElement('p');p.textContent=this.error||'Cargando…';card.append(p);return; }
    const field = (parent,label,type,value,onchange) => {
      const box=document.createElement('label');box.append(document.createTextNode(label+' '));
      const el=document.createElement(type==='textarea'?'textarea':'input');
      if(type!=='textarea') el.type=type;
      if(type==='checkbox') el.checked=value;else el.value=value;
      if(type==='number'){el.min=1;el.max=100;}
      el.addEventListener('input',()=>onchange(type==='checkbox'?el.checked:type==='number'?Number(el.value):el.value));
      box.append(el);parent.append(box);return el;
    };
    const layoutLabel=document.createElement('label');layoutLabel.textContent='Diseño ';
    const layout=document.createElement('select');
    for(const [value,label] of [['classic','Diseño anterior'],['full_height','Sidebar de altura completa']]){const option=document.createElement('option');option.value=value;option.textContent=label;layout.append(option);}
    layout.value=this.layout;layout.onchange=()=>this.layout=layout.value;layoutLabel.append(layout);card.append(layoutLabel);
    field(card,'Telemetría inferior','checkbox',this.footer,v=>this.footer=v);
    const width=field(card,'Ancho de sidebar (320–384 px)','number',this.sidebarWidth,v=>this.sidebarWidth=v);width.min=320;width.max=384;width.step=2;
    field(card,'Publicar novedades','checkbox' ,this.news.enabled,v=>this.news.enabled=v);
    field(card,'Velocidad (px/s)','number',this.news.speed_px_s,v=>this.news.speed_px_s=v);
    const button=(parent,text,fn)=>{const b=document.createElement('button');b.textContent=text;b.onclick=fn;parent.append(b);return b;};
    this.news.messages.forEach((m,i)=>{
      const article=document.createElement('article');card.append(article);
      field(article,'Activo','checkbox',m.enabled!==false,v=>m.enabled=v);
      field(article,'Título','text',m.title,v=>m.title=v).maxLength=200;
      field(article,'Subtítulo','textarea',m.subtitle||'',v=>m.subtitle=v).maxLength=800;
      button(article,'↑',()=>{if(i){[this.news.messages[i-1],this.news.messages[i]]=[m,this.news.messages[i-1]];this.draw();}});
      button(article,'↓',()=>{if(i+1<this.news.messages.length){[this.news.messages[i+1],this.news.messages[i]]=[m,this.news.messages[i+1]];this.draw();}});
      button(article,'Quitar',()=>{this.news.messages.splice(i,1);this.draw();});
    });
    button(card,'Añadir anuncio',()=>{if(this.news.messages.length>=32)return;this.news.messages.push({id:crypto.randomUUID(),title:'Nuevo anuncio',subtitle:'',icon:'radio',enabled:true,priority:0});this.draw();});
    button(card,'Guardar',async()=>{
      this.news.messages.forEach((m,i)=>m.priority=i*10);
      try{
        await this._hass.callWS({type:'live_studio/overlay/update',entity_id:this.config.entity,changes:{vertical_news:this.news,broadcast_layout:this.layout,weather_footer_enabled:this.footer,sidebar_width:this.sidebarWidth}});
        this.error='Guardado. Se aplica sin reiniciar la emisión.';
      }catch(e){this.error=e.message||'No se pudo guardar';}
      this.draw();
    });
    const status=document.createElement('p');status.textContent=this.error||'';card.append(status);
  }
  getCardSize(){return 5;}
}
customElements.define('live-studio-news-card',LiveStudioNewsCard);
window.customCards=window.customCards||[];
window.customCards.push({type:'live-studio-news-card',name:'Live Studio · Novedades',description:'Anuncios verticales independientes por live.'});
