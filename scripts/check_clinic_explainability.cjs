#!/usr/bin/env node
/* Browser-only, evidence-preserving regression checks. No ROS or solver processes. */
const fs=require('fs'),path=require('path'),os=require('os'),cp=require('child_process'),assert=require('assert/strict');
const args=process.argv.slice(2),get=(name,fallback)=>{const i=args.indexOf(name);return i>=0?args[i+1]:fallback};
const url=get('--url','http://127.0.0.1:8765/'),out=path.resolve(get('--out',fs.mkdtempSync(path.join(os.tmpdir(),'clinic-research-browser-'))));
fs.mkdirSync(out,{recursive:true});
const checks=[],blocked=[],screenshots=[],sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(test,timeout=45000){const deadline=Date.now()+timeout;let last;while(deadline>Date.now()){try{if(await test())return}catch(e){last=e}await sleep(90)}throw Error('Timeout after '+checks.length+' checks: '+(last?.message||'condition'))}
let chrome,ws;
(async()=>{
 const profile=fs.mkdtempSync(path.join(os.tmpdir(),'clinic-research-chrome-'));
 chrome=cp.spawn(process.env.CLINIC_REVIEW_CHROME||'/usr/bin/google-chrome',['--headless','--no-sandbox','--disable-gpu','--no-proxy-server','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
 const portFile=path.join(profile,'DevToolsActivePort');await wait(()=>fs.existsSync(portFile),15000);
 const port=fs.readFileSync(portFile,'utf8').split(String.fromCharCode(10))[0],tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 ws=new WebSocket(tabs.find(tab=>tab.type==='page').webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject});
 let next=0;const pending=new Map(),exceptions=[];
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const task=pending.get(m.id);pending.delete(m.id);if(m.error)task.reject(Error(JSON.stringify(m.error)));else task.resolve(m.result)}else if(m.method==='Runtime.exceptionThrown')exceptions.push(m.params)};
 function send(method,params={}){return new Promise((resolve,reject)=>{const id=++next;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
 async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
 async function select(name){await evaluate("$('run').value="+JSON.stringify(name)+";load()");await wait(()=>evaluate("data?.name==="+JSON.stringify(name)+"&&!$('clock').disabled"))}
 async function shot(name){const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(out,name),Buffer.from(screenshot.data,'base64'));screenshots.push(name)}
 function pass(name,detail){checks.push({name,status:'PASS',detail:detail??null})}
 await send('Page.enable');await send('Runtime.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url});
 await wait(()=>evaluate("typeof Platform!=='undefined'&&data?.name==='verification/visual_positive_2026-11-18_c1/positive_02'&&document.querySelectorAll('#primary-gantt svg').length===1&&Review.grid!==null"));

 await wait(()=>evaluate("Explain.catalog.length===110&&Explain.catalog.filter(m=>m.primary_research).length===5&&!!data.explanation&&data.name==='verification/visual_positive_2026-11-18_c1/positive_02'&&$('experiment-current').textContent.includes('真实跌倒正例闭环')"));
 assert.equal(await evaluate("document.querySelectorAll('nav button').length"),7);
 assert.equal(await evaluate("getComputedStyle(document.querySelector('#changes-table td')).fontSize"),'14px');pass('seven pages, semantic adapter and readable 14px main tables');
 assert.equal(await evaluate("document.querySelectorAll('#research-directory .research-directory-card').length"),8);
 assert.ok(await evaluate("$('research-explanation').textContent.includes('角色：R1核验并持续监护')&&$('research-explanation').textContent.includes('何时插入新任务')"));pass('explicit research catalog, roles, scene, task plan and event insertion timing');
 await evaluate("openTab('semantic')");assert.ok(await evaluate("$('semantic-association').textContent.includes('video_source_registered')&&$('semantic-association').textContent.includes('V1')&&$('semantic-association').textContent.includes('不是从随机人体像素在线估计')"));pass('event coordinate, registered service goals and sensor-estimated boundary are visible');
 await evaluate("$('experiment-picker').open=true;$('experiment-all').checked=true;$('experiment-search').value='unified_bed';filterExperiments()");
 assert.equal(await evaluate("document.querySelectorAll('.experiment-row').length"),2);
 assert.ok(await evaluate("[...document.querySelectorAll('.experiment-row strong')].some(n=>n.textContent.includes('承诺保护下局部修复'))"));
 await evaluate("document.querySelector('.experiment-row>button:last-child').click();$('experiment-favorites').checked=true;filterExperiments()");
 assert.equal(await evaluate("document.querySelectorAll('.experiment-row').length"),1);
 await shot('selector_chinese_search_favorites.png');
 await evaluate("$('experiment-search').value='';$('experiment-favorites').checked=false;$('experiment-all').checked=false;filterExperiments();$('experiment-picker').open=false");
 assert.equal(await evaluate("document.querySelectorAll('.experiment-row').length"),5);
 assert.equal(await evaluate("new Set(Explain.catalog.map(m=>m.run_id)).size"),110);pass('searchable Chinese catalog, independent raw IDs and persistent favorites');
 await select('unified_bed_local_r1');
 assert.equal(await evaluate("data.explanation.tasks.C0_r3_W2.nominal_owner"),'r3');
 assert.equal(await evaluate("data.explanation.tasks.C0_r3_W2.actual_executor"),'r1');
 assert.equal(await evaluate("data.explanation.tasks.C0_r3_W2.definition.clear_anchor"),'CPW2C');
 assert.ok(await evaluate("!taskLabel(data,'C0_r3_W2').includes('C0_r3_W2')"));pass('structured cycle/stop naming and nominal R3 versus actual R1 ownership');
 await evaluate("openTab('semantic')");
 const planningCard=await evaluate("[...document.querySelectorAll('#semantic-flow .flow-node')].find(n=>n.querySelector('strong').textContent==='协同规划').textContent");
 assert.ok(planningCard.includes('187.65')&&!planningCard.includes('0.56'));
 assert.deepEqual(await evaluate("data.explanation.event_planning.E1.excluded_initial_normal"),[0]);
 assert.ok(await evaluate("$('semantic-association').textContent.includes('人体时序')&&$('semantic-association').textContent.includes('gazebo_reference_pose')"));
 await shot('semantic_corrected_187_65.png');pass('E1 association excludes 0.56 initial commit and shows 187.65 verification commit');
 await evaluate("openTab('replay');chooseTime(500);mapReset(false)");
 const roundtrip=await evaluate("(()=>{const n=data.anchors.EPW2,p=Platform.projection,s=p.xy(n[0],n[1]),w=p.world(...s);return Math.hypot(w[0]-n[0],w[1]-n[1])})()");assert.ok(roundtrip<1e-9);
 for(const mode of ['none','current','recent','all','selected']){await evaluate("$('trajectory-mode').value="+JSON.stringify(mode)+";$('trajectory-mode').dispatchEvent(new Event('change'))");assert.equal(await evaluate("Platform.trailMode"),mode)}
 await evaluate("$('trajectory-mode').value='recent';$('trajectory-mode').dispatchEvent(new Event('change'));$('map-robot').value='all';Platform.robot='all';mapReset(false)");
 for(const [width,height] of [[1366,768],[1440,900],[1920,1080]]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
  await evaluate("window.scrollTo(0,0);mapReset(false)");
  assert.ok(await evaluate("document.documentElement.scrollWidth<=innerWidth"));
  await shot('space_'+width+'x'+height+'.png');
  const metrics=await send('Page.getLayoutMetrics');const png=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width,height:Math.min(1800,metrics.cssContentSize.height),scale:1}});fs.writeFileSync(path.join(out,'space_full_'+width+'.png'),Buffer.from(png.data,'base64'));
 }
 pass('correct map/world roundtrip, five trajectory modes and three desktop viewport widths');
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
 await evaluate("nodeDetail('EPW2')");assert.ok(await evaluate("$('node-focus').textContent.includes('PW2 服务入口 EPW2')"));
 assert.ok(await evaluate("data.explanation.nodes.find(n=>n.id==='EPW2').sources.some(s=>s.sha256)"));
 await evaluate("$('spatial-relation-mode').value='matrix';renderSpatialRelations()");assert.ok(await evaluate("$('spatial-relation-content').textContent.includes('模型秒')"));
 await evaluate("$('spatial-relations').scrollIntoView()");await shot('travel_matrix_sources.png');
 await evaluate("$('spatial-relation-mode').value='nodes';renderSpatialRelations()");assert.equal(await evaluate("document.querySelectorAll('#spatial-relation-content tbody tr').length"),22);pass('22 registered nodes with source SHA256, clickable details and separate saved travel matrix');
 await evaluate("openTab('diagnostics');window.scrollTo(0,0);$('task-relation-mode').value='dag';renderTaskRelations()");
 assert.equal(await evaluate("document.querySelectorAll('#task-relation-content .dag-node').length"),22);
 assert.ok(await evaluate("$('task-relation-content').textContent.includes('持续监护守卫')&&$('task-relation-content').textContent.includes('资源需求')"));await shot('explicit_task_dependency_graph.png');
 await evaluate("$('task-relation-mode').value='sequences';$('relation-version').value='3';renderTaskRelations()");
 assert.equal(await evaluate("document.querySelectorAll('.sequence-row').length"),3);
 assert.ok(await evaluate("$('task-relation-content').textContent.includes('对照上一版')"));await shot('robot_sequence_changes.png');
 await evaluate("$('task-relation-mode').value='dictionary';renderTaskRelations()");assert.ok(await evaluate("$('task-relation-content').textContent.includes('预设任务通道')&&$('task-relation-content').textContent.includes('实际执行机器人')&&$('task-relation-content').textContent.includes('C表示周期')"));pass('explicit task DAG/guard/resource types, per-version three-robot sequences and semantic dictionary');
 await evaluate("openTab('replay');$('lane-plan').value='3';$('lane-display').value='plan';$('lane-display').dispatchEvent(new Event('change'))");
 assert.ok(await evaluate("[...document.querySelectorAll('#primary-gantt .task-hit')].every(r=>r.getAttribute('height')==='9')"));
 await evaluate("$('lane-display').value='overlay';$('lane-display').dispatchEvent(new Event('change'))");
 assert.ok(await evaluate("document.querySelector('#primary-gantt .protected-task')!==null"));
 await evaluate("$('display-mode').click()");assert.equal(await evaluate("taskLabel(data,'C0_r3_W2')"),'C0_r3_W2');
 await evaluate("$('display-mode').click()");assert.ok(await evaluate("taskLabel(data,'C0_r3_W2').includes('预设R3')"));pass('plan/actual/overlay lanes, evidence-derived commitment locks and demo/audit name toggle');
 await evaluate("openTab('planning');window.scrollTo(0,0)");
 assert.equal(await evaluate("document.querySelectorAll('.plan-timeline button').length"),6);
 assert.ok(await evaluate("data.explanation.repair_diagnostics.every(r=>r.budget_stop_recorded&&r.released_count===10&&r.suffix_count===11&&r.reassigned_tasks.length===0)"));
 assert.ok(await evaluate("$('repair-explanation').textContent.includes('首次完整验证解精确时刻')"));
 await shot('three_repairs_budget_scope.png');pass('six plan commits and three budget-stopped repairs with 10/11 release and zero actual reassignment');
 await select('unified_bed_full_r1');assert.equal(await evaluate("data.explanation.metadata.strategy_raw"),'full_warm');assert.equal(await evaluate("data.passed"),true);
 await select('hospital_normal_v5');assert.equal(await evaluate("data.passed"),false);assert.equal(await evaluate("data.failure_info.code"),'ARRIVAL_NOT_STABLE');
 await select('hospital_normal_v6');assert.equal(await evaluate("data.passed"),true);assert.equal(await evaluate("data.semantic_events.length"),0);
 await select('verification/visual_positive_2026-11-18_c1/positive_02');assert.ok(await evaluate("data.explanation.metadata.event_source.includes('视频')"));
 await select('verification/visual_integration_2026-11-18_b1/visual_false_alarm_a1');assert.equal(await evaluate("data.semantic_events[0].final.event.closed_reason"),'no_fall');
 await select('unified_bed_local_r1');assert.ok(await evaluate("data.explanation.metadata.event_source.includes('注入')"));pass('required full/local, failure/success normal, real-video positive/negative and injected historical samples');
 const other=await(await fetch(new URL('/api/run?name=unified_bed_full_r1',url))).json();
 assert.ok(await evaluate("comparisonChecks([data,"+JSON.stringify({comparison_signature:other.comparison_signature})+"]).some(c=>c.label==='任务与规划约束'&&c.status==='MISMATCH')"));pass('actual task-release constraint differences prevent unsupported same-condition quantitative claims');
 await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:out});
 await evaluate("openTab('evidence');[...document.querySelectorAll('#evidence button')].find(b=>b.textContent==='节点登记 JSON').click();[...document.querySelectorAll('#evidence button')].find(b=>b.textContent==='全部实验分类映射 JSON').click();$('export-summary').click()");
 await wait(()=>fs.existsSync(path.join(out,'unified_bed_local_r1-nodes.json'))&&fs.existsSync(path.join(out,'clinic-experiment-registry.json'))&&fs.existsSync(path.join(out,'unified_bed_local_r1-research-summary.json')));
 assert.equal(JSON.parse(fs.readFileSync(path.join(out,'unified_bed_local_r1-nodes.json'))).length,22);assert.ok(JSON.parse(fs.readFileSync(path.join(out,'unified_bed_local_r1-research-summary.json'))).explanation);
 pass('semantic registries, experiment mapping and complete explanatory summary export');
 assert.equal(exceptions.length,0);pass('no uncaught JavaScript exceptions in second-round feature checks');
 const receipt={passed:true,url,checks,screenshots,uncaught_exceptions:exceptions,notes:'Read-only UI and existing evidence verification. No ROS/Gazebo/planner run.'};fs.writeFileSync(path.join(out,'explainability_browser.json'),JSON.stringify(receipt,null,2));console.log(JSON.stringify({passed:true,checks:checks.length,screenshots:screenshots.length}));ws.close();chrome.kill('SIGTERM');
})().catch(error=>{if(ws)ws.close();if(chrome)chrome.kill('SIGTERM');fs.writeFileSync(path.join(out,'explainability_browser.json'),JSON.stringify({passed:false,checks,error:error.stack,screenshots},null,2));console.error(error);process.exitCode=1});
