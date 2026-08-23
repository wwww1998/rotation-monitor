#!/usr/bin/env python3
"""
指数轮动策略监控服务 - FastAPI Web 应用
部署到 Render 等平台，支持手机每日查看
"""
import akshare as ak
import pandas as pd
import numpy as np
import json
import os
import time
import warnings
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

warnings.filterwarnings("ignore")

# ─── 策略参数 ─────────────────────────────────────────────────
BUY_THRESHOLD = 0.20   # 比值 < 20% → 买入创业板
SELL_THRESHOLD = 0.40  # 比值 > 40% → 买入红利低波

# ─── 缓存 ─────────────────────────────────────────────────────
_cache = {"data": None, "time": 0}
CACHE_TTL = 300  # 缓存5分钟，避免频繁请求


def fetch_data():
    """获取指数数据并计算策略信号"""
    now = time.time()
    if _cache["data"] and (now - _cache["time"]) < CACHE_TTL:
        return _cache["data"]

    # 创业板指
    cyb = ak.stock_zh_index_daily(symbol="sz399006")
    cyb["date"] = pd.to_datetime(cyb["date"])
    cyb = cyb.sort_values("date").reset_index(drop=True)

    # 红利低波
    hldb = ak.stock_zh_index_hist_csindex(
        symbol="H30269",
        start_date="20100101",
        end_date=datetime.now().strftime("%Y%m%d"),
    )
    hldb = hldb.rename(columns={"日期": "date", "收盘": "close"})
    hldb["date"] = pd.to_datetime(hldb["date"])
    hldb = hldb.sort_values("date").reset_index(drop=True)
    hldb = hldb.drop_duplicates(subset=["date"])

    # 合并
    merged = pd.merge(
        cyb[["date", "close"]],
        hldb[["date", "close"]],
        on="date",
        how="inner",
        suffixes=("_cyb", "_hldb"),
    )
    merged = merged.sort_values("date").reset_index(drop=True)
    merged.columns = ["date", "cyb_close", "hldb_close"]
    merged["ratio"] = merged["cyb_close"] / merged["hldb_close"]

    latest = merged.iloc[-1]
    ratio = latest["ratio"]

    # 策略信号
    if ratio < BUY_THRESHOLD:
        signal = "买入创业板"
        hold = "创业板指 (399006)"
        signal_class = "buy-cyb"
        reason = f"比值 {ratio*100:.2f}% &lt; 20%，创业板相对低估，建议买入创业板。"
    elif ratio > SELL_THRESHOLD:
        signal = "买入红利低波"
        hold = "红利低波 (H30269)"
        signal_class = "buy-hldb"
        reason = f"比值 {ratio*100:.2f}% &gt; 40%，创业板相对高估，建议切换至红利低波。"
    else:
        if ratio < 0.30:
            signal = "建议持有创业板"
            hold = "创业板指 (399006)"
            signal_class = "hold-cyb"
            reason = f"比值 {ratio*100:.2f}%，处于20%-40%观望区间，偏创业板方向。"
        else:
            signal = "建议持有红利低波"
            hold = "红利低波 (H30269)"
            signal_class = "hold-hldb"
            reason = f"比值 {ratio*100:.2f}%，处于20%-40%观望区间，偏红利低波方向。"

    # 涨跌幅
    cyb_chg = None
    hldb_chg = None
    if len(merged) >= 2:
        prev = merged.iloc[-2]
        cyb_chg = round((latest["cyb_close"] / prev["cyb_close"] - 1) * 100, 2)
        hldb_chg = round((latest["hldb_close"] / prev["hldb_close"] - 1) * 100, 2)

    # 近60日数据（用于图表）
    recent = merged[merged["date"] >= latest["date"] - pd.Timedelta(days=90)].copy()

    # 近5日数据
    recent_5 = []
    for _, r in merged.tail(5).iterrows():
        idx = r.name
        cyb_c = hldb_c = None
        if idx > 0:
            pr = merged.iloc[idx - 1]
            cyb_c = round((r["cyb_close"] / pr["cyb_close"] - 1) * 100, 2)
            hldb_c = round((r["hldb_close"] / pr["hldb_close"] - 1) * 100, 2)
        recent_5.append({
            "date": r["date"].strftime("%m-%d"),
            "cyb": round(float(r["cyb_close"]), 2),
            "hldb": round(float(r["hldb_close"]), 2),
            "cyb_chg": cyb_c,
            "hldb_chg": hldb_c,
            "ratio": round(float(r["ratio"]), 4),
        })

    # 历史比值统计
    hist_ratios = [round(float(r * 100), 2) for r in merged["ratio"]]
    ratio_median = round(float(np.median(hist_ratios)), 2)

    # 图表数据
    chart_data = {
        "dates": [r["date"].strftime("%Y-%m-%d") for _, r in recent.iterrows()],
        "ratios": [round(float(r["ratio"] * 100), 2) for _, r in recent.iterrows()],
    }

    signal_colors = {
        "buy-cyb": {"bg": "#e8f5e9", "border": "#4caf50", "text": "#2e7d32"},
        "buy-hldb": {"bg": "#fff3e0", "border": "#ff9800", "text": "#e65100"},
        "hold-cyb": {"bg": "#e3f2fd", "border": "#2196f3", "text": "#1565c0"},
        "hold-hldb": {"bg": "#fce4ec", "border": "#e91e63", "text": "#c62828"},
    }
    sc = signal_colors.get(signal_class, signal_colors["hold-cyb"])

    result = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "latest_date": latest["date"].strftime("%Y-%m-%d"),
        "cyb_close": round(float(latest["cyb_close"]), 2),
        "hldb_close": round(float(latest["hldb_close"]), 2),
        "ratio": round(float(ratio * 100), 2),
        "signal": signal,
        "hold": hold,
        "reason": reason,
        "signal_class": signal_class,
        "signal_color": sc,
        "cyb_chg": cyb_chg,
        "hldb_chg": hldb_chg,
        "ratio_median": ratio_median,
        "recent_5": recent_5,
        "chart_data": chart_data,
    }

    _cache["data"] = result
    _cache["time"] = now
    return result


def build_html(data):
    """生成HTML页面"""
    sc = data["signal_color"]
    ratio = data["ratio"]
    cyb_chg = data["cyb_chg"]
    hldb_chg = data["hldb_chg"]

    # 涨跌幅CSS类
    cyb_cls = "up" if cyb_chg and cyb_chg >= 0 else "down" if cyb_chg else "neutral"
    hldb_cls = "up" if hldb_chg and hldb_chg >= 0 else "down" if hldb_chg else "neutral"
    cyb_chg_str = f"{cyb_chg:+.2f}%" if cyb_chg is not None else "--"
    hldb_chg_str = f"{hldb_chg:+.2f}%" if hldb_chg is not None else "--"

    # 近5日表格行
    rows_html = ""
    for r in reversed(data["recent_5"]):
        c_cls = "up" if r["cyb_chg"] and r["cyb_chg"] >= 0 else "down"
        h_cls = "up" if r["hldb_chg"] and r["hldb_chg"] >= 0 else "down"
        c_str = f'{r["cyb_chg"]:+.2f}%' if r["cyb_chg"] is not None else "--"
        h_str = f'{r["hldb_chg"]:+.2f}%' if r["hldb_chg"] is not None else "--"
        rows_html += f"""
          <tr>
            <td>{r["date"]}</td>
            <td>{r["cyb"]}</td>
            <td class="{c_cls}">{c_str}</td>
            <td>{r["hldb"]}</td>
            <td class="{h_cls}">{h_str}</td>
            <td>{r["ratio"]*100:.2f}%</td>
          </tr>"""

    # 图表SVG
    n = len(data["chart_data"]["dates"])
    chart_svg = ""
    if n >= 2:
        margin = {"top": 20, "right": 20, "bottom": 30, "left": 50}
        cw, ch = 800, 240
        pw = cw - margin["left"] - margin["right"]
        ph = ch - margin["top"] - margin["bottom"]
        cr = data["chart_data"]["ratios"]
        mr, xr = min(cr), max(cr)
        rg = xr - mr if xr != mr else 1

        pts = []
        for i, v in enumerate(cr):
            x = margin["left"] + (i / (n - 1)) * pw
            y = margin["top"] + ph - ((v - mr) / rg) * ph
            pts.append(f"{x:.1f},{y:.1f}")
        pl = " ".join(pts)
        ap = " ".join(pts) + f" {margin['left'] + pw:.1f},{margin['top'] + ph:.1f} {margin['left']:.1f},{margin['top'] + ph:.1f}"

        buy_y = margin["top"] + ph - ((20 - mr) / rg) * ph
        sell_y = margin["top"] + ph - ((40 - mr) / rg) * ph
        buy_y = max(margin["top"], min(margin["top"] + ph, buy_y))
        sell_y = max(margin["top"], min(margin["top"] + ph, sell_y))

        y_lbls = "".join(f'<text x="{margin["left"] - 8}" y="{margin["top"] + ph - (i/4)*ph + 4}" text-anchor="end" font-size="11" fill="#6b7a8f">{mr + rg*i/4:.1f}%</text>' for i in range(5))
        xt = max(1, n // 6)
        x_lbls = "".join(f'<text x="{margin["left"] + (i/(n-1))*pw}" y="{ch - 6}" text-anchor="middle" font-size="10" fill="#6b7a8f">{data["chart_data"]["dates"][i][5:]}</text>' for i in range(0, n, xt))

        chart_svg = f"""
      <svg viewBox="0 0 {cw} {ch}" xmlns="http://www.w3.org/2000/svg">
        <line x1="{margin['left']}" y1="{margin['top']}" x2="{margin['left']+pw}" y2="{margin['top']}" stroke="#e2e8f0" stroke-width="1"/>
        <line x1="{margin['left']}" y1="{margin['top']+ph*.25}" x2="{margin['left']+pw}" y2="{margin['top']+ph*.25}" stroke="#e2e8f0" stroke-width="1"/>
        <line x1="{margin['left']}" y1="{margin['top']+ph*.5}" x2="{margin['left']+pw}" y2="{margin['top']+ph*.5}" stroke="#e2e8f0" stroke-width="1"/>
        <line x1="{margin['left']}" y1="{margin['top']+ph*.75}" x2="{margin['left']+pw}" y2="{margin['top']+ph*.75}" stroke="#e2e8f0" stroke-width="1"/>
        <line x1="{margin['left']}" y1="{margin['top']+ph}" x2="{margin['left']+pw}" y2="{margin['top']+ph}" stroke="#e2e8f0" stroke-width="1"/>
        <line x1="{margin['left']}" y1="{buy_y}" x2="{margin['left']+pw}" y2="{buy_y}" stroke="#4caf50" stroke-width="1.5" stroke-dasharray="6,3"/>
        <text x="{margin['left']+pw+4}" y="{buy_y+4}" font-size="10" fill="#4caf50">买入 20%</text>
        <line x1="{margin['left']}" y1="{sell_y}" x2="{margin['left']+pw}" y2="{sell_y}" stroke="#f44336" stroke-width="1.5" stroke-dasharray="6,3"/>
        <text x="{margin['left']+pw+4}" y="{sell_y+4}" font-size="10" fill="#f44336">卖出 40%</text>
        <polygon points="{ap}" fill="rgba(37, 99, 235, 0.1)"/>
        <polyline points="{pl}" fill="none" stroke="#2563eb" stroke-width="2" stroke-linejoin="round"/>
        {y_lbls}
        {x_lbls}
      </svg>"""

    html = f"""<!-- Generated by Trae Work -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>指数轮动策略 · 每日监控</title>
<style>
:root {{
  --bg: #f5f7fa;
  --bg2: #ffffff;
  --ink: #1a2332;
  --muted: #6b7a8f;
  --rule: #e2e8f0;
  --accent: #2563eb;
  --accent2: #f59e0b;
  --success: #10b981;
  --danger: #ef4444;
  --radius: 12px;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--ink);
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}}
.container {{ max-width: 960px; margin: 0 auto; padding: 16px 12px; }}

.header {{ text-align: center; padding: 24px 0 20px; }}
.header h1 {{ font-size: 24px; font-weight: 700; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.header .subtitle {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
.header .update-time {{ color: var(--muted); font-size: 12px; margin-top: 6px; }}

.signal-card {{
  background: var(--bg2); border-radius: var(--radius); box-shadow: var(--shadow);
  padding: 24px 20px; margin-bottom: 16px;
  border-left: 5px solid {sc["border"]};
  background: linear-gradient(135deg, {sc["bg"]}, var(--bg2));
}}
.signal-card .signal-label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
.signal-card .signal-value {{ font-size: 28px; font-weight: 800; color: {sc["text"]}; }}
.signal-card .signal-reason {{ font-size: 13px; color: var(--muted); margin-top: 6px; line-height: 1.5; }}

.stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 16px; }}
.stat-card {{ background: var(--bg2); border-radius: var(--radius); box-shadow: var(--shadow); padding: 14px 10px; text-align: center; }}
.stat-card .stat-label {{ font-size: 11px; color: var(--muted); margin-bottom: 4px; }}
.stat-card .stat-value {{ font-size: 20px; font-weight: 700; }}
.stat-card .stat-change {{ font-size: 11px; margin-top: 2px; }}
.up {{ color: var(--danger); }}
.down {{ color: var(--success); }}
.neutral {{ color: var(--muted); }}

.ratio-bar-wrap {{ background: var(--bg2); border-radius: var(--radius); box-shadow: var(--shadow); padding: 18px 20px; margin-bottom: 16px; }}
.ratio-bar-title {{ font-size: 14px; font-weight: 600; margin-bottom: 10px; }}
.ratio-bar {{ position: relative; height: 36px; background: linear-gradient(to right, #4caf50, #8bc34a, #ffeb3b, #ff9800, #f44336); border-radius: 8px; margin: 12px 0; }}
.ratio-marker {{ position: absolute; top: -6px; width: 4px; height: 48px; background: #1a2332; border-radius: 2px; transition: left 0.5s ease; }}
.ratio-marker::after {{ content: ""; position: absolute; top: -5px; left: -5px; width: 14px; height: 14px; background: #1a2332; border-radius: 50%; }}
.ratio-value-label {{ text-align: center; font-size: 22px; font-weight: 800; color: var(--accent); }}
.ratio-thresholds {{ display: flex; justify-content: space-between; font-size: 11px; margin-top: 4px; }}
.ratio-thresholds .buy {{ color: #4caf50; font-weight: 600; }}
.ratio-thresholds .sell {{ color: #f44336; font-weight: 600; }}
.ratio-labels {{ display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); margin-top: 4px; }}

.section {{ background: var(--bg2); border-radius: var(--radius); box-shadow: var(--shadow); padding: 18px 20px; margin-bottom: 16px; }}
.section-title {{ font-size: 15px; font-weight: 700; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 2px solid var(--rule); }}
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ background: var(--bg); padding: 8px 10px; text-align: right; font-weight: 600; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid var(--rule); white-space: nowrap; }}
th:first-child {{ text-align: left; }}
td {{ padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--rule); white-space: nowrap; }}
td:first-child {{ text-align: left; font-weight: 600; }}

.axis-chart {{ margin-top: 10px; }}
.axis-chart svg {{ width: 100%; height: auto; }}

.rules-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
.rule-card {{ padding: 12px; border-radius: 8px; border: 1px solid var(--rule); }}
.rule-card.buy {{ border-left: 4px solid #4caf50; }}
.rule-card.sell {{ border-left: 4px solid #f44336; }}
.rule-card.hold {{ border-left: 4px solid #2196f3; }}
.rule-card .rule-title {{ font-size: 13px; font-weight: 700; margin-bottom: 4px; }}
.rule-card .rule-desc {{ font-size: 12px; color: var(--muted); }}

.backtest-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; }}
.bt-card {{ text-align: center; padding: 12px; border-radius: 8px; border: 1px solid var(--rule); }}
.bt-card .bt-label {{ font-size: 11px; color: var(--muted); margin-bottom: 4px; }}
.bt-card .bt-value {{ font-size: 18px; font-weight: 700; }}

.footer {{ text-align: center; padding: 16px; color: var(--muted); font-size: 11px; line-height: 1.8; }}

@media (max-width: 640px) {{
  .stats-grid {{ grid-template-columns: repeat(2, 1fr); gap: 8px; }}
  .rules-grid {{ grid-template-columns: 1fr; }}
  .backtest-grid {{ grid-template-columns: 1fr; }}
  .header h1 {{ font-size: 20px; }}
  .signal-card .signal-value {{ font-size: 24px; }}
  .stat-card {{ padding: 10px 8px; }}
  .stat-card .stat-value {{ font-size: 17px; }}
  .container {{ padding: 12px 8px; }}
}}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>指数轮动策略 · 每日监控</h1>
    <div class="subtitle">创业板指 (399006) vs 中证红利低波 (H30269)</div>
    <div class="update-time">更新于 {data["update_time"]} · 最新交易日 {data["latest_date"]}</div>
  </div>

  <div class="signal-card">
    <div class="signal-label">当前策略信号</div>
    <div class="signal-value">{data["signal"]}</div>
    <div class="signal-reason">{data["reason"]}</div>
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">创业板指</div>
      <div class="stat-value">{data["cyb_close"]}</div>
      <div class="stat-change {cyb_cls}">{cyb_chg_str}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">红利低波</div>
      <div class="stat-value">{data["hldb_close"]}</div>
      <div class="stat-change {hldb_cls}">{hldb_chg_str}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">当前比值</div>
      <div class="stat-value" style="color:{sc['text']}">{ratio}%</div>
      <div class="stat-change neutral">中位数 {data["ratio_median"]}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">建议持仓</div>
      <div class="stat-value" style="font-size:14px;color:{sc['text']}">{data["hold"]}</div>
      <div class="stat-change neutral">点击刷新获取最新</div>
    </div>
  </div>

  <div class="ratio-bar-wrap">
    <div class="ratio-bar-title">比值位置</div>
    <div class="ratio-value-label">{ratio}%</div>
    <div class="ratio-bar">
      <div class="ratio-marker" style="left: min(max({ratio / 60 * 100}%, 2%), 98%);"></div>
    </div>
    <div class="ratio-thresholds">
      <span class="buy">0% ▼ 买入 20%</span>
      <span class="sell">卖出 40% ▲ 60%+</span>
    </div>
    <div class="ratio-labels">
      <span>买入创业板</span>
      <span>持有区间</span>
      <span>买入红利低波</span>
    </div>
  </div>

  <div class="section">
    <div class="section-title">近5日数据</div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>日期</th><th>创业板指</th><th>涨跌幅</th><th>红利低波</th><th>涨跌幅</th><th>比值</th></tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
  </div>

  <div class="section">
    <div class="section-title">近60日比值趋势</div>
    <div class="axis-chart">
      {chart_svg}
    </div>
  </div>

  <div class="section">
    <div class="section-title">策略规则</div>
    <div class="rules-grid">
      <div class="rule-card buy">
        <div class="rule-title">买入创业板</div>
        <div class="rule-desc">当比值 &lt; 20% 时，全仓切换至创业板指</div>
      </div>
      <div class="rule-card sell">
        <div class="rule-title">买入红利低波</div>
        <div class="rule-desc">当比值 &gt; 40% 时，全仓切换至红利低波</div>
      </div>
      <div class="rule-card hold">
        <div class="rule-title">持有观望</div>
        <div class="rule-desc">比值在 20%-40% 之间，维持现有持仓不变</div>
      </div>
      <div class="rule-card" style="border-left: 4px solid #9c27b0;">
        <div class="rule-title">初始持仓</div>
        <div class="rule-desc">初始买入红利低波，全仓操作，不含交易成本</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">回测结果（2016.08 - 2026.08）</div>
    <div class="backtest-grid">
      <div class="bt-card"><div class="bt-label">总收益率</div><div class="bt-value" style="color:var(--accent)">+556.50%</div></div>
      <div class="bt-card"><div class="bt-label">年化收益率</div><div class="bt-value" style="color:var(--accent)">+20.61%</div></div>
      <div class="bt-card"><div class="bt-label">最大回撤</div><div class="bt-value" style="color:var(--danger)">-37.44%</div></div>
    </div>
    <div class="backtest-grid" style="margin-top:8px;">
      <div class="bt-card"><div class="bt-label">创业板持有收益</div><div class="bt-value" style="color:var(--muted)">+75.76%</div></div>
      <div class="bt-card"><div class="bt-label">红利低波持有收益</div><div class="bt-value" style="color:var(--muted)">+50.08%</div></div>
      <div class="bt-card"><div class="bt-label">交易次数</div><div class="bt-value">4次</div></div>
    </div>
  </div>

  <div class="footer">
    <p>数据来源：AKShare（新浪财经 / 中证指数官网）</p>
    <p>策略逻辑：创业板与红利低波指数轮动，基于比值阈值判断</p>
    <p style="color:#ef4444;font-weight:600;">⚠️ 本页面数据仅供参考，不构成投资建议</p>
    <p style="margin-top:6px;"><a href="javascript:location.reload()" style="color:var(--accent);text-decoration:none;font-weight:600;">&#x21bb; 刷新页面</a> 获取最新数据</p>
  </div>

</div>
</body>
</html>"""
    return html


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时预热数据
    print("正在预热数据...")
    try:
        fetch_data()
        print("数据预热完成")
    except Exception as e:
        print(f"数据预热失败: {e}")
    yield


app = FastAPI(title="指数轮动策略监控", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index():
    try:
        data = fetch_data()
        return HTMLResponse(content=build_html(data))
    except Exception as e:
        error_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>数据获取失败</title>
<style>
body {{ font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #f5f7fa; }}
.card {{ background: white; padding: 32px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); text-align: center; max-width: 400px; }}
h1 {{ color: #ef4444; font-size: 20px; margin-bottom: 12px; }}
p {{ color: #6b7a8f; font-size: 14px; line-height: 1.6; }}
a {{ display: inline-block; margin-top: 16px; padding: 10px 24px; background: #2563eb; color: white; text-decoration: none; border-radius: 8px; font-size: 14px; }}
</style>
</head>
<body>
<div class="card">
<h1>数据获取失败</h1>
<p>无法从数据源获取指数信息，请稍后刷新重试。</p>
<p style="font-size:12px;margin-top:8px;">错误: {str(e)}</p>
<a href="javascript:location.reload()">重新加载</a>
</div>
</body>
</html>"""
        return HTMLResponse(content=error_html, status_code=502)


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)