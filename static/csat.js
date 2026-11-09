// CSAT · usa as mesmas classes, componentes e funções visuais de 1BD/5CD.
// Semanas W44/W45 vêm da aba BASE, coluna D. Não recalcule semana ISO.
const csId = key => document.getElementById(key);
let csFiltersReady = false;
let csLoading = false;
const csFmtPct = v => v === null || v === undefined ? '—' : `${(v*100).toFixed(2).replace('.', ',')}%`;
const csFmtNum = v => new Intl.NumberFormat('pt-BR').format(v ?? 0);
// Tradução apenas visual: os valores originais permanecem no PostgreSQL.
const csCategoriaPT = Object.freeze({
  '干线工单': 'Transferência (Line Haul)',
  'DNR工单': 'Entrega não recebida (DNR)',
  '末端工单': 'Última milha (Last Mile)'
});
const csNomeCategoria = nome => csCategoriaPT[String(nome ?? '').trim()] ?? nome;
const csFmtPP = d => d?.pp === null || d?.pp === undefined ? '—' : `${d.pp>0?'+':''}${d.pp.toFixed(2).replace('.', ',')} p.p.`;
const csDiffCls = d => (d?.pp || 0) > 0 ? 'positive' : (d?.pp || 0) < 0 ? 'negative' : '';
const csSafe = x => String(x ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const csQs = obj => new URLSearchParams(Object.entries(obj).filter(([,v])=>v!==''&&v!==null&&v!==undefined)).toString();
function csOptions(el, values, getPair, keep=true) {
  const old = keep ? el.value : '';
  el.innerHTML = '<option value="">Todos</option>' + values.map(it=>{
    const [value,label]=getPair(it);
    return `<option value="${csSafe(value)}">${csSafe(label)}</option>`;
  }).join('');
  if ([...el.options].some(x=>x.value===old)) el.value=old;
}
async function csGet(url) {
  const response = await fetch(url, {cache:'no-store'});
  if (!response.ok) throw new Error(`Falha na API CSAT (HTTP ${response.status}). Confira JT_STORAGE_MODE=api e a tabela jt_csat_registros.`);
  return response.json();
}
async function csRefreshFilters(initial=false){
  const uf=csId('csUf').value, sc=csId('csSc').value;
  const filters=await csGet('/api/csat/filtros?'+csQs({uf,sc}));
  csOptions(csId('csStart'),filters.semanas,x=>[x.id,x.rotulo],true);
  csOptions(csId('csEnd'),filters.semanas,x=>[x.id,x.rotulo],true);
  csOptions(csId('csUf'),filters.ufs,x=>[x,x],true);
  csOptions(csId('csSc'),filters.scs,x=>[x,x],true);
  csOptions(csId('csBase'),filters.bases,x=>[x.nome,`${x.nome} · ${x.uf}`],true);
  if(initial && filters.semanas.length){
    csId('csStart').value=filters.semanas[filters.semanas.length-1].id;
    csId('csEnd').value=filters.semanas[filters.semanas.length-1].id;
  }
  csFiltersReady=true;
}
function csValues(){return {
  semana_inicio:csId('csStart').value,semana_fim:csId('csEnd').value,
  uf:csId('csUf').value,sc:csId('csSc').value,base:csId('csBase').value,
  min_volume:csId('csMinvol').value
};}
function csPlot(canvas, kind, labels, series, details=[],opts={}){
  // buildChart é a função Chart.js já usada nos indicadores 1BD e 5CD.
  buildChart(canvas,kind,labels,series,details,opts);
}
function csRenderCharts(data){
  const w=data.evolucao_semanal,d=data.evolucao_diaria,uf=data.ranking_uf,cat=data.ranking_categorias;
  csPlot('csWeeklyChart','line',w.map(x=>x.semana.split('-')[1]),[
    {label:'CSAT',data:w.map(x=>x.taxa===null?null:x.taxa*100),borderColor:'#d71920',backgroundColor:'#d7192020',tension:.22,pointRadius:6,fill:true,borderWidth:3}
  ],w.map(x=>[`Semana: ${x.rotulo}`,`Positivas: ${csFmtNum(x.sim)} / ${csFmtNum(x.total)}`,`Variação: ${csFmtPP(x.vs_anterior)}`]));
  csPlot('csDailyChart','line',d.map(x=>x.data.split('-').reverse().slice(0,2).join('/')),[
    {label:'CSAT diário',data:d.map(x=>x.taxa===null?null:x.taxa*100),borderColor:'#4f5c70',backgroundColor:'#4f5c7018',fill:true,tension:.22,pointRadius:3,borderWidth:2}
  ],d.map(x=>[`Data: ${x.data}`,`Positivas: ${csFmtNum(x.sim)} / ${csFmtNum(x.total)}`]));
  csPlot('csUfChart','bar',uf.map(x=>x.nome),[
    {label:'CSAT UF',data:uf.map(x=>x.taxa===null?null:x.taxa*100),backgroundColor:'#d71920',borderRadius:5,maxBarThickness:56}
  ],uf.map(x=>[`Avaliações: ${csFmtNum(x.total)}`,`Positivas: ${csFmtNum(x.sim)}`,`Variação W/W: ${csFmtPP(x.variacao_semana)}`]));
  csPlot('csCategoryChart','bar',cat.map(x=>csNomeCategoria(x.nome)),[
    {label:'Positivas',data:cat.map(x=>x.sim),backgroundColor:'#199a62',borderRadius:4,maxBarThickness:44},
    {label:'Negativas',data:cat.map(x=>x.nao),backgroundColor:'#d71920',borderRadius:4,maxBarThickness:44}
  ],cat.map(x=>[`Total: ${csFmtNum(x.total)}`,`CSAT: ${csFmtPct(x.taxa)}`]),
  {plugins:{legend:{display:true,position:'bottom'}},scales:{y:{beginAtZero:true,grid:{color:'#edf0f4'},ticks:{precision:0}},x:{grid:{display:false},ticks:{autoSkip:false,maxRotation:20}}}});
}
function csFillTable(idBody,idCount,items,isBase){
  csId(idCount).textContent=`${csFmtNum(items.length)} ${isBase?'bases':'responsáveis'}`;
  const cols=isBase?10:9;
  csId(idBody).innerHTML=items.length?items.map(x=>{
    const title=isBase
      ? `<td>${csSafe(x.nome)}</td><td>${csSafe(x.uf)}</td><td>${csSafe(x.sc)}</td>`
      : `<td>${csSafe(x.nome)}</td><td>${csSafe(x.tipo)}</td>`;
    return `<tr>${title}<td class="right">${csFmtNum(x.total)}</td><td class="right">${csFmtNum(x.sim)}</td><td class="right">${csFmtNum(x.nao)}</td><td class="right"><strong>${csFmtPct(x.taxa)}</strong></td><td class="right">${csFmtPct(x.semana_passada.taxa)}</td><td class="right">${csFmtPct(x.semana.taxa)}</td><td class="right"><span class="delta ${csDiffCls(x.variacao_semana)==='positive'?'up':csDiffCls(x.variacao_semana)==='negative'?'down':'flat'}">${csFmtPP(x.variacao_semana)}</span></td></tr>`;
  }).join(''):`<tr><td colspan="${cols}" class="empty">Sem avaliações para os filtros selecionados</td></tr>`;
}
async function loadCsat(){
  if(csLoading) return;
  csLoading=true;
  const btn=csId('csApply');btn.disabled=true;btn.textContent='Atualizando...';
  csId('csNotice').hidden=true;
  try{
    if(!csFiltersReady)await csRefreshFilters(true);
    const x=await csGet('/api/csat/dashboard?'+csQs(csValues()));
    if(x.sem_dados){csId('csContent').hidden=true;csId('csNotice').hidden=false;csId('csNotice').textContent=x.mensagem;return;}
    csId('csContent').hidden=false;
    csId('csLast').textContent=`Última semana: ${x.contexto.ultima_semana}`;
    csId('csRate').textContent=csFmtPct(x.resumo.taxa);
    csId('csRateTotal').textContent=`${csFmtNum(x.resumo.total)} avaliações`;
    csId('csPositive').textContent=csFmtNum(x.resumo.sim);
    csId('csNegative').textContent=csFmtNum(x.resumo.nao);
    csId('csCurrent').textContent=csFmtPct(x.semana_atual.taxa);
    csId('csPrevious').textContent=csFmtPct(x.semana_passada.taxa);
    csId('csCurrentLabel').textContent=x.contexto.semana_fim;
    csId('csPreviousLabel').textContent=x.contexto.semana_anterior||'Sem semana anterior';
    csId('csVariation').textContent=csFmtPP(x.variacao_semana);
    csId('csVariation').className='kpi-value '+csDiffCls(x.variacao_semana);
    csId('csRelative').textContent=x.variacao_semana.percentual===null?'Sem base de comparação':
       `${x.variacao_semana.percentual>0?'+':''}${x.variacao_semana.percentual.toFixed(2).replace('.', ',')}% relativo à semana anterior`;
    csFillTable('csScTable','csScCount',x.ranking_sc,false);
    csFillTable('csBaseTable','csBaseCount',x.ranking_bases,true);
    csRenderCharts(x);
  }catch(e){csId('csNotice').hidden=false;csId('csNotice').textContent=e.message;csId('csContent').hidden=true;}
  finally{btn.disabled=false;btn.textContent='Aplicar';csLoading=false;}
}
csId('csApply').addEventListener('click',loadCsat);
csId('csClear').addEventListener('click',async()=>{
  for(const k of ['csStart','csEnd','csUf','csSc','csBase'])csId(k).value='';
  csId('csMinvol').value='1';csFiltersReady=false;await loadCsat();
});
csId('csUf').addEventListener('change',async()=>{csId('csSc').value='';csId('csBase').value='';await csRefreshFilters();});
csId('csSc').addEventListener('change',async()=>{csId('csBase').value='';await csRefreshFilters();});
csId('csExport').addEventListener('click',()=>{
  const vals=csValues();delete vals.min_volume;
  location.href='/api/csat/exportar.csv?'+csQs(vals);
});
window.loadCsat=loadCsat;
if(location.hash.slice(1)==='csat')loadCsat();
