#!/usr/bin/env python3
"""
A股盘面信号监控系统
基于「看信号，做决策」思维导图，每个交易日定时采集并评估盘面信号。

数据源: a-stock-data (https://github.com/simonlin1212/a-stock-data)
- 腾讯财经: 指数行情
- 同花顺 hsgtApi: 北向资金
- 东财 push2: 涨跌家数、资金流向、IF期货
- 东财 datacenter: 融资融券
- 同花顺热点: 题材归因

信号体系:
1. 盘面结构信号: 共振、权重、题材、涨跌
2. 资金信号: 北向、成交量、主动性买盘、融资余额
3. IF沪深300股指: 持仓、异动、基差
"""

import json
import os
import sys
from collections import Counter
from datetime import datetime

# ── 数据层：全部来自 a-stock-data ────────────────────────────────────
from lib.data_source import (
    tencent_quote,
    ths_hot_reason,
    hsgt_realtime,
    eastmoney_fund_flow_minute,
    get_market_breadth,
    get_total_volume,
    get_margin_balance,
    get_if_futures,
)


# ═══════════════════════════════════════════════════════════════════
# 信号评估层
# ═══════════════════════════════════════════════════════════════════

def evaluate_index_resonance(quotes: dict) -> dict:
    """指数共振评估"""
    sh = quotes.get("000001", {}).get("change_pct", 0)
    hs300 = quotes.get("000300", {}).get("change_pct", 0)
    cyb = quotes.get("399006", {}).get("change_pct", 0)

    all_up = sh > 0 and hs300 > 0 and cyb > 0
    all_up_2pct = sh >= 2 and hs300 >= 2 and cyb >= 2

    if all_up_2pct:
        level = "🔴 突破"
        note = f"三大指数均涨≥2%，强势突破！上证{sh:.2f}% 沪深300{hs300:.2f}% 创业板{cyb:.2f}%"
    elif all_up:
        level = "🟡 及格"
        note = f"三大指数同步上涨。上证{sh:.2f}% 沪深300{hs300:.2f}% 创业板{cyb:.2f}%"
    else:
        level = "⚪ 不及格"
        note = f"指数分化。上证{sh:.2f}% 沪深300{hs300:.2f}% 创业板{cyb:.2f}%"

    return {"指标": "指数共振", "等级": level, "说明": note}


def evaluate_cap_resonance() -> dict:
    """权重与小票共振评估 — 沪深300 vs 中证2000"""
    quotes = tencent_quote(["000300", "399303"])
    hs300_pct = quotes.get("000300", {}).get("change_pct", 0)
    zz2000_pct = quotes.get("399303", {}).get("change_pct", 0)
    spread = abs(hs300_pct - zz2000_pct)

    if spread <= 1.5:
        level = "🟡 正常"
        note = f"剪刀差{spread:.2f}%，权重与小票共振正常。沪深300:{hs300_pct:+.2f}% 中证2000:{zz2000_pct:+.2f}%"
    else:
        level = "⚪ 分化"
        note = f"剪刀差{spread:.2f}%>1.5%，权重与小票分化。沪深300:{hs300_pct:+.2f}% 中证2000:{zz2000_pct:+.2f}%"

    return {"指标": "权重与小票共振", "等级": level, "说明": note}


def evaluate_weight_stocks() -> dict:
    """权重股评估 — 创业板6大权重"""
    weight_codes = {
        "300750": "宁德时代",
        "300274": "阳光电源",
        "300059": "东方财富",
        "300760": "迈瑞医疗",
        "300124": "汇川技术",
        "300308": "中际旭创",
    }
    quotes = tencent_quote(list(weight_codes.keys()))
    up_count = 0
    details = []
    for code, name in weight_codes.items():
        q = quotes.get(code, {})
        pct = q.get("change_pct", 0)
        if pct > 0:
            up_count += 1
        details.append(f"{name}:{pct:+.2f}%")

    if up_count == 6:
        level = "🔴 良好"
        note = f"创业板6大权重全部上涨！{' '.join(details)}"
    elif up_count >= 4:
        level = "🟡 及格"
        note = f"创业板6大权重{up_count}只上涨。{' '.join(details)}"
    else:
        level = "⚪ 不及格"
        note = f"创业板6大权重仅{up_count}只上涨。{' '.join(details)}"

    return {"指标": "创业板权重", "等级": level, "说明": note}


def evaluate_themes() -> dict:
    """题材情况评估 — 同花顺热点 reason tags"""
    hot_stocks = ths_hot_reason()
    if not hot_stocks:
        return {"指标": "题材情况", "等级": "⚪ 无数据", "说明": "无法获取题材数据"}

    all_tags = []
    for s in hot_stocks[:30]:
        reason = s.get("reason", "")
        if reason:
            tags = [t.strip() for t in str(reason).split("+") if t.strip()]
            all_tags.extend(tags)

    tag_counter = Counter(all_tags)
    top_tags = tag_counter.most_common(5)
    has_main_theme = len(top_tags) > 0 and top_tags[0][1] >= 3

    if has_main_theme:
        theme_str = " ".join([f"#{t[0]}({t[1]}只)" for t in top_tags])
        level = "🔴 有主线"
        note = f"有明确主线题材。{theme_str}"
    else:
        level = "⚪ 无主线"
        note = f"题材分散，无明确主线。热门: {', '.join([t[0] for t in top_tags[:3]]) if top_tags else '无'}"

    return {"指标": "题材情况", "等级": level, "说明": note}


def evaluate_breadth(breadth: dict) -> dict:
    """涨跌情况评估"""
    limit_up = breadth.get("limit_up", 0)
    up = breadth.get("up", 0)
    down = breadth.get("down", 0)

    if limit_up >= 80:
        level = "🔴 突破"
        note = f"涨停{limit_up}家≥80，市场极度活跃！上涨{up}家 下跌{down}家"
    elif limit_up >= 60:
        level = "🟡 及格"
        note = f"涨停{limit_up}家≥60，市场活跃。上涨{up}家 下跌{down}家"
    else:
        level = "⚪ 不及格"
        note = f"涨停{limit_up}家<60，市场偏冷。上涨{up}家 下跌{down}家"

    return {"指标": "涨跌情况", "等级": level, "说明": note}


def evaluate_northbound(nb: dict) -> dict:
    """北向资金评估"""
    total = nb.get("total_yi", 0)

    if total >= 100:
        level = "🔴 突破"
        note = f"北向净买入{total:.1f}亿≥100亿，外资大幅流入！"
    elif total >= 50:
        level = "🟡 及格"
        note = f"北向净买入{total:.1f}亿≥50亿，外资持续流入。"
    elif total > 0:
        level = "⚪ 一般"
        note = f"北向净买入{total:.1f}亿<50亿，流入力度一般。"
    else:
        level = "⚪ 不及格"
        note = f"北向净卖出{abs(total):.1f}亿，外资流出。"

    return {"指标": "北向资金", "等级": level, "说明": note}


def evaluate_volume(vol_yi: float) -> dict:
    """成交量评估"""
    if vol_yi >= 12000:
        level = "🔴 突破"
        note = f"成交额{vol_yi:.0f}亿≥1.2万亿，放量突破！"
    elif vol_yi >= 10000:
        level = "🟡 及格"
        note = f"成交额{vol_yi:.0f}亿≥万亿，量能达标。"
    else:
        level = "⚪ 不及格"
        note = f"成交额{vol_yi:.0f}亿<万亿，量能不足。"

    return {"指标": "成交量", "等级": level, "说明": note}


def evaluate_active_buying(flow: list[dict]) -> dict:
    """主动性买盘评估 — 沪深300主力净流入"""
    if not flow:
        return {"指标": "主动性买盘", "等级": "⚪ 无数据", "说明": "资金流数据暂不可用"}

    last = flow[-1]
    main_net = last.get("main_net", 0)
    main_net_yi = main_net / 1e8

    if main_net_yi >= 0.02 * 10000:
        level = "🔴 突破"
        note = f"沪深300主力净流入{main_net_yi:.2f}亿，主动性买盘强劲！"
    elif main_net > 0:
        level = "🟡 及格"
        note = f"沪深300主力净流入{main_net_yi:.2f}亿，买盘为正。"
    else:
        level = "⚪ 不及格"
        note = f"沪深300主力净流出{abs(main_net_yi):.2f}亿，卖压较重。"

    return {"指标": "主动性买盘", "等级": level, "说明": note}


def evaluate_margin(margin: dict) -> dict:
    """融资余额评估"""
    rz = margin.get("rz_yi", 0)
    if rz > 0:
        level = "🟡 良好"
        note = f"融资余额{rz:.0f}亿，杠杆资金活跃。"
    else:
        level = "⚪ 无数据"
        note = "融资余额数据暂不可用。"
    return {"指标": "融资余额", "等级": level, "说明": note}


def evaluate_if_futures() -> dict:
    """IF沪深300股指期货评估"""
    d = get_if_futures()
    price = d.get("price", 0)
    change = d.get("change", 0)

    if price:
        return {
            "指标": "IF沪深300股指",
            "等级": "🟡 参考",
            "说明": f"IF主力合约 {price}点 涨跌{change:.2f}%（持仓/基差需盘后数据）",
        }
    return {"指标": "IF沪深300股指", "等级": "⚪ 无数据", "说明": "IF期货数据暂不可用"}


# ═══════════════════════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════════════════════

def generate_report() -> str:
    """生成完整的盘面信号报告"""
    now = datetime.now()
    report_time = now.strftime("%Y-%m-%d %H:%M")

    # ── 采集数据（全部走 a-stock-data）──────────────────────────
    print(f"[{report_time}] 开始采集盘面数据...", file=sys.stderr)

    index_codes = ["000001", "000300", "399006", "000905", "399303"]
    index_quotes = tencent_quote(index_codes)                   # 腾讯财经
    breadth = get_market_breadth()                               # 东财 push2
    northbound = hsgt_realtime()                                 # 同花顺 hsgtApi
    volume_yi = get_total_volume()                               # 腾讯财经
    fund_flow = eastmoney_fund_flow_minute("1.000300")           # 东财 push2
    margin = get_margin_balance()                                # 东财 datacenter

    print(f"[{report_time}] 数据采集完成，开始评估...", file=sys.stderr)

    # ── 评估信号 ──────────────────────────────────────────────
    signals = []

    # 1. 盘面结构信号
    signals.append(evaluate_index_resonance(index_quotes))
    signals.append(evaluate_cap_resonance())
    signals.append(evaluate_weight_stocks())
    signals.append(evaluate_themes())
    signals.append(evaluate_breadth(breadth))

    # 2. 资金信号
    signals.append(evaluate_northbound(northbound))
    signals.append(evaluate_volume(volume_yi))
    signals.append(evaluate_active_buying(fund_flow))
    signals.append(evaluate_margin(margin))

    # 3. IF沪深300
    signals.append(evaluate_if_futures())

    # ── 生成报告 ──────────────────────────────────────────────
    lines = []
    lines.append("📊 **盘面信号监控报告**")
    lines.append(f"⏰ {report_time}")
    lines.append("")

    sh = index_quotes.get("000001", {})
    hs300 = index_quotes.get("000300", {})
    cyb = index_quotes.get("399006", {})
    zz500 = index_quotes.get("000905", {})
    zz2000 = index_quotes.get("399303", {})

    lines.append("**📈 指数行情**")
    lines.append(f"- 上证指数: {sh.get('price', 0):.2f} ({sh.get('change_pct', 0):+.2f}%)")
    lines.append(f"- 沪深300: {hs300.get('price', 0):.2f} ({hs300.get('change_pct', 0):+.2f}%)")
    lines.append(f"- 创业板指: {cyb.get('price', 0):.2f} ({cyb.get('change_pct', 0):+.2f}%)")
    lines.append(f"- 中证500: {zz500.get('price', 0):.2f} ({zz500.get('change_pct', 0):+.2f}%)")
    lines.append(f"- 中证2000: {zz2000.get('price', 0):.2f} ({zz2000.get('change_pct', 0):+.2f}%)")
    lines.append(f"- 涨跌家数: ↑{breadth.get('up', 0)} ↓{breadth.get('down', 0)}")
    lines.append(f"- 涨停: {breadth.get('limit_up', 0)}家 | 跌停: {breadth.get('limit_down', 0)}家")
    lines.append(f"- 全市场成交: {volume_yi:.0f}亿")
    lines.append(f"- 北向资金: 沪股通{northbound.get('hgt_yi', 0):.1f}亿 深股通{northbound.get('sgt_yi', 0):.1f}亿 合计{northbound.get('total_yi', 0):.1f}亿")
    lines.append("")

    lines.append("**🔔 信号评估**")
    lines.append("")

    sections = [
        ("一、盘面结构信号", signals[:5]),
        ("二、资金信号", signals[5:9]),
        ("三、IF沪深300股指", signals[9:]),
    ]

    for section_name, section_signals in sections:
        lines.append(f"**{section_name}**")
        for s in section_signals:
            lines.append(f"- {s['等级']} **{s['指标']}**: {s['说明']}")
        lines.append("")

    red_count = sum(1 for s in signals if "🔴" in s["等级"])
    yellow_count = sum(1 for s in signals if "🟡" in s["等级"])
    white_count = sum(1 for s in signals if "⚪" in s["等级"])

    lines.append("**📊 综合评分**")
    lines.append(f"- 🔴突破/良好: {red_count}个")
    lines.append(f"- 🟡及格/正常: {yellow_count}个")
    lines.append(f"- ⚪不及格/无数据: {white_count}个")
    lines.append("")

    if red_count >= 5:
        lines.append("**🟢 综合判断: 强势 — 多数信号突破，可积极参与**")
    elif red_count + yellow_count >= 7:
        lines.append("**🟡 综合判断: 偏强 — 多数信号及格，可适度参与**")
    elif red_count + yellow_count >= 4:
        lines.append("**⚪ 综合判断: 震荡 — 信号分化，控制仓位**")
    else:
        lines.append("**🔴 综合判断: 偏弱 — 多数信号不及格，谨慎观望**")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    report = generate_report()
    print(report)

    # 飞书 Webhook 推送（可选）
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if webhook_url:
        try:
            payload = json.dumps({
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": "📊 盘面信号监控报告"},
                        "template": "blue"
                    },
                    "elements": [
                        {"tag": "markdown", "content": report}
                    ]
                }
            }, ensure_ascii=False).encode("utf-8")
            import urllib.request
            req = urllib.request.Request(
                webhook_url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                print("\n✅ 飞书 Webhook 推送成功")
            else:
                print(f"\n⚠️ 飞书 Webhook 响应: {result}")
        except Exception as e:
            print(f"\n❌ 飞书 Webhook 推送失败: {e}")
