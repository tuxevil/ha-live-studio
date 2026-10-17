/* Fast DOM-boundary and request tests; FFmpeg rendering is tested by the engine. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const registered = new Map();
global.window = {};
global.customElements = {get: name=>registered.get(name), define:(name,klass)=>registered.set(name,klass)};
global.HTMLElement = class {
  attachShadow() {
    this.status = {textContent:'',style:{}};
    this.shadowRoot = {innerHTML:'',addEventListener(){},getElementById:()=>this.status,activeElement:null};
  }
};
vm.runInThisContext(process.env.LIVE_STUDIO_CARD_SOURCE || fs.readFileSync(path.join(__dirname,'../custom_components/live_studio/frontend/live-studio-overlay-card.js'),'utf8'));
(async()=>{
 const Card = registered.get('live-studio-overlay-card');
 assert(Card);assert.equal(window.customCards.length,1);
 const card = new Card();card._config = {entity:'sensor.test_live'};
 const layout = {band:{position:'bottom',visible:true,height:108,color:'#000000',opacity:45}};
 for(const key of ['ticker','sensor','title','source','date','clock','cta']) layout[key]={visible:true,anchor:'auto',x:24,y:24,font_size:28,color:'#FFFFFF',background_color:'#000000',background_opacity:0,shadow:true,scroll:'off',speed:65,direction:'left',format:key==='date'?'iso':'24h_seconds'};
 const backend = {config:{overlay_layout:layout,title:'<img src=x onerror=alert(1)>',ticker:'Literal <script> text',cta:'Hello',timezone:'UTC',cta_period:600,cta_duration:12},pending:false};
 const requests=[];
 card._hass={language:'es',callWS:async message=>{
  requests.push(message);assert.equal(message.type,'live_studio/overlay/update');
  card._merge(backend.config,message.changes);return structuredClone(backend);
 }};
 card._data=structuredClone(backend);card._element='title';card._render();
 assert(card.shadowRoot.innerHTML.includes('&lt;img'));
 assert(!card.shadowRoot.innerHTML.includes('<img src='));
 assert(card.shadowRoot.innerHTML.includes('Cámara'));
 card._element='ticker';card._render();
 assert(card.shadowRoot.innerHTML.includes('&lt;script&gt;'));
 function change(section,key,value,type='select-one') {
  card._change({target:{dataset:{section,key},type,value,checked:value,checkValidity:()=>true}});
 }
 change('source','visible',false,'checkbox');change('band','position','top');change('ticker','font_size','40','range');
 clearTimeout(card._timer);await card._flush();
 assert.equal(requests.length,1);
 assert.deepEqual(requests[0].changes.overlay_layout,{source:{visible:false},band:{position:'top'},ticker:{font_size:40}});
 assert.equal(backend.config.overlay_layout.date.visible,true);
 assert.equal(backend.config.overlay_layout.clock.visible,true);
 card._hass.callWS=async()=>{throw new Error('private details must not render');};
 change('ticker','speed','120','range');clearTimeout(card._timer);await card._flush();
 assert.equal(card.status.textContent,card._t.error);
 assert(!card.shadowRoot.innerHTML.includes('private details'));
 console.log('PASS overlay card: safe literal text, independent controls, coalesced patches and visible errors');
})().catch(error=>{console.error(error);process.exitCode=1;});
