const id = x => document.getElementById(x);
// Data de referência padrão: D-2 no fuso horário local do navegador.
// Só preenche campos vazios, preservando datas que o usuário escolher manualmente.
function todayMinusTwo() {
  const day = new Date();
  day.setDate(day.getDate() - 2);
  const year = day.getFullYear();
  const month = String(day.getMonth() + 1).padStart(2, '0');
  const date = String(day.getDate()).padStart(2, '0');
  return `${year}-${month}-${date}`;
}
function defaultPeriodD2(ids) {
  const value = todayMinusTwo();
  for (const key of ids) {
    const element = id(key);
    if (element && !element.value) element.value = value;
  }
}
defaultPeriodD2(['start', 'end', 'c5Start', 'c5End']);
const chartObjs = {};
const nf = new Intl.NumberFormat('pt-BR');
const num = x => nf.format(x ?? 0);
const pct = x => x === null || x === undefined ? '—' : `${(x*100).toFixed(2).replace('.', ',')}%`;
const fnum = x => Number(x).toFixed(2).replace('.', ',');
const datefmt = s => s ? s.split('-').reverse().join('/') : '—';
const safe = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const qs = obj => new URLSearchParams(Object.entries(obj).filter(([,v])=>v!==''&&v!==null&&v!==undefined)).toString();
function deltaHTML(d){
 if (!d || d.pp===null) return '<span class="delta flat">—</span>';
 const cls = d.pp>0?'up':d.pp<0?'down':'flat';
 const sig = d.pp>0?'+':'';
 const rel = d.percentual===null ? '' : `<small>${d.percentual>0?'+':''}${fnum(d.percentual)}% relativo</small>`;
 return `<span class="delta-line"><span class="delta ${cls}">${sig}${fnum(d.pp)} p.p.</span>${rel}</span>`;
}
function chipRate(r){
 if(r===null || r===undefined)return '—';
 return `<span class="pct ${r>=.80?'good':'bad'}">${pct(r)}</span>`;
}
function values(){return {inicio:id('start').value,fim:id('end').value,uf:id('uf').value,sc:id('sc').value,base:id('base').value,min_volume:id('minvol').value};}
function selectOptions(el, list, mapper, keep){
 const previous = keep ? el.value : '';
 el.innerHTML = '<option value="">Todos</option>' + list.map(x=>{let [val,label]=mapper(x);return `<option value="${safe(val)}">${safe(label)}</option>`;}).join('');
 if([...el.options].some(o=>o.value===previous))el.value=previous;
}
async function getJSON(url){
 const res=await fetch(url,{cache:'no-cache'});
 if(!res.ok){const t=await res.text();throw new Error(`Erro ${res.status}: ${t.slice(0,300)}`);}
 return res.json();
}
async function refreshFilters(){
 const uf=id('uf').value,sc=id('sc').value;
 const data=await getJSON('/api/filtros?'+qs({uf,sc}));
 selectOptions(id('uf'),data.ufs,x=>[x,x],true);
 selectOptions(id('sc'),data.scs,x=>[x,x],true);
 selectOptions(id('base'),data.bases,x=>[x.nome,`${x.nome} · ${x.uf}`],true);
}
const commonOpts={responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{backgroundColor:'#252a34',padding:12,displayColors:false,titleFont:{size:12},bodyFont:{size:11}}},scales:{y:{beginAtZero:true,max:100,grid:{color:'#edf0f4'},ticks:{callback:x=>x+'%'}},x:{grid:{display:false},ticks:{maxRotation:0,autoSkip:true,maxTicksLimit:14}}}};
function buildChart(canvas,type,labels,datasets,details,opts={}){
 if(chartObjs[canvas])chartObjs[canvas].destroy();
 if(typeof Chart==='undefined'){id(canvas).replaceWith(document.createTextNode('Não foi possível carregar o Chart.js.'));return;}
 chartObjs[canvas]=new Chart(id(canvas), {type,data:{labels,datasets},options:{...commonOpts,...opts,
 plugins:{...commonOpts.plugins,...opts.plugins,tooltip:{...commonOpts.plugins.tooltip,...(opts.plugins?.tooltip||{}),
 callbacks:{afterBody:ctx=>details?.[ctx[0].dataIndex]||''}}},scales:{...commonOpts.scales,...opts.scales}}});
}
function weekLabel(s){let d=new Date(s+'T12:00:00');let w=Math.ceil((((d-new Date(d.getFullYear(),0,1))/86400000)+new Date(d.getFullYear(),0,1).getDay()+1)/7);return `W${String(w).padStart(2,'0')}`;}
function formatComparative(d){return d?.pp===null ? 'sem base de comparação' : `${d.pp>0?'+':''}${fnum(d.pp)} p.p. | ${d.percentual>0?'+':''}${d.percentual===null?'—':fnum(d.percentual)+'%'} relativo`;}
function drawCharts(x){
 const daily=x.evolucao_diaria, weekly=x.evolucao_semanal,uf=x.ranking_uf,months=x.evolucao_mensal;
 buildChart('dailyChart','line',daily.map(i=>datefmt(i.data).slice(0,5)),[
  {label:'1BD',data:daily.map(i=>i.taxa===null?null:i.taxa*100),borderColor:'#d7242e',backgroundColor:'#d7242e15',fill:true,tension:.25,pointRadius:3,spanGaps:true,borderWidth:2.5},
  {label:'Meta referência',data:daily.map(()=>x.contexto.meta*100),borderColor:'#9CA3AF',borderDash:[5,5],pointRadius:0,borderWidth:1.3}
 ],daily.map(i=>[`Avaliações: ${num(i.total)}`,`Sim: ${num(i.sim)}`,`Vs mesmo dia semana passada: ${formatComparative(i.vs_d7)}`]),
 {plugins:{tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${ctx.raw===null?'—':fnum(ctx.raw)+'%'}`}}}});
 buildChart('weeklyChart','bar',weekly.map(i=>weekLabel(i.inicio)),[
  {label:'Taxa',data:weekly.map(i=>i.taxa===null?null:i.taxa*100),backgroundColor:weekly.map((i,idx)=>idx===weekly.length-1?'#D7242E':'#5B6573'),borderRadius:5,maxBarThickness:34}
 ],weekly.map(i=>[`De ${datefmt(i.inicio)} a ${datefmt(i.fim)}`,`Avaliações: ${num(i.total)} (Sim: ${num(i.sim)})`,`Vs semana anterior: ${formatComparative(i.vs_semana_anterior)}`]));
 buildChart('ufChart','bar',uf.map(i=>i.nome),[
   {label:'Taxa por UF',data:uf.map(i=>i.taxa===null?null:i.taxa*100),backgroundColor:'#CA2D36',borderRadius:5,maxBarThickness:60}
 ],uf.map(i=>[`Avaliações: ${num(i.total)}`,`Semana anterior: ${pct(i.semana_passada.taxa)}`,`Semana atual: ${pct(i.semana.taxa)}`,`Variação: ${formatComparative(i.variacao_semana)}`]));
 buildChart('monthChart','line',months.map(i=>i.mes.slice(5)+'/'+i.mes.slice(2,4)),[
   {label:'Taxa por mês',data:months.map(i=>i.taxa===null?null:i.taxa*100),borderColor:'#404B59',backgroundColor:'#404B5919',borderWidth:2.5,pointRadius:5,fill:true,tension:.2}
 ],months.map((i,ind)=>[`Avaliações: ${num(i.total)}`, `Sim: ${num(i.sim)}`,ind>0 && months[ind-1].taxa!==null ? `Vs mês anterior: ${formatComparative({pp:Math.round((i.taxa-months[ind-1].taxa)*10000)/100,percentual:Math.round((i.taxa/months[ind-1].taxa-1)*10000)/100})}`:'']));
}
function fillSC(items){
 id('scCounter').textContent=`${num(items.length)} responsáveis`;
 id('scTable').innerHTML=items.length ? items.map(i=>`<tr><td>${safe(i.nome)}</td><td>${safe(i.tipo)}</td><td class="right">${num(i.total)}</td><td class="right">${num(i.sim)}</td><td class="right">${num(i.nao)}</td><td class="right">${chipRate(i.taxa)}</td><td class="right">${pct(i.semana_passada.taxa)}</td><td class="right">${pct(i.semana.taxa)}</td><td class="right">${deltaHTML(i.variacao_semana)}</td><td class="right">${pct(i.mesmo_dia_semana_passada.taxa)}</td><td class="right">${deltaHTML(i.variacao_d7)}</td></tr>`).join(''):'<tr><td colspan="11" class="empty">Nenhum S/C encontrado para os filtros</td></tr>';
}
function fillBase(items){
 id('baseCounter').textContent=`${num(items.length)} bases`;
 id('baseTable').innerHTML=items.length ? items.map(i=>`<tr><td>${safe(i.nome)}<span class="sub">${safe(i.codigo)}</span></td><td>${safe(i.uf)}</td><td>${safe(i.sc)}</td><td class="right">${num(i.total)}</td><td class="right">${num(i.sim)}</td><td class="right">${num(i.nao)}</td><td class="right">${chipRate(i.taxa)}</td><td class="right">${pct(i.semana_passada.taxa)}</td><td class="right">${pct(i.semana.taxa)}</td><td class="right">${deltaHTML(i.variacao_semana)}</td><td class="right">${pct(i.mesmo_dia_semana_passada.taxa)}</td><td class="right">${deltaHTML(i.variacao_d7)}</td></tr>`).join(''):'<tr><td colspan="12" class="empty">Nenhuma base encontrada para os filtros</td></tr>';
}
async function load(){
 const b=id('apply');b.disabled=true;b.textContent='Atualizando...';
 id('notice').hidden=true;
 try{
  const x=await getJSON('/api/dashboard?'+qs(values()));
  if(x.sem_dados){id('notice').hidden=false;id('notice').textContent=x.mensagem;id('panelContent').hidden=true;return;}
  id('panelContent').hidden=false;
  const c=x.contexto;
  if(!id('start').value)id('start').value=c.inicio;
  if(!id('end').value)id('end').value=c.fim;
  id('start').min=c.primeira_data;id('end').max=c.ultima_data;
  id('lastDate').textContent=`Última avaliação: ${datefmt(c.ultima_data)}`;
  id('kpiRate').textContent=pct(x.resumo.taxa);
  id('kpiTotal').textContent=`${num(x.resumo.total)} avaliações`;
  id('kpiYes').textContent=num(x.resumo.sim);id('kpiNo').textContent=num(x.resumo.nao);
  id('rateBar').style.width=`${Math.min(100,(x.resumo.taxa||0)*100)}%`;
  id('kpiGoal').textContent=`Meta de referência: ${pct(c.meta)}`;
  id('kpiWeek').textContent=pct(x.semana_atual.taxa);
  id('kpiPrev').textContent=pct(x.semana_passada.taxa);
  id('weekLabel').textContent=`${datefmt(c.semana_inicio)}–${datefmt(c.semana_fim)}`;
  id('prevLabel').textContent=`${datefmt(c.semana_passada_inicio)}–${datefmt(c.semana_passada_fim)}`;
  id('weekDelta').innerHTML=deltaHTML(x.semana_atual.vs_semana_passada);
  id('kpiDay').textContent=pct(x.dia_atual.taxa);
  const d=new Date(c.fim+'T12:00:00');d.setDate(d.getDate()-7);
  id('dayLabel').textContent=`${datefmt(c.fim)} vs ${datefmt(d.toISOString().slice(0,10))}`;
  id('dayDelta').innerHTML=deltaHTML(x.dia_atual.vs_mesmo_dia_semana_passada);
  fillSC(x.ranking_sc);fillBase(x.ranking_bases);drawCharts(x);
 }catch(e){id('notice').hidden=false;id('notice').textContent=e.message;}
 finally{b.disabled=false;b.textContent='Aplicar';}
}
id('apply').addEventListener('click',load);
id('clear').addEventListener('click',async()=>{
 ['uf','sc','base'].forEach(k=>id(k).value='');id('start').value='';id('end').value='';defaultPeriodD2(['start','end']);id('minvol').value='1';
 await refreshFilters();await load();
});
id('uf').addEventListener('change',async()=>{id('sc').value='';id('base').value='';await refreshFilters();});
id('sc').addEventListener('change',async()=>{id('base').value='';await refreshFilters();});
id('export').addEventListener('click',()=>{
 const f=values();delete f.min_volume;
 location.href='/api/exportar.csv?'+qs(f);
});
(async()=>{try{await refreshFilters();await load();}catch(e){id('notice').hidden=false;id('notice').textContent=e.message;}})();


// Navegação compartilhada da suíte. Indicadores sem arquivo validado não exibem métricas.
const indicatorTabs = ['1bd','5cd','csat'];
function selectIndicator(name, updateUrl=true) {
 const active = indicatorTabs.includes(name) ? name : '1bd';
 for (const key of indicatorTabs) {
  const show = key===active;
  const tab = id(`tab-${key}`);
  tab.setAttribute('aria-selected', String(show));
  tab.classList.toggle('active',show);
  id(`indicador-${key}`).hidden=!show;
 }
 document.title = `J&T Express | ${active.toUpperCase()} · Qualidade`;
 if(updateUrl) history.replaceState(null,'',`#${active}`);
 // Chart.js dimensiona canvases apenas quando visíveis: corrigir ao reabrir o 1BD.
 if(active==='1bd') requestAnimationFrame(()=>Object.values(chartObjs).forEach(chart=>chart.resize()));
 if(active==='5cd') requestAnimationFrame(()=>window.load5cd?.());
 if(active==='csat') requestAnimationFrame(()=>window.loadCsat?.());
}
document.querySelectorAll('.indicator-tab').forEach(tab=>{
 tab.addEventListener('click',()=>selectIndicator(tab.dataset.indicator));
 tab.addEventListener('keydown',event=>{
  if(!['ArrowLeft','ArrowRight'].includes(event.key))return;
  const current=indicatorTabs.indexOf(tab.dataset.indicator);
  const next=indicatorTabs[(current+(event.key==='ArrowRight'?1:indicatorTabs.length-1))%indicatorTabs.length];
  id(`tab-${next}`).focus();selectIndicator(next);event.preventDefault();
 });
});
window.addEventListener('hashchange',()=>selectIndicator(location.hash.slice(1),false));
selectIndicator(location.hash.slice(1)||'1bd',false);
