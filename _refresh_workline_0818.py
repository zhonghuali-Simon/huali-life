# -*- coding: utf-8 -*-
import json, os, subprocess

P = '/Users/simon/.qoderwork/workspace/mrip73rtvdfbrpv4/outputs/huali-life/sync.json'
RESIDENT_PATH = '/Users/simon/.qoderwork/growth-guard/resident_tpl.txt'
TODAY = '2026-08-18'

# Load sync.json
d = json.load(open(P, encoding='utf-8'))

# Load fresh resident baseline
RESIDENT = open(RESIDENT_PATH, encoding='utf-8').read().strip()

# Ensure today key exists with proper inheritance
if TODAY not in d:
    ys = sorted(k for k in d if k < TODAY)[-1]
    d[TODAY] = {
        'done': [],
        'bonus': [],
        'blockedTitles': d[ys].get('blockedTitles') or [],
        'manualTasks': d[ys].get('manualTasks') or []
    }

node = d[TODAY]

# Preserve manualTasks verbatim
manual_tasks = node.get('manualTasks') or []
node['manualTasks'] = manual_tasks

# Build work-line: start with daily check, append manual tasks, then use existing items if present
# The existing work-line for 2026-08-18 is already comprehensive; we refresh from fresh data by
# preserving it unless manualTasks changed.
existing_lines = [l for l in node.get('tpl', '').splitlines() if l.strip()]
work_lines = []
for l in existing_lines:
    if l.startswith('T-1'):
        work_lines.append(l)

# If no existing work-line, create minimal from manual tasks
if not work_lines:
    work_lines = [
        'T-101 | 工作线 | 每日检查渠道消耗+核心数据巡检 | 各渠道消耗/异动/日报每日必看·07:30监控告警群已推召回/IPVUV/闪购GAB/CVR/U3唤端·含DSP反作弊日报(gap<0.3%)·10:00前完成巡检 | 10 | DA:6,PM:4'
    ]
    for mt in manual_tasks:
        if mt.strip() and mt not in work_lines:
            work_lines.append(mt)

# Append manual tasks that are not already in work-line
for mt in manual_tasks:
    if mt.strip() and mt not in work_lines:
        work_lines.append(mt)

# Compose tpl: work-line + resident baseline
node['tpl'] = '\n'.join(work_lines) + '\n' + RESIDENT

# Self-check
work_count = len(work_lines)
resident_count = len([l for l in RESIDENT.splitlines() if l.strip()])
assert work_count >= 3, f'工作线仅 {work_count} 项，需 ≥3'
assert resident_count >= 30, f'常驻基线仅 {resident_count} 行，需 ≥30'
assert isinstance(node.get('manualTasks'), list), 'manualTasks 必须是列表'

# Write only if changed
old = json.load(open(P, encoding='utf-8'))
if old.get(TODAY, {}).get('tpl') != node['tpl'] or old.get(TODAY, {}).get('manualTasks') != node['manualTasks']:
    json.dump(d, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('CHANGED')
else:
    print('UNCHANGED')

print(f'工作线: {work_count} 项 | 常驻基线: {resident_count} 行 | manualTasks: {len(manual_tasks)} 条')
