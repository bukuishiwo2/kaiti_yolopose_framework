#!/usr/bin/env python3
"""Render an honest measured-trajectory replay, including unsuccessful runs."""
import argparse
from bisect import bisect_right
import json
import math
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle
from matplotlib.transforms import Affine2D
import numpy as np
from PIL import Image

W=Path('/home/yhc/clinic_planning_ws')


def render(run,out,step=.8,fps=15):
    out.mkdir(parents=True,exist_ok=False)
    s=json.loads((run/'summary.json').read_text())
    cfg=json.loads((run/'runtime_scenario.json').read_text())
    trace=[json.loads(l) for l in (run/'trace.jsonl').open()]
    samples=s.get('pose_records',[])
    if not samples:raise ValueError('no measured pose records to animate')
    font=Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    if font.exists():
        font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']='Noto Sans CJK JP'
    plt.rcParams['axes.unicode_minus']=False
    times=[r['at'] for r in samples];end=times[-1]
    colors=dict(r1='#1677b8',r2='#db820a',r3='#279454')
    img=np.asarray(Image.open(W/'config/hospital_aligned/semantic_navigation.pgm'))
    fig=plt.figure(figsize=(14.4,8.1),dpi=100)
    grid=fig.add_gridspec(1,3,width_ratios=[.85,1.1,1.05],left=.035,right=.985,top=.85,bottom=.09,wspace=.2)
    overview=fig.add_subplot(grid[0]);detail=fig.add_subplot(grid[1]);panel=fig.add_subplot(grid[2]);panel.axis('off')
    lines={};dots={};beds={}
    coords={rid:np.array([[q['poses'].get(rid,{}).get('x',np.nan),q['poses'].get(rid,{}).get('y',np.nan)] for q in samples]) for rid in colors}
    for ax in [overview,detail]:
        ax.imshow(img,cmap='gray',origin='upper',extent=[0,60,-50,0],vmin=0,vmax=255)
        ax.set_aspect('equal');ax.set_xlabel('map x / m');ax.set_ylabel('map y / m')
        for rid,color in colors.items():
            lines[ax,rid],=ax.plot([],[],color=color,lw=1.4,alpha=.8,label=rid.upper())
            dots[ax,rid],=ax.plot([],[],'o',color=color,ms=8,mec='white',mew=1)
        for name in ['M1','H1','G1','TL','V3']:
            x,y=cfg['anchors'][name][:2]
            ax.plot(x,y,'s',color='#6b3693',ms=5);ax.annotate(name,(x,y),xytext=(5,5),textcoords='offset points',fontsize=9)
        rect=Rectangle((-1.05,-.55),2.1,1.1,fc='#d84444',ec='#a11111',alpha=.8,zorder=5)
        ax.add_patch(rect);beds[ax]=rect
    overview.set(xlim=(5,27),ylim=(-34,-8),title='Clinic实际测量轨迹')
    detail.set(xlim=(16,25.5),ylim=(-31,-9),title='A区监护与取送通道')
    overview.legend(loc='lower left',fontsize=9)
    title=fig.suptitle('',fontsize=16,y=.965)
    subtitle=fig.text(.04,.90,'',fontsize=10,color='#444444')
    text=panel.text(0,.99,'',va='top',fontsize=10.2,linespacing=1.55)
    fig.text(.04,.025,'轨迹来自Gazebo实际位姿采样；床轮廓为对象ACK示意。离线轨迹动画，非机器人相机录像；未平滑或推演未来运动。',fontsize=9,color='#555555')
    event_phases={
        'visual_candidate_created':'真实模型产生候选',
        'initial_clearance_committed':'扰动前排入同一监护清空策略',
        'bed_scenario_requested':'请求插入真实床对象',
        'bed_navigation_cancel_requested':'R2请求取消导航',
        'bed_navigation_cancel_ACK':'R2收到取消ACK与终态',
        'actual_plan_invalidated':'观测证明旧时序计划失效',
        'visual_repair_committed':'局部修复通过版本门禁并提交',
        'bed_observed_clear_resume':'实际观测通道清空并恢复',
        'scripted_handover_ack':'交付后场景收货方交接ACK'}
    events=[(r['episode_time'],event_phases[r['phase']]) for r in trace if r['phase'] in event_phases]
    labels={'E1_pickup':'真实取货及G1清空完成', 'E1_deliver':'真实交付完成',
        'E1_monitor_clear':'R1已清到V3并释放TL资源'}
    for r in s.get('records',[]):
        if r.get('status')=='SUCCEEDED' and r['job_id'] in labels and r.get('end') is not None:
            events.append((r['end'],labels[r['job_id']]))
    events.sort()
    repairs=s.get('repairs',[])
    def draw(t):
        i=max(0,bisect_right(times,t)-1);q=samples[i]
        for ax in [overview,detail]:
            for rid in colors:
                xy=coords[rid];lines[ax,rid].set_data(xy[:i+1,0],xy[:i+1,1]);dots[ax,rid].set_data([xy[i,0]],[xy[i,1]])
            truth=[d for d in s.get('bed_truth',[]) if d['at']-s.get('epoch',0)<=t]
            d=truth[-1] if truth else None;bed=beds[ax]
            bed.set_visible(bool(d and d['action']!='removed'))
            if d and d['action']!='removed':
                bed.set_transform(Affine2D().rotate(d.get('yaw',d.get('last_yaw',math.pi/2))).translate(d['x'],d['y'])+ax.transData)
        title.set_text(f'真实视频正例 → 物理床扰动 → 承诺保护与局部修复   t={t:.1f}s')
        subtitle.set_text(f'fall-01-cam0单次播放 / 原YOLO Pose＋32帧LSTM / video_source_registered / 实际三机Nav2与服务ACK / 终态 {s.get("status")}')
        current=[f'当前采样 {q["at"]:.2f} 仿真秒',f'全片加速 {step*fps:g}×；不代表实时性能','']
        for rid in colors:
            state=q['states'][rid]
            current += [f'{rid.upper()}  {state["state"]}',str(state['job'] or '等待合法派发'),f'携货：{state["cargo"] or "无"}','']
        current += ['修复过程（仅局部方案在线执行）：']
        current += [f'{at:6.1f}s  {label}' for at,label in events if at<=t][-6:]
        current += ['',f'已提交局部修复 {sum(r["returned_at"]<=t for r in repairs)} 次',
            '全量方案：相同快照离线对照', '单例功能证据；不宣称性能/创新成立']
        text.set_text('\n'.join(current))
        fig.canvas.draw()
    blocked=next((t for t,label in events if '失效' in label),end/2)
    draw(min(end,blocked+2));fig.savefig(out/'preview.png',dpi=100)
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgba','-s','1440x810','-r',str(fps),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'trajectory.mp4')]
    frames=np.arange(0,end+step,step)
    with subprocess.Popen(cmd,stdin=subprocess.PIPE) as proc:
        for t in frames:
            draw(min(float(t),end));proc.stdin.write(fig.canvas.buffer_rgba())
        proc.stdin.close()
        if proc.wait()!=0:raise RuntimeError('ffmpeg failed')
    plt.close(fig)
    meta=dict(run=str(run),frames=len(frames),fps=fps,sim_step=step,speedup=step*fps,
        measured_samples=len(samples),end_sim_seconds=end,status=s.get('status'),
        source='measured Gazebo poses, original execution state and actual object ACKs',
        camera_recording=False,interpolated=False,video=str(out/'trajectory.mp4'))
    (out/'render.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--step',type=float,default=.8);p.add_argument('--fps',type=int,default=15)
    a=p.parse_args();render(a.run,a.out,a.step,a.fps)
