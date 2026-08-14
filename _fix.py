import json

P='sync.json'
d=json.load(open(P,encoding='utf-8'))
TODAY='2026-08-14'
PREV='2026-08-13'
e=d[TODAY]; prev=d[PREV]

# 1) 今日任务：复制最近一天 tpl / blockedTitles / manualTasks（不复制 done/bonus/kb/stock/tb/bs）
if not e.get('tpl'):
    e['tpl']=prev['tpl']            # 首行已是 T-101 渠道消耗巡检
if 'blockedTitles' not in e:
    e['blockedTitles']=list(prev.get('blockedTitles') or [])
if 'manualTasks' not in e:
    e['manualTasks']=list(prev.get('manualTasks') or [])

# 校验 manualTasks(08-13 为空) 全部出现在 tpl 工作线末尾
for mt in (prev.get('manualTasks') or []):
    tid=mt.get('id') if isinstance(mt,dict) else str(mt)
    assert tid in e['tpl'], f'manualTask {tid} 丢失'

# 2) 股市：把已有 08-14 内容重塑为页面 schema（us/kr/a 均含 hot）
e['stockToday']={
 "date": TODAY,
 "us": {
  "label": "🇺🇸 美股 (8-13收盘/8-14盘中)",
  "indices": [
   {"name":"道琼斯","val":"53,812.60","chg":"+0.08%","up":True},
   {"name":"纳斯达克","val":"26,701.35","chg":"+0.42%","up":True},
   {"name":"标普500","val":"7,769.80","chg":"+0.27%","up":True}
  ],
  "hot": [
   "三大指数小幅收涨，纳指再领先，资金仍聚焦AI算力与科技权重",
   "市场对美联储9月降息预期维持高位，利率敏感的成长股情绪偏暖",
   "涨幅普遍收窄、量能未放大，属高位窄幅震荡而非趋势加速",
   "结论：延续结构性行情，指数层面追高性价比低，看个股业绩兑现"
  ]
 },
 "kr": {
  "label": "🇰🇷 韩股 (8-14)",
  "indices": [
   {"name":"KOSPI","val":"6,742.10","chg":"-1.05%","up":False},
   {"name":"KOSDAQ","val":"858.90","chg":"-0.29%","up":False}
  ],
  "hot": [
   "KOSPI在前一日大涨3.56%后回落约1%，属获利了结式技术性回调",
   "半导体权重股高位震荡，追高风险仍高于跟随风险",
   "韩股半导体链可作为A股设备/材料板块的先行观察窗口"
  ]
 },
 "a": {
  "label": "🇨🇳 A股 (8-14收盘)",
  "hot": [
   {"name":"科技(TMT)","note":"AI应用与算力硬件分化，偏好从主题炒作转向业绩兑现；关注capex增速与毛利率匹配，国内大模型降价利好应用层但竞争加剧"},
   {"name":"消费","note":"暑期文旅『旺丁不旺财』，7月社零略低预期、可选品类放缓；政策以以旧换新与服务补贴为主，短期难有强刺激"},
   {"name":"医药","note":"创新药出海授权延续高景气、首付款超预期；CXO与器械估值仍在历史低位，院内回款周期压制板块，GLP-1/ADC/双抗受关注"},
   {"name":"新能源","note":"光伏硅料硅片价格企稳、部分企业减产去库，产能出清仍需时间；储能海外订单高增但准入门槛上升，电动车价格战向中游传导"},
   {"name":"金融","note":"银行净息差承压、存款挂牌利率跟进下调缓解；险企中报NBV回暖、银保价值率提升成亮点；券商成交低迷缺催化"}
  ]
 },
 "notes": "仅供参考·非投资建议。今日观察：外盘小幅收涨、A股冲高回落看能否守住关键支撑；韩股回调提示别把单日波动当趋势，重点看成交额能否重回万亿与业绩兑现节奏。"
}

# 3) 淘宝创新：仅重写 crossover（原3条命中 体验课/私教/健身房 会被前端分类器挪进 fitness→crossover变空）
tb=e['tbToday']
tb['crossover']=[
 {"type":"crossover",
  "title":"酒店收益管理(动态定价) × 闪购GAB预算：按实时转化率调价，取代全天一口价折扣（思路）",
  "summary":"酒店按入住率实时调房价的收益管理思路，可迁移到闪购GAB的预算与出价节奏——用转化信号动态分配有限预算，而非全天固定折扣。",
  "points":[
   "核心是『按需定价』：高转化时段加价争量，低效时段收量，最大化有限预算的单位产出",
   "落到GAB：把库存与预算按分时转化率切片，peak段追量、平段控价，避免均摊浪费",
   "可先小流量A/B验证分时出价曲线，跑通再放大到主力渠道"
  ]},
 {"type":"crossover",
  "title":"订阅制SaaS的流失预警模型 × 召回人群分层：用『活跃频次下滑斜率』提前触达（思路）",
  "summary":"SaaS靠使用频次下滑提前预测流失并干预，这套预警逻辑可迁移到用户召回——别等用户彻底沉默才动作。",
  "points":[
   "关键指标不是『是否流失』而是『活跃斜率』：下滑速率快的人优先触达",
   "落到召回：按最近访问间隔与IPV衰减做分层，衰减快的给强钩子、慢的给轻提醒",
   "把预算从『无差别召回』改成『按流失概率加权』，同预算召回效率更高"
  ]},
 {"type":"crossover",
  "title":"航司里程『保级机制』 × 88VIP复购节奏：用『差一点掉级』的损失厌恶驱动高频回访（思路）",
  "summary":"航空会员靠『差一点就掉级』的紧迫感驱动持续消费，这种损失厌恶设计可迁移到会员复购运营，提升回访频次。",
  "points":[
   "机制核心：把长期目标切成可视化的『保级进度条』，临界点前推动一次行为",
   "落到运营：给临界会员发『再X单保级/升级』提示，比无差别发券更精准",
   "配合分时唤端，把提醒落在用户高活跃时段的第一屏，提高触达转化"
  ]}
]

# 自检：crossover 不得命中禁用词
BAN=['出个汗','Sughan','私教','教练','健身房','体测','体态','增肌','减脂','训练营','飞盘','瑜伽','体验课','会员卡','涨粉']
for x in tb['crossover']:
    blob=(x.get('title','')+x.get('summary','')+''.join(x.get('points',[])))
    hit=[w for w in BAN if w in blob]
    assert not hit, f'crossover 命中禁用词 {hit}: {x["title"]}'

json.dump(d,open(P,'w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('OK. 08-14 fields:', list(e.keys()))
print('tpl first line:', e['tpl'].splitlines()[0])
print('crossover count:', len(tb['crossover']))
