# TOOLS.md - Local Notes

## 数据源密钥（在 `~/API.txt`）

读取方式（脚本统一用这个，不要硬编码）：

```bash
TOKEN=$(grep '^TUSHARE_TOKEN=' ~/API.txt | cut -d= -f2 | tr -d '[:space:]')
```

| Token 变量 | 数据源 |
|-----------|--------|
| `TUSHARE_TOKEN` | Tushare（A股，HTTP API: `http://api.tushare.pro`） |
| `FMP_TOKEN` | Financial Modeling Prep |
| `ALPHA_VANTAGE_TOKEN` | Alpha Vantage |
| `FRED_TOKEN` | FRED（圣路易斯联储） |
| `EIA_TOKEN` | EIA 能源数据 |
| `CENSUSDATA_TOKEN` | US Census Bureau |

## Python 环境

- 系统 Python: `/usr/bin/python3`（3.10.12）
- 暂无 pandas/tushare，需在首次跑数据脚本前安装（建议建独立 venv，见 `scripts/README`）

## Tushare 快速验证（已验证可用）

```bash
curl -sS -X POST http://api.tushare.pro \
  -H "Content-Type: application/json" \
  -d '{"api_name":"trade_cal","token":"<TOKEN>","params":{"exchange":"SSE","start_date":"20260810","end_date":"20260816"},"fields":"exchange,cal_date,is_open"}'
```
