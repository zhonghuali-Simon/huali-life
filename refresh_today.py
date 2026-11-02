#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh today's work-line tpl in huali-life sync.json."""
import json
import subprocess
from pathlib import Path

TODAY = subprocess.check_output(['date', '+%F']).decode().strip()
SYNC_PATH = Path('/Users/simon/.qoderwork/workspace/mrip73rtvdfbrpv4/outputs/huali-life/sync.json')
RESIDENT_PATH = Path('/Users/simon/.qoderwork/growth-guard/resident_tpl.txt')


def main():
    data = json.loads(SYNC_PATH.read_text(encoding='utf-8'))
    resident_text = RESIDENT_PATH.read_text(encoding='utf-8').strip()

    if TODAY not in data:
        prev = sorted(k for k in data if k < TODAY)[-1]
        data[TODAY] = {
            'blockedTitles': list(data[prev].get('blockedTitles') or []),
            'manualTasks': list(data[prev].get('manualTasks') or [])
        }

    today = data[TODAY]
    mt = list(today.get('manualTasks') or [])

    # Fixed first task + real tasks for today.
    # 爱晴-assigned tasks are annotated and placed before other real tasks.
    WORK_TASKS = [
        ('T-101', '每日检查渠道消耗+核心数据巡检', '各渠道消耗/异动/日报每日必看·07:30监控告警群已推召回/IPVUV/闪购GAB/CVR/U3唤端·含DSP反作弊日报(gap<0.3%)·10:00前完成巡检', '10', 'DA:6,PM:4'),
        ('T-102', '9月AAC项目启动沟通节奏确认(爱晴)', '爱晴安排：9.14启动沟通，9.18项目服务最后一天·提前对齐会议/资料/参会人', '8', 'PM:4,TM:4'),
        ('T-103', 'AAC项目执行节奏文档终稿', '补充里程碑节点、责任人分工、风险点，形成可执行版本并同步相关方', '10', 'DA:6,PM:4'),
        ('T-104', '私域社群SOP终稿完善', '完善拉群链路流程图、运营规范细则、奖惩机制条款，形成可落地版本', '8', 'PM:4,TM:4'),
        ('T-105', '直管同学待办检查与反馈', '检查米亓/柯特/赵笑影/贰囍本周待办完成情况·对滞后任务@相关同学并给出改进建议', '6', 'PM:6'),
        ('T-106', '过期待办清理', '逐条检查D001-D024及T系列过期待办·标记完成或重新设定合理截止时间', '6', 'PM:6'),
    ]

    work_lines = [f"{tid} | 工作线 | {title} | {desc} | {score} | {dims}" for tid, title, desc, score, dims in WORK_TASKS]

    for r in mt:
        if r.strip() and r not in work_lines:
            work_lines.append(r)

    today['manualTasks'] = mt
    today['tpl'] = '\n'.join(work_lines) + '\n' + resident_text

    SYNC_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    # Self-check
    data = json.loads(SYNC_PATH.read_text(encoding='utf-8'))
    tpl_lines = data[TODAY]['tpl'].split('\n')
    work_count = sum(1 for l in tpl_lines if ' | 工作线 | ' in l)
    resident_count = sum(1 for l in tpl_lines if l.startswith('T-') and ' | 工作线 | ' not in l)
    manual_present = all(m in data[TODAY]['tpl'] for m in mt)

    print(f'TODAY={TODAY}')
    print(f'Work-line tasks: {work_count}')
    for l in tpl_lines:
        if ' | 工作线 | ' in l:
            print('  ', l)
    print(f'Resident items: {resident_count}')
    print(f'manualTasks present: {manual_present}')
    assert work_count >= 3, f'work line too short: {work_count}'
    assert resident_count >= 30, f'resident baseline too short: {resident_count}'
    assert manual_present, 'manualTasks missing'
    print('Self-check passed.')


if __name__ == '__main__':
    main()
