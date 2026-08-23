import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import math

# ─── 指数代码 ───────────────────────────────────────────────────
CYB_CODE = "399006"
HLDB_CODE = "H30269"

# ─── 策略参数 ───────────────────────────────────────────────────
BUY_THRESHOLD = 0.20
SELL_THRESHOLD = 0.40
INITIAL_CAPITAL = 1_000_000
BACKTEST_START = "2016-08-03"

# ─── 数据获取 ───────────────────────────────────────────────────
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

def normalize(df, close_col, date_col):
    d = df[[date_col, close_col]].copy()
    d.columns = ["date", "close"]
    d["date"] = pd.to_datetime(d["date"])
    d = d.sort_values("date").reset_index(drop=True)
    return d

def fmt_num(n, decimals=2):
    if pd.isna(n): return "N/A"
    return f"{n:,.{decimals}f}"

def pct_str(val):
    if val is None or pd.isna(val): return "N/A", "neutral"
    if val > 0: return f"+{val:.2f}%", "up"
    elif val < 0: return f"{val:.2f}%", "down"
    return "0.00%", "neutral"

# ─── SVG 绘图工具 ──────────────────────────────────────────────
def svg_path_from_data(x_vals, y_vals, svg_w, svg_h, pad_l, pad_r, pad_t, pad_b,
                       x_min=None, x_max=None, y_min=None, y_max=None):
    n = len(x_vals)
    if n < 2: return "", ""
    if x_min is None: x_min = min(x_vals)
    if x_max is None: x_max = max(x_vals)
    if y_min is None: y_min = min(y_vals)
    if y_max is None: y_max = max(y_vals)
    x_rng = x_max - x_min if x_max > x_min else 1
    y_rng = y_max - y_min if y_max > y_min else 1
    plot_w = svg_w - pad_l - pad_r
    plot_h = svg_h - pad_t - pad_b

    pts = []
    for i in range(n):
        sx = pad_l + ((x_vals[i] - x_min) / x_rng) * plot_w
        sy = pad_t + plot_h - ((y_vals[i] - y_min) / y_rng) * plot_h
        pts.append(f"{sx:.1f},{sy:.1f}")
    line = " ".join(pts)
    area = f"{pts[0]} {line} {pts[-1]}"
    return line, area

def svg_point(x, x_min, x_max, pad_l, plot_w):
    x_rng = x_max - x_min if x_max > x_min else 1
    return pad_l + ((x - x_min) / x_rng) * plot_w

# ─── 回测引擎 ───────────────────────────────────────────────────
def run_backtest(data):
    """在合并后的数据上运行回测，返回每日净值序列和回撤序列"""
    bd = data[(data['date'] >= BACKTEST_START)].copy().reset_index(drop=True)
    if len(bd) < 20:
        return None, None

    position = 'hldb'
    shares_cyb = 0.0
    shares_hldb = INITIAL_CAPITAL / bd.iloc[0]['close_hldb']

    cyb_start = bd.iloc[0]['close_cyb']
    hldb_start = bd.iloc[0]['close_hldb']

    nav_daily = []
    for _, row in bd.iterrows():
        cp, hp, ratio = row['close_cyb'], row['close_hldb'], row['ratio']
        mkt = shares_cyb * cp + shares_hldb * hp
        cyb_val = INITIAL_CAPITAL / cyb_start * cp
        hldb_val = INITIAL_CAPITAL / hldb_start * hp

        if position == 'hldb' and ratio < BUY_THRESHOLD:
            shares_cyb = mkt / cp
            shares_hldb = 0.0
            position = 'cyb'
        elif position == 'cyb' and ratio > SELL_THRESHOLD:
            shares_hldb = mkt / hp
            shares_cyb = 0.0
            position = 'hldb'

        nav_daily.append({
            'date': row['date'],
            'nav': mkt,
            'cyb_hold': cyb_val,
            'hldb_hold': hldb_val,
            'ratio': ratio,
            'position': position
        })

    nav_df = pd.DataFrame(nav_daily)

    # 回撤
    peak = np.maximum.accumulate(nav_df['nav'].values)
    drawdown = (nav_df['nav'].values - peak) / peak * 100
    max_dd = drawdown.min()
    max_dd_idx = np.argmin(drawdown)

    # 基准回撤
    cyb_peak = np.maximum.accumulate(nav_df['cyb_hold'].values)
    cyb_dd = (nav_df['cyb_hold'].values - cyb_peak) / cyb_peak * 100
    hldb_peak = np.maximum.accumulate(nav_df['hldb_hold'].values)
    hldb_dd = (nav_df['hldb_hold'].values - hldb_peak) / hldb_peak * 100

    nav_df['drawdown'] = drawdown
    nav_df['cyb_dd'] = cyb_dd
    nav_df['hldb_dd'] = hldb_dd

    return nav_df, max_dd

# ─── 主页面生成 ────────────────────────────────────────────────
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
    if "date" in cyb_df.columns:
        cyb = normalize(cyb_df, "close", "date")
    elif "日期" in cyb_df.columns:
        cyb = normalize(cyb_df, "收盘", "日期")
    else:
        print("ERROR: 无法识别创业板数据列名"); return

    if "date" in hldb_df.columns:
        hldb = normalize(hldb_df, "close", "date")
    elif "日期" in hldb_df.columns:
        hldb = normalize(hldb_df, "收盘", "日期")
    else:
        print("ERROR: 无法识别红利低波数据列名"); return

    merged = pd.merge(cyb, hldb, on="date", how="inner", suffixes=("_cyb", "_hldb"))
    merged = merged.dropna().reset_index(drop=True)
    if len(merged) < 20:
        print("ERROR: 数据不足"); return

    merged["ratio"] = merged["close_cyb"] / merged["close_hldb"]
    merged["cyb_pct"] = merged["close_cyb"].pct_change() * 100
    merged["hldb_pct"] = merged["close_hldb"].pct_change() * 100

    # ── 最新数据 ──
    latest = merged.iloc[-1]
    prev = merged.iloc[-2]
    latest_date = latest["date"]
    ratio = latest["ratio"]
    cyb_close = latest["close_cyb"]
    hldb_close = latest["close_hldb"]
    cyb_chg = latest["cyb_pct"]
    hldb_chg = latest["hldb_pct"]
    ratio_median = merged["ratio"].median()

    # 信号
    if ratio < BUY_THRESHOLD:
        signal, hold, signal_class = "买入创业板", "创业板指 (399006)", "buy-cyb"
        reason = f"比值 {ratio*100:.2f}% < 20%，创业板相对低估，建议买入创业板。"
    elif ratio > SELL_THRESHOLD:
        signal, hold, signal_class = "买入红利低波", "红利低波 (H30269)", "buy-hldb"
        reason = f"比值 {ratio*100:.2f}% > 40%，创业板相对高估，建议切换至红利低波。"
    else:
        if ratio < 0.30:
            signal, hold, signal_class = "建议持有创业板", "创业板指 (399006)", "hold-cyb"
            reason = f"比值 {ratio*100:.2f}%，处于20%-40%观望区间，偏创业板方向。"
        else:
            signal, hold, signal_class = "建议持有红利低波", "红利低波 (H30269)", "hold-hldb"
            reason = f"比值 {ratio*100:.2f}%，处于20%-40%观望区间，偏红利低波方向。"

    signal_colors = {
        "buy-cyb": {"bg": "linear-gradient(135deg, #e3f2fd, #fff)", "border": "#2196f3", "text": "#1565c0"},
        "buy-hldb": {"bg": "linear-gradient(135deg, #fce4ec, #fff)", "border": "#e91e63", "text": "#c62828"},
        "hold-cyb": {"bg": "linear-gradient(135deg, #e8f5e9, #fff)", "border": "#4caf50", "text": "#2e7d32"},
        "hold-hldb": {"bg": "linear-gradient(135deg, #fff8e1, #fff)", "border": "#ff9800", "text": "#e65100"},
    }
    sc = signal_colors.get(signal_class, signal_colors["hold-hldb"])

    # ── 运行回测 ──
    print("运行回测...")
    nav_df, max_dd = run_backtest(merged)
    if nav_df is None:
        print("ERROR: 回测失败"); return

    final_value = nav_df['nav'].iloc[-1]
    total_return_pct = (final_value / INITIAL_CAPITAL - 1) * 100
    years = (nav_df['date'].iloc[-1] - nav_df['date'].iloc[0]).days / 365.25
    annual_return_pct = ((final_value / INITIAL_CAPITAL) ** (1 / years) - 1) * 100

    cyb_hold_final = nav_df['cyb_hold'].iloc[-1]
    hldb_hold_final = nav_df['hldb_hold'].iloc[-1]
    cyb_return_pct = (cyb_hold_final / INITIAL_CAPITAL - 1) * 100
    hldb_return_pct = (hldb_hold_final / INITIAL_CAPITAL - 1) * 100

    cyb_nav = nav_df['cyb_hold'].values
    hldb_nav = nav_df['hldb_hold'].values
    cyb_peak = np.maximum.accumulate(cyb_nav)
    hldb_peak = np.maximum.accumulate(hldb_nav)
    cyb_max_dd = ((cyb_nav - cyb_peak) / cyb_peak * 100).min()
    hldb_max_dd = ((hldb_nav - hldb_peak) / hldb_peak * 100).min()
    current_drawdown = nav_df['drawdown'].iloc[-1]

    # 最新一日回撤
    latest_dd = nav_df['drawdown'].iloc[-1]
    latest_dd_str, _ = pct_str(latest_dd)

    # 交易记录
    trades = []
    pos = 'hldb'
    for _, row in nav_df.iterrows():
        r = row['ratio']
        if pos == 'hldb' and r < BUY_THRESHOLD:
            trades.append({'date': row['date'], 'action': '红利低波→创业板', 'ratio': r, 'nav': row['nav']})
            pos = 'cyb'
        elif pos == 'cyb' and r > SELL_THRESHOLD:
            trades.append({'date': row['date'], 'action': '创业板→红利低波', 'ratio': r, 'nav': row['nav']})
            pos = 'hldb'

    # ── SVG 收益曲线 ──
    # 采样：每5天取一个点，加上首尾
    sample_step = 5
    svg_idx = list(range(0, len(nav_df), sample_step))
    if svg_idx[-1] != len(nav_df) - 1:
        svg_idx.append(len(nav_df) - 1)

    svg_dates = [nav_df.iloc[i]['date'] for i in svg_idx]
    svg_nav = [nav_df.iloc[i]['nav'] / 1e6 for i in svg_idx]
    svg_cyb = [nav_df.iloc[i]['cyb_hold'] / 1e6 for i in svg_idx]
    svg_hldb = [nav_df.iloc[i]['hldb_hold'] / 1e6 for i in svg_idx]

    # 日期转数字用于SVG坐标
    ref_date = nav_df['date'].iloc[0]
    x_days = [(d - ref_date).days for d in svg_dates]

    W1, H1 = 900, 300
    pad_l, pad_r, pad_t, pad_b = 60, 30, 30, 40
    plot_w = W1 - pad_l - pad_r
    plot_h = H1 - pad_t - pad_b

    all_vals = svg_nav + svg_cyb + svg_hldb
    y_min = min(all_vals) * 0.95
    y_max = max(all_vals) * 1.05
    x_min, x_max = min(x_days), max(x_days)

    def sx(x):
        return pad_l + ((x - x_min) / (x_max - x_min if x_max > x_min else 1)) * plot_w
    def sy(v):
        return pad_t + plot_h - ((v - y_min) / (y_max - y_min if y_max > y_min else 1)) * plot_h

    nav_pts = " ".join(f"{sx(x_days[i]):.1f},{sy(svg_nav[i]):.1f}" for i in range(len(svg_idx)))
    cyb_pts = " ".join(f"{sx(x_days[i]):.1f},{sy(svg_cyb[i]):.1f}" for i in range(len(svg_idx)))
    hldb_pts = " ".join(f"{sx(x_days[i]):.1f},{sy(svg_hldb[i]):.1f}" for i in range(len(svg_idx)))

    # 交易标记
    trade_markers = ""
    for t in trades:
        td = (t['date'] - ref_date).days
        tx = sx(td)
        ty = sy(t['nav'] / 1e6)
        color = "#4caf50" if "红利低波→创业板" in t['action'] else "#f44336"
        trade_markers += f'<circle cx="{tx:.1f}" cy="{ty:.1f}" r="5" fill="{color}" stroke="#000" stroke-width="1.5"/>\n'

    # Y轴刻度
    y_ticks_equity = 5
    y_tick_labels_equity = ""
    for i in range(y_ticks_equity + 1):
        val = y_min + (i / y_ticks_equity) * (y_max - y_min)
        yy = sy(val)
        y_tick_labels_equity += f'<text x="{pad_l - 8}" y="{yy + 4}" text-anchor="end" font-size="11" fill="#6b7a8f">{val:.1f}</text>\n'

    # X轴刻度（取年份）
    year_ticks = []
    for yr in range(nav_df['date'].iloc[0].year, nav_df['date'].iloc[-1].year + 2):
        yr_dt = datetime(yr, 1, 1)
        if ref_date <= yr_dt <= nav_df['date'].iloc[-1]:
            year_ticks.append((yr, (yr_dt - ref_date).days))
    x_labels_equity = ""
    for yr, xd in year_ticks:
        xx = sx(xd)
        x_labels_equity += f'<text x="{xx:.1f}" y="{H1 - 8}" text-anchor="middle" font-size="11" fill="#6b7a8f">{yr}</text>\n'
        x_labels_equity += f'<line x1="{xx:.1f}" y1="{pad_t}" x2="{xx:.1f}" y2="{H1 - pad_b}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="4,4"/>\n'

    # 水平网格线
    grid_equity = ""
    for i in range(y_ticks_equity + 1):
        val = y_min + (i / y_ticks_equity) * (y_max - y_min)
        yy = sy(val)
        grid_equity += f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{W1 - pad_r}" y2="{yy:.1f}" stroke="#e2e8f0" stroke-width="1"/>\n'

    # ── SVG 回撤曲线 ──
    W2, H2 = 900, 200
    dd_dates_all = nav_df['date']
    dd_vals = nav_df['drawdown'].values
    dd_x_days = [(d - ref_date).days for d in dd_dates_all]

    # 采样（每5天）
    dd_svg_idx = list(range(0, len(nav_df), sample_step))
    if dd_svg_idx[-1] != len(nav_df) - 1:
        dd_svg_idx.append(len(nav_df) - 1)
    dd_svg_x = [dd_x_days[i] for i in dd_svg_idx]
    dd_svg_y = [dd_vals[i] for i in dd_svg_idx]

    dd_ylim = min(dd_vals) * 1.1
    pad_t2, pad_b2 = 20, 30
    plot_h2 = H2 - pad_t2 - pad_b2
    dd_range = 0 - dd_ylim if 0 > dd_ylim else 1

    def sy2(v):
        return pad_t2 + plot_h2 - ((v - dd_ylim) / dd_range) * plot_h2

    # 计算 dd_pts 和 area
    dd_pts = " ".join(f"{sx(dd_svg_x[i]):.1f},{sy2(dd_svg_y[i]):.1f}" for i in range(len(dd_svg_idx)))
    area_bottom = sy2(0)
    first_x = sx(dd_svg_x[0])
    last_x = sx(dd_svg_x[-1])
    area_pts = f"{first_x:.1f},{area_bottom:.1f} {dd_pts} {last_x:.1f},{area_bottom:.1f}"

    # 最大回撤标记
    max_dd_val = dd_vals.min()
    max_dd_date = dd_dates_all.iloc[np.argmin(dd_vals)]
    max_dd_x = sx((max_dd_date - ref_date).days)
    max_dd_y = sy2(max_dd_val)

    # 最新回撤标记
    latest_dd_x = sx(dd_x_days[-1])
    latest_dd_y = sy2(dd_vals[-1])

    # DD Y轴刻度
    dd_y_ticks = ""
    for i in range(5):
        val = dd_ylim + (i / 4) * (0 - dd_ylim)
        yy = sy2(val)
        if i == 0:
            dd_y_ticks += f'<text x="{pad_l - 8}" y="{yy + 4}" text-anchor="end" font-size="11" fill="#6b7a8f">{val:.0f}%</text>\n'
        elif i == 4:
            dd_y_ticks += f'<text x="{pad_l - 8}" y="{yy + 4}" text-anchor="end" font-size="11" fill="#6b7a8f">0%</text>\n'
        else:
            dd_y_ticks += f'<text x="{pad_l - 8}" y="{yy + 4}" text-anchor="end" font-size="11" fill="#6b7a8f">{val:.0f}%</text>\n'

    # DD 网格线
    dd_grid = ""
    for i in range(5):
        val = dd_ylim + (i / 4) * (0 - dd_ylim)
        yy = sy2(val)
        dd_grid += f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{W1 - pad_r}" y2="{yy:.1f}" stroke="#e2e8f0" stroke-width="1"/>\n'

    # DD X轴标签（复用年份）
    dd_x_labels = ""
    for yr, xd in year_ticks:
        xx = sx(xd)
        dd_x_labels += f'<text x="{xx:.1f}" y="{H2 - 4}" text-anchor="middle" font-size="11" fill="#6b7a8f">{yr}</text>\n'

    # ── 完整历史比值图SVG ──
    rh = nav_df.copy()
    rh_ratio = rh['ratio'].values * 100
    rh_min = max(0, rh_ratio.min() - 2)
    rh_max = min(60, rh_ratio.max() + 2)
    rh_ref = rh['date'].iloc[0]
    rh_x_days = [(d - rh_ref).days for d in rh['date']]
    rh_x_min, rh_x_max = rh_x_days[0], rh_x_days[-1]

    # 采样（每5天）
    rh_step = 5
    rh_idx = list(range(0, len(rh), rh_step))
    if rh_idx[-1] != len(rh) - 1: rh_idx.append(len(rh) - 1)
    rh_sx = [rh_x_days[i] for i in rh_idx]
    rh_sy = [rh_ratio[i] for i in rh_idx]

    RHW, RHH = 900, 300
    rh_pl, rh_pr, rh_pt, rh_pb = 60, 30, 30, 40
    rh_plot_w = RHW - rh_pl - rh_pr
    rh_plot_h = RHH - rh_pt - rh_pb
    rh_x_rng = rh_x_max - rh_x_min if rh_x_max > rh_x_min else 1
    rh_y_rng = rh_max - rh_min if rh_max > rh_min else 1

    def rhx(x): return rh_pl + ((x - rh_x_min) / rh_x_rng) * rh_plot_w
    def rhy(v): return rh_pt + rh_plot_h - ((v - rh_min) / rh_y_rng) * rh_plot_h

    # 比值线
    rh_line = " ".join(f"{rhx(rh_sx[i]):.1f},{rhy(rh_sy[i]):.1f}" for i in range(len(rh_idx)))

    # 持有区间背景（20%-40%）
    rh_hold_top = rhy(40)
    rh_hold_btm = rhy(20)
    rh_gray_area = f"{rhx(rh_x_min):.1f},{rh_hold_top:.1f} {rhx(rh_x_max):.1f},{rh_hold_top:.1f} {rhx(rh_x_max):.1f},{rh_hold_btm:.1f} {rhx(rh_x_min):.1f},{rh_hold_btm:.1f}"

    # 买卖信号标记
    rh_buy_markers = ""
    rh_sell_markers = ""
    for tidx, t in enumerate(trades):
        td = (t['date'] - rh_ref).days
        tx_pos = rhx(td)
        ty_pos = rhy(t['ratio'] * 100)
        is_buy = "红利低波→创业板" in t['action']
        if is_buy:
            # 绿色三角形（买入）
            rh_buy_markers += f'<polygon points="{tx_pos:.1f},{ty_pos-10:.1f} {tx_pos-6:.1f},{ty_pos+4:.1f} {tx_pos+6:.1f},{ty_pos+4:.1f}" fill="#4caf50" stroke="#000" stroke-width="0.5"/>\n'
        else:
            # 红色倒三角形（卖出）
            rh_sell_markers += f'<polygon points="{tx_pos:.1f},{ty_pos+10:.1f} {tx_pos-6:.1f},{ty_pos-4:.1f} {tx_pos+6:.1f},{ty_pos-4:.1f}" fill="#f44336" stroke="#000" stroke-width="0.5"/>\n'

    # Y轴刻度
    rh_y_ticks = ""
    for i in range(5):
        val = rh_max - (i / 4) * (rh_max - rh_min)
        yy = rhy(val)
        rh_y_ticks += f'<text x="{rh_pl - 8}" y="{yy + 4:.1f}" text-anchor="end" font-size="11" fill="#6b7a8f">{val:.1f}%</text>\n'

    # X轴刻度（年份）
    rh_x_labels = ""
    rh_x_grid = ""
    for yr in range(rh['date'].iloc[0].year, rh['date'].iloc[-1].year + 2):
        yr_dt = datetime(yr, 1, 1)
        if rh_ref <= yr_dt <= rh['date'].iloc[-1]:
            xx = rhx((yr_dt - rh_ref).days)
            rh_x_labels += f'<text x="{xx:.1f}" y="{RHH - 8}" text-anchor="middle" font-size="11" fill="#6b7a8f">{yr}</text>\n'
            rh_x_grid += f'<line x1="{xx:.1f}" y1="{rh_pt}" x2="{xx:.1f}" y2="{RHH - rh_pb}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="4,4"/>\n'

    # 水平网格线
    rh_grid = ""
    for i in range(5):
        val = rh_max - (i / 4) * (rh_max - rh_min)
        yy = rhy(val)
        rh_grid += f'<line x1="{rh_pl}" y1="{yy:.1f}" x2="{RHW - rh_pr}" y2="{yy:.1f}" stroke="#e2e8f0" stroke-width="1"/>\n'

    # 阈值线
    rh_buy_line_y = rhy(20)
    rh_sell_line_y = rhy(40)

    # ── 近5日数据 ──
    recent_5 = merged.tail(5).iloc[::-1]

    # ── 60日趋势SVG（与原网页一致）──
    trend_60 = merged.tail(60).reset_index(drop=True)
    tr_min = trend_60["ratio"].min() * 100
    tr_max = trend_60["ratio"].max() * 100
    tr_pad = (tr_max - tr_min) * 0.1 or 5
    tr_y_min = tr_min - tr_pad
    tr_y_max = tr_max + tr_pad

    TW, TH = 800, 240
    t_pad_l, t_pad_r, t_pad_t, t_pad_b = 50, 30, 20, 30
    t_plot_w = TW - t_pad_l - t_pad_r
    t_plot_h = TH - t_pad_t - t_pad_b

    def tx(idx):
        return t_pad_l + (idx / (len(trend_60) - 1)) * t_plot_w
    def ty(val_pct):
        rng = tr_y_max - tr_y_min if tr_y_max > tr_y_min else 1
        return t_pad_t + t_plot_h - ((val_pct - tr_y_min) / rng) * t_plot_h

    tr_pts = " ".join(f"{tx(i):.1f},{ty(row['ratio']*100):.1f}" for i, (_, row) in enumerate(trend_60.iterrows()))
    tr_area_bottom = t_pad_t + t_plot_h
    tr_area = f"{tx(0):.1f},{tr_area_bottom:.1f} {tr_pts} {tx(len(trend_60)-1):.1f},{tr_area_bottom:.1f}"

    buy_line_y = ty(20)
    sell_line_y = ty(40)

    # 5条水平网格线 & Y轴标签
    tr_grid_lines = ""
    tr_y_labels = ""
    for i in range(5):
        val_pct = tr_y_max - (i / 4) * (tr_y_max - tr_y_min)
        yy = ty(val_pct)
        tr_grid_lines += f'<line x1="{t_pad_l}" y1="{yy:.1f}" x2="{TW - t_pad_r}" y2="{yy:.1f}" stroke="#e2e8f0" stroke-width="1"/>\n'
        tr_y_labels += f'<text x="{t_pad_l - 8}" y="{yy + 4:.1f}" text-anchor="end" font-size="11" fill="#6b7a8f">{val_pct:.1f}%</text>\n'

    # 7个均匀X轴标签
    tr_x_labels = ""
    for i in range(7):
        idx = int((i / 6) * (len(trend_60) - 1))
        xx = tx(idx)
        tr_x_labels += f'<text x="{xx:.1f}" y="{TH - 4}" text-anchor="middle" font-size="10" fill="#6b7a8f">{trend_60.iloc[idx]["date"].strftime("%m-%d")}</text>\n'

    # 近5日表格
    recent_rows = ""
    for _, row in recent_5.iterrows():
        c_str, c_cls = pct_str(row["cyb_pct"])
        h_str, h_cls = pct_str(row["hldb_pct"])
        r_val = row["ratio"] * 100
        recent_rows += f"""          <tr>
            <td>{row['date'].strftime('%m-%d')}</td>
            <td>{fmt_num(row['close_cyb'])}</td>
            <td class="{c_cls}">{c_str}</td>
            <td>{fmt_num(row['close_hldb'])}</td>
            <td class="{h_cls}">{h_str}</td>
            <td>{r_val:.2f}%</td>
          </tr>\n"""

    # 交易记录表格
    trade_rows = ""
    for t in trades:
        trade_rows += f"""          <tr><td>{t['date'].strftime('%Y-%m-%d')}</td><td>{t['action']}</td><td>{t['ratio']*100:.2f}%</td><td>{fmt_num(t['nav'])}</td></tr>\n"""

    # ── 生成HTML ──
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    ratio_pct = ratio * 100
    ratio_median_pct = ratio_median * 100
    ratio_pos = min(98, max(2, ((ratio_pct - 0) / (60 - 0)) * 100))
    cyb_chg_str, cyb_chg_cls = pct_str(cyb_chg)
    hldb_chg_str, hldb_chg_cls = pct_str(hldb_chg)

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
.header {{ text-align: center; padding: 32px 0 24px; }}
.header h1 {{ font-size: 28px; font-weight: 700; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.header .subtitle {{ color: var(--muted); font-size: 14px; margin-top: 4px; }}
.header .update-time {{ color: var(--muted); font-size: 13px; margin-top: 8px; }}

.signal-card {{ background: {sc['bg']}; border-radius: var(--radius); box-shadow: var(--shadow); padding: 28px 24px; margin-bottom: 20px; border-left: 5px solid {sc['border']}; }}
.signal-card .signal-label {{ font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
.signal-card .signal-value {{ font-size: 32px; font-weight: 800; color: {sc['text']}; }}
.signal-card .signal-reason {{ font-size: 14px; color: var(--muted); margin-top: 8px; line-height: 1.5; }}

.stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }}
.stat-card {{ background: var(--bg2); border-radius: var(--radius); box-shadow: var(--shadow); padding: 16px; text-align: center; }}
.stat-card .stat-label {{ font-size: 12px; color: var(--muted); margin-bottom: 4px; }}
.stat-card .stat-value {{ font-size: 22px; font-weight: 700; }}
.stat-card .stat-change {{ font-size: 12px; margin-top: 2px; }}
.up {{ color: var(--danger); }} .down {{ color: var(--success); }} .neutral {{ color: var(--muted); }}

.ratio-bar-wrap {{ background: var(--bg2); border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px 24px; margin-bottom: 20px; }}
.ratio-bar-title {{ font-size: 14px; font-weight: 600; margin-bottom: 12px; }}
.ratio-bar {{ position: relative; height: 40px; background: linear-gradient(to right, #4caf50, #8bc34a, #ffeb3b, #ff9800, #f44336); border-radius: 8px; margin: 16px 0; }}
.ratio-marker {{ position: absolute; top: -8px; width: 4px; height: 56px; background: #1a2332; border-radius: 2px; transition: left 0.5s ease; }}
.ratio-marker::after {{ content: ''; position: absolute; top: -6px; left: -5px; width: 14px; height: 14px; background: #1a2332; border-radius: 50%; }}
.ratio-labels {{ display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); margin-top: 4px; }}
.ratio-value-label {{ text-align: center; font-size: 24px; font-weight: 800; color: var(--accent); }}
.ratio-thresholds {{ display: flex; justify-content: space-between; font-size: 12px; margin-top: 4px; }}
.ratio-thresholds .buy {{ color: #4caf50; font-weight: 600; }}
.ratio-thresholds .sell {{ color: #f44336; font-weight: 600; }}

.section {{ background: var(--bg2); border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px 24px; margin-bottom: 20px; }}
.section-title {{ font-size: 16px; font-weight: 700; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 2px solid var(--rule); }}
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th {{ background: var(--bg); padding: 10px 12px; text-align: right; font-weight: 600; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 2px solid var(--rule); }}
th:first-child {{ text-align: left; }}
td {{ padding: 10px 12px; text-align: right; border-bottom: 1px solid var(--rule); }}
td:first-child {{ text-align: left; font-weight: 600; }}

.rules-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }}
.rule-card {{ padding: 14px; border-radius: 8px; border: 1px solid var(--rule); }}
.rule-card.buy {{ border-left: 4px solid #4caf50; }}
.rule-card.sell {{ border-left: 4px solid #f44336; }}
.rule-card.hold {{ border-left: 4px solid #2196f3; }}
.rule-card .rule-title {{ font-size: 14px; font-weight: 700; margin-bottom: 4px; }}
.rule-card .rule-desc {{ font-size: 13px; color: var(--muted); }}

.backtest-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px; }}
.bt-card {{ text-align: center; padding: 14px; border-radius: 8px; border: 1px solid var(--rule); }}
.bt-card .bt-label {{ font-size: 12px; color: var(--muted); margin-bottom: 4px; }}
.bt-card .bt-value {{ font-size: 20px; font-weight: 700; }}

.chart-wrap {{ background: var(--bg2); border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px 24px; margin-bottom: 20px; overflow: hidden; }}
.chart-wrap svg {{ width: 100%; height: auto; }}
.axis-chart {{ margin-top: 12px; }}
.axis-chart svg {{ width: 100%; height: auto; }}
.legend {{ display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 12px; font-size: 13px; }}
.legend-item {{ display: flex; align-items: center; gap: 6px; }}
.legend-dot {{ width: 14px; height: 3px; border-radius: 2px; }}

.footer {{ text-align: center; padding: 20px; color: var(--muted); font-size: 12px; line-height: 1.8; }}
.footer a {{ color: var(--accent); text-decoration: none; }}

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
      <div class="stat-change neutral">交易日 {latest_date.strftime('%Y-%m-%d')}</div>
    </div>
  </div>

  <!-- Ratio Bar -->
  <div class="ratio-bar-wrap">
    <div class="ratio-bar-title">比值位置</div>
    <div class="ratio-value-label">{ratio_pct:.2f}%</div>
    <div class="ratio-bar">
      <div class="ratio-marker" style="left: {ratio_pos:.2f}%;"></div>
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

  <!-- Recent 5 Days -->
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
{recent_rows}
        </tbody>
      </table>
    </div>
  </div>

  <!-- 60-day Trend -->
  <div class="section">
    <div class="section-title">近60日比值趋势</div>
    <div class="axis-chart" style="padding:10px 0;">
      <svg viewBox="0 0 {TW} {TH}" xmlns="http://www.w3.org/2000/svg">
        {tr_grid_lines}
        <line x1="{t_pad_l}" y1="{buy_line_y:.1f}" x2="{TW - t_pad_r}" y2="{buy_line_y:.1f}" stroke="#4caf50" stroke-width="1.5" stroke-dasharray="6,3"/>
        <text x="{TW - t_pad_r + 4}" y="{buy_line_y + 4:.1f}" font-size="10" fill="#4caf50">买入 20%</text>
        <line x1="{t_pad_l}" y1="{sell_line_y:.1f}" x2="{TW - t_pad_r}" y2="{sell_line_y:.1f}" stroke="#f44336" stroke-width="1.5" stroke-dasharray="6,3"/>
        <text x="{TW - t_pad_r + 4}" y="{sell_line_y + 4:.1f}" font-size="10" fill="#f44336">卖出 40%</text>
        <polygon points="{tr_area}" fill="rgba(37, 99, 235, 0.1)"/>
        <polyline points="{tr_pts}" fill="none" stroke="#2563eb" stroke-width="2" stroke-linejoin="round"/>
        {tr_y_labels}
        {tr_x_labels}
      </svg>
    </div>
  </div>

  <!-- Equity Curve Chart -->
  <div class="chart-wrap">
    <div class="section-title">回测收益曲线（{nav_df['date'].iloc[0].strftime('%Y')} - {nav_df['date'].iloc[-1].strftime('%Y')}）</div>
    <div class="legend">
      <div class="legend-item"><span class="legend-dot" style="background:#2563eb;"></span> 轮动策略</div>
      <div class="legend-item"><span class="legend-dot" style="background:#e74c3c;"></span> 创业板持有</div>
      <div class="legend-item"><span class="legend-dot" style="background:#10b981;"></span> 红利低波持有</div>
      <div class="legend-item"><span class="legend-dot" style="background:transparent;border:1px dashed #666;"></span> 买卖信号</div>
    </div>
    <svg viewBox="0 0 {W1} {H1}" xmlns="http://www.w3.org/2000/svg">
      {grid_equity}
      {y_tick_labels_equity}
      {x_labels_equity}
      <polyline points="{nav_pts}" fill="none" stroke="#2563eb" stroke-width="2" stroke-linejoin="round"/>
      <polyline points="{cyb_pts}" fill="none" stroke="#e74c3c" stroke-width="1.5" stroke-dasharray="6,3" stroke-linejoin="round"/>
      <polyline points="{hldb_pts}" fill="none" stroke="#10b981" stroke-width="1.5" stroke-dasharray="6,3" stroke-linejoin="round"/>
      {trade_markers}
      <text x="{W1 - pad_r}" y="{pad_t + 12}" text-anchor="end" font-size="12" font-weight="bold" fill="#2563eb">策略: {total_return_pct:.1f}%</text>
      <text x="{W1 - pad_r}" y="{pad_t + 28}" text-anchor="end" font-size="11" fill="#e74c3c">创业板: {cyb_return_pct:.1f}%</text>
      <text x="{W1 - pad_r}" y="{pad_t + 44}" text-anchor="end" font-size="11" fill="#10b981">红利低波: {hldb_return_pct:.1f}%</text>
    </svg>
  </div>

  <!-- Drawdown Chart -->
  <div class="chart-wrap">
    <div class="section-title">回撤曲线（最新回撤: {latest_dd:.2f}%）</div>
    <svg viewBox="0 0 {W1} {H2}" xmlns="http://www.w3.org/2000/svg">
      {dd_grid}
      <line x1="{pad_l}" y1="{sy2(0):.1f}" x2="{W1 - pad_r}" y2="{sy2(0):.1f}" stroke="#333" stroke-width="1"/>
      <polygon points="{area_pts}" fill="rgba(239, 68, 68, 0.2)"/>
      <polyline points="{dd_pts}" fill="none" stroke="#ef4444" stroke-width="1.5" stroke-linejoin="round"/>
      {dd_y_ticks}
      {dd_x_labels}
      <line x1="{max_dd_x:.1f}" y1="{max_dd_y:.1f}" x2="{max_dd_x:.1f}" y2="{sy2(0):.1f}" stroke="#dc2626" stroke-width="1" stroke-dasharray="4,4"/>
      <circle cx="{max_dd_x:.1f}" cy="{max_dd_y:.1f}" r="4" fill="#dc2626"/>
      <text x="{max_dd_x + 4:.1f}" y="{max_dd_y - 4:.1f}" font-size="11" fill="#dc2626" font-weight="bold">最大回撤 {max_dd:.1f}%</text>
      <circle cx="{latest_dd_x:.1f}" cy="{latest_dd_y:.1f}" r="4" fill="#2563eb"/>
      <text x="{latest_dd_x + 4:.1f}" y="{latest_dd_y - 4:.1f}" font-size="11" fill="#2563eb">最新 {latest_dd:.2f}%</text>
    </svg>
  </div>

  <!-- Full Historical Ratio Chart -->
  <div class="chart-wrap">
    <div class="section-title">创业板/红利低波 历史比值（{nav_df['date'].iloc[0].strftime('%Y')} - {nav_df['date'].iloc[-1].strftime('%Y')}）</div>
    <div class="legend" style="margin-bottom:8px;">
      <div class="legend-item"><span class="legend-dot" style="background:#2563eb;"></span> 创业板/红利低波 比值(%)</div>
      <div class="legend-item"><span class="legend-dot" style="background:#4caf50;border:1px dashed #4caf50;"></span> 买入阈值 20%</div>
      <div class="legend-item"><span class="legend-dot" style="background:#f44336;border:1px dashed #f44336;"></span> 卖出阈值 40%</div>
      <div class="legend-item"><span class="legend-dot" style="background:#e2e8f0;"></span> 持有区间</div>
    </div>
    <svg viewBox="0 0 {RHW} {RHH}" xmlns="http://www.w3.org/2000/svg">
      {rh_grid}
      {rh_x_grid}
      <polygon points="{rh_gray_area}" fill="rgba(226, 232, 240, 0.5)"/>
      <line x1="{rh_pl}" y1="{rh_buy_line_y:.1f}" x2="{RHW - rh_pr}" y2="{rh_buy_line_y:.1f}" stroke="#4caf50" stroke-width="1.5" stroke-dasharray="6,3"/>
      <text x="{RHW - rh_pr + 4}" y="{rh_buy_line_y + 4:.1f}" font-size="10" fill="#4caf50">买入 20%</text>
      <line x1="{rh_pl}" y1="{rh_sell_line_y:.1f}" x2="{RHW - rh_pr}" y2="{rh_sell_line_y:.1f}" stroke="#f44336" stroke-width="1.5" stroke-dasharray="6,3"/>
      <text x="{RHW - rh_pr + 4}" y="{rh_sell_line_y + 4:.1f}" font-size="10" fill="#f44336">卖出 40%</text>
      <polyline points="{rh_line}" fill="none" stroke="#2563eb" stroke-width="2" stroke-linejoin="round"/>
      {rh_buy_markers}
      {rh_sell_markers}
      {rh_y_ticks}
      {rh_x_labels}
    </svg>
    <div style="text-align:center;font-size:12px;color:#6b7a8f;margin-top:6px;">
      <span style="display:inline-block;width:12px;height:12px;background:#4caf50;clip-path:polygon(50% 0%, 0% 100%, 100% 100%);margin-right:2px;"></span> 买入信号
      &nbsp;&nbsp;
      <span style="display:inline-block;width:12px;height:12px;background:#f44336;clip-path:polygon(0% 0%, 100% 0%, 50% 100%);margin-right:2px;"></span> 卖出信号
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
    <div class="section-title">回测结果（{nav_df['date'].iloc[0].strftime('%Y.%m')} - {nav_df['date'].iloc[-1].strftime('%Y.%m')}）</div>
    <div class="backtest-grid">
      <div class="bt-card">
        <div class="bt-label">总收益率</div>
        <div class="bt-value" style="color:var(--accent)">{total_return_pct:.2f}%</div>
      </div>
      <div class="bt-card">
        <div class="bt-label">年化收益率</div>
        <div class="bt-value" style="color:var(--accent)">{annual_return_pct:.2f}%</div>
      </div>
      <div class="bt-card">
        <div class="bt-label">最大回撤</div>
        <div class="bt-value" style="color:var(--danger)">{max_dd:.2f}%</div>
      </div>
    </div>
    <div class="backtest-grid" style="margin-top:8px;">
      <div class="bt-card">
        <div class="bt-label">创业板持有收益</div>
        <div class="bt-value" style="color:var(--muted)">{cyb_return_pct:.2f}%</div>
      </div>
      <div class="bt-card">
        <div class="bt-label">红利低波持有收益</div>
        <div class="bt-value" style="color:var(--muted)">{hldb_return_pct:.2f}%</div>
      </div>
      <div class="bt-card">
        <div class="bt-label">交易次数</div>
        <div class="bt-value">{len(trades)} 次</div>
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
{trade_rows}
        </tbody>
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
    print(f"回测总收益: {total_return_pct:.2f}% | 年化: {annual_return_pct:.2f}% | 最大回撤: {max_dd:.2f}%")
    print(f"最新回撤: {latest_dd:.2f}%")

if __name__ == "__main__":
    generate_page()