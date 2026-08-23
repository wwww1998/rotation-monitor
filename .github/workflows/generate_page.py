import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import math

# 指数代码
CYB_CODE = "399006"
HLDB_CODE = "H30269"

# 策略阈值
BUY_THRESHOLD = 0.20
SELL_THRESHOLD = 0.40

# 回测结果（已知）
BACKTEST = {
    "total_return": "+556.50%",
    "annual_return": "+20.61%",
    "max_drawdown": "-37.44%",
    "cyb_hold_return": "+75.76%",
    "hldb_hold_return": "+50.08%",
    "trade_count": "4次",
    "trades": [
        {"date": "2017-07-17", "action": "红利低波→创业板", "ratio": "19.20%", "value": "1,207,369"},
        {"date": "2021-01-22", "action": "创业板→红利低波", "ratio": "41.43%", "value": "2,447,810"},
        {"date": "2023-09-20", "action": "红利低波→创业板", "ratio": "19.99%", "value": "3,001,664"},
        {"date": "2026-06-18", "action": "创业板→红利低波", "ratio": "40.53%", "value": "6,422,922"},
    ]
}

def fetch_index_data(code, market="sh", start_date="20100101"):
    try:
        if code == "H30269":
            df = ak.stock_zh_index_hist_csindex(symbol=code, start_date=start_date, end_date=datetime.now().strftime("%Y%m%d"))
        else:
            symbol = f"sz{code}" if market == "sz" else f"sh{code}"
            df = ak.stock_zh_index_daily(symbol=symbol)
        return df
    except Exception as e:
        return None

def fmt_num(n, decimals=2):
    if pd.isna(n):
        return "N/A"
    return f"{n:,.{decimals}f}"

def pct_str(val):
    if val is None or pd.isna(val):
        return "N/A", "neutral"
    if val > 0:
        return f"+{val:.2f}%", "up"
    elif val < 0:
        return f"{val:.2f}%", "down"
    return "0.00%", "neutral"

def compute_ratio_position(ratio_pct, min_val=0, max_val=60):
    clamped = max(min_val, min(max_val, ratio_pct))
    if max_val == min_val:
        return 50
    return (clamped - min_val) / (max_val - min_val) * 100

def generate_page():
    print("正在获取指数数据...")

    cyb_df = fetch_index_data(CYB_CODE, market="sz")
    if cyb_df is None:
        print("ERROR: 无法获取创业板指数据")
        return

    hldb_df = fetch_index_data(HLDB_CODE)
    if hldb_df is None:
        print("ERROR: 无法获取红利低波指数数据")
        return

    # 统一列名
    def normalize(df, close_col, date_col):
        d = df[[date_col, close_col]].copy()
        d.columns = ["date", "close"]
        d["date"] = pd.to_datetime(d["date"])
        d = d.sort_values("date").reset_index(drop=True)
        return d

    if "date" in cyb_df.columns:
        cyb = normalize(cyb_df, "close", "date")
    elif "日期" in cyb_df.columns:
        cyb = normalize(cyb_df, "收盘", "日期")
    else:
        print("ERROR: 无法识别创业板数据列名")
        return

    if "date" in hldb_df.columns:
        hldb = normalize(hldb_df, "close", "date")
    elif "日期" in hldb_df.columns:
        hldb = normalize(hldb_df, "收盘", "日期")
    else:
        print("ERROR: 无法识别红利低波数据列名")
        return

    # 合并
    merged = pd.merge(cyb, hldb, on="date", how="inner", suffixes=("_cyb", "_hldb"))
    merged = merged.dropna().reset_index(drop=True)

    if len(merged) < 20:
        print("ERROR: 数据不足")
        return

    # 计算比值和涨跌幅
    merged["ratio"] = merged["close_cyb"] / merged["close_hldb"]
    merged["cyb_pct"] = merged["close_cyb"].pct_change() * 100
    merged["hldb_pct"] = merged["close_hldb"].pct_change() * 100

    latest = merged.iloc[-1]
    prev = merged.iloc[-2]
    latest_date = latest["date"]
    ratio = latest["ratio"]
    cyb_close = latest["close_cyb"]
    hldb_close = latest["close_hldb"]
    cyb_chg = latest["cyb_pct"]
    hldb_chg = latest["hldb_pct"]
    ratio_median = merged["ratio"].median()

    # 信号判断
    if ratio < BUY_THRESHOLD:
        signal = "买入创业板"
        hold = "创业板指 (399006)"
        signal_class = "buy-cyb"
        reason = f"比值 {ratio*100:.2f}% < 20%，创业板相对低估，建议买入创业板。"
    elif ratio > SELL_THRESHOLD:
        signal = "买入红利低波"
        hold = "红利低波 (H30269)"
        signal_class = "buy-hldb"
        reason = f"比值 {ratio*100:.2f}% > 40%，创业板相对高估，建议切换至红利低波。"
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

    # 近5日数据
    recent_5 = merged.tail(5).iloc[::-1]

    # 60日趋势数据（SVG用）
    trend_60 = merged.tail(60).reset_index(drop=True)
    ratio_min = trend_60["ratio"].min() * 100
    ratio_max = trend_60["ratio"].max() * 100
    ratio_pad = (ratio_max - ratio_min) * 0.1 or 5
    svg_y_min = ratio_min - ratio_pad
    svg_y_max = ratio_max + ratio_pad
    svg_y_range = svg_y_max - svg_y_min

    W, H = 800, 240
    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 50, 30, 20, 30
    PLOT_L = W - MARGIN_L - MARGIN_R
    PLOT_H = H - MARGIN_T - MARGIN_B

    def svg_x(idx):
        return MARGIN_L + (idx / (len(trend_60) - 1)) * PLOT_L

    def svg_y(val_pct):
        ratio_y = (val_pct - svg_y_min) / svg_y_range
        return MARGIN_T + PLOT_H - ratio_y * PLOT_H

    # 生成SVG路径
    points = []
    for i, (_, row) in enumerate(trend_60.iterrows()):
        x = svg_x(i)
        y = svg_y(row["ratio"] * 100)
        points.append(f"{x:.1f},{y:.1f}")

    # 面积填充底部
    area_bottom = MARGIN_T + PLOT_H
    first_x = svg_x(0)
    last_x = svg_x(len(trend_60) - 1)
    area_points = f"{first_x:.1f},{area_bottom:.1f} " + " ".join(points) + f" {last_x:.1f},{area_bottom:.1f}"

    # Y轴刻度
    y_ticks = 5
    y_labels = []
    for i in range(y_ticks + 1):
        val_pct = svg_y_max - (i / y_ticks) * svg_y_range
        y_labels.append(val_pct)

    # X轴刻度
    x_labels = []
    x_label_count = 7
    for i in range(x_label_count):
        idx = int((i / (x_label_count - 1)) * (len(trend_60) - 1))
        x_labels.append((svg_x(idx), trend_60.iloc[idx]["date"].strftime("%m-%d")))

    # 阈值线位置
    buy_line_y = svg_y(20)
    sell_line_y = svg_y(40)

    # 生成完整HTML
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    last_trade_date = latest_date.strftime("%Y-%m-%d")
    ratio_pct = ratio * 100
    ratio_median_pct = ratio_median * 100
    ratio_pos = compute_ratio_position(ratio_pct)

    cyb_chg_str, cyb_chg_cls = pct_str(cyb_chg)
    hldb_chg_str, hldb_chg_cls = pct_str(hldb_chg)

    # 信号卡颜色
    signal_colors = {
        "buy-cyb": {"bg": "linear-gradient(135deg, #e3f2fd, #fff)", "border": "#2196f3", "text": "#1565c0"},
        "buy-hldb": {"bg": "linear-gradient(135deg, #fce4ec, #fff)", "border": "#e91e63", "text": "#c62828"},
        "hold-cyb": {"bg": "linear-gradient(135deg, #e8f5e9, #fff)", "border": "#4caf50", "text": "#2e7d32"},
        "hold-hldb": {"bg": "linear-gradient(135deg, #fff8e1, #fff)", "border": "#ff9800", "text": "#e65100"},
    }
    sc = signal_colors.get(signal_class, signal_colors["hold-hldb"])

    html = f"""<!DOCTYPE html>
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
}}
.container {{ max-width: 960px; margin: 0 auto; padding: 20px 16px; }}

.header {{
  text-align: center;
  padding: 32px 0 24px;
}}
.header h1 {{
  font-size: 28px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.header .subtitle {{
  color: var(--muted);
  font-size: 14px;
  margin-top: 4px;
}}
.header .update-time {{
  color: var(--muted);
  font-size: 13px;
  margin-top: 8px;
}}

.signal-card {{
  background: {sc['bg']};
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 28px 24px;
  margin-bottom: 20px;
  border-left: 5px solid {sc['border']};
}}
.signal-card .signal-label {{
  font-size: 13px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 4px;
}}
.signal-card .signal-value {{
  font-size: 32px;
  font-weight: 800;
  color: {sc['text']};
}}
.signal-card .signal-reason {{
  font-size: 14px;
  color: var(--muted);
  margin-top: 8px;
  line-height: 1.5;
}}

.stats-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}}
.stat-card {{
  background: var(--bg2);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 16px;
  text-align: center;
}}
.stat-card .stat-label {{
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}}
.stat-card .stat-value {{
  font-size: 22px;
  font-weight: 700;
}}
.stat-card .stat-change {{
  font-size: 12px;
  margin-top: 2px;
}}
.up {{ color: var(--danger); }}
.down {{ color: var(--success); }}
.neutral {{ color: var(--muted); }}

.ratio-bar-wrap {{
  background: var(--bg2);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 20px 24px;
  margin-bottom: 20px;
}}
.ratio-bar-title {{
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}}
.ratio-bar {{
  position: relative;
  height: 40px;
  background: linear-gradient(to right, #4caf50, #8bc34a, #ffeb3b, #ff9800, #f44336);
  border-radius: 8px;
  margin: 16px 0;
}}
.ratio-marker {{
  position: absolute;
  top: -8px;
  width: 4px;
  height: 56px;
  background: #1a2332;
  border-radius: 2px;
  transition: left 0.5s ease;
}}
.ratio-marker::after {{
  content: "";
  position: absolute;
  top: -6px;
  left: -5px;
  width: 14px;
  height: 14px;
  background: #1a2332;
  border-radius: 50%;
}}
.ratio-labels {{
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--muted);
  margin-top: 4px;
}}
.ratio-value-label {{
  text-align: center;
  font-size: 24px;
  font-weight: 800;
  color: var(--accent);
}}
.ratio-thresholds {{
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-top: 4px;
}}
.ratio-thresholds .buy {{ color: #4caf50; font-weight: 600; }}
.ratio-thresholds .sell {{ color: #f44336; font-weight: 600; }}

.section {{
  background: var(--bg2);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 20px 24px;
  margin-bottom: 20px;
}}
.section-title {{
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--rule);
}}
.table-wrap {{
  overflow-x: auto;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}}
th {{
  background: var(--bg);
  padding: 10px 12px;
  text-align: right;
  font-weight: 600;
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 2px solid var(--rule);
}}
th:first-child {{ text-align: left; }}
td {{
  padding: 10px 12px;
  text-align: right;
  border-bottom: 1px solid var(--rule);
}}
td:first-child {{ text-align: left; font-weight: 600; }}

.rules-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}}
.rule-card {{
  padding: 14px;
  border-radius: 8px;
  border: 1px solid var(--rule);
}}
.rule-card.buy {{ border-left: 4px solid #4caf50; }}
.rule-card.sell {{ border-left: 4px solid #f44336; }}
.rule-card.hold {{ border-left: 4px solid #2196f3; }}
.rule-card .rule-title {{
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 4px;
}}
.rule-card .rule-desc {{
  font-size: 13px;
  color: var(--muted);
}}

.backtest-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-top: 12px;
}}
.bt-card {{
  text-align: center;
  padding: 14px;
  border-radius: 8px;
  border: 1px solid var(--rule);
}}
.bt-card .bt-label {{
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}}
.bt-card .bt-value {{
  font-size: 20px;
  font-weight: 700;
}}

.footer {{
  text-align: center;
  padding: 20px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.8;
}}
.footer a {{
  color: var(--accent);
  text-decoration: none;
}}

.axis-chart {{ margin-top: 12px; }}
.axis-chart svg {{ width: 100%; height: auto; }}

@media (max-width: 640px) {{
  .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
  .rules-grid {{ grid-template-columns: 1fr; }}
  .backtest-grid {{ grid-template-columns: 1fr; }}
  .header h1 {{ font-size: 22px; }}
  .signal-card .signal-value {{ font-size: 26px; }}
}}
</style>
</head>
<body>

<div class="container">

  <!-- Header -->
  <div class="header">
    <h1>指数轮动策略 · 每日监控</h1>
    <div class="subtitle">创业板指 (399006) vs 中证红利低波 (H30269)</div>
    <div class="update-time">更新于 {now_str}</div>
  </div>

  <!-- Signal Card -->
  <div class="signal-card">
    <div class="signal-label">当前策略信号</div>
    <div class="signal-value">{signal}</div>
    <div class="signal-reason">{reason}</div>
  </div>

  <!-- Stats Grid -->
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">创业板指</div>
      <div class="stat-value">{fmt_num(cyb_close)}</div>
      <div class="stat-change {cyb_chg_cls}">{cyb_chg_str}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">红利低波</div>
      <div class="stat-value">{fmt_num(hldb_close)}</div>
      <div class="stat-change {hldb_chg_cls}">{hldb_chg_str}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">当前比值</div>
      <div class="stat-value" style="color:{sc['text']}">{ratio_pct:.2f}%</div>
      <div class="stat-change neutral">中位数 {ratio_median_pct:.2f}%</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">建议持仓</div>
      <div class="stat-value" style="font-size:16px; color:{sc['text']}">{hold}</div>
      <div class="stat-change neutral">交易日 {last_trade_date}</div>
    </div>
  </div>

  <!-- Ratio Bar -->
  <div class="ratio-bar-wrap">
    <div class="ratio-bar-title">比值位置</div>
    <div class="ratio-value-label">{ratio_pct:.2f}%</div>
    <div class="ratio-bar">
      <div class="ratio-marker" style="left: min(max({ratio_pos:.2f}%, 2%), 98%);"></div>
    </div>
    <div class="ratio-thresholds">
      <span class="buy">0% ▼ 买入阈值 20%</span>
      <span class="sell">卖出阈值 40% ▲ 60%+</span>
    </div>
    <div class="ratio-labels">
      <span>买入创业板</span>
      <span>持有区间</span>
      <span>买入红利低波</span>
    </div>
  </div>

  <!-- Recent 5 Days Data -->
  <div class="section">
    <div class="section-title">近5日数据</div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>创业板指</th>
            <th>涨跌幅</th>
            <th>红利低波</th>
            <th>涨跌幅</th>
            <th>比值</th>
          </tr>
        </thead>
        <tbody>
"""

    for _, row in recent_5.iterrows():
        r_c = row["cyb_pct"]
        r_h = row["hldb_pct"]
        c_str, c_cls = pct_str(r_c)
        h_str, h_cls = pct_str(r_h)
        r_val = row["ratio"] * 100
        html += f"""          <tr>
            <td>{row['date'].strftime('%m-%d')}</td>
            <td>{fmt_num(row['close_cyb'])}</td>
            <td class="{c_cls}">{c_str}</td>
            <td>{fmt_num(row['close_hldb'])}</td>
            <td class="{h_cls}">{h_str}</td>
            <td>{r_val:.2f}%</td>
          </tr>
"""

    # 60日趋势SVG
    html += f"""        </tbody>
      </table>
    </div>
  </div>

  <!-- Trend Chart SVG -->
  <div class="section">
    <div class="section-title">近60日比值趋势</div>
    <div class="axis-chart">
      <svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
"""

    # Grid lines
    for i in range(y_ticks + 1):
        val_pct = svg_y_max - (i / y_ticks) * svg_y_range
        yy = svg_y(val_pct)
        html += f'        <line x1="{MARGIN_L}" y1="{yy:.1f}" x2="{W - MARGIN_R}" y2="{yy:.1f}" stroke="#e2e8f0" stroke-width="1"/>\n'

    # Threshold lines
    html += f"""        <line x1="{MARGIN_L}" y1="{buy_line_y:.1f}" x2="{W - MARGIN_R}" y2="{buy_line_y:.1f}" stroke="#4caf50" stroke-width="1.5" stroke-dasharray="6,3"/>
        <text x="{W - MARGIN_R + 4}" y="{buy_line_y + 4:.1f}" font-size="10" fill="#4caf50">买入 20%</text>
        <line x1="{MARGIN_L}" y1="{sell_line_y:.1f}" x2="{W - MARGIN_R}" y2="{sell_line_y:.1f}" stroke="#f44336" stroke-width="1.5" stroke-dasharray="6,3"/>
        <text x="{W - MARGIN_R + 4}" y="{sell_line_y + 4:.1f}" font-size="10" fill="#f44336">卖出 40%</text>
"""

    # Area fill
    html += f'        <polygon points="{area_points}" fill="rgba(37, 99, 235, 0.1)"/>\n'

    # Line
    html += f'        <polyline points="{" ".join(points)}" fill="none" stroke="#2563eb" stroke-width="2" stroke-linejoin="round"/>\n'

    # Y labels
    for i in range(y_ticks + 1):
        val_pct = svg_y_max - (i / y_ticks) * svg_y_range
        yy = svg_y(val_pct)
        html += f'        <text x="{MARGIN_L - 8}" y="{yy + 4:.1f}" text-anchor="end" font-size="11" fill="#6b7a8f">{val_pct:.1f}%</text>\n'

    # X labels
    for x_pos, label in x_labels:
        html += f'        <text x="{x_pos:.1f}" y="{H - 4}" text-anchor="middle" font-size="10" fill="#6b7a8f">{label}</text>\n'

    # Strategy Rules
    html += f"""      </svg>
    </div>
  </div>

  <!-- Strategy Rules -->
  <div class="section">
    <div class="section-title">策略规则</div>
    <div class="rules-grid">
      <div class="rule-card buy">
        <div class="rule-title">买入创业板</div>
        <div class="rule-desc">当创业板/红利低波比值 &lt; 20% 时，全仓切换至创业板指</div>
      </div>
      <div class="rule-card sell">
        <div class="rule-title">买入红利低波</div>
        <div class="rule-desc">当创业板/红利低波比值 &gt; 40% 时，全仓切换至红利低波</div>
      </div>
      <div class="rule-card hold">
        <div class="rule-title">持有观望</div>
        <div class="rule-desc">比值在 20%-40% 之间时，维持现有持仓不变</div>
      </div>
      <div class="rule-card" style="border-left: 4px solid #9c27b0;">
        <div class="rule-title">初始持仓</div>
        <div class="rule-desc">初始买入红利低波，全仓操作，不含交易成本</div>
      </div>
    </div>
  </div>

  <!-- Backtest Results -->
  <div class="section">
    <div class="section-title">回测结果（2016.08 - 2026.08）</div>
    <div class="backtest-grid">
      <div class="bt-card">
        <div class="bt-label">总收益率</div>
        <div class="bt-value" style="color:var(--accent)">{BACKTEST["total_return"]}</div>
      </div>
      <div class="bt-card">
        <div class="bt-label">年化收益率</div>
        <div class="bt-value" style="color:var(--accent)">{BACKTEST["annual_return"]}</div>
      </div>
      <div class="bt-card">
        <div class="bt-label">最大回撤</div>
        <div class="bt-value" style="color:var(--danger)">{BACKTEST["max_drawdown"]}</div>
      </div>
    </div>
    <div class="backtest-grid" style="margin-top:8px;">
      <div class="bt-card">
        <div class="bt-label">创业板持有收益</div>
        <div class="bt-value" style="color:var(--muted)">{BACKTEST["cyb_hold_return"]}</div>
      </div>
      <div class="bt-card">
        <div class="bt-label">红利低波持有收益</div>
        <div class="bt-value" style="color:var(--muted)">{BACKTEST["hldb_hold_return"]}</div>
      </div>
      <div class="bt-card">
        <div class="bt-label">交易次数</div>
        <div class="bt-value">{BACKTEST["trade_count"]}</div>
      </div>
    </div>
    <div class="table-wrap" style="margin-top:12px;">
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>操作</th>
            <th>比值</th>
            <th>市值</th>
          </tr>
        </thead>
        <tbody>
"""

    for trade in BACKTEST["trades"]:
        html += f"""          <tr><td>{trade["date"]}</td><td>{trade["action"]}</td><td>{trade["ratio"]}</td><td>{trade["value"]}</td></tr>
"""

    html += f"""        </tbody>
      </table>
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <p>数据来源：AKShare（新浪财经 / 中证指数官网）</p>
    <p>策略逻辑：创业板与红利低波指数轮动，基于比值阈值判断</p>
    <p>⚠️ 本页面数据仅供参考，不构成投资建议</p>
    <p style="margin-top:4px;">
      <a href="javascript:location.reload()">刷新页面</a> 获取最新数据
    </p>
  </div>

</div>

</body>
</html>"""

    os.makedirs("public", exist_ok=True)
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"页面已生成: public/index.html ({len(html)} 字节)")
    print(f"最新信号: {signal}")
    print(f"比值: {ratio_pct:.2f}%")

if __name__ == "__main__":
    generate_page()