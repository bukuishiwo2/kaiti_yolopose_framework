"""Publish audited execution records and manually reviewed short video intervals."""
import argparse
import json
from pathlib import Path

from factorial import WORKSPACE, benchmark, READ, WRITE
from publish import publish

OBSERVATIONS = (
    ('visual_positive_2026-11-18_c1/positive_02/video/causal.jsonl', 'fall-01-cam0',
     137, 138, 139, '倒地后人体部分出画，姿态漏检两帧'),
    ('visual_integration_2026-11-18_b1/visual_false_alarm_a2/video/causal.jsonl', 'adl-01-cam0',
     0, 7, 8, '人体从门框后进入画面'),
)
ROLES = {'E1_verify': '现场核验', 'E1_monitor': '现场监护',
         'E1_pickup': '领取物资', 'E1_deliver': '送达物资'}


def observations(root):
    for relative, video, first, last, recovery, label in OBSERVATIONS:
        path = root/'verification'/relative
        frames = {}
        with path.open() as stream:
            for line, text in enumerate(stream, 1):
                row = json.loads(text)
                if row['kind'] != 'image_model_event_tasks':
                    continue
                sample = row['sample']
                if sample['source_id'] == video and sample['replay'] == 0:
                    frame = round(sample['video_time'] * 30)
                    if first <= frame <= recovery:
                        frames[frame] = (line, sample, row['model']['seq_visible_keypoint_count'])
        yield dict(label=label, video=video, start=frames[first][1]['video_time'],
                   end=frames[last][1]['video_time'],
                   minimum=min(frames[i][2] for i in range(first, last + 1)),
                   recovered=frames[recovery][2], source=str(path), sha256=benchmark.sha(path),
                   lines=[frames[first][0], frames[recovery][0]],
                   stable=[frames[i][1]['stable'] for i in range(first, recovery + 1)])


def execution(out):
    run = out/'gazebo_fixed_reference'
    audit = out/'gazebo_fixed_reference_standard_audit/summary.json'
    summary = run/'summary.json'
    s, a = READ(summary), READ(audit)
    if not (s['passed'] and a['passed'] and a['summary_sha256'] == benchmark.sha(summary)
            and READ(run/'runtime_preflight.json')['passed'] and READ(run/'cleanup.json')['passed']):
        raise ValueError('Gazebo witness failed audit, preflight, or cleanup')
    records = [dict(id=j, robot=r['robot'].upper(), label=ROLES.get(j,'常态巡检')+'（'+r['anchor']+'）',
                    start=r['service_started'], finish=r['service_finished'])
               for j, r in s['completed'].items()]
    confirmed = next(q['message']['at'] for q in s['protocol_records'] if q.get('verdict'))
    delivery = s['completed']['E1_deliver']['service_finished']
    return dict(description=f'A 区固定应急角色的独立执行见证。{len(records)} 项服务完成，{len(a["checks"])} 项独立检查通过。'
                            '该入口使用真实视频触发，任务后缀与离线四格不同。',
                pairing='固定归属与局部改派的同条件执行配对尚未运行。两组叠加条件均未出现有收益的按需改派。'
                        '全量方案包含未获资格的角色与常态改派。',
                confirmed=confirmed, delivery=delivery, deliveryAfterConfirmation=delivery-confirmed,
                routineCompletion=s['completed']['C0_r3_W2']['end'], records=records,
                sources={str(p): benchmark.sha(p) for p in (summary,audit)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    WRITE(out/'observations.json', list(observations(WORKSPACE)))
    if (out/'gazebo_fixed_reference/summary.json').is_file():
        WRITE(out/'execution.json', execution(out))
    publish(out, WORKSPACE)
