# A股盘面信号监控系统

基于「看信号，做决策」框架的 A 股盘面信号自动采集与评估系统。每个交易日定时采集 10 个维度的盘面数据，生成量化决策报告。

## 信号体系

### 一、盘面结构信号（5 个）

| 信号 | 数据源 | 及格标准 | 突破标准 |
|------|--------|----------|----------|
| 指数共振 | 腾讯财经 | 三大指数同步上涨 | 均涨≥2% |
| 权重与小票共振 | 腾讯财经 | 沪深300与中证2000剪刀差≤1.5% | - |
| 创业板权重 | 腾讯财经 | 宁德/阳光/东财/迈瑞/汇川/中际综合上涨 | - |
| 题材情况 | 同花顺热点 | 有主线题材（TOP1标签≥3只） | - |
| 涨跌情况 | 东财 push2 | 涨停≥60家 | 涨停≥80家 |

### 二、资金信号（4 个）

| 信号 | 数据源 | 及格标准 | 突破标准 |
|------|--------|----------|----------|
| 北向资金 | 同花顺 hsgtApi | 净买入≥50亿 | 净买入≥100亿 |
| 成交量 | 腾讯财经 | ≥万亿 | ≥1.2万亿 |
| 主动性买盘 | 东财 push2 | 沪深300主力净流入为正 | - |
| 融资余额 | 东财 datacenter | 持续上升 | - |

### 三、IF 沪深300 股指（1 个）

持仓情况、盘中异动、基差情况（需盘后数据）

## 快速开始

### 环境要求

- Python 3.11+（推荐，3.9 的 LibreSSL 可能导致部分 HTTPS 站点 SSL 握手失败）
- 依赖：`requests`

### 安装

```bash
pip install requests
```

### 运行

```bash
# 基本运行（输出到终端）
python3 scripts/market-signal-monitor.py

# 推送到飞书 Webhook
FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN" \
  python3 scripts/market-signal-monitor.py
```

### 定时任务

推荐使用 crontab 在交易日定时运行：

```crontab
# 交易日 11:10 / 14:15 / 15:08 各跑一次
10 11 * * 1-5 FEISHU_WEBHOOK_URL="..." /usr/bin/python3 /path/to/scripts/market-signal-monitor.py
15 14 * * 1-5 FEISHU_WEBHOOK_URL="..." /usr/bin/python3 /path/to/scripts/market-signal-monitor.py
8 15 * * 1-5 FEISHU_WEBHOOK_URL="..." /usr/bin/python3 /path/to/scripts/market-signal-monitor.py
```

## 综合评分逻辑

```
🔴突破/良好 ≥5个 → 强势：可积极参与
🔴+🟡 ≥7个       → 偏强：可适度参与
🔴+🟡 ≥4个       → 震荡：控制仓位
其他             → 偏弱：谨慎观望
```

## 数据源

| 数据 | 来源 | 封 IP 风险 |
|------|------|-----------|
| 指数行情 | 腾讯财经 `qt.gtimg.cn` | 极低 |
| 涨跌家数/涨跌停 | 东财 `push2.eastmoney.com` | 低 |
| 北向资金 | 同花顺 `data.hexin.cn` | 极低 |
| 主力资金流 | 东财 `push2.eastmoney.com` | 低 |
| 融资余额 | 东财 `datacenter-web.eastmoney.com` | 低 |
| 题材归因 | 同花顺 `zx.10jqka.com.cn` | 极低 |
| 创业板权重 | 腾讯财经 | 极低 |

所有数据源均为公开 HTTP API，无需 API Key。

## 自定义

### 调整信号阈值

编辑 `scripts/market-signal-monitor.py` 中的评估函数：

```python
# 示例：修改涨停及格标准从 60 改为 50
def evaluate_breadth(breadth: dict) -> dict:
    limit_up = breadth.get("limit_up", 0)
    if limit_up >= 80:
        level = "🔴 突破"
    elif limit_up >= 50:  # 原来是 60
        level = "🟡 及格"
    ...
```

### 添加新信号

1. 新增数据采集函数
2. 新增信号评估函数
3. 在 `generate_report()` 中调用并加入信号列表

## 项目结构

```
market-signal-monitor/
├── scripts/
│   └── market-signal-monitor.py   # 主程序
├── docs/
│   ├── signal-criteria.md         # 信号评估标准原文
│   └── common-pitfalls.md         # 常见踩坑记录
├── README.md
├── LICENSE
└── .gitignore
```

## 踩坑记录

详见 [docs/common-pitfalls.md](docs/common-pitfalls.md)

## License

MIT
