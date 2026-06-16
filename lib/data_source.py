"""
a-stock-data 数据采集层
提取自 https://github.com/simonlin1212/a-stock-data (V3.2.2)
仅保留 market-signal-monitor 所需的子集。
"""

import random
import time
import urllib.request
from datetime import date

import requests

# ── 常量 ──────────────────────────────────────────────────────────────
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
UA_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"

# ── 东财防封 helper ─────────────────────────────────────────────────
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})
EM_MIN_INTERVAL = 1.0
_em_last_call = [0.0]


def em_get(url, params=None, headers=None, timeout=15, **kwargs):
    """东财统一请求入口：自动节流 + 复用 session + 默认 UA。"""
    wait = EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers,
                              timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()


def eastmoney_datacenter(report_name, columns="ALL", filter_str="",
                         page_size=50, sort_columns="", sort_types="-1"):
    """东财数据中心统一查询 — 龙虎榜/融资融券/解禁/大宗/股东/分红 共用（已内置限流）"""
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
# Layer 1: 行情层
# ═══════════════════════════════════════════════════════════════════

# 指数代码 → 腾讯前缀映射
INDEX_MAP = {
    "000001": "sh000001",   # 上证指数
    "000300": "sh000300",   # 沪深300
    "000905": "sh000905",   # 中证500
    "399001": "sz399001",   # 深证成指
    "399006": "sz399006",   # 创业板指
    "399303": "sz399303",   # 国证2000
}


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """腾讯财经批量行情（指数 + 个股 + ETF）"""
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
            time.sleep(2)

    result = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key.replace("=", "")
        if code.startswith(("sh", "sz", "bj")):
            code = code[2:]
        result[code] = {
            "name":         vals[1],
            "price":        float(vals[3]) if vals[3] else 0,
            "last_close":   float(vals[4]) if vals[4] else 0,
            "open":         float(vals[5]) if vals[5] else 0,
            "change_pct":   float(vals[32]) if vals[32] else 0,
            "high":         float(vals[33]) if vals[33] else 0,
            "low":          float(vals[34]) if vals[34] else 0,
            "amount_wan":   float(vals[37]) if vals[37] else 0,
            "turnover_pct": float(vals[38]) if vals[38] else 0,
            "pe_ttm":       float(vals[39]) if vals[39] else 0,
            "mcap_yi":      float(vals[44]) if vals[44] else 0,
            "pb":           float(vals[46]) if vals[46] else 0,
            "vol_ratio":    float(vals[49]) if vals[49] else 0,
        }
    return result


# ═══════════════════════════════════════════════════════════════════
# Layer 3: 信号层
# ═══════════════════════════════════════════════════════════════════

def ths_hot_reason(date_str: str = None) -> list[dict]:
    """同花顺当日强势股归因 — 题材标签 reason tags（零鉴权 73ms）"""
    if date_str is None:
        date_str = date.today().strftime("%Y-%m-%d")
    url = (
        f"http://zx.10jqka.com.cn/event/api/getharden/"
        f"date/{date_str}/orderby/date/orderway/desc/charset/GBK/"
    )
    headers = {"User-Agent": UA_WIN}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data.get("errocode", 0) != 0:
            return []
        return data.get("data") or []
    except Exception:
        return []


def hsgt_realtime() -> dict:
    """同花顺北向资金实时分钟流向 — 沪股通/深股通累计净买入（亿元）"""
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    headers = {
        "User-Agent": UA_WIN,
        "Host": "data.hexin.cn",
        "Referer": "https://data.hexin.cn/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        d = r.json()
        times = d.get("time", [])
        hgt = d.get("hgt", [])
        sgt = d.get("sgt", [])
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
        return {"hgt_yi": 0, "sgt_yi": 0, "total_yi": 0, "points": 0,
                "error": str(e)}


def eastmoney_fund_flow_minute(code: str) -> list[dict]:
    """个股/指数资金流向（分钟级，当日盘中）— 东财 push2（已内置限流）"""
    secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": secid, "klt": 1,
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    headers = {
        "User-Agent": UA,
        "Referer": "https://quote.eastmoney.com/",
        "Origin": "https://quote.eastmoney.com",
    }
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        d = r.json()
    except Exception:
        return []

    rows = []
    for line in d.get("data", {}).get("klines", []):
        parts = line.split(",")
        if len(parts) >= 6:
            rows.append({
                "time":      parts[0],
                "main_net":  float(parts[1]),
                "small_net": float(parts[2]),
                "mid_net":   float(parts[3]),
                "large_net": float(parts[4]),
                "super_net": float(parts[5]),
            })
    return rows


# ═══════════════════════════════════════════════════════════════════
# Layer 4: 资金面
# ═══════════════════════════════════════════════════════════════════

def get_market_breadth() -> dict:
    """涨跌家数、涨跌停 — 东财 push2 全市场统计（已内置限流）"""
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
                "up":         items[0].get("f104", 0),
                "down":       items[0].get("f105", 0),
                "limit_up":   items[0].get("f106", 0),
                "limit_down": items[0].get("f107", 0),
            }
    except Exception:
        pass
    return {"up": 0, "down": 0, "limit_up": 0, "limit_down": 0}


def get_total_volume() -> float:
    """全市场成交额（亿元）— 上证+深证成交额"""
    quotes = tencent_quote(["000001", "399001"])
    sh_amount = quotes.get("000001", {}).get("amount_wan", 0)
    sz_amount = quotes.get("399001", {}).get("amount_wan", 0)
    return round((sh_amount + sz_amount) / 10000, 0)


def get_margin_balance() -> dict:
    """融资融券余额 — 东财 datacenter（已内置限流）"""
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
            "rz_yi":    round(total_rz / 1e8, 2),
            "rq_yi":    round(total_rq / 1e8, 2),
            "total_yi": round((total_rz + total_rq) / 1e8, 2),
        }
    return {"rz_yi": 0, "rq_yi": 0, "total_yi": 0}


def get_if_futures() -> dict:
    """IF沪深300股指期货 — 东财 push2（已内置限流）"""
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f170",
        "secids": "8.IF2506",
    }
    headers = {"User-Agent": UA}
    try:
        r = em_get(url, params=params, headers=headers, timeout=10)
        d = r.json().get("data", {})
        if d:
            return {
                "price":  d.get("f43", 0),
                "change": d.get("f170", 0),
            }
    except Exception:
        pass
    return {"price": 0, "change": 0}
