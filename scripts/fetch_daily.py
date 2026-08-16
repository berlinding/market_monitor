#!/usr/bin/env python3
"""
fetch_daily.py — 每日下载 A 股日线行情并入库（SQLite）

纯标准库实现，无第三方依赖。

用法:
  python3 fetch_daily.py [--date YYYYMMDD] [--watchlist wl.csv]

默认:
  - 下载最近一个交易日全市场日线（Tushare `daily` 接口）
  - 写入 data/market.db 的 daily_bars 表
  - 记录 fetch_log（含缺口检查）

密钥从 ~/API.txt 读取 TUSHARE_TOKEN。
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta

TUSHARE_API = "http://api.tushare.pro"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "market.db")
API_TXT = os.path.expanduser("~/API.txt")


def load_token():
    try:
        with open(API_TXT) as f:
            for line in f:
                if line.startswith("TUSHARE_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return os.environ.get("TUSHARE_TOKEN", "")


def tushare_post(api_name, token, params, fields):
    body = json.dumps({
        "api_name": api_name,
        "token": token,
        "params": params,
        "fields": fields,
    }).encode("utf-8")
    req = urllib.request.Request(
        TUSHARE_API, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"Tushare error {data.get('code')}: {data.get('msg')}")
    fields_out = data["data"]["fields"]
    items = data["data"]["items"]
    return [dict(zip(fields_out, row)) for row in items]


def latest_trade_date(token, base_date=None):
    """向前回退，找到最近一个交易日。

    优先用 trade_cal（该接口 1 次/小时限额）；若被限流，退化为用
    `daily` 单只股票（000001.SZ）逐日探测。
    """
    d = base_date or datetime.now()
    try:
        for _ in range(20):
            ds = d.strftime("%Y%m%d")
            cal = tushare_post("trade_cal", token,
                               {"exchange": "SSE", "start_date": ds, "end_date": ds},
                               "cal_date,is_open")
            if cal and cal[0]["is_open"] == 1:
                return ds
            d = d - timedelta(days=1)
    except RuntimeError as e:
        print(f"[warn] trade_cal 不可用，改用 daily 探测: {e}", file=sys.stderr)

    # 退化路径：用单只股票探测最近有成交的日期
    for _ in range(20):
        ds = d.strftime("%Y%m%d")
        rows = tushare_post("daily", token,
                            {"ts_code": "000001.SZ", "trade_date": ds},
                            "ts_code,trade_date")
        if rows:
            return ds
        d = d - timedelta(days=1)
    raise RuntimeError("20 天内未找到交易日")


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_bars (
            ts_code    TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            open       REAL, high REAL, low REAL, close REAL,
            pre_close  REAL, change REAL, pct_chg REAL,
            vol        REAL, amount REAL,
            PRIMARY KEY (ts_code, trade_date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fetch_log (
            trade_date TEXT PRIMARY KEY,
            fetched_at TEXT,
            rows INTEGER,
            note TEXT
        )
    """)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="交易日 YYYYMMDD，缺省为最近一个交易日")
    ap.add_argument("--watchlist", help="可选，仅下载该 CSV 内的 ts_code 列表")
    args = ap.parse_args()

    token = load_token()
    if not token:
        print("ERROR: 未找到 TUSHARE_TOKEN", file=sys.stderr)
        sys.exit(1)

    trade_date = args.date or latest_trade_date(token)
    print(f"[fetch] 交易日: {trade_date}")

    rows = tushare_post(
        "daily", token,
        {"trade_date": trade_date},
        "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    )
    print(f"[fetch] 拉取 {len(rows)} 条日线")

    if args.watchlist:
        with open(args.watchlist) as f:
            want = {ln.strip() for ln in f if ln.strip() and not ln.startswith("#")}
        rows = [r for r in rows if r["ts_code"] in want]
        print(f"[fetch] 按 watchlist 过滤后 {len(rows)} 条")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    upserted = 0
    for r in rows:
        cur = conn.execute(
            """INSERT INTO daily_bars
               (ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(ts_code,trade_date) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, pre_close=excluded.pre_close,
                 change=excluded.change, pct_chg=excluded.pct_chg,
                 vol=excluded.vol, amount=excluded.amount""",
            (r["ts_code"], r["trade_date"],
             r.get("open"), r.get("high"), r.get("low"), r.get("close"),
             r.get("pre_close"), r.get("change"), r.get("pct_chg"),
             r.get("vol"), r.get("amount")),
        )
        upserted += cur.rowcount

    conn.execute(
        "INSERT INTO fetch_log(trade_date,fetched_at,rows,note) VALUES(?,?,?,?) "
        "ON CONFLICT(trade_date) DO UPDATE SET fetched_at=excluded.fetched_at, rows=excluded.rows",
        (trade_date, datetime.now().isoformat(timespec="seconds"), len(rows), ""),
    )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
    conn.close()

    print(f"[fetch] 完成: {trade_date} 写入 {len(rows)} 条 (upsert {upserted})，库累计 {total} 条")
    if len(rows) < 100:
        print(f"[warn] 该交易日仅 {len(rows)} 条，可能数据异常，请检查", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
