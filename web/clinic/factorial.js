'use strict';

const $ = id => document.getElementById(id);
const methods = {fixed:'固定常态归属', targeted:'按需开放归属', full:'全量开放归属', closure:'完整影响闭包'};
const snapshots = {dense_loop_a13:'三机巡检快照', unified_bed_local_r1:'含长时库存检查的巡检快照'};
const cells = {e0_g0:'无应急 · 物资站可用', e0_g1:'无应急 · 物资站占用', e1_g0:'有应急 · 物资站可用',
  e1_g1:'有应急 · 物资站占用', qualification:'机制检查 · 原归属资格撤销'};
const statuses = {OPTIMAL:'可行，已证最优', FEASIBLE_BUDGET:'预算内可行', INFEASIBLE:'已证无解', UNKNOWN_BUDGET:'预算内未找到解'};
const n = (v, digits=1) => Number.isFinite(v) ? v.toFixed(digits) : '—';
let study, cell = 'e1_g1', map, selected, requestId = 0;

function make(tag, content) {
  const node = document.createElement(tag);
  if (content !== undefined) node.textContent = content;
  return node;
}

async function fetchJSON(path) {
  const res = await fetch(path);
  const data = await res.json();
  if (!res.ok) throw Error(data.error);
  return data;
}

function fill(id, entries) {
  $(id).replaceChildren(...entries.map(([key,label]) => new Option(label,key)));
}

function table(headers, rows, firstColumnHeader=false) {
  const t = make('table');
  const hr = t.createTHead().insertRow();
  for (const label of headers) {
    const th = make('th', label);
    th.scope = 'col';
    hr.append(th);
  }
  const body = t.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const [i,value] of row.entries()) {
      const heading = firstColumnHeader && i === 0;
      const td = make(heading ? 'th' : 'td', value);
      if (heading) td.scope = 'row';
      tr.append(td);
    }
  }
  return t;
}

function current() {
  return study.snapshots[$('snapshot').value][cell];
}

function choose(id) {
  cell = id;
  selected = null;
  render();
}

function render() {
  const group = study.snapshots[$('snapshot').value];
  const view = current();
  $('matrix').replaceChildren(...Object.keys(cells).slice(0,4).map(id => {
    const state = group[id].results.fixed;
    const button = make('button', cells[id]);
    button.type = 'button';
    button.setAttribute('aria-pressed', id === cell);
    button.append(make('small', '固定归属：' + (statuses[state.status] || state.status)));
    button.onclick = () => choose(id);
    return button;
  }));
  $('mechanism').setAttribute('aria-pressed', cell === 'qualification');
  renderOffsetChart(group);
  const margin = $('margin').value;
  const fixed = view.results.fixed?.metrics;
  const full = view.results.full?.metrics;
  const text = ['当前条件：' + cells[cell] + '。'];
  if (fixed && full) {
    const delay = fixed.positive_delay - full.positive_delay;
    const delivery = full.delivery_from_confirmed - fixed.delivery_from_confirmed;
    text.push(Math.abs(delay) < 0.05 ? '两种策略的常态完工正向偏移相同。' :
      '全量开放的常态完工正向偏移' + (delay < 0 ? '增加 ' : '减少 ') + n(Math.abs(delay)) + ' 秒。');
    if (view.factors.event) text.push(Math.abs(delivery) < 0.05 ? '预测交付时间相同。' :
      '全量开放的预测交付' + (delivery < 0 ? '提前 ' : '推迟 ') + n(Math.abs(delivery)) + ' 秒。');
  } else if (cell === 'qualification') {
    text.push('此条件只撤销一个常态任务原执行者的资格，用来检查固定分工为何失效。');
  }
  $('conclusion').textContent = text.join('');
  const four = ['e0_g0','e0_g1','e1_g0','e1_g1'];
  const summary = table(['策略','四格预算内可行','额外叠加延误 / s'],study.methods.map(key => {
    const results = four.map(id => group[id].results[key]);
    const offsets = results.map(r => r.metrics?.positive_delay);
    const interaction = offsets.every(Number.isFinite) ? offsets[3] - offsets[2] - offsets[1] + offsets[0] : null;
    return [methods[key],results.filter(r => Number.isFinite(r.first) && r.first <= study.budget).length + ' / 4',n(interaction)];
  }),true);
  $('interactions').replaceChildren(summary);
  $('metrics').replaceChildren(table(['策略','求解状态','首个可验证解 / s','总耗时 / s','常态改派 / 项','交付 / s',
    '完工正向偏移 / s','超出评价线 / s'], study.methods.map(key => {
    const r = view.results[key], m = r.metrics || {};
    return [methods[key], statuses[r.status] || r.status, n(r.first,3), n(r.seconds,3),
      m.accepted_owner_changes ?? '—', n(m.delivery_from_confirmed), n(m.positive_delay), n(m.tardiness?.[margin])];
  }), true));
  $('prefix').textContent = '快照中保留的已派发任务：' + view.issued.map(x => x.robot.toUpperCase() + ' / ' + x.job).join('、');
  renderGantt(view);
  $('targets').replaceChildren(table(['目标点','站点','地图坐标 / m'],
    [...new Map(Object.values(view.targets).map(t => [t.anchor,t])).values()].map(t =>
      [t.label,t.anchor,t.xy.map(x => n(x,2)).join(', ')]),true));
  const offsets = view.results[$('method').value].metrics?.completion_offset;
  $('task-offsets').replaceChildren(...(offsets ? [table(['常态任务','服务点','相对原计划完工 / s'],
    Object.entries(offsets).map(([id,offset]) => [id,view.targets[id].anchor,n(offset)]),true)] : []));
  const gaps = view.results[$('method').value]?.qualificationGaps;
  $('qualification').textContent = !gaps ? '当前策略没有可供资格检查的计划。' : gaps.length ?
    '当前策略的资格缺口：' + gaps.join('；') + '。' : '当前计划的应急角色与旧证书一致。该条件的并发时序仍需本轮执行验证。';
  renderTask(view);
}

function renderOffsetChart(group) {
  const ids = Object.keys(cells).slice(0,4);
  const compared = ['fixed','targeted','full'];
  const delay = (id,key) => group[id].results[key].metrics?.positive_delay;
  const max = Math.max(1,...ids.flatMap(id => compared.map(key => delay(id,key) ?? 0)));
  $('offset-chart').replaceChildren(...ids.map(id => {
    const panel = make('div');
    panel.className = 'offset-group';
    panel.append(make('strong',cells[id]));
    for (const key of compared) {
      const row = make('div');
      row.className = 'offset-row ' + key;
      const track = make('div');
      track.className = 'offset-track';
      track.setAttribute('aria-hidden','true');
      const bar = make('span');
      const value = delay(id,key);
      bar.style.width = ((value ?? 0)/max*100) + '%';
      track.append(bar);
      row.append(make('span',methods[key]),track,make('span',n(value)));
      panel.append(row);
    }
    return panel;
  }));
}

function renderGantt(view) {
  const other = $('method').value;
  const comparison = other === 'fixed' ? ['fixed'] : ['fixed',other];
  const limit = Math.max(100, Math.ceil(Math.max(0,...Object.values(view.results).flatMap(r => (r.bars || []).map(x => x.finish)))/100) * 100);
  const graph = make('div');
  graph.className = 'gantt';
  for (const method of comparison) {
    const result = view.results[method];
    graph.append(make('h3', methods[method] + (result.bars ? '' : ' · ' + (statuses[result.status] || result.status))));
    if (!result.bars) continue;
    const ruler = make('div');
    ruler.className = 'ruler';
    for (let i=0; i<=5; i++) {
      const tick = make('span', n(limit*i/5,0) + ' s');
      tick.style.left = i*20 + '%';
      ruler.append(tick);
    }
    graph.append(make('span','机器人'), ruler);
    for (const robot of ['r1','r2','r3']) {
      const track = make('div');
      track.className = 'track';
      for (const bar of result.bars.filter(x => x.robot === robot)) {
        const t = view.targets[bar.id];
        const button = make('button', t.anchor);
        button.type = 'button';
        button.className = t.kind === 'normal' ? '' : 'event';
        button.style.left = bar.start/limit*100 + '%';
        button.style.width = (bar.finish-bar.start)/limit*100 + '%';
        button.title = t.label + ' · ' + n(bar.start) + '–' + n(bar.finish) + ' 秒';
        button.setAttribute('aria-label',button.title);
        button.onclick = () => { selected = {bar,method}; renderTask(view); };
        track.append(button);
      }
      graph.append(make('strong', robot.toUpperCase()),track);
    }
  }
  $('gantt').replaceChildren(graph);
}

function renderTask(view) {
  const bar = selected?.bar;
  const t = bar && view.targets[bar.id];
  $('task-detail').textContent = t ?
    methods[selected.method] + ' · ' + bar.robot.toUpperCase() + ' · ' + t.label + '（' + t.anchor + '）· ' +
    n(bar.start) + '–' + n(bar.finish) + ' 秒 · ' + bar.id : '选择甘特图中的任务查看服务站和计划时间。';
  drawMap(view.targets, t?.anchor);
}

function drawMap(targets, highlight) {
  const canvas = $('map'), bounds = canvas.getBoundingClientRect(), ratio = devicePixelRatio || 1;
  const w = bounds.width, h = bounds.height;
  canvas.width = w*ratio;
  canvas.height = h*ratio;
  const ctx = canvas.getContext('2d');
  ctx.scale(ratio,ratio);
  const points = [...new Map(Object.values(targets).map(t => [t.anchor,t])).values()];
  const xmin = Math.min(...points.map(t => t.xy[0])) - 2, xmax = Math.max(...points.map(t => t.xy[0])) + 2;
  const ymin = Math.min(...points.map(t => t.xy[1])) - 2, ymax = Math.max(...points.map(t => t.xy[1])) + 2;
  const scale = Math.min((w-40)/(xmax-xmin),(h-35)/(ymax-ymin));
  const xy = (x,y) => [(w-(xmax-xmin)*scale)/2+(x-xmin)*scale, (h-(ymax-ymin)*scale)/2+(ymax-y)*scale];
  if (map) {
    const [x,y] = xy(map.origin[0],map.origin[1]+map.height*map.resolution);
    ctx.drawImage(map.image,x,y,map.width*map.resolution*scale,map.height*map.resolution*scale);
  }
  ctx.font = '600 15px system-ui';
  for (const t of points) {
    const [x,y] = xy(...t.xy);
    ctx.fillStyle = t.kind === 'normal' ? '#2b5c73' : '#a24726';
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x,y,t.anchor === highlight ? 9 : 5,0,2*Math.PI);
    ctx.fill();
    ctx.stroke();
    ctx.lineWidth = 4;
    ctx.strokeText(t.anchor,x+9,y-7);
    ctx.fillText(t.anchor,x+9,y-7);
  }
}

function renderEvidence() {
  const e = study.execution;
  const evidence = $('execution-evidence');
  evidence.replaceChildren(make('p',e.description || '本实验的规划结果尚无同条件 Gazebo 执行记录。'));
  if (e.pairing) evidence.append(make('p',e.pairing));
  if (e.records?.length) {
    evidence.append(make('p','核验确认至实际交付：' + n(e.deliveryAfterConfirmation,2) +
      ' 仿真秒。后续常态任务完成并驶离服务区：回合第 ' + n(e.routineCompletion,2) + ' 秒。'));
    const scroll = make('div');
    scroll.className = 'scroll';
    scroll.append(table(['机器人','任务','服务开始 / s','服务完成 / s'],e.records.map(t =>
      [t.robot,t.label,n(t.start),n(t.finish)])));
    evidence.append(scroll);
  }
  $('observation-evidence').replaceChildren(...(study.observations.length ?
    [make('p','以下时间使用真实视频时钟。关键点数来自已保存的模型记录。'),
    table(['片段','源视频','视频区间 / s','最低可见点数','恢复点数'],study.observations.map(x =>
      [x.label,x.video,n(x.start,2)+'–'+n(x.end,2),String(x.minimum),String(x.recovered)]))] :
    [make('p','此批次尚无人工复核的真实遮挡片段。')]));
}

async function load() {
  const id = ++requestId;
  const data = await fetchJSON('/api/factorial?name=' + encodeURIComponent($('experiment').value));
  if (id !== requestId) return;
  study = data;
  $('status').textContent = '';
  $('hold').textContent = '从快照时刻起占用 G1 ' + study.g1Seconds + ' 秒';
  fill('snapshot',Object.keys(study.snapshots).map(k => [k,snapshots[k] || k]));
  fill('margin',study.margins.map(m => [String(m),'原计划完成 +' + m + ' 秒']));
  fill('method',study.methods.map(m => [m,methods[m]]));
  $('margin').value = '90';
  $('method').value = 'targeted';
  $('study').hidden = false;
  renderEvidence();
  choose('e1_g1');
}

function showError(error) {
  $('status').textContent = '读取实验失败：' + error.message;
}

async function start() {
  const list = await fetchJSON('/api/factorial');
  fill('experiment',list.map(name => [name,'应急任务与物资站占用 · ' + name.replace('factorial_','')]));
  if (!list.length) {
    $('status').textContent = '尚无已发布的四格实验。运行实验脚本后刷新。';
    return;
  }
  $('experiment').onchange = () => load().catch(showError);
  $('snapshot').onchange = () => choose(cell);
  $('margin').onchange = render;
  $('method').onchange = () => { selected = null; render(); };
  $('mechanism').onclick = () => choose('qualification');
  new ResizeObserver(() => { if (study) renderTask(current()); }).observe($('map'));
  await load();
  try {
    const data = await fetchJSON('/api/map');
    const pixels = atob(data.pixels);
    const image = make('canvas');
    image.width = data.width;
    image.height = data.height;
    const ctx = image.getContext('2d'), raster = ctx.createImageData(data.width,data.height);
    for (let i=0; i<pixels.length; i++) {
      raster.data.set([pixels.charCodeAt(i),pixels.charCodeAt(i),pixels.charCodeAt(i),255],i*4);
    }
    ctx.putImageData(raster,0,0);
    map = {...data,image};
    renderTask(current());
  } catch {
    $('map-caption').textContent = '占用地图暂不可读，点位仍使用保存的地图坐标。';
  }
}

start().catch(showError);
