import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import math
import io
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

# ─── 指数代码 ───────────────────────────────────────────────────
CYB_CODE = "399006"
HLDB_CODE = "H30269"

# ─── 策略参数（固定阈值）────────────────────────────────────────
BUY_THRESHOLD = 0.20     # 比值 < 20% → 买入创业板
SELL_THRESHOLD = 0.40    # 比值 > 40% → 卖出创业板（买入红利低波）
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

# ─── 回测引擎 ───────────────────────────────────────────────────
def run_backtest(data):
    bd = data[(data['date'] >= BACKTEST_START)].copy().reset_index(drop=True)
    if len(bd) < 20: return None, None

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
            shares_cyb = mkt / cp; shares_hldb = 0.0; position = 'cyb'
        elif position == 'cyb' and ratio > SELL_THRESHOLD:
            shares_hldb = mkt / hp; shares_cyb = 0.0; position = 'hldb'
        nav_daily.append({'date': row['date'], 'nav': mkt, 'cyb_hold': cyb_val, 'hldb_hold': hldb_val,
                          'ratio': ratio, 'position': position})

    nav_df = pd.DataFrame(nav_daily)
    peak = np.maximum.accumulate(nav_df['nav'].values)
    nav_df['drawdown'] = (nav_df['nav'].values - peak) / peak * 100
    max_dd = nav_df['drawdown'].min()
    return nav_df, max_dd

# ─── matplotlib 三面板图 ─────────────────────────────────────────
def setup_chinese_font():
    """设置中文字体，确保matplotlib正确渲染中文"""
    plt.rcParams['axes.unicode_minus'] = False
    try:
        import matplotlib.font_manager as fm
        # 刷新字体缓存
        fm._load_fontmanager(try_read_cache=False)
        # 查找系统中所有可用字体
        available = sorted(set([f.name for f in fm.fontManager.ttflist]))
        candidates = ['Noto Sans CJK SC', 'Noto Sans CJK JP', 'WenQuanYi Micro Hei',
                      'Noto Sans SC', 'Noto Sans', 'SimHei', 'Microsoft YaHei']
        for c in candidates:
            if c in available:
                plt.rcParams['font.sans-serif'] = [c, 'DejaVu Sans']
                print(f"使用字体: {c}")
                return True
        # 任何支持中文的字体
        cn_fonts = [f for f in available if any(k in f.lower() for k in ['cjk', 'noto', 'hei', 'song', 'ming', 'fang', 'kai', 'chinese', 'wenquanyi'])]
        if cn_fonts:
            plt.rcParams['font.sans-serif'] = [cn_fonts[0], 'DejaVu Sans']
            print(f"使用字体: {cn_fonts[0]}")
            return True
    except Exception as e:
        print(f"字体检测异常: {e}")
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
    print("未找到中文字体，使用DejaVu Sans（中文可能显示为方框）")
    return False

def generate_chart(nav_df, trades, max_dd):
    """生成三面板图表并返回base64编码的SVG"""
    has_cn = setup_chinese_font()

    # 回测数据
    dates = nav_df['date'].values
    nav = nav_df['nav'].values
    cyb = nav_df['cyb_hold'].values
    hldb = nav_df['hldb_hold'].values
    ratios = nav_df['ratio'].values * 100
    dd = nav_df['drawdown'].values

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 9),
                                         gridspec_kw={'height_ratios': [3, 2, 1.5]})
    fig.patch.set_facecolor('white')

    # 公共样式
    for ax in [ax1, ax2, ax3]:
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_facecolor('#fafafa')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    # ── Panel 1: 净值曲线 ──
    ax1.plot(dates, nav / 1e6, color='#2563eb', linewidth=2, label='轮动策略', zorder=5)
    ax1.plot(dates, cyb / 1e6, color='#e74c3c', linewidth=1.5, linestyle='--', alpha=0.7, label='创业板（持有）')
    ax1.plot(dates, hldb / 1e6, color='#10b981', linewidth=1.5, linestyle='-.', alpha=0.7, label='红利低波（持有）')

    # 买卖标记
    for t in trades:
        td = t['date']
        tv = t['nav'] / 1e6
        is_buy = "红利低波→创业板" in t['action']
        color = '#4caf50' if is_buy else '#f44336'
        marker = '^' if is_buy else 'v'
        ax1.scatter(td, tv, c=color, s=100, marker=marker, edgecolors='black', linewidth=0.5, zorder=10)

    # 最大回撤标注
    max_dd_idx = np.argmin(dd)
    max_dd_date = dates[max_dd_idx]
    max_dd_val = nav[max_dd_idx] / 1e6
    label = '最大回撤: -37.4%' if not has_cn else f'最大回撤: {max_dd:.1f}%'
    ax1.annotate(label, xy=(max_dd_date, max_dd_val),
                 xytext=(max_dd_date, max_dd_val * 1.15),
                 fontsize=10, color='#dc2626', fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#dc2626', alpha=0.9),
                 arrowprops=dict(arrowstyle='->', color='#dc2626', lw=1.5))

    ax1.set_ylabel('资产（百万元）', fontsize=11)
    ax1.set_title('轮动策略 vs 持有策略 收益对比（初始资产 100万元）', fontsize=13, fontweight='bold', pad=10)
    ax1.legend(loc='upper left', fontsize=10, framealpha=0.9)
    ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.1f}'))
    ax1.set_ylim(0, max(nav / 1e6) * 1.2)

    # ── Panel 2: 比值图 ──
    ax2.fill_between(dates, 20, 40, alpha=0.15, color='#9ca3af', label='持有区间' if has_cn else 'Hold Zone')
    ax2.axhline(y=20, color='#4caf50', linewidth=1.5, linestyle='--', label='买入阈值（20%）' if has_cn else 'Buy 20%')
    ax2.axhline(y=40, color='#f44336', linewidth=1.5, linestyle='--', label='卖出阈值（40%）' if has_cn else 'Sell 40%')
    ax2.plot(dates, ratios, color='#2563eb', linewidth=2, label='创业板/红利低波 比值(%)')

    for t in trades:
        td = t['date']
        tr = t['ratio'] * 100
        is_buy = "红利低波→创业板" in t['action']
        color = '#4caf50' if is_buy else '#f44336'
        marker = '^' if is_buy else 'v'
        ax2.scatter(td, tr, c=color, s=120, marker=marker, edgecolors='black', linewidth=0.5, zorder=10)

    ax2.set_ylabel('比值（%）', fontsize=11)
    ax2.set_ylim(10, 50)
    ax2.legend(loc='upper left', fontsize=9, framealpha=0.9, ncol=2)

    # ── Panel 3: 回撤曲线 ──
    ax3.fill_between(dates, 0, dd, color='#ef4444', alpha=0.3)
    ax3.plot(dates, dd, color='#ef4444', linewidth=1.5)
    ax3.axhline(y=0, color='#333', linewidth=0.8)
    ax3.scatter(max_dd_date, max_dd, c='#dc2626', s=50, zorder=10)
    label2 = f'Max DD: {max_dd:.1f}%' if not has_cn else f'最大回撤 {max_dd:.1f}%'
    ax3.annotate(label2, xy=(max_dd_date, max_dd),
                 xytext=(max_dd_date, max_dd * 1.5),
                 fontsize=10, color='#dc2626', fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#dc2626', alpha=0.9),
                 arrowprops=dict(arrowstyle='->', color='#dc2626', lw=1.5))
    ax3.set_ylabel('回撤（%）', fontsize=11)
    ax3.set_xlabel('日期', fontsize=11)
    ax3.set_ylim(min(dd) * 1.3, 5)

    # X轴格式
    for ax in [ax1, ax2, ax3]:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.tick_params(axis='x', labelsize=9)

    plt.tight_layout(pad=2.0)

    # 保存为SVG并base64编码
    buf = io.BytesIO()
    plt.savefig(buf, format='svg', dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    svg_str = buf.getvalue().decode('utf-8')
    # 提取<svg>标签内的内容
    svg_start = svg_str.find('<svg ')
    svg_end = svg_str.find('</svg>') + 6
    return svg_str[svg_start:svg_end]

# ─── 主页面生成 ────────────────────────────────────────────────
def generate_page():
    print("正在获取指数数据...")

    cyb_df = fetch_index_data(CYB_CODE, market="sz")
    if cyb_df is None: print("ERROR: 无法获取创业板指数据"); return
    hldb_df = fetch_index_data(HLDB_CODE)
    if hldb_df is None: print("ERROR: 无法获取红利低波指数数据"); return

    if "date" in cyb_df.columns: cyb = normalize(cyb_df, "close", "date")
    elif "日期" in cyb_df.columns: cyb = normalize(cyb_df, "收盘", "日期")
    else: print("ERROR: 无法识别创业板数据列名"); return

    if "date" in hldb_df.columns: hldb = normalize(hldb_df, "close", "date")
    elif "日期" in hldb_df.columns: hldb = normalize(hldb_df, "收盘", "日期")
    else: print("ERROR: 无法识别红利低波数据列名"); return

    merged = pd.merge(cyb, hldb, on="date", how="inner", suffixes=("_cyb", "_hldb"))
    merged = merged.dropna().reset_index(drop=True)
    if len(merged) < 20: print("ERROR: 数据不足"); return

    merged["ratio"] = merged["close_cyb"] / merged["close_hldb"]
    merged["cyb_pct"] = merged["close_cyb"].pct_change() * 100
    merged["hldb_pct"] = merged["close_hldb"].pct_change() * 100

    # 最新数据
    latest = merged.iloc[-1]
    prev = merged.iloc[-2]
    latest_date = latest["date"]
    ratio = latest["ratio"]
    cyb_close = latest["close_cyb"]
    hldb_close = latest["close_hldb"]
    cyb_chg = latest["cyb_pct"]
    hldb_chg = latest["hldb_pct"]
    ratio_median = merged["ratio"].median()

    # 信号（基于固定阈值）
    ratio_pct = ratio * 100
    if ratio_pct < 20:
        signal, hold, signal_class, reason = "买入创业板", "创业板指 (399006)", "buy-cyb", \
            f"比值 {ratio_pct:.2f}% < 20%，创业板相对低估，建议买入创业板。"
    elif ratio_pct > 40:
        signal, hold, signal_class, reason = "买入红利低波", "红利低波 (H30269)", "buy-hldb", \
            f"比值 {ratio_pct:.2f}% > 40%，创业板相对高估，建议切换至红利低波。"
    else:
        if ratio_pct < 30:
            signal, hold, signal_class, reason = "建议持有创业板", "创业板指 (399006)", "hold-cyb", \
                f"比值 {ratio_pct:.2f}%，处于20%-40%观望区间，偏创业板方向。"
        else:
            signal, hold, signal_class, reason = "建议持有红利低波", "红利低波 (H30269)", "hold-hldb", \
                f"比值 {ratio_pct:.2f}%，处于20%-40%观望区间，偏红利低波方向。"

    signal_colors = {
        "buy-cyb": {"bg": "linear-gradient(135deg, #e3f2fd, #fff)", "border": "#2196f3", "text": "#1565c0"},
        "buy-hldb": {"bg": "linear-gradient(135deg, #fce4ec, #fff)", "border": "#e91e63", "text": "#c62828"},
        "hold-cyb": {"bg": "linear-gradient(135deg, #e8f5e9, #fff)", "border": "#4caf50", "text": "#2e7d32"},
        "hold-hldb": {"bg": "linear-gradient(135deg, #fff8e1, #fff)", "border": "#ff9800", "text": "#e65100"},
    }
    sc = signal_colors.get(signal_class, signal_colors["hold-hldb"])

    # 运行回测
    print("运行回测...")
    nav_df, max_dd = run_backtest(merged)
    if nav_df is None: print("ERROR: 回测失败"); return

    final_value = nav_df['nav'].iloc[-1]
    total_return_pct = (final_value / INITIAL_CAPITAL - 1) * 100
    years = (nav_df['date'].iloc[-1] - nav_df['date'].iloc[0]).days / 365.25
    annual_return_pct = ((final_value / INITIAL_CAPITAL) ** (1 / years) - 1) * 100
    cyb_return_pct = (nav_df['cyb_hold'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    hldb_return_pct = (nav_df['hldb_hold'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    current_drawdown = nav_df['drawdown'].iloc[-1]

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

    # 生成matplotlib三面板图
    print("生成图表...")
    chart_svg = generate_chart(nav_df, trades, max_dd)

    # 近5日数据
    recent_5 = merged.tail(5).iloc[::-1]

    # 1年趋势SVG（约250个交易日）
    trend_1y = merged.tail(250).reset_index(drop=True)
    tr_min = trend_1y["ratio"].min() * 100
    tr_max = trend_1y["ratio"].max() * 100
    tr_pad = (tr_max - tr_min) * 0.1 or 5
    tr_y_min = tr_min - tr_pad
    tr_y_max = tr_max + tr_pad
    TW, TH = 800, 240
    t_pad_l, t_pad_r, t_pad_t, t_pad_b = 50, 30, 20, 30
    t_plot_w = TW - t_pad_l - t_pad_r
    t_plot_h = TH - t_pad_t - t_pad_b
    def tx(idx): return t_pad_l + (idx / (len(trend_1y) - 1)) * t_plot_w
    def ty(val_pct):
        rng = tr_y_max - tr_y_min if tr_y_max > tr_y_min else 1
        return t_pad_t + t_plot_h - ((val_pct - tr_y_min) / rng) * t_plot_h
    tr_pts = " ".join(f"{tx(i):.1f},{ty(row['ratio']*100):.1f}" for i, (_, row) in enumerate(trend_1y.iterrows()))
    tr_area_bottom = t_pad_t + t_plot_h
    tr_area = f"{tx(0):.1f},{tr_area_bottom:.1f} {tr_pts} {tx(len(trend_1y)-1):.1f},{tr_area_bottom:.1f}"
    buy_line_y = ty(20); sell_line_y = ty(40)
    tr_grid_lines = ""; tr_y_labels = ""
    for i in range(5):
        val_pct = tr_y_max - (i / 4) * (tr_y_max - tr_y_min)
        yy = ty(val_pct)
        tr_grid_lines += f'<line x1="{t_pad_l}" y1="{yy:.1f}" x2="{TW - t_pad_r}" y2="{yy:.1f}" stroke="#e2e8f0" stroke-width="1"/>\n'
        tr_y_labels += f'<text x="{t_pad_l - 8}" y="{yy + 4:.1f}" text-anchor="end" font-size="11" fill="#6b7a8f">{val_pct:.1f}%</text>\n'
    tr_x_labels = ""
    for i in range(7):
        idx = int((i / 6) * (len(trend_1y) - 1))
        xx = tx(idx)
        tr_x_labels += f'<text x="{xx:.1f}" y="{TH - 4}" text-anchor="middle" font-size="10" fill="#6b7a8f">{trend_1y.iloc[idx]["date"].strftime("%m-%d")}</text>\n'

    # 2025年全年比值趋势SVG
    d2025 = merged[(merged["date"] >= "2025-01-01") & (merged["date"] <= "2025-12-31")].copy().reset_index(drop=True)
    y25_min = d2025["ratio"].min() * 100
    y25_max = d2025["ratio"].max() * 100
    y25_pad = (y25_max - y25_min) * 0.1 or 5
    y25_y_min = y25_min - y25_pad
    y25_y_max = y25_max + y25_pad
    TW25, TH25 = 800, 240
    def t25x(idx): return t_pad_l + (idx / (len(d2025) - 1)) * t_plot_w
    def t25y(val_pct):
        rng = y25_y_max - y25_y_min if y25_y_max > y25_y_min else 1
        return t_pad_t + t_plot_h - ((val_pct - y25_y_min) / rng) * t_plot_h
    y25_pts = " ".join(f"{t25x(i):.1f},{t25y(row['ratio']*100):.1f}" for i, (_, row) in enumerate(d2025.iterrows()))
    y25_area_bottom = t_pad_t + t_plot_h
    y25_area = f"{t25x(0):.1f},{y25_area_bottom:.1f} {y25_pts} {t25x(len(d2025)-1):.1f},{y25_area_bottom:.1f}"
    y25_buy_line_y = t25y(20); y25_sell_line_y = t25y(40)
    y25_grid = ""; y25_ylabels = ""
    for i in range(5):
        val_pct = y25_y_max - (i / 4) * (y25_y_max - y25_y_min)
        yy = t25y(val_pct)
        y25_grid += f'<line x1="{t_pad_l}" y1="{yy:.1f}" x2="{TW25 - t_pad_r}" y2="{yy:.1f}" stroke="#e2e8f0" stroke-width="1"/>\n'
        y25_ylabels += f'<text x="{t_pad_l - 8}" y="{yy + 4:.1f}" text-anchor="end" font-size="11" fill="#6b7a8f">{val_pct:.1f}%</text>\n'
    y25_xlabels = ""
    for i in range(7):
        idx = int((i / 6) * (len(d2025) - 1))
        xx = t25x(idx)
        y25_xlabels += f'<text x="{xx:.1f}" y="{TH25 - 4}" text-anchor="middle" font-size="10" fill="#6b7a8f">{d2025.iloc[idx]["date"].strftime("%m-%d")}</text>\n'
    y25_ratio_avg = d2025["ratio"].mean() * 100
    y25_ratio_mid = d2025["ratio"].median() * 100

    # 表格行
    recent_rows = ""
    for _, row in recent_5.iterrows():
        c_str, c_cls = pct_str(row["cyb_pct"]); h_str, h_cls = pct_str(row["hldb_pct"])
        r_val = row["ratio"] * 100
        recent_rows += f"""          <tr><td>{row['date'].strftime('%m-%d')}</td><td>{fmt_num(row['close_cyb'])}</td><td class="{c_cls}">{c_str}</td><td>{fmt_num(row['close_hldb'])}</td><td class="{h_cls}">{h_str}</td><td>{r_val:.2f}%</td></tr>\n"""

    trade_rows = ""
    for t in trades:
        trade_rows += f"""          <tr><td>{t['date'].strftime('%Y-%m-%d')}</td><td>{t['action']}</td><td>{t['ratio']*100:.2f}%</td><td>{fmt_num(t['nav'])}</td></tr>\n"""

    # ── 生成HTML ──
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    ratio_pct = ratio * 100; ratio_median_pct = ratio_median * 100
    ratio_pos = min(98, max(2, ((ratio_pct - 0) / (60 - 0)) * 100))
    cyb_chg_str, cyb_chg_cls = pct_str(cyb_chg); hldb_chg_str, hldb_chg_cls = pct_str(hldb_chg)

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
.chart-wrap img {{ width: 100%; height: auto; border-radius: 8px; }}
.axis-chart {{ margin-top: 12px; }}
.axis-chart svg {{ width: 100%; height: auto; }}
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

  <!-- 近5日数据 -->
  <div class="section">
    <div class="section-title">近5日数据</div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>日期</th><th>创业板指</th><th>涨跌幅</th><th>红利低波</th><th>涨跌幅</th><th>比值</th></tr>
        </thead>
        <tbody>
{recent_rows}
        </tbody>
      </table>
    </div>
  </div>

  <!-- 1年比值趋势 -->
  <div class="section">
    <div class="section-title">近1年比值趋势</div>
    <div class="axis-chart" style="padding:10px 0;">
      <svg viewBox="0 0 {TW} {TH}" xmlns="http://www.w3.org/2000/svg">
        {tr_grid_lines}
        <line x1="{t_pad_l}" y1="{buy_line_y:.1f}" x2="{TW - t_pad_r}" y2="{buy_line_y:.1f}" stroke="#4caf50" stroke-width="1.5" stroke-dasharray="6,3"/>
        <text x="{TW - t_pad_r + 7}" y="{buy_line_y + 10:.1f}" text-anchor="end" font-size="10" fill="#4caf50">卖出红利 买入创业板 20%</text>
        <line x1="{t_pad_l}" y1="{sell_line_y:.1f}" x2="{TW - t_pad_r}" y2="{sell_line_y:.1f}" stroke="#f44336" stroke-width="1.5" stroke-dasharray="6,3"/>
        <text x="{TW - t_pad_r + 7}" y="{sell_line_y - 2:.1f}" text-anchor="end" font-size="10" fill="#f44336">买入红利 卖出创业板 40%</text>
        <polygon points="{tr_area}" fill="rgba(37, 99, 235, 0.1)"/>
        <polyline points="{tr_pts}" fill="none" stroke="#2563eb" stroke-width="2" stroke-linejoin="round"/>
        {tr_y_labels}
        {tr_x_labels}
      </svg>
    </div>
  </div>

  <!-- 三面板回测图 -->
  <div class="chart-wrap">
    <div class="section-title">轮动策略 vs 持有策略 收益对比（初始资产 100万元）</div>
    {chart_svg}
  </div>

  <!-- 策略规则 -->
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

  <!-- 回测结果 -->
  <div class="section">
    <div class="section-title">回测结果（{nav_df['date'].iloc[0].strftime('%Y.%m')} - {nav_df['date'].iloc[-1].strftime('%Y.%m')}）</div>
    <div class="backtest-grid">
      <div class="bt-card"><div class="bt-label">总收益率</div><div class="bt-value" style="color:var(--accent)">{total_return_pct:.2f}%</div></div>
      <div class="bt-card"><div class="bt-label">年化收益率</div><div class="bt-value" style="color:var(--accent)">{annual_return_pct:.2f}%</div></div>
      <div class="bt-card"><div class="bt-label">最大回撤</div><div class="bt-value" style="color:var(--danger)">{max_dd:.2f}%</div></div>
    </div>
    <div class="backtest-grid" style="margin-top:8px;">
      <div class="bt-card"><div class="bt-label">创业板持有收益</div><div class="bt-value" style="color:var(--muted)">{cyb_return_pct:.2f}%</div></div>
      <div class="bt-card"><div class="bt-label">红利低波持有收益</div><div class="bt-value" style="color:var(--muted)">{hldb_return_pct:.2f}%</div></div>
      <div class="bt-card"><div class="bt-label">交易次数</div><div class="bt-value">{len(trades)} 次</div></div>
    </div>
    <div class="table-wrap" style="margin-top:12px;">
      <table>
        <thead><tr><th>日期</th><th>操作</th><th>比值</th><th>市值</th></tr></thead>
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
    <p style="margin-top:4px;"><a href="javascript:location.reload()">刷新页面</a> 获取最新数据</p>
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

if __name__ == "__main__":
    generate_page()