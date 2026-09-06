"""
美債觀察儀表板 (US Debt Refinancing Watch)
追蹤：殖利率曲線(2Y/10Y/30Y)、殖利率利差、BTC對比走勢、
關鍵時間軸(FOMC/回購/選舉)、CFTC 10年期公債期貨部位(手動輸入)

部署方式：上傳到 GitHub -> Streamlit Cloud 連結部署
本機測試：streamlit run us_debt_watch_app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="美債觀察儀表板", layout="wide", page_icon="📉")

# ---------------------------------------------------------------------------
# 關鍵時間軸設定（可自行更新）
# ---------------------------------------------------------------------------
KEY_EVENTS = [
    ("2026-09-09", "財政部擴大長債回購上限 ($2B→$4B)"),
    ("2026-09-15", "CLARITY Act 程序關卡"),
    ("2026-09-16", "FOMC 決議"),
    ("2026-10-28", "FOMC 決議"),
    ("2026-11-03", "美國期中選舉"),
    ("2026-11-04", "財政部季度再融資聲明 (Quarterly Refunding)"),
]
BUYBACK_START = "2026-09-09"
BUYBACK_END = "2026-11-04"

# ---------------------------------------------------------------------------
# 資料抓取
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_treasury_yields(lookback_days: int = 365) -> pd.DataFrame:
    """從 FRED 抓取 2Y / 10Y / 30Y 公債殖利率"""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2,DGS10,DGS30"
    df = pd.read_csv(url)
    df.columns = ["date", "y2", "y10", "y30"]
    df["date"] = pd.to_datetime(df["date"])
    for c in ["y2", "y10", "y30"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["y2", "y10", "y30"], how="all")
    cutoff = datetime.now() - timedelta(days=lookback_days)
    return df[df["date"] >= cutoff].reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_btc_price(days: int = 365) -> pd.DataFrame:
    """從 CoinGecko 抓取 BTC 價格"""
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": "usd", "days": days}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()["prices"]
    df = pd.DataFrame(data, columns=["ts", "price"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms")
    return df[["date", "price"]]


def add_event_lines(fig: go.Figure, y_range=None, row=None, col=None):
    """在圖上標示關鍵時間軸"""
    for date_str, label in KEY_EVENTS:
        fig.add_vline(
            x=pd.Timestamp(date_str),
            line_width=1,
            line_dash="dot",
            line_color="gray",
            annotation_text=label,
            annotation_textangle=-90,
            annotation_font_size=9,
            row=row,
            col=col,
        )
    fig.add_vrect(
        x0=pd.Timestamp(BUYBACK_START),
        x1=pd.Timestamp(BUYBACK_END),
        fillcolor="LightSalmon",
        opacity=0.15,
        line_width=0,
        annotation_text="財政部長債回購期間",
        annotation_position="top left",
        row=row,
        col=col,
    )


# ---------------------------------------------------------------------------
# 側邊欄
# ---------------------------------------------------------------------------
st.sidebar.title("設定")
lookback = st.sidebar.slider("回看天數", min_value=90, max_value=730, value=365, step=30)
st.sidebar.caption("資料來源：FRED（殖利率）、CoinGecko（BTC）。CFTC COT 部位需手動輸入（見下方說明）。")
if st.sidebar.button("🔄 清除快取重新抓取"):
    st.cache_data.clear()

st.title("📉 美債觀察儀表板")
st.caption("追蹤美債再融資相關指標：殖利率曲線、BTC連動、關鍵時間軸與期貨部位")

# ---------------------------------------------------------------------------
# Section 1: 殖利率曲線與利差
# ---------------------------------------------------------------------------
st.header("1. 殖利率曲線與利差 (2Y / 10Y / 30Y)")

try:
    yields = fetch_treasury_yields(lookback)
    yields["spread_10_2"] = yields["y10"] - yields["y2"]

    latest = yields.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("2年期", f"{latest['y2']:.2f}%")
    c2.metric("10年期", f"{latest['y10']:.2f}%")
    c3.metric("30年期", f"{latest['y30']:.2f}%")
    c4.metric("10Y-2Y 利差", f"{latest['spread_10_2']:.2f}%")

    fig1 = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        row_heights=[0.65, 0.35],
        subplot_titles=("殖利率走勢", "10Y - 2Y 利差（扁平化/陡峭化觀察）"),
    )
    fig1.add_trace(go.Scatter(x=yields["date"], y=yields["y2"], name="2年期", line=dict(color="#1f77b4")), row=1, col=1)
    fig1.add_trace(go.Scatter(x=yields["date"], y=yields["y10"], name="10年期", line=dict(color="#ff7f0e")), row=1, col=1)
    fig1.add_trace(go.Scatter(x=yields["date"], y=yields["y30"], name="30年期", line=dict(color="#2ca02c")), row=1, col=1)
    fig1.add_trace(go.Scatter(x=yields["date"], y=yields["spread_10_2"], name="10Y-2Y利差", line=dict(color="#d62728"), fill="tozeroy"), row=2, col=1)
    fig1.add_hline(y=0, line_dash="dash", line_color="black", row=2, col=1)

    add_event_lines(fig1, row=1, col=1)
    add_event_lines(fig1, row=2, col=1)

    fig1.update_layout(height=650, hovermode="x unified", legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig1, use_container_width=True)

    st.info(
        "**判讀重點**：若2年期上升速度快於10/30年期（利差收窄甚至轉負），"
        "代表市場正在為「Fed偏鷹、短端不降息」重新定價——即文章中提到的"
        "「反向扁平化」，對風險資產（BTC、成長股）通常不友善。"
    )
except Exception as e:
    st.error(f"殖利率資料抓取失敗：{e}")
    st.caption("可能是 FRED 暫時無法連線，稍後重試或改用 https://fred.stlouisfed.org 手動查詢。")

# ---------------------------------------------------------------------------
# Section 2: BTC 對比走勢
# ---------------------------------------------------------------------------
st.header("2. BTC 對比 2 年期殖利率")

try:
    btc = fetch_btc_price(lookback)
    merged = pd.merge_asof(
        btc.sort_values("date"), yields[["date", "y2"]].sort_values("date"),
        on="date", direction="nearest",
    )

    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    fig2.add_trace(go.Scatter(x=merged["date"], y=merged["price"], name="BTC (USD)", line=dict(color="#f2a900")), secondary_y=False)
    fig2.add_trace(go.Scatter(x=merged["date"], y=merged["y2"], name="2年期殖利率", line=dict(color="#1f77b4", dash="dot")), secondary_y=True)
    add_event_lines(fig2)
    fig2.update_yaxes(title_text="BTC 價格 (USD)", secondary_y=False)
    fig2.update_yaxes(title_text="2年期殖利率 (%)", secondary_y=True)
    fig2.update_layout(height=450, hovermode="x unified", legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig2, use_container_width=True)

    st.info(
        "**判讀重點**：觀察 Fed 談話或 FOMC 前後，BTC 走勢是否與 2 年期殖利率"
        "呈現反向連動（殖利率上升、BTC下跌）。若相關性減弱，代表市場焦點"
        "已轉向財政部回購／穩定幣買盤等其他敘事。"
    )
except Exception as e:
    st.error(f"BTC 資料抓取失敗：{e}")

# ---------------------------------------------------------------------------
# Section 3: CFTC 10年期公債期貨部位（手動輸入，因官方格式常變動、不穩定）
# ---------------------------------------------------------------------------
st.header("3. CFTC 10年期公債期貨部位（手動追蹤）")
st.caption(
    "CFTC 官方 COT 報告每週五更新，格式常變動不易穩定自動解析，建議每週手動登記兩個數字。"
    "資料來源：https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"
    "（選擇 Financial Futures → 搜尋 10-YEAR U.S. TREASURY NOTES）"
)

if "cot_data" not in st.session_state:
    st.session_state.cot_data = pd.DataFrame(
        {
            "報告日期": pd.to_datetime(["2026-08-25"]),
            "槓桿基金多單(口)": [317000],
            "槓桿基金空單(口)": [2450000],
        }
    )

edited = st.data_editor(
    st.session_state.cot_data,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "報告日期": st.column_config.DateColumn("報告日期"),
        "槓桿基金多單(口)": st.column_config.NumberColumn("槓桿基金多單(口)"),
        "槓桿基金空單(口)": st.column_config.NumberColumn("槓桿基金空單(口)"),
    },
)
st.session_state.cot_data = edited

if len(edited) > 0:
    plot_df = edited.dropna().sort_values("報告日期").copy()
    plot_df["淨部位(口)"] = plot_df["槓桿基金多單(口)"] - plot_df["槓桿基金空單(口)"]

    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=plot_df["報告日期"], y=plot_df["淨部位(口)"], name="淨部位", marker_color="crimson"))
    fig3.add_hline(y=0, line_dash="dash", line_color="black")
    fig3.update_layout(height=350, title="槓桿基金淨部位（多單-空單）— 越負代表空單越擁擠，回補潛力越大")
    st.plotly_chart(fig3, use_container_width=True)

    st.info(
        "**判讀重點**：淨空單部位若從歷史極端值開始收斂（回補），"
        "常伴隨長債價格上漲、殖利率下降，可搭配上方殖利率利差圖交叉確認。"
        "注意：這些空單有相當比例可能是 basis trade（現券多、期貨空的套利倉），"
        "不能單純解讀成「全市場看空美債」。"
    )

# ---------------------------------------------------------------------------
# Section 4: 關鍵時間軸
# ---------------------------------------------------------------------------
st.header("4. 關鍵時間軸")
events_df = pd.DataFrame(KEY_EVENTS, columns=["日期", "事件"])
events_df["日期"] = pd.to_datetime(events_df["日期"])
today = pd.Timestamp(datetime.now().date())
events_df["狀態"] = np.where(events_df["日期"] < today, "✅ 已發生", "⏳ 未到")
st.dataframe(events_df.sort_values("日期"), use_container_width=True, hide_index=True)

st.caption(
    "此儀表板僅供研究參考，非投資建議。資料延遲/中斷時請以官方來源"
    "（FRED、CFTC、Treasury.gov）為準。"
)
