# A股盘面信号监控系统

基于「看信号，做决策」框架的 A 股盘面信号自动采集与评估系统。每个交易日定时采集 10 个维度的盘面数据，生成量化决策报告。

> **完整技能文档**: [SKILL.md](SKILL.md) — 包含信号体系、使用方法、自定义修改、踩坑记录等。

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

## 项目结构

```
market-signal-monitor/
├── SKILL.md                          # 技能定义（完整文档）
├── scripts/
│   └── market-signal-monitor.py      # 主程序
├── references/
│   ├── signal-criteria.md            # 信号评估标准原文
│   └── common-pitfalls.md            # 常见踩坑记录
├── README.md                         # 本文件
├── LICENSE                           # MIT
└── .gitignore
```

## 作为 Hermes Skill 使用

```bash
# 方式 1：符号链接
ln -s /path/to/market-signal-monitor ~/.hermes/skills/market-signal-monitor

# 方式 2：复制
cp -r /path/to/market-signal-monitor ~/.hermes/skills/
```

## License

MIT
