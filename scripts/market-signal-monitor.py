#!/usr/bin/env python3
"""
A股盘面信号监控系统
基于「看信号，做决策」思维导图，每个交易日定时采集并评估盘面信号。

数据源:
- 腾讯财经: 指数行情、涨跌家数、涨跌停
- 同花顺 hsgtApi: 北向资金分钟流向
- 东财 push2: 个股资金流、行业板块
- 同花顺热点: 题材归因
- 东财 datacenter: 融资融券

信号体系:
1. 盘面结构信号: 共振、权重、题材、涨跌
2. 资金信号: 北向、成交量、主动性买盘、融资余额
3. IF沪深300股指: 持仓、异动、基差
"""

import json
import os
import time
import urllib.request
import requests
import sys
from datetime import datetime, date

# ── 常量 ──────────────────────────────────────────────────────────────
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
UA_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"

# ── 东财防封 helper ─────────────────────────────────────────────────
import random
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]

def em_get(url, params=None, headers=None, timeout=15):
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout)
    finally:
        _em_last_call[0] = time.time()


# ═══════════════════════════════════════════════════════════════════
# 数据采集层
# ═══════════════════════════════════════════════════════════════════

def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """腾讯财经批量行情"""
    # 指数代码需要特殊前缀
    INDEX_MAP = {
        "000001": "sh000001",  # 上证指数
        "000300": "sh000300",  # 沪深300
        "000905": "sh000905",  # 中证500
        "399001": "sz399001",  # 深证成指
        "399006": "sz399006",  # 创业板指
        "399303": "sz399303",  # 国证2000
    }
    prefixed = []
    for c in codes:
        if c in INDEX_MAP:
            prefixed.append(INDEX_MAP[c])
        elif c.startswith(("6", "9")):
            prefixed.append(f"sh{c}")
        elif c.startswith("8"):
            prefixed.append(f"bj{c}")
        else:
            prefixed.append(f"sz{c}")
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    for _attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            data = resp.read().decode("gbk")
            break
        except Exception:
            if _attempt == 2:
                raise
            import time; time.sleep(2)
    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        # 去掉市场前缀和可能的=号
        code = key.replace("=", "")
        if code.startswith(("sh", "sz", "bj")):
            code = code[2:]
        result[code] = {
            "name": vals[1],
            "price": float(vals[3]) if vals[3] else 0,
            "last_close": float(vals[4]) if vals[4] else 0,
            "open": float(vals[5]) if vals[5] else 0,
            "change_pct": float(vals[32]) if vals[32] else 0,
            "high": float(vals[33]) if vals[33] else 0,
            "low": float(vals[34]) if vals[34] else 0,
            "amount_wan": float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm": float(vals[39]) if vals[39] else 0,
            "mcap_yi": float(vals[44]) if vals[44] else 0,
            "pb": float(vals[46]) if vals[46] else 0,
            "vol_ratio": float(vals[49]) if vals[49] else 0,
        }
    return result


def get_market_overview() -> dict:
    """全市场涨跌概况 — 通过东财 push2 获取涨跌家数、涨跌停"""
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f104,f105,f106",
        "secids": "1.000001,0.399001,0.399006,1.000300,1.000905,0.399303",
    }
    headers = {"User-Agent": UA}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        d = r.json()
        items = d.get("data", {}).get("diff", [])
        up = items[0].get("f104", 0) if items else 0
        down = items[0].get("f105", 0) if items else 0
        limit_up = items[0].get("f106", 0) if items else 0
        return {"up": up, "down": down, "limit_up": limit_up}
    except Exception:
        return {"up": 0, "down": 0, "limit_up": 0}


def get_market_breadth() -> dict:
    """涨跌家数、涨跌停 — 通过东财全市场统计"""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    # 涨停数
    params_up = {
        "pn": "1", "pz": "1", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
        "fields": "f1,f2,f3",
        "fid": "f3",
        "f0": "0",  # 涨幅>0
    }
    # 使用更简单的方式: 东财涨跌停统计
    url_stat = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params_stat = {
        "fltt": "2", "invt": "2",
        "fields": "f104,f105,f106,f107",
        "secids": "1.000001",
    }
    headers = {"User-Agent": UA}
    try:
        r = em_get(url_stat, params=params_stat, headers=headers, timeout=10)
        d = r.json()
        items = d.get("data", {}).get("diff", [])
        if items:
            return {
                "up": items[0].get("f104", 0),
                "down": items[0].get("f105", 0),
                "limit_up": items[0].get("f106", 0),
                "limit_down": items[0].get("f107", 0),
            }
    except Exception:
        pass
    return {"up": 0, "down": 0, "limit_up": 0, "limit_down": 0}


def get_northbound_flow() -> dict:
    """北向资金实时分钟流向"""
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    headers = {"User-Agent": UA_WIN, "Host": "data.hexin.cn", "Referer": "https://data.hexin.cn/"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])
        # 取最后一个非空值
        hgt_val = hgt[-1] if hgt else 0
        sgt_val = sgt[-1] if sgt else 0
        total = (hgt_val or 0) + (sgt_val or 0)
        return {
            "hgt_yi": round(hgt_val or 0, 2),
            "sgt_yi": round(sgt_val or 0, 2),
            "total_yi": round(total, 2),
            "points": len(times),
        }
    except Exception as e:
        return {"hgt_yi": 0, "sgt_yi": 0, "total_yi": 0, "points": 0, "error": str(e)}


def get_index_fund_flow() -> dict:
    """主要指数资金流（主动性买盘 proxy）"""
    # 沪深300主力净流入
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": "1.000300", "klt": 1,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        d = r.json()
        klines = d.get("data", {}).get("klines", [])
        if klines:
            last = klines[-1].split(",")
            main_net = float(last[1]) if len(last) > 1 else 0
            return {"main_net": main_net, "points": len(klines)}
    except Exception:
        pass
    return {"main_net": 0, "points": 0}


def get_total_volume() -> float:
    """全市场成交额（亿元）— 从主要指数成交额估算"""
    # 上证+深证成交额
    quotes = tencent_quote(["000001", "399001"])
    sh_amount = quotes.get("000001", {}).get("amount_wan", 0)
    sz_amount = quotes.get("399001", {}).get("amount_wan", 0)
    total_yi = (sh_amount + sz_amount) / 10000  # 万→亿
    return round(total_yi, 0)


def get_margin_balance() -> dict:
    """融资融券余额（最新数据）"""
    from datetime import timedelta
    today = date.today().strftime("%Y-%m-%d")
    week_ago = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    data = eastmoney_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        columns="ALL",
        filter_str=f"(DATE>='{week_ago}')(DATE<='{today}')",
        page_size=5,
        sort_columns="DATE", sort_types="-1",
    )
    if data:
        total_rz = sum(row.get("RZYE", 0) or 0 for row in data)
        total_rq = sum(row.get("RQYE", 0) or 0 for row in data)
        return {
            "rz_yi": round(total_rz / 1e8, 2),
            "rq_yi": round(total_rq / 1e8, 2),
            "total_yi": round((total_rz + total_rq) / 1e8, 2),
        }
    return {"rz_yi": 0, "rq_yi": 0, "total_yi": 0}


def get_ths_hot_themes() -> list[dict]:
    """同花顺当日强势股题材归因"""
    url = f"http://zx.10jqka.com.cn/event/api/getharden/date/{date.today().strftime('%Y-%m-%d')}/orderby/date/orderway/desc/charset/GBK/"
    headers = {"User-Agent": UA_WIN}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data.get("errocode", 0) != 0:
            return []
        rows = data.get("data") or []
        return rows[:30]
    except Exception:
        return []


def eastmoney_datacenter(report_name, columns="ALL", filter_str="",
                         page_size=50, sort_columns="", sort_types="-1"):
    """东财数据中心统一查询"""
    DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": report_name, "columns": columns,
        "filter": filter_str, "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DATACENTER_URL, params=params, timeout=15)
    d = r.json()
    if d.get("result") and d["result"].get("data"):
        return d["result"]["data"]
    return []


# ═══════════════════════════════════════════════════════════════════
# 信号评估层
# ═══════════════════════════════════════════════════════════════════

def evaluate_index_resonance(quotes: dict) -> dict:
    """指数共振评估"""
    sh = quotes.get("000001", {}).get("change_pct", 0)
    hs300 = quotes.get("000300", {}).get("change_pct", 0)
    cyb = quotes.get("399006", {}).get("change_pct", 0)

    avg = (sh + hs300 + cyb) / 3
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
    """权重与小票共振评估 — 通过沪深300和中证2000对比"""
    # 中证2000在腾讯API的代码是 932000（深圳指数）
    quotes = tencent_quote(["000300", "399303"])  # 沪深300, 中证2000(国证2000)
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
    down_5pct = 0
    details = []
    for code, name in weight_codes.items():
        q = quotes.get(code, {})
        pct = q.get("change_pct", 0)
        if pct > 0:
            up_count += 1
        if pct <= -5:
            down_5pct += 1
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
    """题材情况评估"""
    hot_stocks = get_ths_hot_themes()
    if not hot_stocks:
        return {"指标": "题材情况", "等级": "⚪ 无数据", "说明": "无法获取题材数据"}

    # 统计题材标签
    from collections import Counter
    all_tags = []
    for s in hot_stocks:
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


def evaluate_active_buying(flow: dict) -> dict:
    """主动性买盘评估"""
    main_net = flow.get("main_net", 0)
    main_net_yi = main_net / 1e8

    if main_net_yi >= 0.02 * 10000:  # 2% of 万亿
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
    # 尝试从东财获取IF主力合约数据
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f170",
        "secids": "8.IF2506",  # IF主力合约
    }
    headers = {"User-Agent": UA}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        d = r.json().get("data", {})
        if d:
            price = d.get("f43", 0)
            change = d.get("f170", 0)
            return {
                "指标": "IF沪深300股指",
                "等级": "🟡 参考",
                "说明": f"IF主力合约 {price}点 涨跌{change:.2f}%（持仓/基差需盘后数据）",
            }
    except Exception:
        pass

    return {"指标": "IF沪深300股指", "等级": "⚪ 无数据", "说明": "IF期货数据暂不可用（非交易时间或无权限）"}


# ═══════════════════════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════════════════════

def generate_report() -> str:
    """生成完整的盘面信号报告"""
    now = datetime.now()
    report_time = now.strftime("%Y-%m-%d %H:%M")

    # ── 采集数据 ──────────────────────────────────────────────
    print(f"[{report_time}] 开始采集盘面数据...", file=sys.stderr)

    # 指数行情
    index_codes = ["000001", "000300", "399006", "000905", "399303"]
    index_quotes = tencent_quote(index_codes)

    # 涨跌家数
    breadth = get_market_breadth()

    # 北向资金
    northbound = get_northbound_flow()

    # 成交量
    volume_yi = get_total_volume()

    # 资金流
    fund_flow = get_index_fund_flow()

    # 融资余额
    margin = get_margin_balance()

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
    lines.append(f"📊 **盘面信号监控报告**")
    lines.append(f"⏰ {report_time}")
    lines.append("")

    # 指数行情概览
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

    # 信号评估
    lines.append("**🔔 信号评估**")
    lines.append("")

    # 按板块分组
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

    # 综合评分
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
    import json as _json
    report = generate_report()
    print(report)

    # 飞书 Webhook 推送
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if webhook_url:
        try:
            payload = _json.dumps({
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
            req = urllib.request.Request(
                webhook_url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = _json.loads(resp.read().decode("utf-8"))
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                print("\n✅ 飞书 Webhook 推送成功")
            else:
                print(f"\n⚠️ 飞书 Webhook 响应: {result}")
        except Exception as e:
            print(f"\n❌ 飞书 Webhook 推送失败: {e}")
