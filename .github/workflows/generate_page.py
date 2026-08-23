import akshare as ak
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import os

# 指数代码
CYB_CODE = "399006"  # 创业板指
HLDB_CODE = "H30269"  # 中证红利低波动指数

# 策略阈值
BUY_THRESHOLD = 0.20    # 比值 < 20% 买入创业板
SELL_THRESHOLD = 0.40   # 比值 > 40% 切换回红利低波

def fetch_index_data(code, market="sh", start_date="20100101"):
    """获取指数日线数据"""
    try:
        if code == "H30269":
            df = ak.stock_zh_index_hist_csindex(symbol=code, start_date=start_date, end_date=datetime.now().strftime("%Y%m%d"))
        else:
            if market == "sz":
                symbol = f"sz{code}"
            else:
                symbol = f"sh{code}"
            df = ak.stock_zh_index_daily(symbol=symbol)
        return df
    except Exception as e:
        return None

def generate_page():
    print("正在获取指数数据...")

    # 获取创业板指数据
    cyb_df = fetch_index_data(CYB_CODE, market="sz")
    if cyb_df is None:
        print("ERROR: 无法获取创业板指数据")
        return

    # 获取红利低波指数数据
    hldb_df = fetch_index_data(HLDB_CODE)
    if hldb_df is None:
        print("ERROR: 无法获取红利低波指数数据")
        return

    # 处理数据列名
    if "date" in cyb_df.columns:
        cyb_date_col = "date"
        cyb_close_col = "close"
    elif "日期" in cyb_df.columns:
        cyb_date_col = "日期"
        cyb_close_col = "收盘"
    else:
        print("ERROR: 无法识别创业板数据列名")
        return

    if "date" in hldb_df.columns:
        hldb_date_col = "date"
        hldb_close_col = "close"
    elif "日期" in hldb_df.columns:
        hldb_date_col = "日期"
        hldb_close_col = "收盘"
    else:
        print("ERROR: 无法识别红利低波数据列名")
        return

    # 提取日期和收盘价
    cyb = cyb_df[[cyb_date_col, cyb_close_col]].copy()
    cyb.columns = ["date", "cyb_close"]
    cyb["date"] = pd.to_datetime(cyb["date"])
    cyb = cyb.sort_values("date").reset_index(drop=True)

    hldb = hldb_df[[hldb_date_col, hldb_close_col]].copy()
    hldb.columns = ["date", "hldb_close"]
    hldb["date"] = pd.to_datetime(hldb["date"])
    hldb = hldb.sort_values("date").reset_index(drop=True)

    # 合并数据
    merged = pd.merge(cyb, hldb, on="date", how="inner")
    merged = merged.dropna().reset_index(drop=True)

    if len(merged) < 20:
        print("ERROR: 数据不足")
        return

    # 计算比值 (创业板/红利低波)
    merged["ratio"] = merged["cyb_close"] / merged["hldb_close"]

    # 获取最新数据
    latest = merged.iloc[-1]
    prev = merged.iloc[-2]
    latest_date = latest["date"]
    ratio = latest["ratio"]
    cyb_close = latest["cyb_close"]
    hldb_close = latest["hldb_close"]

    # 判断信号
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

    # 生成近期比值数据（用于图表显示）
    recent = merged.tail(120)
    ratio_data = []
    for _, row in recent.iterrows():
        ratio_data.append({
            "date": row["date"].strftime("%Y-%m-%d"),
            "ratio": round(row["ratio"] * 100, 2)
        })

    # 创建输出目录
    os.makedirs("public", exist_ok=True)

    # 生成HTML
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>指数轮动策略监控</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #333; padding: 20px; }}
    .container {{ max-width: 800px; margin: 0 auto; }}
    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; padding: 30px; border-radius: 16px; margin-bottom: 20px; text-align: center; }}
    .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
    .header .update-time {{ font-size: 13px; opacity: 0.8; }}
    .signal-card {{ background: #fff; border-radius: 16px; padding: 24px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .signal-badge {{ display: inline-block; padding: 8px 20px; border-radius: 20px; font-size: 18px; font-weight: 600; }}
    .signal-badge.buy-cyb {{ background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }}
    .signal-badge.buy-hldb {{ background: #fff7e6; color: #fa8c16; border: 1px solid #ffd591; }}
    .signal-badge.hold-cyb {{ background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }}
    .signal-badge.hold-hldb {{ background: #fffbe6; color: #fadb14; border: 1px solid #ffe58f; }}
    .signal-text {{ margin-top: 12px; font-size: 14px; color: #666; line-height: 1.6; }}
    .data-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }}
    .data-item {{ background: #fff; border-radius: 12px; padding: 16px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .data-item .label {{ font-size: 12px; color: #999; margin-bottom: 4px; }}
    .data-item .value {{ font-size: 20px; font-weight: 600; }}
    .data-item .value.cyb {{ color: #e74c3c; }}
    .data-item .value.hldb {{ color: #2ecc71; }}
    .data-item .value.ratio {{ color: #667eea; }}
    .chart-container {{ background: #fff; border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .chart-container h3 {{ font-size: 16px; margin-bottom: 16px; color: #333; }}
    .chart {{ width: 100%; height: 300px; }}
    .chart-bar {{ display: flex; align-items: flex-end; height: 250px; gap: 2px; }}
    .bar {{ flex: 1; min-width: 3px; background: linear-gradient(to top, #667eea, #764ba2); border-radius: 2px 2px 0 0; position: relative; }}
    .bar.above40 {{ background: linear-gradient(to top, #e74c3c, #c0392b); }}
    .bar.below20 {{ background: linear-gradient(to top, #3498db, #2980b9); }}
    .bar.equals30 {{ background: linear-gradient(to top, #f39c12, #e67e22); }}
    .threshold-lines {{ position: relative; height: 0; }}
    .info-text {{ font-size: 12px; color: #999; text-align: center; margin-top: 8px; }}
    .footer {{ text-align: center; font-size: 12px; color: #bbb; padding: 20px 0; }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>指数轮动策略监控</h1>
        <p>创业板指 vs 中证红利低波动指数</p>
        <div class="update-time">更新时间: {now_str}</div>
    </div>

    <div class="signal-card">
        <div style="text-align: center;">
            <div class="signal-badge {signal_class}">{signal}</div>
            <div class="signal-text">{reason}</div>
        </div>
    </div>

    <div class="data-grid">
        <div class="data-item">
            <div class="label">创业板指</div>
            <div class="value cyb">{cyb_close:.2f}</div>
        </div>
        <div class="data-item">
            <div class="label">红利低波</div>
            <div class="value hldb">{hldb_close:.2f}</div>
        </div>
        <div class="data-item">
            <div class="label">比值 (创业板/红利低波)</div>
            <div class="value ratio">{ratio*100:.2f}%</div>
        </div>
    </div>

    <div class="chart-container">
        <h3>近120日比值趋势</h3>
        <div style="position: relative;">
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 250px; pointer-events: none;">
                <div style="position: absolute; top: 0; left: 0; right: 0; border-top: 1px dashed #e74c3c; text-align: right; font-size: 11px; color: #e74c3c; padding-right: 4px;">40%</div>
                <div style="position: absolute; top: 50%; left: 0; right: 0; border-top: 1px dashed #f39c12;"></div>
                <div style="position: absolute; bottom: 0; left: 0; right: 0; border-top: 1px dashed #3498db; text-align: right; font-size: 11px; color: #3498db; padding-right: 4px;">20%</div>
            </div>
            <div class="chart-bar" id="chart-bars">
"""

    # 计算柱状图
    max_ratio = max(r["ratio"] for r in ratio_data)
    min_ratio = min(r["ratio"] for r in ratio_data)
    range_h = max_ratio - min_ratio if max_ratio > min_ratio else 1

    for r in ratio_data:
        pct = (r["ratio"] - min_ratio) / range_h * 100
        pct = max(5, min(100, pct))
        bar_class = ""
        if r["ratio"] > 40:
            bar_class = " above40"
        elif r["ratio"] < 20:
            bar_class = " below20"
        html += f'                <div class="bar{bar_class}" style="height: {pct}%;" title="{r["date"]}: {r["ratio"]}%"></div>\n'

    html += f"""            </div>
        </div>
        <div class="info-text">颜色说明: 蓝色(比值<20%) | 橙色(正常区间) | 红色(比值>40%)</div>
    </div>

    <div class="footer">
        数据来源: AKShare · 策略: 指数轮动 · 自动每日更新
    </div>
</div>
</body>
</html>"""

    # 写入文件
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"页面已生成: public/index.html")
    print(f"最新信号: {signal}")
    print(f"比值: {ratio*100:.2f}%")

if __name__ == "__main__":
    generate_page()