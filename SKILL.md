---
name: market-signal-monitor
description: |
  A股盘面信号监控系统 — 基于「看信号，做决策」框架，定时采集盘面数据并评估10个信号维度。
  涵盖盘面结构（指数共振/权重/题材/涨跌）、资金信号（北向/成交量/主动性买盘/融资余额）、IF股指期货。
  支持终端输出和飞书 Webhook 推送。所有数据源均为公开 API，无需 API Key。
version: 1.0.0
author: Richard Wild
license: MIT
---

# A股盘面信号监控系统

## Overview

基于「看信号，做决策」思维导图，在交易日定时采集盘面数据，评估 10 个信号维度，生成辅助决策报告。

数据源全部为公开 HTTP API（腾讯财经、东财 push2、同花顺 hsgtApi、东财 datacenter），无需任何 API Key。

## When to Use

- 用户要求分析 A 股盘面信号 / 盘面情绪 / 市场温度
- 用户要求定时监控盘面并推送报告
- 用户提到"看信号做决策"、"盘面信号"、"市场信号监控"
- 用户想了解当前大盘共振情况、资金流向、涨跌家数

**Don't use for:**

- 个股分析
- 股票复盘视频分析
- ETF 调仓策略

## 快速开始

### 环境要求

- Python 3.11+
- 依赖：`requests`

```bash
pip install requests
```

### 运行

```bash
# 基本运行 — 输出到终端
python3 scripts/market-signal-monitor.py

# 推送到飞书 Webhook
FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN" \
  python3 scripts/market-signal-monitor.py
```

### 定时任务（crontab）

```crontab
# 交易日 11:10 / 14:15 / 15:08
10 11 * * 1-5 FEISHU_WEBHOOK_URL="..." /usr/bin/python3 /path/to/scripts/market-signal-monitor.py
15 14 * * 1-5 FEISHU_WEBHOOK_URL="..." /usr/bin/python3 /path/to/scripts/market-signal-monitor.py
8 15 * * 1-5 FEISHU_WEBHOOK_URL="..." /usr/bin/python3 /path/to/scripts/market-signal-monitor.py
```

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

## 自定义修改

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

## 报告输出格式

```
📊 盘面信号监控报告
⏰ {时间}

📈 指数行情
- 上证指数: {价格} ({涨跌幅}%)
- 沪深300: ...
- 创业板指: ...
- 中证500: ...
- 中证2000: ...
- 涨跌家数: ↑{涨} ↓{跌}
- 涨停: {N}家 | 跌停: {N}家
- 全市场成交: {N}亿
- 北向资金: 沪股通{N}亿 深股通{N}亿 合计{N}亿

🔔 信号评估
一、盘面结构信号
- {等级} {指标}: {说明}
二、资金信号
- {等级} {指标}: {说明}
三、IF沪深300股指
- {等级} {指标}: {说明}

📊 综合评分
- 🔴突破/良好: {N}个
- 🟡及格/正常: {N}个
- ⚪不及格/无数据: {N}个
{综合判断}
```
