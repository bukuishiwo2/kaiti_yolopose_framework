(() => {
  'use strict';

  const nav = document.querySelector('nav');
  const section = document.createElement('section');
  section.id = 'online-pair';
  section.className = 'view panel';
  section.hidden = true;
  document.querySelector('footer').before(section);

  const labels = {fixed:'固定常态分工', full:'允许常态改派'};
  const names = {E1_verify:'现场核验', E1_monitor:'现场监护', E1_pickup:'领取物资', E1_deliver:'送达物资'};
  const responseName = job => names[job] || (job==='E1_monitor_approach'?'监护前中间停稳':'已派发巡检');
  const failureLabel = r => r.passed ? '审计通过' :
    /Nav2 route qualification/.test(r.reason) ? '路径资格未通过' :
    /PROTOCOL_ACK_TIMEOUT/.test(r.reason) ? '核验就绪回执超时' :
    /PREFLIGHT/.test(r.reason) ? '启动预检未通过' :
    r.reason ? '执行未完成' : '审计未通过';
  const format = v => Number.isFinite(v) ? v.toFixed(2) : '—';
  let pair, feedback, qualification, spatialStand, standSwitch, standResponse;

  const node = (tag, text, cls) => {
    const item = document.createElement(tag);
    if (text) item.textContent = text;
    if (cls) item.className = cls;
    return item;
  };

  function table(headers, rows) {
    const wrap = node('div', null, 'pair-metrics');
    const t = node('table');
    const header = t.createTHead().insertRow();
    for (const label of headers) {
      const th = node('th', label);
      th.scope = 'col';
      header.append(th);
    }
    const body = t.createTBody();
    for (const row of rows) {
      const tr = body.insertRow();
      row.forEach(value => tr.append(node('td', String(value))));
    }
    wrap.append(t);
    return wrap;
  }

  function timeline(graph, detail, records, predicted) {
    const key = predicted ? 'predicted' : 'actual';
    const ends = records.flatMap(r => r[key].map(task => task.finish));
    const limit = Math.max(100, Math.ceil(Math.max(0,...ends)/100)*100);
    graph.replaceChildren();
    detail.textContent = '选择任务条可查看服务点、地图坐标与时刻。';
    for (const r of records) {
      graph.append(node('h3', r.title || labels[r.policy]+(predicted && r.commit===null?' · 候选未提交':'')));
      const ruler = node('div', null, 'pair-ruler');
      for (let i=0; i<=5; i++) {
        const tick = node('span', limit*i/5 + ' s');
        tick.style.left = i*20 + '%';
        ruler.append(tick);
      }
      graph.append(node('strong','机器人'),ruler);
      for (const robot of ['r1','r2','r3']) {
        const lane = node('div', null, 'pair-lane');
        if (r.reservation) {
          const booking = node('span', null, 'pair-booking');
          booking.style.left = r.reservation[0]/limit*100 + '%';
          booking.style.width = (Math.min(limit,r.reservation[1])-r.reservation[0])/limit*100 + '%';
          lane.append(booking);
        }
        if (Number.isFinite(r.confirmed)) {
          const confirm = node('span', null, 'pair-confirmation');
          confirm.style.left = r.confirmed/limit*100 + '%';
          lane.append(confirm);
        }
        for (const task of r[key].filter(t => t.robot===robot)) {
          const bar = node('button', task.anchor, 'pair-bar'+(names[task.job] ? ' pair-emergency' : ''));
          bar.type = 'button';
          bar.style.left = task.start/limit*100 + '%';
          bar.style.width = (task.finish-task.start)/limit*100 + '%';
          const label = task.label+' · '+task.anchor+' · '+format(task.start)+'–'+format(task.finish)+' 秒';
          bar.title = label;
          bar.setAttribute('aria-label',label);
          bar.onclick = () => {
            detail.textContent = (r.title || labels[r.policy])+' · '+robot.toUpperCase()+' · '+label+
              ' · 地图坐标 '+task.xy.map(format).join(', ')+' m';
          };
          lane.append(bar);
        }
        graph.append(node('strong',robot.toUpperCase()),lane);
      }
    }
  }

  function drawFeedback() {
    const panel = node('section');
    const picker = node('select');
    picker.setAttribute('aria-label','路径拒绝回放快照');
    feedback.cases.forEach(c => picker.append(new Option(c.run, c.run)));
    const controls = node('div',null,'pair-chart-controls');
    controls.append(node('h3','路径查询拒绝后的重规划'), picker);
    const body = node('div');
    panel.append(controls, body);
    const solveStatus = {OPTIMAL:'模型最优', FEASIBLE_BUDGET:'模型可行', INFEASIBLE:'模型无解', UNKNOWN_BUDGET:'预算内未找到'};
    picker.onchange = () => {
      const c = feedback.cases.find(x => x.run === picker.value);
      const [robot, source, target] = c.witness.edge;
      const prefix = Object.values(c.prefixes).flatMap(p => p.jobs).join('、');
      body.replaceChildren(node('p', 'Nav2 拒绝了 '+robot.toUpperCase()+' 从 '+source+' 到 '+target+
        ' 的路径查询，原候选没有提交。回放只排除这次拒绝对应的任务衔接，冻结已派发任务 '+prefix+
        '，使用同一资格域和 G1 预约。每次重算预算 '+feedback.budget+' 秒。'));
      body.append(node('p','以下是模型预测。替代路径与并行执行仍待 Gazebo 核验。','pair-note'));
      const choices = [
        ['原候选，门禁拦截', c.rejected],
        ['反馈重算，允许改派', c.repaired],
        ['反馈重算，固定分工', c.fixed]
      ].filter(([,r]) => r);
      body.append(table(['方案','结果','交付耗时 / 秒','常态完工推迟 / 任务秒','改派 / 项','首次可行 / 毫秒','求解总耗时 / 秒'],
        choices.map(([title,r],i) => [title,i === 0 ? '路径查询拒绝' : solveStatus[r.status] || r.status,
          format(r.delivery),format(r.delay),r.changes ?? '—',
          Number.isFinite(r.first) ? (r.first*1000).toFixed(1) : '—',format(r.wall)])));
      body.append(node('p','交付耗时从事件确认起计。常态完工推迟为各巡检任务相对原计划的正向偏移之和。','pair-note'));
      const details = node('details');
      details.append(node('summary','查看常态迟到阈值与各机器人任务次序'));
      const margins = ['0','60','90','120'];
      details.append(table(['方案',...margins.map(m => '容许 '+m+' 秒后的迟到量 / 任务秒')],
        choices.map(([title,r]) => [title,...margins.map(m => format(r.tardiness?.[m]))])));
      details.append(table(['方案','机器人','任务顺序（服务点）'],
        choices.flatMap(([title,r]) => Object.entries(r.routes || {}).map(([rid,jobs]) =>
          [title,rid.toUpperCase(),jobs.map(job => (names[job] || job)+'（'+
            r.predicted.find(t => t.job === job).anchor+'）').join(' → ') || '待命']))));
      const graph = node('div',null,'pair-graph');
      const scroll = node('div',null,'pair-graph-scroll');
      const detail = node('p',null,'pair-task-detail');
      scroll.append(graph);
      body.append(details,node('h4','各候选计划的服务时间'),
        node('p','蓝色为巡检，橙色为应急。虚线标记事件确认，浅棕色区域标记 G1 预约。','pair-note'),scroll,detail);
      timeline(graph,detail,choices.filter(([,r]) => r.predicted.length).map(([title,r]) =>
        ({title,confirmed:c.confirmed,reservation:c.reservation,predicted:r.predicted.map(t =>
          ({...t,label:names[t.job] || '巡检 '+t.job}))})),true);
    };
    picker.onchange();
    return panel;
  }

  function svg(tag, attributes, value) {
    const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [name,v] of Object.entries(attributes)) element.setAttribute(name,v);
    if (value) element.textContent = value;
    return element;
  }

  function measuredTrack(batch) {
    const graphic = svg('svg',{viewBox:'0 0 370 390',role:'img',
      'aria-label':'占位与空位条件下从 CTLR3 出发的 R3 实测轨迹均未到达 EPW2'});
    const project = ([x,y]) => [43+(x-13)*48,33+(-10.6-y)*48];
    for (let x=13; x<=19; x++) {
      const [px] = project([x,0]);
      graphic.append(svg('line',{x1:px,x2:px,y1:33,y2:344,class:'epw-grid'}),
        svg('text',{x:px,y:366,'text-anchor':'middle'},x+' m'));
    }
    for (let y=-17; y<=-11; y++) {
      const [,py] = project([0,y]);
      graphic.append(svg('line',{x1:43,x2:331,y1:py,y2:py,class:'epw-grid'}),
        svg('text',{x:38,y:py+5,'text-anchor':'end'},String(y)));
    }
    for (const c of batch.cases) {
      const points = c.track.map(([,x,y]) => project([x,y]));
      const [x,y] = points.at(-1);
      const style = c.occupied ? 'epw-occupied' : 'epw-vacant';
      graphic.append(svg('polyline',{points:points.map(p=>p.join(',')).join(' '),class:style}),
        svg('circle',{cx:x,cy:y,r:4,class:style}));
    }
    for (const key of ['CTLR3','M1','V1','EPW2','PW2']) {
      const [x,y] = project(batch.anchors[key]);
      const dy = key==='M1' ? 19 : -8;
      graphic.append(svg('circle',{cx:x,cy:y,r:4,class:'epw-anchor'}),
        svg('text',{x,y:y+dy,'text-anchor':key==='EPW2'?'end':'middle'},key));
    }
    return graphic;
  }

  function standTrack(batch) {
    const graphic = svg('svg',{viewBox:'0 0 440 280',role:'img',
      'aria-label':'R1 实测轨迹、新备选站位、原核验点和占用栅格负对照'});
    const project = ([x,y]) => [50+(x-13)*64,24+(-11.8-y)*64];
    for (let x=13; x<=18; x++) {
      const [px] = project([x,0]);
      graphic.append(svg('line',{x1:px,x2:px,y1:24,y2:234,class:'epw-grid'}),
        svg('text',{x:px,y:255,'text-anchor':'middle'},x+' m'));
    }
    for (let y=-15; y<=-12; y++) {
      const [,py] = project([0,y]);
      graphic.append(svg('line',{x1:50,x2:370,y1:py,y2:py,class:'epw-grid'}),
        svg('text',{x:44,y:py+5,'text-anchor':'end'},String(y)));
    }
    const points = batch.actual.track.map(([,x,y]) => project([x,y]));
    graphic.append(svg('polyline',{points:points.map(p=>p.join(',')).join(' '),class:'epw-occupied'}));
    const [sx,sy] = project(batch.origin);
    graphic.append(svg('circle',{cx:sx,cy:sy,r:4,class:'epw-anchor'}),
      svg('text',{x:sx+8,y:sy-9},'起点 V3'));
    for (const candidate of batch.candidates) {
      const [x,y] = project(candidate.pose);
      const label = {baseline:'原核验点',negative:'负对照'}[candidate.kind] ||
        (candidate.id===batch.actual.selected ? '实跑备选点' : '东侧备选');
      graphic.append(svg('circle',{cx:x,cy:y,r:4,class:candidate.passed?'epw-anchor':'stand-rejected'}),
        svg('text',{x,y:y+(candidate.kind==='baseline' || candidate.id===batch.actual.selected?19:-9),
          'text-anchor':candidate.kind==='negative'?'end':'middle'},label));
    }
    return graphic;
  }

  function drawSpatialStand() {
    const panel = node('section',null,'epw-qualification');
    const result = spatialStand.actual;
    const selected = spatialStand.candidates.find(c=>c.id===result.selected);
    panel.append(node('h3','A 区空间站位验收'),
      node('p','R1 从同一实测位置查询四个预设目标，使用相同的事件占区和其他机器人站位。通过路径筛选的首个备选点进入实跑。'));
    panel.append(node('h4','第一步 · Nav2 全局路径筛选'),
      table(['候选站位','地图坐标 / 米','路径查询','路径长度 / 米','实际服务'],
      spatialStand.candidates.map(c=>[c.label,c.pose.slice(0,2).map(format).join(', '),
        c.passed?'通过':'未通过',c.passed?format(c.length):'—',
        c.id===result.selected?(result.status==='PASS'?'实测通过':'实测未通过'):'未执行'])));
    if (selected) {
      const report = {
        tracking:result.follow.map(f=>f.status===5 && result.checks.tracking?
          '到位后交给姿态控制':f.status===4?'跟踪完成':'终态 '+f.status).join('、') || '无跟踪记录',
        stable:'停稳 '+format(result.stableDuration)+' 秒，位置误差 '+format(result.arrival?.position_error)+' 米',
        worker:result.workerFeedback.map(s=>({started:'开始',succeeded:'成功'})[s] || s).join(' → ') || '无回执'
      };
      panel.append(node('h4','第二步 · Gazebo 跟踪、停稳和服务'),
        table(['实测环节','结果','记录'],[
          ['跟踪',result.checks.tracking?'通过':'未通过',report.tracking],
          ['稳定到达',result.checks.stable_arrival?'通过':'未通过',report.stable],
          ['执行回执',result.checks.worker_ack?'通过':'未通过',report.worker+' · '+format(result.serviceStart)+'–'+format(result.serviceFinish)+' 仿真秒']
        ]),
        node('p','蓝线为实测轨迹。圆点标记查询目标。','pair-note'),standTrack(spatialStand));
    }
    panel.append(node('p','本例验证单机到达与服务，场景使用人工地图坐标、静止同伴和原服务回执。','pair-note'));
    return panel;
  }

  function drawStandSwitch() {
    const panel = node('section',null,'epw-qualification');
    const labels = {original:'V1 空闲',switch:'V1 被占，南侧可用',blocked:'两处均被占'};
    const explanation = {occupied_by_body_mask:'人体占区',nav2_path_rejected:'路径查询未通过',eligible:'路径通过'};
    panel.append(node('h3','人体占用变化如何改变正式核验任务'),
      node('p','同一地图、跌倒候选和机器人起点。三种条件只移动仿真人体安全占区。'));
    panel.append(table(['条件','人体位置 / 米','V1','南侧备选','核验目标','任务状态','进入排程'],
      standSwitch.conditions.map(c=>[
        labels[c.condition],c.center.map(format).join(', '),...c.queries.map(q=>explanation[q.reason]),
        c.selected || '等待合格目标',c.task.state==='READY'?'就绪':'待核验',
        c.plan ? c.plan.owner.toUpperCase()+' · 行驶估计 '+format(c.plan.travelPrior)+' 秒' : '等待新目标'
      ])));
    const e = standSwitch.execution;
    if (e) {
      const coords = pose => pose?.slice(0,2).map(format).join(', ') || '—';
      panel.append(node('h4','南侧备选点的正式任务与 Gazebo 执行'),
        table(['环节','目标坐标 / 米','记录'],[
          ['核验任务',coords(e.task.target.xy),e.task.task_id+' · 版本 '+e.task.revision],
          ['MILP 排程',coords(e.model.modelTarget),e.model.owner.toUpperCase()+' · 计划服务 '+format(e.model.start)+'–'+format(e.model.finish)+' 秒'],
          ['Nav2 实际请求',coords(e.goals[0]?.pose),e.goals.length+' 次路径请求'],
          ['实际服务回执',coords(e.goals[0]?.pose),e.passed
            ? '通过 · 停稳后服务 '+format(e.record.service_started)+'–'+format(e.record.service_finished)+' 秒'
            : '未通过 · '+(standSwitch.failure || e.record?.status || '缺少执行回执')]
        ]));
    }
    panel.append(node('p','证据覆盖受控人体占区、目标选择、任务排程及现场核验。','pair-note'));
    return panel;
  }

  function drawStandResponse() {
    const panel = node('section',null,'epw-qualification');
    const {response,execution,runtime_records:records=[]} = standResponse;
    panel.append(node('h3','南侧核验点切换后的三机应急响应'),
      node('p','R1 在南侧点核验并接续监护，R2 负责取送，R3 继续之前已派发的巡检。人体占区和核验结论由实验设定。'));
    if (!response?.passed) {
      panel.append(node('p','完整协作未通过。'+(standResponse.failure || '请查看已保存的执行记录。')));
    } else {
      const cargo = records.find(r=>r.job_id==='E1_deliver');
      panel.append(node('p','第 '+format(response.confirmed)+' 秒确认应急事件，第 '+format(cargo.service_finished)+
        ' 秒送达物资。R3 的巡检保留原派发身份，并完成 TL 工位服务和释放。'));
      if (response.monitorAfterPatrol) {
        const patrol = records.find(r=>r.job_id==='C0_r3_W1');
        panel.append(node('p','响应计划保留 R3 的原巡检。R1 收到 TL 驶离及租约释放后才出发去 M1，R2 到达 G1 后等待监护开始回执。巡检于第 '+format(patrol.end)+' 秒结束。'));
      }
    }
    panel.append(table(['任务','机器人','服务点','实际导航派发','停稳','服务开始','服务结束','租约释放'],
      records.map(r=>[responseName(r.job_id),r.robot.toUpperCase(),r.anchor,
        ...[r.begin,r.stable_at,r.service_started,r.service_finished,r.lease_released_at].map(format)])));
    const completed = records.filter(r=>r.status==='SUCCEEDED' && Number.isFinite(r.service_finished));
    if (completed.length) {
      const graph = node('div',null,'pair-graph');
      const scroll = node('div',null,'pair-graph-scroll');
      const detail = node('p',null,'pair-task-detail');
      scroll.append(graph);
      panel.append(node('p','甘特图只画实际服务区间。横轴为本次 Gazebo 回合时间，虚线标记核验成功。','pair-note'),scroll,detail);
      timeline(graph,detail,[{title:'三机实际服务',confirmed:response?.confirmed,actual:completed.map(r=>({
        robot:r.robot,job:r.job_id,label:responseName(r.job_id),anchor:r.anchor,
        xy:[r.target.x,r.target.y],start:r.service_started,finish:r.service_finished
      }))}],false);
    }
    if (execution?.passed && response?.path_queries) {
      const routes = node('details');
      routes.append(node('summary','查看切换后的响应路径查询'),
        table(['机器人','起点','目标','全局路径长度 / 米','结果'],
          response.path_queries.map(q=>[q.robot.toUpperCase(),q.source,q.id,format(q.length),q.passed?'通过':'未通过'])));
      panel.append(routes);
    }
    if (standResponse.priorAttempts?.length) {
      panel.append(node('h4','先前两次跟踪中止'),
        table(['监护接近方案','中止目标','全局查询','跟踪中止次数','停止 / 仿真秒'],
          standResponse.priorAttempts.map(a=>[
            a.viaV3?'经 V3 停稳':'直接前往 M1',a.anchor,a.pathPassed?'通过':'未通过',
            a.aborts,format(a.stop)
          ])));
    }
    return panel;
  }

  function drawQualification() {
    const panel = node('section',null,'epw-qualification');
    const cases = qualification.cases;
    panel.append(node('h3','R3 进入 EPW2 的 Gazebo 资格对照'),
      node('p','R3 和 R2 从同一实测位置出发，保留相同的事件障碍和 G1 预约。R1 分别停在监护位 M1 和核验位 V1。'));
    panel.append(table(['条件','全局路径通过 / 查询','路径跟踪中止 / 次','进入工位并取得租约','终止时刻 / 仿真秒'],
      cases.map(c=>[c.occupied?'M1 占位':'M1 空位',
        c.paths.filter(p=>p.accepted).length+' / '+c.paths.length,
        c.attempts.filter(a=>a.leg==='entry' && a.status===6).length,
        c.stages.lease==null?'无工位许可':'取得许可',format(c.stages.terminal)])));
    if (cases.every(c=>!c.passed && c.collisionWarnings>0)) {
      panel.append(node('p','两组都找到了全局路径，Nav2 局部控制均报告前方碰撞风险并中止。长队列暂未获得执行资格。'));
    }
    panel.append(node('h4','R3 的实测轨迹'),
      node('p','蓝实线为 M1 占位，橙虚线为 M1 空位。圆点标出停止位置。坐标单位为米。','pair-note'),
      measuredTrack(qualification));
    const w = qualification.bedWitness;
    if (w?.passed) {
      panel.append(node('h3','独立执行见证 · 取货前实体床扰动'),
        node('p','历史 Gazebo 回合由实体床扰动触发后缀重规划。实际交付发生在第 '+format(w.delivery)+
          ' 秒，'+w.services+' 项服务及清空在第 '+format(w.routineEnd)+' 秒完成。该回合采用不同扰动和计划。'),
        node('p','计划更新提交于第 '+w.repairTimes.map(format).join('、')+' 秒。下图使用实际服务回执。','pair-note'));
      const graph = node('div',null,'pair-graph');
      const scroll = node('div',null,'pair-graph-scroll');
      const detail = node('p',null,'pair-task-detail');
      scroll.append(graph);
      panel.append(scroll,detail);
      timeline(graph,detail,[{title:'三机实际服务时间',actual:w.actual.map(t=>
        ({...t,label:names[t.job] || t.job}))}],false);
    }
    return panel;
  }

  function draw() {
    section.replaceChildren(node('h2','在线协同配对'));
    if (standResponse) section.append(drawStandResponse());
    if (standSwitch?.conditions?.length) section.append(drawStandSwitch());
    if (spatialStand?.candidates?.length) section.append(drawSpatialStand());
    if (qualification?.cases?.length) section.append(drawQualification());
    if (feedback?.cases?.length) section.append(drawFeedback());
    if (!pair) {
      section.append(node('p','暂无已发布运行。离线四格条件和预测结果可从“规划与对比”查看。'));
      return;
    }
    section.append(node('h3','历史 Gazebo 配对记录'));
    const runs = Object.values(pair.arms);
    section.append(node('p',pair.candidate));
    section.append(node('p',pair.matched ?
      '固定分工组和允许改派组均完成并通过审计，共用初始计划、任务资格域和确认阶段的已派发任务。' :
      pair.conditionsMatched ? '两组共用初始计划、资格域和确认阶段。执行中有任务中止，以下显示候选计划和实际完成记录。' :
      '以下是已有 Gazebo 运行记录。同条件完整配对仍待验证。'));
    section.append(table(['策略','运行状态','预测交付 / s','实际交付 / s','常态完工并驶离 / s','改派 / 项'],
      runs.map(r=>[labels[r.policy],failureLabel(r),format(r.predictionDelivery),format(r.delivery),
                 format(r.routineEnd),r.changes ? Object.keys(r.changes).length : '—'])));
    for (const r of runs.filter(r => r.reason)) {
      const failure = node('details');
      failure.append(node('summary',labels[r.policy]+'的停止原因'),node('p',r.reason));
      section.append(failure);
    }
    if (pair.repeats?.length) {
      const repeats = node('details');
      repeats.append(node('summary','查看重复运行'),table(['策略','运行','状态','已完成任务','停止任务'],
        pair.repeats.map(r=>[labels[r.policy],r.run,failureLabel(r),r.completed,r.failedJobs.join('、')||'—'])));
      section.append(repeats);
    }
    const any = runs.find(r => r.newTasks);
    if (any) {
      section.append(node('h3','确认事件后的任务和约束'));
      section.append(node('p','取送同机、监护异机，监护覆盖取送和交接。G1 的预约与工位租约同时决定何时可进站。'));
      section.append(table(['任务','服务点','前置任务','共享资源'],
        Object.keys(names).filter(j=>any.newTasks[j]).map(j=>any.newTasks[j]).map(t=>[t.label,t.anchor,t.prerequisites.map(j=>names[j]||j).join('、')||'—',t.resource.join('、')||'—'])));
    }
    const graph = node('div',null,'pair-graph');
    const scroller = node('div',null,'pair-graph-scroll');
    scroller.append(graph);
    const detail = node('p',null,'pair-task-detail');
    const picker = node('select');
    picker.setAttribute('aria-label','时间轴数据来源');
    picker.append(new Option('实际服务反馈','actual'),new Option('在线计划预测（含未提交）','predicted'));
    const controls = node('div',null,'pair-chart-controls');
    controls.append(node('h3','三机任务时间轴'),picker);
    section.append(controls,node('p','蓝色为常态，橙色为应急。虚线为事件确认，浅棕色区域为 G1 预约。横轴为 Gazebo 回合时钟。','pair-note'),scroller,detail);
    picker.onchange = () => timeline(graph,detail,runs,picker.value==='predicted');
    picker.onchange();
    section.append(node('h3','分工决策及承诺'));
    section.append(node('p','固定策略保留未派发常态任务的原执行者。协同策略在共同资格域内比较改派后的响应、常态等待和分工变更代价。表中交付与常态完成均从确认时刻起算。','pair-note'));
    for (const r of runs) {
      if (!r.changes) continue;
      const changes = Object.entries(r.changes).map(([j,[old,cur]]) => j+' '+old.toUpperCase()+' → '+cur.toUpperCase());
      section.append(node('p',labels[r.policy]+'。'+(r.commit===null?'候选未提交。':'')+(changes.join('、')||'保留原常态分工')+
        '。已派发任务 '+Object.values(r.checkpoint).flat().join('、')+' '+(r.checks.prefix?'保留原派发身份并完成。':'尚缺通过的完成证据。')));
      if (r.sameSnapshotComparison) {
        const shadow = r.sameSnapshotComparison;
        section.append(node('p','同一捕获快照改用「'+labels[shadow.otherPolicy]+'」后的预测差值：交付 '+
          format(shadow.deliveryDelta)+' 秒，常态正向完工偏移 '+format(shadow.positiveDelayDelta)+
          ' 累计任务秒，加权代价 '+format(shadow.objectiveDelta)+'。','pair-note'));
      }
    }
    const terms = [['response','响应'],['completion','总完工'],['normal_wait','常态等待'],
      ['owner','改派'],['shift','计划时移'],['travel','旅行']];
    const costs = runs.filter(r => r.terms);
    if (costs.length) {
      const details = node('details');
      details.append(node('summary','查看加权规划代价'));
      details.append(table(['策略',...terms.map(t=>t[1])],
        costs.map(r=>[labels[r.policy],...terms.map(([key])=>format(r.terms[key]))])));
      section.append(details);
    }
  }

  const button = node('button','在线协同配对');
  button.dataset.view = section.id;
  button.onclick = async () => {
    openTab(section.id);
    section.replaceChildren(node('p','正在读取在线运行证据…'));
    try {
      [pair, feedback, qualification, spatialStand, standSwitch, standResponse] = await Promise.all([
        api('/api/online-pair'), api('/api/feedback-repair').catch(() => null),
        api('/api/epw2-qualification').catch(() => null), api('/api/spatial-stand').catch(() => null),
        api('/api/verify-stand-switch').catch(() => null), api('/api/stand-switch-response').catch(() => null)
      ]);
      draw();
    } catch (error) {
      section.replaceChildren(node('p','读取失败：'+error.message));
    }
  };
  nav.append(button);
  if (new URLSearchParams(location.search).get('view') === section.id) button.click();
})();
