# scripts/ 说明

## fetch_daily.py

每日下载 A 股日线行情（Tushare `daily` 接口）并写入 `data/market.db`。

- **纯标准库**，无第三方依赖，开箱即用
- 密钥从 `~/API.txt` 读 `TUSHARE_TOKEN`
- 幂等：按 `(ts_code, trade_date)` upsert，可重复跑

```bash
# 下载最近一个交易日全市场日线
python3 fetch_daily.py

# 指定日期
python3 fetch_daily.py --date 20260814

# 只下载 watchlist（CSV 每行一个 ts_code，如 000001.SZ）
python3 fetch_daily.py --watchlist watchlist.csv
```

## 后续扩展（待 Berlin 确认再建）

- `indicators.py` —— 技术指标计算（MA/RSI/MACD/ATR/波动率）
- `fundamentals.py` —— 财务数据（Tushare `fina_indicator` 等）
- `macro.py` —— FRED 宏观指标
- `backtest.py` —— 回测框架
