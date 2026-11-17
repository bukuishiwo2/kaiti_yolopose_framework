"""Measured Matplotlib/FFmpeg replay, explicit function; no runtime source rewriting."""
from .config import ROOT
from pathlib import Path
import argparse, json, math, subprocess
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle, Patch
from matplotlib.transforms import Affine2D

def render(run, destination, audit_summary):
    run = Path(run)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    r = json.loads((run / 'result.json').read_text())
    audit = audit_summary
    assert r['passed'] and audit['passed']
    c = json.loads((run / 'runtime_scenario.json').read_text())
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
    plt.rcParams['axes.unicode_minus'] = False
    trace = [json.loads(x) for x in (run / 'trace.jsonl').read_text().splitlines()]
    wait_intervals = []
    for stop in [v['episode_time'] for v in trace if v['phase'] == 'bed_stopped']:
        wait_intervals.append((stop, next((v['episode_time'] for v in trace if v['phase'] == 'bed_observed_clear_resume' and v['episode_time'] > stop))))
    colors = {'r1': '#1677b8', 'r2': '#da8115', 'r3': '#3a9448'}
    img = np.array(Image.open(ROOT / 'config/hospital_aligned/semantic_navigation.pgm'))
    event = r['event_at']
    close = r['incident_closed_at']
    period = c['period_seconds']
    end = audit['episode_sim_seconds']
    (fig, ax) = plt.subplots(figsize=(16, 6), constrained_layout=True)
    for (n, (rid, color)) in enumerate(colors.items()):
        y = 2 - n
        for q in r['records']:
            if q['robot'] != rid:
                continue
            emergency = q['job_id'].startswith('E1_')
            ax.broken_barh([(q['begin'], q['end'] - q['begin'])], (y - 0.23, 0.46), facecolors=color, alpha=0.25, hatch='///' if emergency else None, edgecolor=color)
            ax.broken_barh([(q['service_started'], q['service_finished'] - q['service_started'])], (y - 0.23, 0.46), facecolors=color, alpha=0.95)
            ax.text((q['begin'] + q['end']) / 2, y + 0.3, q['job_id'], fontsize=7, rotation=25, ha='center')
    for (at, label, color) in [(event, '跌倒事件', '#b02a2a'), (close, '事件关闭 / 恢复延期巡逻', '#ad6f0b'), (period, '固定时钟释放第1周期', '#754baa')]:
        ax.axvline(at, c=color, ls='--')
        ax.text(at + 3, 2.85 if at == close else 2.65 if at == period else 2.7, label, fontsize=9, c=color)
    for e in r['active_repairs']:
        ax.axvline(e['requested_at'], c='#a42c2c', ls=':', alpha=0.7)
    ax.set(yticks=[2, 1, 0], yticklabels=['R1', 'R2', 'R3'], xlabel='仿真时间 / s', ylim=(-0.55, 3.05), title='实际任务时间线：第0周期巡逻—应急协作—恢复—第1周期')
    ax.grid(axis='x', alpha=0.2)
    ax.legend(handles=[Patch(color='gray', alpha=0.25, label='任务区间：含导航、等待和清空'), Patch(color='gray', alpha=0.95, label='实际服务'), Patch(facecolor='white', edgecolor='gray', hatch='///', label='应急任务')], loc='upper right', fontsize=8)
    fig.savefig(destination / 'execution_timeline.png', dpi=160)
    fig.savefig(destination / 'execution_timeline.svg')
    plt.close(fig)
    fig = plt.figure(figsize=(18, 8))
    fig.subplots_adjust(left=0.045, right=0.985, bottom=0.095, top=0.875, wspace=0.2)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.05, 0.8])
    full = fig.add_subplot(gs[0, 0])
    local = fig.add_subplot(gs[0, 1])
    panel = fig.add_subplot(gs[0, 2])
    panel.axis('off')
    for axis in [full, local]:
        axis.imshow(img, cmap='gray', extent=(0, 60, -50, 0), vmin=0, vmax=254)
        axis.set_aspect('equal')
        axis.set_xlabel('map x / m')
        axis.set_ylabel('map y / m')
    full.set(xlim=(0, 60), ylim=(-50, 0), title='完整Clinic地图 / 原比例')
    full.add_patch(Rectangle((6, -33.5), 20, 25, fill=False, ec='#b32b2b', lw=2, ls='--'))
    local.set(xlim=(6, 26), ylim=(-33.5, -8.5), title='20×25米局部任务区 / 实测轨迹')
    for (k, label) in {'DL': '护理站DL', 'G1': '物资G1', 'PW1': '候诊PW1', 'PW2': '候诊PW2', 'TL': '诊疗TL', 'V1': '核验V1', 'M1': '监护M1', 'H1': '交付H1', 'CTLR3': 'R3清空停靠', 'BDL': '侧边清空BDL', 'CPW2B': '候诊清空B', 'CPW2C': '候诊清空C'}.items():
        (x, y, _) = c['anchors'][k]
        local.scatter(x, y, s=10, c='#777')
        local.annotate(label, (x, y), xytext=(3, 4), textcoords='offset points', fontsize=7, bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', pad=0.2))
    pack = {}
    artists = []
    for axis in [full, local]:
        pack[axis] = {}
        for (rid, color) in colors.items():
            (line,) = axis.plot([], [], c=color, lw=1.25)
            (dot,) = axis.plot([], [], marker='o', c=color, ms=6)
            pack[axis][rid] = (line, dot)
            artists.extend([line, dot])
    stars = []
    for axis in [full, local]:
        (star,) = axis.plot([c['event']['center'][0]], [c['event']['center'][1]], '*', c='#bf2929', ms=11, visible=False)
        stars.append(star)
        artists.append(star)
    bed_artists = {}
    for axis in [full, local]:
        for phase in ['short', 'long']:
            rect = Rectangle((-1.01, -0.52), 2.02, 1.04, facecolor='#b73131', edgecolor='black', alpha=0.65, visible=False)
            axis.add_patch(rect)
            bed_artists[axis, phase] = rect
            artists.append(rect)
    status = panel.text(0, 1, '', va='top', fontsize=9, linespacing=1.25)
    title = fig.suptitle('', fontsize=14)
    artists.extend([status, title])
    fig.text(0.5, 0.005, '蓝R1／橙R2／绿R3。Gazebo物理位姿、Nav2与独立服务ACK；参考定位；实体床脚本占道，无行人；无真实视觉跌倒识别或抓取。', ha='center', fontsize=9)
    samples = [s for s in r['truth_samples'] if s['at'] >= r['epoch']]
    times = np.array([s['at'] - r['epoch'] for s in samples])
    xy = {rid: np.array([[s['poses'][rid]['x'], s['poses'][rid]['y']] for s in samples]) for rid in colors}
    fps = 10
    step = 1.5
    schedule = np.arange(0, end + step, step)
    preview = []
    for artist in artists:
        artist.set_animated(True)
    fig.canvas.draw()
    if hasattr(fig, 'set_layout_engine'):
        fig.set_layout_engine(None)
    else:
        fig.set_constrained_layout(False)
        fig.set_tight_layout(False)
    back = fig.canvas.copy_from_bbox(fig.bbox)
    (w, h) = fig.canvas.get_width_height()
    proc = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-s', f'{w}x{h}', '-pix_fmt', 'rgba', '-r', str(fps), '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '23', '-preset', 'fast', '-threads', '2', str(destination / 'mission_replay.mp4')], stdin=subprocess.PIPE)
    try:
        for (frame, t) in enumerate(schedule):
            t = min(t, end)
            k = max(0, min(len(times) - 1, int(np.searchsorted(times, t, side='right') - 1)))
            stage = '三机正常巡逻' if t < event else '跌倒事件 / 核验与协同分配' if t < r['completed']['E1_verify']['end'] else 'MILP应急分工 / 前往服务点' if t < r['completed']['E1_monitor']['service_started'] else '持续监护＋物资取送＋常态任务' if t < close else '事件关闭 / 恢复延期任务' if t < period else '下一周期释放与执行'
            title.set_text(f'{stage} ｜ t={t:.1f}s ｜15×实测回放')
            for axis in [full, local]:
                for (rid, (line, dot)) in pack[axis].items():
                    line.set_data(xy[rid][:k + 1, 0], xy[rid][:k + 1, 1])
                    dot.set_data([xy[rid][k, 0]], [xy[rid][k, 1]])
            for star in stars:
                star.set_visible(event <= t < close)
            bed_labels = []
            for phase in ['short', 'long']:
                truth = [d for d in r['bed_truth'] if d.get('phase_id') == phase and d['at'] - r['epoch'] <= t]
                d = truth[-1] if truth else None
                visible = bool(d and d['action'] != 'removed')
                if visible:
                    bed_labels.append('短时床占道' if phase == 'short' else '持续床占道')
                for axis in [full, local]:
                    rect = bed_artists[axis, phase]
                    rect.set_visible(visible)
                    if visible:
                        rect.set_transform(Affine2D().rotate(d.get('yaw', math.pi / 2)).translate(d['x'], d['y']) + axis.transData)
            waiting = any((lo <= t < hi for (lo, hi) in wait_intervals))
            solving = any((e['requested_at'] <= t < e['returned_at'] for e in r['active_repairs']))
            text = [stage, 'R2观测停车等待' if waiting else 'R2通道未处于停车等待', '修复求解中：保留执行任务' if solving else '当前无活动修复求解', '策略：' + ('局部修复' if r['strategy'] == 'local_impact' else '热启动全量'), '脚本床状态：' + ('/'.join(bed_labels) if bed_labels else '不占道'), '修复已提交：' + str(sum((e['returned_at'] <= t for e in r['active_repairs']))), '']
            for rid in colors:
                current = next((q for q in r['records'] if q['robot'] == rid and q['begin'] <= t < q['end']), None)
                if current:
                    phase = '服务中' if current['service_started'] <= t < current['service_finished'] else '执行中（含等候/清空）'
                    text += [rid.upper() + ' ' + phase, current['job_id'] + ' → ' + current['anchor']]
                    if current['job_id'].startswith('C') and r['tasks'][current['job_id']]['nominal_owner'] != rid:
                        text += ['改派自 ' + r['tasks'][current['job_id']]['nominal_owner'].upper()]
                else:
                    text += [rid.upper() + ' 待命 / 等待派发']
            text += ['', '事件 E1 / 优先级100：' + ('未发生' if t < event else '已关闭' if t >= close else '处理中')]
            response = next((e for e in r['planning_records'] if e['stage'] == 'response' and e['returned_at'] <= t), None)
            if response:
                owners = response['solver']['plan']['owners']
                text += ['监护：' + owners['E1_monitor'].upper(), '取送：' + owners['E1_pickup'].upper()]
            n0 = sum((q['end'] <= t for (j, q) in r['completed'].items() if j.startswith('C0_')))
            n1 = sum((q['end'] <= t for (j, q) in r['completed'].items() if j.startswith('C1_')))
            ne = sum((q['end'] <= t for (j, q) in r['completed'].items() if j.startswith('E1_')))
            deferred = [j for j in r['deferred_at_event'] if r['completed'][j]['end'] > t] if t >= event else []
            text += ['', f'第0周期完成：{n0}/9', f'应急任务完成：{ne}/4', f'原延期任务未完成：{len(deferred)}', f'第1周期：' + (f'完成{n1}/9' if t >= period else '尚未释放')]
            if t >= period:
                text += [f'周期释放时刻：{period:.0f}s（固定）']
            status.set_text('\n'.join(text))
            fig.canvas.restore_region(back)
            for artist in artists:
                artist.axes.draw_artist(artist) if artist.axes else fig.draw_artist(artist)
            proc.stdin.write(fig.canvas.buffer_rgba())
            if frame % 3 == 0:
                preview.append(Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()).resize((1080, 480)))
    finally:
        proc.stdin.close()
        code = proc.wait()
    assert code == 0
    preview[0].save(destination / 'mission_preview.gif', save_all=True, append_images=preview[1:], duration=300, loop=0, optimize=False)
    plt.close(fig)
    (destination / 'animation_manifest.json').write_text(json.dumps(dict(frames=len(schedule), fps=fps, sim_seconds_per_frame=step, playback_speed=15, coordinates='preceding actual Gazebo sample, no path interpolation', event_source='script', source=str(run / 'result.json')), indent=2))
