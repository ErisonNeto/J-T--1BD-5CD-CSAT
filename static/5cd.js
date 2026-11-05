/* Indicador 5CD: volumes/snapshots. Sem porcentagem de sucesso inventada. */
const c5 = n => document.getElementById(n);
const c5format = new Intl.NumberFormat('pt-BR',{maximumFractionDigits:2});
const c5num = v => v===null || v===undefined ? '—' : c5format.format(v);
const c5safe = s => String(s??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const c5fmt = s=>s?s.split('-').reverse().join('/'):'—';
const c5qs=o=>new URLSearchParams(Object.entries(o).filter(([,v])=>v!==''&&v!=null)).toString();
const c5plots={}; let c5Init=false;let c5Busy=false;
const c5params=()=>({inicio:c5('c5Start').value,fim:c5('c5End').value,uf:c5('c5Uf').value,sc:c5('c5Sc').value,base:c5('c5Base').value,min_volume:c5('c5Minvol').value});
async function c5get(url){const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw new Error((await response.text()).slice(0,350));return response.json();}
function c5delta(d){
 if(!d||d.abs===null||d.abs===undefined)return '<span class="delta flat">—</span>';
 const cls=d.abs<0?'up':d.abs>0?'down':'flat',sign=d.abs>0?'+':'';
 const pct=d.percentual===null||d.percentual===undefined?'':`<small>${d.percentual>0?'+':''}${c5num(d.percentual)}%</small>`;
 return `<span class="delta-line"><span class="delta ${cls}">${sign}${c5num(d.abs)} rem.</span>${pct}</span>`;
}
function c5choices(el,values,mapper){
 const prior=el.value;
 el.innerHTML='<option value="">Todos</option>'+values.map(o=>{const [value,title]=mapper(o);return `<option value="${c5safe(value)}">${c5safe(title)}</option>`}).join('');
 if([...el.options].some(o=>o.value===prior))el.value=prior;
}
async function c5filters(){
 const uf=c5('c5Uf').value,sc=c5('c5Sc').value;
 const data=await c5get('/api/5cd/filtros?'+c5qs({uf,sc}));
 c5choices(c5('c5Uf'),data.ufs,v=>[v,v]);
 c5choices(c5('c5Sc'),data.scs,v=>[v,v]);
 c5choices(c5('c5Base'),data.bases,v=>[v.nome,`${v.nome} · ${v.uf}`]);
}
function c5chart(elem,kind,labels,values,title,details,colors){
 if(c5plots[elem])c5plots[elem].destroy();
 if(typeof Chart==='undefined')return;
 c5plots[elem]=new Chart(c5(elem),{type:kind,data:{labels,datasets:[{label:title,data:values,
   borderColor:'#D7242E',backgroundColor:colors||'#D7242E',borderRadius:5,maxBarThickness:43,
   borderWidth:2,fill:kind==='line',tension:.25,pointRadius:kind==='line'?3:0,spanGaps:false}]},
   options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{afterBody:ctx=>details?.[ctx[0].dataIndex]||''}}},
     scales:{x:{ticks:{maxRotation:0,maxTicksLimit:12},grid:{display:false}},y:{beginAtZero:true,grid:{color:'#EDF0F4'}}}}});
}
function c5rank(idName,items,isBase){
 const html=items.length?items.map(x=>`<tr>
 <td>${c5safe(x.nome)}${isBase?`<span class="sub">${c5safe(x.codigo)}</span>`:''}</td>
 <td>${c5safe(isBase?x.uf:x.tipo)}</td>${isBase?`<td>${c5safe(x.sc)}</td>`:''}
 <td class="right">${c5num(x.total)}</td><td class="right">${c5num(x.aging_10_plus)}</td>
 <td class="right">${c5num(x.semana_passada.media)}</td><td class="right">${c5num(x.semana.media)}</td>
 <td class="right">${c5delta(x.variacao_semana)}</td><td class="right">${c5num(x.mesmo_dia_semana_passada)}</td>
 <td class="right">${c5delta(x.variacao_d7)}</td></tr>`).join(''):
 `<tr><td class="empty" colspan="${isBase?10:9}">Sem dados neste período</td></tr>`;
 c5(idName).innerHTML=html;
}
async function c5load(force=false){
 if(c5Busy)return;
 if(!force&&location.hash!=="#5cd")return;
 c5Busy=true;c5('c5Apply').disabled=true;
 c5('c5Notice').hidden=true;
 try{
  if(!c5Init){await c5filters();c5Init=true;}
  const x=await c5get('/api/5cd/dashboard?'+c5qs(c5params()));
  if(x.sem_dados){c5('c5Content').hidden=true;c5('c5Notice').hidden=false;c5('c5Notice').textContent=x.mensagem;return;}
  c5('c5Content').hidden=false;
  const ctx=x.contexto;
  if(!c5('c5Start').value)c5('c5Start').value=ctx.inicio;
  if(!c5('c5End').value)c5('c5End').value=ctx.fim;
  c5('c5Start').min=ctx.primeira_data;c5('c5End').max=ctx.ultima_data;
  c5('c5Date').textContent=`Relatório ${c5fmt(ctx.data_referencia)} · último disponível ${c5fmt(ctx.ultima_data)}`;
  c5('c5Total').textContent=c5num(x.resumo.total);c5('c5Aging5').textContent=c5num(x.resumo.aging_5_9);
  c5('c5Aging10').textContent=c5num(x.resumo.aging_10_plus);
  c5('c5Aging5Delta').innerHTML=c5delta(x.aging_variacao_semana.aging_5_9);
  c5('c5Aging10Delta').innerHTML=c5delta(x.aging_variacao_semana.aging_10_plus);
  c5('c5Week').textContent=c5num(x.semana_atual.media);c5('c5Prev').textContent=c5num(x.semana_passada.media);
  c5('c5WeekLabel').textContent=`${c5fmt(ctx.semana_inicio)}–${c5fmt(ctx.semana_fim)} · ${x.semana_atual.dias} dia(s)`;
  c5('c5PrevLabel').textContent=`${c5fmt(ctx.semana_passada_inicio)}–${c5fmt(ctx.semana_passada_fim)} · ${x.semana_passada.dias} dia(s)`;
  c5('c5WeekDelta').innerHTML=c5delta(x.semana_atual.vs_semana_passada);
  c5('c5PastDay').textContent=c5num(x.mesmo_dia_semana_passada);
  const d7=new Date(ctx.data_referencia+'T12:00:00');d7.setDate(d7.getDate()-7);
  c5('c5DayLabel').textContent=`${c5fmt(ctx.data_referencia)} vs ${c5fmt(d7.toISOString().slice(0,10))}`;
  c5('c5DayDelta').innerHTML=c5delta(x.dia_atual.vs_mesmo_dia_semana_passada);
  c5rank('c5ScTable',x.ranking_sc,false);c5rank('c5BaseTable',x.ranking_bases,true);
  c5('c5ScCount').textContent=`${c5num(x.ranking_sc.length)} responsáveis`;
  c5('c5BaseCount').textContent=`${c5num(x.ranking_bases.length)} bases`;
  const daily=x.evolucao_diaria,weekly=x.evolucao_semanal,ufs=x.ranking_uf;
  c5chart('c5DailyChart','line',daily.map(r=>c5fmt(r.data).slice(0,5)),daily.map(r=>r.total),'Pendentes',
    daily.map(r=>`10+ dias: ${c5num(r.aging_10_plus)} | D-7: ${r.vs_d7.percentual===null?'—':c5num(r.vs_d7.percentual)+'%'}`));
  c5chart('c5WeeklyChart','bar',weekly.map(r=>c5fmt(r.inicio).slice(0,5)),weekly.map(r=>r.media),'Média de pendentes',
    weekly.map(r=>`${c5fmt(r.inicio)}–${c5fmt(r.fim)} | ${r.dias} dia(s) | vs W-1 ${r.vs_semana_anterior.percentual===null?'—':c5num(r.vs_semana_anterior.percentual)+'%'}`));
  c5chart('c5UfChart','bar',ufs.map(r=>r.nome),ufs.map(r=>r.total),'Pendentes por UF',
    ufs.map(r=>`Semana atual: ${c5num(r.semana.media)} | W-1: ${c5num(r.semana_passada.media)} | Δ ${r.variacao_semana.percentual===null?'—':c5num(r.variacao_semana.percentual)+'%'}`));
  c5chart('c5AgeChart','bar',['5–9','10–14','15–19','20+'],
   [x.resumo.aging_5_9,x.resumo.aging_10_14,x.resumo.aging_15_19,x.resumo.aging_20_plus],
   'Dias em base',
    ['aging_5_9','aging_10_14','aging_15_19','aging_20_plus'].map(k=>`Variação W/W: ${x.aging_variacao_semana[k].percentual===null?'—':c5num(x.aging_variacao_semana[k].percentual)+'%'}`),
    ['#596273','#A06E36','#D9883A','#C52C36']);
 }catch(err){c5('c5Notice').textContent=err.message;c5('c5Notice').hidden=false;}
 finally{c5Busy=false;c5('c5Apply').disabled=false;}
}
window.load5cd=()=>c5load();
c5('c5Apply').addEventListener('click',()=>c5load(true));
c5('c5Clear').addEventListener('click',async()=>{
 ['c5Uf','c5Sc','c5Base'].forEach(key=>c5(key).value='');c5('c5Start').value='';c5('c5End').value='';defaultPeriodD2(['c5Start','c5End']);c5('c5Minvol').value='1';await c5filters();await c5load(true);
});
c5('c5Uf').addEventListener('change',async()=>{c5('c5Sc').value='';c5('c5Base').value='';await c5filters();});
c5('c5Sc').addEventListener('change',async()=>{c5('c5Base').value='';await c5filters();});
c5('c5Export').addEventListener('click',()=>{
 const args=c5params();delete args.min_volume;
 location.href='/api/5cd/exportar.csv?'+c5qs(args);
});
if(location.hash==='#5cd')requestAnimationFrame(()=>c5load(true));
