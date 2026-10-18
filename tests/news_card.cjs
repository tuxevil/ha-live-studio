const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.value='';}
 append(...items){this.children.push(...items);}
 replaceChildren(){this.children=[];}
 addEventListener(name,fn){this.listeners[name]=fn;}
}
global.document={createElement:t=>new Element(t),createTextNode:t=>({textContent:t})};
global.HTMLElement=class{attachShadow(){this.shadowRoot=new Element('shadow');}};
const definitions=new Map();global.customElements={define:(n,c)=>definitions.set(n,c)};global.window={};
vm.runInThisContext(fs.readFileSync('custom_components/live_studio/frontend/live-studio-news-card.js','utf8'));
function nodes(el){return [el,...(el.children||[]).flatMap(nodes)];}
(async()=>{
 const Card=definitions.get('live-studio-news-card');const card=new Card();const requests=[];
 card.config={entity:'sensor.landscape'};card._hass={callWS:async msg=>{requests.push(msg);return {config:{broadcast_layout:'full_height',vertical_news:{enabled:true,speed_px_s:25,messages:[{id:'one',title:'<script>literal</script>',enabled:true}]}}};}};
 await card.load();assert.equal(card.loaded,true);
 assert(nodes(card.shadowRoot).some(n=>n.value==='<script>literal</script>'));
 const save=nodes(card.shadowRoot).find(n=>n.tag==='button'&&n.textContent==='Guardar');
 card.news.speed_px_s=40;await save.onclick();
 assert.equal(requests[1].entity_id,'sensor.landscape');
 assert.equal(requests[1].changes.vertical_news.speed_px_s,40);
 assert.equal(requests[1].changes.broadcast_layout,'full_height');
 const remove=nodes(card.shadowRoot).find(n=>n.tag==='button'&&n.textContent==='Quitar');remove.onclick();
 assert.equal(card.news.messages.length,0);
 console.log('PASS news editor: literal text, per-live writes, live speed/layout, removal');
})().catch(e=>{console.error(e);process.exitCode=1;});
