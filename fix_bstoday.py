# -*- coding: utf-8 -*-
import json, hashlib, tempfile, os, sys

REPO = '/Users/simon/.qoderwork/workspace/mrip73rtvdfbrpv4/outputs/huali-life'
FILE = os.path.join(REPO, 'sync.json')
TODAY = '2026-10-22'

# Load
with open(FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Snapshot non-target field hashes (everything except TODAY.bsToday)
def snapshot(obj):
    h = {}
    for k, v in obj.items():
        if k == TODAY:
            continue
        h[k] = hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    # Also snapshot non-bsToday fields within TODAY
    today_obj = obj.get(TODAY, {})
    for k, v in today_obj.items():
        if k == 'bsToday':
            continue
        h[f'{TODAY}.{k}'] = hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    return h

pre_hashes = snapshot(data)

# Get current bsToday
bs = data[TODAY]['bsToday']
print(f"Before fix: topic={bs['topic'][:40]}...")
print(f"  keyPoints count: {len(bs.get('keyPoints',[]))}")
print(f"  rounds count: {len(bs.get('rounds',[]))}")

# Fix 1: Populate keyPoints with meaningful titles and descriptions
# Based on the discussion content, extract 5 key themes
bs['keyPoints'] = [
    {
        "title": "统一决策引擎框架",
        "desc": "一人三角色的核心不是让AI干活，而是让DSP投放、健身房运营、社群内容三个角色的决策流共享一个中台。底层都是'基于规则+数据的状态机'，可抽象为统一的决策引擎。"
    },
    {
        "title": "数据打通与模型定义",
        "desc": "三个角色当前使用割裂的工具系统，需通过n8n/Make等自动化平台做中间层，先定义数据模型和关联字段（如用户ID跨系统打通），再拉通数据到统一数据库。"
    },
    {
        "title": "权限隔离与安全架构",
        "desc": "采用'逻辑共享、物理隔离'方案——决策引擎统一，但底层数据存储在三个独立数据库，通过权限网关控制访问。DSP涉及客户预算、健身房涉及个人隐私、社群涉及行为画像，合规风险需前置设计。"
    },
    {
        "title": "决策释放率衡量指标",
        "desc": "不用传统的'自动化覆盖率'，而用'决策释放率'——自动化省下的时间有多少用在了更高价值的事情上。配合Toggl/RescueTime等时间日志工具，每周复盘时间结构变化。"
    },
    {
        "title": "安全网与分级处理机制",
        "desc": "关键动作分级：低风险（社群定时发布）全自动，中风险（排课调整）自动但通知，高风险（DSP预算调整）必须人工确认。底线是'人随时能接管'，保留人工干预接口。"
    }
]

# Fix 2: Trim rounds from 18 to 14
# Keep rounds 0-13 (core discussion arc: framework → data → permission → metrics → safety → summary)
# These 14 rounds form a complete narrative with clear beginning, middle, and conclusion
original_rounds = bs.get('rounds', [])
bs['rounds'] = original_rounds[:14]

print(f"\nAfter fix:")
print(f"  keyPoints count: {len(bs.get('keyPoints',[]))}")
for i, kp in enumerate(bs['keyPoints']):
    print(f"    [{i}] title={kp['title']}, desc={kp['desc'][:40]}...")
print(f"  rounds count: {len(bs.get('rounds',[]))}")
print(f"  sparks count: {len(bs.get('sparks',[]))}")
print(f"  qa count: {len(bs.get('qa',[]))}")
print(f"  summary length: {len(str(bs.get('summary','')))}")

# Validation
assert bs['topic'] and len(bs['topic']) > 0, "topic empty"
assert all(kp.get('title') and kp.get('desc') for kp in bs['keyPoints']), "keyPoints incomplete"
assert 10 <= len(bs['rounds']) <= 14, f"rounds {len(bs['rounds'])} out of range"
assert 4 <= len(bs['sparks']) <= 6, f"sparks {len(bs['sparks'])} out of range"
assert 3 <= len(bs['qa']) <= 4, f"qa {len(bs['qa'])} out of range"
summary_text = str(bs.get('summary', ''))
assert len(summary_text) > 100, "summary too short"
print("\nAll validations passed!")

# Atomic write
tmp_fd, tmp_path = tempfile.mkstemp(dir=REPO, suffix='.tmp')
try:
    with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, FILE)
    print(f"Atomic write successful: {tmp_path} -> {FILE}")
except Exception as e:
    os.unlink(tmp_path)
    print(f"Atomic write failed: {e}", file=sys.stderr)
    sys.exit(1)

# Verify: reload and check non-target hashes
with open(FILE, 'r', encoding='utf-8') as f:
    data2 = json.load(f)

post_hashes = snapshot(data2)

mismatches = []
for k in pre_hashes:
    if pre_hashes[k] != post_hashes.get(k):
        mismatches.append(k)

if mismatches:
    print(f"\nHASH MISMATCH for non-target fields: {mismatches}", file=sys.stderr)
    sys.exit(1)
else:
    print(f"\nHash verification passed: all {len(pre_hashes)} non-target fields unchanged.")

# Verify TODAY.bsToday is valid
bs2 = data2[TODAY]['bsToday']
print(f"\nPost-write verification:")
print(f"  topic: {bs2['topic'][:50]}...")
print(f"  keyPoints: {len(bs2['keyPoints'])} items, all with title+desc")
print(f"  rounds: {len(bs2['rounds'])}")
print(f"  sparks: {len(bs2['sparks'])}")
print(f"  qa: {len(bs2['qa'])}")
print(f"  summary: {len(str(bs2['summary']))} chars")
print("\nFix complete!")
