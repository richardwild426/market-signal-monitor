# A股盘面信号监控系统

基于「看信号，做决策」框架的 A 股盘面信号自动采集与评估系统。每个交易日定时采集 10 个维度的盘面数据，生成量化决策报告。

数据采集层使用 [a-stock-data](https://github.com/simonlin1212/a-stock-data)。

## 快速开始

```bash
# 安装依赖
pip install requests

# 运行
python3 scripts/market-signal-monitor.py

# 推送到飞书
FEISHU_WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN" \
  python3 scripts/market-signal-monitor.py
```

## 信号体系概览

**盘面结构信号（5个）**：指数共振、权重与小票共振、创业板权重、题材情况、涨跌情况

**资金信号（4个）**：北向资金、成交量、主动性买盘、融资余额

**IF沪深300股指（1个）**：持仓、异动、基差

完整文档见 [SKILL.md](SKILL.md)

## 项目结构

```
market-signal-monitor/
├── SKILL.md                          # 技能定义（完整文档）
├── lib/
│   ├── __init__.py
│   └── data_source.py                # 数据采集层（提取自 a-stock-data）
├── scripts/
│   └── market-signal-monitor.py      # 信号评估 + 报告生成
├── README.md                         # 本文件
├── LICENSE                           # MIT
└── .gitignore
```

## 数据源

所有数据采集函数提取自 [a-stock-data V3.2.2](https://github.com/simonlin1212/a-stock-data)：

| 数据 | 函数 | 来源 |
|------|------|------|
| 指数行情 | `tencent_quote()` | 腾讯财经 |
| 涨跌家数 | `get_market_breadth()` | 东财 push2 |
| 北向资金 | `hsgt_realtime()` | 同花顺 hsgtApi |
| 主力资金流 | `eastmoney_fund_flow_minute()` | 东财 push2 |
| 融资余额 | `eastmoney_datacenter()` | 东财 datacenter |
| 题材归因 | `ths_hot_reason()` | 同花顺热点 |
| IF 期货 | `get_if_futures()` | 东财 push2 |

## License

MIT
