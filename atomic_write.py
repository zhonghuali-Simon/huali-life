#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import hashlib
import os
import tempfile
import copy

# Load sync.json
print("Loading sync.json...")
with open('sync.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Snapshot non-target field hashes
print("Snapshotting non-target field hashes...")
non_target_fields = ['tpl', 'manualTasks', 'done', 'bonus', 'blockedTitles', 'kbAppend', 'stockToday', 'tbToday']
baseline_hashes = {}
for key, val in data.items():
    if key in ('tpl', 'note') or not isinstance(val, dict):
        continue
    if key == '2026-10-22':
        continue
    for field in non_target_fields:
        if field in val:
            content = json.dumps(val[field], ensure_ascii=False, sort_keys=True)
            h = hashlib.sha256(content.encode('utf-8')).hexdigest()
            if field not in baseline_hashes:
                baseline_hashes[field] = set()
            baseline_hashes[field].add(h)

print(f"Baseline hashes captured for {len(baseline_hashes)} fields")

# Create new 2026-10-22 entry based on 2026-10-21 template
print("Creating 2026-10-22 entry...")
template = copy.deepcopy(data['2026-10-21'])
new_entry = copy.deepcopy(template)

# Set bsToday to new content
new_bsToday = {
    "topic": "「一人三角色」的AI自动化流水线设计：DSP投放、健身房运营与社群内容如何共享同一个智能中台",
    "keyPoints": [
        {
            "point": "认知卸载：把重复性决策交给AI，人只做例外判断",
            "why": "DSP投放、健身房排课、社群内容分发这三类工作里，80%是规则明确的重复动作，只有20%需要人的经验判断。AI自动化的核心价值不是替代人，而是把人从低价值决策中释放出来，聚焦到高杠杆的例外事件上。"
        },
        {
            "point": "SOP标准化是自动化的前提，没有标准化就没有自动化",
            "why": "很多人直接跳到'用什么AI工具'，但真正决定自动化成败的是SOP的颗粒度和清晰度。一个模糊的'发朋友圈'动作，拆成'选素材→配文案→定时间→发指定群'四步，每一步都能写成规则，才能被AI执行。"
        },
        {
            "point": "优先自动化选择标准：高频×低容错×规则明确",
            "why": "不是所有工作都适合自动化。高频意味着投入产出比高，低容错意味着人做容易疲劳出错，规则明确意味着AI能稳定执行。三个条件同时满足的场景，才是自动化的最佳切入点。"
        },
        {
            "point": "决策释放率指标：衡量自动化效果的不是省了多少时间，而是释放了多少高价值决策",
            "why": "传统效率指标看'省了几个小时'，但这不够。真正重要的是：自动化之后，人有没有把省下来的时间用在更高杠杆的事情上？如果省下来的时间只是刷了手机，自动化就失败了。"
        },
        {
            "point": "数据安全地基：三个角色共享一个智能中台，权限隔离和数据安全必须前置",
            "why": "DSP投放数据、健身房会员信息、社群用户画像，这三类数据的敏感度和合规要求不同。共享中台不等于共享权限，必须在架构设计阶段就把数据隔离、访问控制、审计日志做进去，而不是事后补丁。"
        }
    ],
    "rounds": [
        "林AI：我先抛个框架。一人三角色的核心问题不是'怎么让AI干活'，而是'怎么让三个角色的决策流共享一个中台'。DSP投放的素材选择、健身房的排课逻辑、社群的内容分发，这三者底层都是'基于规则+数据的状态机'。如果我们能把这些规则抽象成统一的决策引擎，一个人就能同时管理三条业务线。",
        "钟华力：我同意框架，但有个现实问题。我现在的三个角色是割裂的——DSP在A工具里操作，健身房在B系统里排课，社群在C平台里发内容。要共享中台，第一步是不是得先把数据打通？这个工程量会不会太大？",
        "周衍：数据打通是必要条件，但不一定需要大工程。我的建议是用n8n或者Make这种自动化平台做中间层，通过API把三个系统的数据拉到同一个数据库里。关键是先定义清楚数据模型——投放数据、会员数据、社群数据，它们的关联字段是什么？比如用户ID能不能跨系统打通？",
        "苏小汗：从健身房运营角度，我最关心的是排课自动化。现在教练的排课是人工排的，经常冲突。如果AI能根据教练的可用时间、会员的预约偏好、课程的容量限制自动生成排课方案，我能省多少事？但这个方案能不能和DSP投放、社群内容共享中台？",
        "陈私域：我来接小汗的话。社群内容分发其实和排课逻辑很像——都是'在正确的时间把正确的内容推给正确的人'。如果中台能统一管理内容库、用户标签、分发规则，那健身房的排课和社群的内容推送，底层就是同一套调度引擎。",
        "赵审：我得泼盆冷水。三个角色的数据共享中台，权限隔离怎么做？DSP投放数据涉及客户预算，健身房会员数据涉及个人隐私，社群数据涉及用户行为画像。如果中台被攻破或者内部人员越权访问，合规风险谁来担？",
        "林AI：赵审说得对。我的建议是'逻辑共享、物理隔离'——中台的决策引擎是统一的，但底层数据存储在三个独立的数据库里，通过权限网关控制访问。DSP操盘手只能看投放数据，健身房老板能看会员和排课，社群运营能看用户画像和内容效果。只有'钟华力'这个角色能跨三个数据库看汇总报表。",
        "钟华力：这个方案可行。但我还有个问题：自动化之后，我怎么衡量效果？省了多少时间？",
        "周衍：传统指标是'自动化覆盖率'——多少比例的工作被AI接管了。但我建议用'决策释放率'——自动化之后，你省下来的时间有多少用在了更高价值的事情上？比如排课自动化省了2小时，这2小时你是用来优化投放策略了，还是刷手机了？后者说明自动化失败了。",
        "苏小汗：决策释放率这个指标很犀利。但怎么追踪？我怎么知道自己省下来的时间用在哪了？",
        "陈私域：可以用时间日志工具，比如Toggl或者RescueTime，记录每天的时间分配。每周复盘一次，看自动化前后的时间结构变化。如果高价值工作的时间占比没提升，说明自动化还没到位，或者人的习惯没跟上。",
        "赵审：我再补充一个风险点。AI自动化出错了怎么办？比如DSP投放自动暂停了，健身房排课冲突了，社群内容发错群了。需要有'安全网'机制——关键动作必须有人工确认环节，或者至少要有告警通知。",
        "林AI：完全同意。我的建议是分级处理：低风险动作（比如社群定时发布）全自动，中风险动作（比如排课调整）自动但通知相关人员，高风险动作（比如DSP预算调整）必须人工确认。这个分级标准要在自动化上线前就定义清楚。",
        "钟华力：总结一下。一人三角色的AI自动化流水线，核心是三个层面的设计：第一，数据层——通过自动化平台打通三个系统的数据，建立统一数据模型；第二，决策层——抽象出统一的调度引擎，管理排课、内容分发、投放优化；第三，权限层——逻辑共享、物理隔离，关键动作分级处理。衡量指标用'决策释放率'，看省下来的时间有没有用在高价值事情上。",
        "周衍：我再补一个技术细节。选自动化工具时，n8n和Make的区别是：n8n开源、可自托管、适合复杂逻辑，但学习曲线陡；Make云端托管、开箱即用、适合简单流程，但定制化能力弱。如果你三个角色的流程复杂度差异大，建议用n8n做核心引擎，Make做轻量补充。",
        "陈私域：最后提个醒。自动化不是一蹴而就的，建议从'高频×低容错×规则明确'的场景切入。比如社群内容定时发布，这个场景规则清晰、容错空间大、每天都能用到。先跑通一个场景，积累经验，再扩展到其他场景。",
        "刘教练：我从一线教练角度说句实话。排课自动化我欢迎，但别把我变成系统的奴隶。如果AI排的课我上着不舒服，或者会员有特殊需求系统没考虑到，我得能手动调整。自动化是辅助，不是控制。",
        "钟华力：刘教练说得对。自动化的底线是'人随时能接管'。系统设计要保留人工干预的接口，而不是让人被系统绑着走。"
    ],
    "sparks": [
        "认知卸载的本质不是'让AI替人干活'，而是'让人只做例外判断'——规则明确的交给系统，模糊的留给人脑。",
        "自动化的前提不是选对工具，而是SOP的颗粒度足够细。一个动作拆不成四步以上，就很难被AI稳定执行。",
        "决策释放率比时间节省率更犀利——省下来的时间用在哪，决定了自动化的真实ROI。",
        "三个角色共享中台的关键是'逻辑共享、物理隔离'——决策引擎统一，数据存储分离，权限分级控制。",
        "一线执行者的反馈最重要：自动化是辅助，不是控制。系统设计必须保留人工干预的接口。"
    ],
    "qa": [
        {
            "q": "一人三角色的AI自动化，应该从哪个角色切入？",
            "a": "从'高频×低容错×规则明确'的场景切入。社群内容定时发布是最典型的场景——规则清晰、容错空间大、每天都能用到。先跑通这个场景，积累经验和信心，再扩展到健身房排课、DSP投放优化。"
        },
        {
            "q": "三个角色的数据共享中台，权限隔离怎么做？",
            "a": "采用'逻辑共享、物理隔离'架构。决策引擎统一，但底层数据存储在三个独立数据库里，通过权限网关控制访问。每个角色只能看自己的数据，只有'本人'角色能跨数据库看汇总报表。关键动作分级处理：低风险全自动，中风险自动但通知，高风险必须人工确认。"
        },
        {
            "q": "AI自动化出错了怎么办？",
            "a": "建立分级安全网机制。低风险动作（社群定时发布）全自动，中风险动作（排课调整）自动但通知相关人员，高风险动作（DSP预算调整）必须人工确认。分级标准在自动化上线前就定义清楚，并且保留人工随时接管的接口。"
        },
        {
            "q": "n8n和Make怎么选？",
            "a": "n8n开源、可自托管、适合复杂逻辑，但学习曲线陡；Make云端托管、开箱即用、适合简单流程，但定制化能力弱。如果三个角色的流程复杂度差异大，建议用n8n做核心引擎，Make做轻量补充。如果团队技术能力有限，先从Make起步，遇到瓶颈再迁移到n8n。"
        }
    ],
    "summary": "本次脑洞会议围绕'一人三角色的AI自动化流水线设计'展开，核心结论如下：\n\n1. 【P0-本周必做】梳理三个角色的SOP，把每个动作拆成4步以上，识别'高频×低容错×规则明确'的自动化切入点。建议从社群内容定时发布开始。\n\n2. 【P0-本周必做】定义数据模型和权限架构。三个系统的数据关联字段是什么？权限如何分级？关键动作的风险等级如何划分？这些必须在动手之前想清楚。\n\n3. 【P1-两周内】选型自动化工具。如果团队技术能力强，直接用n8n做核心引擎；如果能力有限，先用Make起步。关键是要能打通三个系统的数据。\n\n4. 【P1-两周内】建立'决策释放率'追踪机制。用时间日志工具记录每天的时间分配，每周复盘一次，看自动化前后的时间结构变化。\n\n5. 【P2-一个月内】跑通第一个自动化场景（社群内容定时发布），积累经验后扩展到健身房排课、DSP投放优化。\n\n6. 【P2-一个月内】建立安全网机制。关键动作分级处理，保留人工干预接口，确保'人随时能接管'。\n\n7. 【长期】构建统一的决策引擎。三个角色的调度逻辑抽象成同一套引擎，实现真正的'一人三角色'智能中台。\n\n8. 【长期】持续优化决策释放率。自动化不是一次性项目，而是持续迭代的过程。每次优化都要回答：省下来的时间，有没有用在更高价值的事情上？"
}

new_entry['bsToday'] = new_bsToday
data['2026-10-22'] = new_entry

# Atomic write via tempfile + os.replace
print("Performing atomic write...")
dir_name = os.path.dirname(os.path.abspath('sync.json'))
fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.json')
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, 'sync.json')
    print(f"Atomic write completed: {temp_path} -> sync.json")
except Exception as e:
    print(f"Error during atomic write: {e}")
    if os.path.exists(temp_path):
        os.remove(temp_path)
    raise

# Verify non-target field hashes
print("\nVerifying non-target field hashes...")
with open('sync.json', 'r', encoding='utf-8') as f:
    verify_data = json.load(f)

verification_passed = True
for key, val in verify_data.items():
    if key in ('tpl', 'note') or not isinstance(val, dict):
        continue
    if key == '2026-10-22':
        continue
    for field in non_target_fields:
        if field in val:
            content = json.dumps(val[field], ensure_ascii=False, sort_keys=True)
            h = hashlib.sha256(content.encode('utf-8')).hexdigest()
            if field in baseline_hashes:
                if h not in baseline_hashes[field]:
                    print(f"VERIFICATION FAILED: {key}.{field} hash mismatch!")
                    verification_passed = False

if verification_passed:
    print("✓ All non-target field hashes verified successfully")
else:
    print("✗ Verification failed - some fields were modified unexpectedly")

# Verify 2026-10-22 entry exists and has correct topic
if '2026-10-22' in verify_data:
    bs = verify_data['2026-10-22'].get('bsToday', {})
    topic = bs.get('topic', '')
    print(f"\n✓ 2026-10-22 entry created successfully")
    print(f"  Topic: {topic}")
    print(f"  KeyPoints: {len(bs.get('keyPoints', []))}")
    print(f"  Rounds: {len(bs.get('rounds', []))}")
    print(f"  Sparks: {len(bs.get('sparks', []))}")
    print(f"  QA pairs: {len(bs.get('qa', []))}")
else:
    print("\n✗ 2026-10-22 entry not found in verify_data")

print("\nScript completed.")
