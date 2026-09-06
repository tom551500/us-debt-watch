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
def fetch_btc_price(days: int = 365):
    """
    抓取 BTC 價格。CoinGecko 免費 API 在雲端主機(如 Streamlit Cloud)常見被
    共用 IP 觸發 429 限流，因此加上 User-Agent 並在失敗時改用 Stooq 當備援。
    回傳 (DataFrame, 資料來源名稱)
    """
    errors = []

    # 主要來源：CoinGecko
    try:
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        params = {"vs_currency": "usd", "days": days}
        headers = {"User-Agent": "Mozilla/5.0 (compatible; StreamlitApp/1.0)"}
        r = requests.get(url, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        payload = r.json()
        if "prices" not in payload:
            raise ValueError(f"回應中沒有 prices 欄位：{payload}")
        data = payload["prices"]
        df = pd.DataFrame(data, columns=["ts", "price"])
        df["date"] = pd.to_datetime(df["ts"], unit="ms")
        df = df[["date", "price"]].dropna()
        if len(df) == 0:
            raise ValueError("CoinGecko 回傳空資料")
        return df, "CoinGecko"
    except Exception as e:
        errors.append(f"CoinGecko: {e}")

    # 備援來源：Stooq（免金鑰、無限流，但只到日線收盤價）
    try:
        url = "https://stooq.com/q/d/l/?s=btcusd&i=d"
        df = pd.read_csv(url)
        df.columns = [c.strip().lower() for c in df.columns]
        if "date" not in df.columns or "close" not in df.columns:
            raise ValueError(f"Stooq 欄位不符預期：{list(df.columns)}")
        df["date"] = pd.to_datetime(df["date"])
        df = df.rename(columns={"close": "price"})[["date", "price"]]
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df.dropna()
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df["date"] >= cutoff]
        if len(df) == 0:
            raise ValueError("Stooq 回傳空資料")
        return df, "Stooq"
    except Exception as e:
        errors.append(f"Stooq: {e}")

    raise RuntimeError(" ｜ ".join(errors))


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
# 情境判讀指南（固定說明，供對照）
# ---------------------------------------------------------------------------
with st.expander("📖 情境判讀指南：出現什麼情況、股市/BTC通常怎麼走？（點開看說明）", expanded=False):
    st.markdown(
        """
| 情境 | 利差(區塊1) | BTC/殖利率(區塊2) | COT淨部位(區塊3) | 意味 | 對股市/BTC的典型影響 |
|---|---|---|---|---|---|
| **A. 鷹派延續** | 快速收窄，甚至轉負 | 反向明顯，BTC走弱 | 空單持續擴大 | 短端不降息、Fed壓通膨優先 | 美股尤其那斯達克/高本益比成長股承壓；美元偏強；BTC及風險資產偏弱；台股外資可能匯出、電子權值股連動下跌 |
| **B. 轉鴿/空單回補** | 利差回升(轉陡) | BTC反彈、相關性回復 | 空單開始收斂 | 通膨數據轉弱，市場重新押注降息 | 美股風險偏好回升，成長股、BTC同步反彈；美元轉弱；台股外資買盤可能回流，電子股較敏感 |
| **C. 財政部撐盤生效** | 長端穩、利差溫和變動 | 相關性減弱 | 部位變化不大 | 回購+穩定幣買盤形成結構性支撐 | 美股區間震盪、波動度下降；對台股影響偏中性；長債價格相對抗跌 |

**簡單判讀口訣**：
- 利差**收窄**＋BTC/成長股**同步走弱** → 偏向情境A，注意風險資產下檔
- 利差**回升**＋COT空單**開始收斂** → 偏向情境B，留意風險資產反彈契機
- 利差與BTC**脫鉤**、波動變小 → 偏向情境C，觀察長債是否走出獨立行情

⚠️ 這是幫助你快速定位「現在市場在哪個劇本」的框架，不是精確預測公式；真實市場常常同時混雜多個訊號，仍需交叉確認多個區塊再下判斷。
        """
    )

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

    # --- 動態情境判讀：用最近10個交易日的利差變化幅度自動分類 ---
    lookback_n = min(10, len(yields) - 1)
    if lookback_n > 0:
        spread_now = yields["spread_10_2"].iloc[-1]
        spread_prev = yields["spread_10_2"].iloc[-1 - lookback_n]
        spread_change = spread_now - spread_prev

        THRESHOLD = 0.05  # 個百分點，用來判斷是否為「明顯」變化
        if spread_change <= -THRESHOLD:
            st.warning(
                f"🔴 **目前偏向情境A(鷹派延續/反向扁平化)**："
                f"近{lookback_n}個交易日利差收窄了 {abs(spread_change):.2f} 個百分點"
                f"（目前 {spread_now:.2f}%）。\n\n"
                "**典型影響**：短端利率續緊，市場對Fed降息期待降溫，"
                "美股成長股/科技股與BTC通常承壓，美元偏強；"
                "台股若跟隨外資情緒，電子權值股可能同步走弱。"
            )
        elif spread_change >= THRESHOLD:
            st.success(
                f"🟢 **目前偏向情境B(轉鴿訊號/空單回補)**："
                f"近{lookback_n}個交易日利差回升了 {spread_change:.2f} 個百分點"
                f"（目前 {spread_now:.2f}%）。\n\n"
                "**典型影響**：市場開始押注降息機率上升，風險偏好回升，"
                "美股與BTC通常反彈，美元轉弱；台股外資買盤可能回流。"
            )
        else:
            st.info(
                f"⚪ **目前偏向情境C(區間盤整/財政部撐盤)**："
                f"近{lookback_n}個交易日利差變化幅度不大"
                f"（{spread_change:+.2f}個百分點，目前 {spread_now:.2f}%）。\n\n"
                "**典型影響**：長端受財政部回購支撐，短端方向未明，"
                "美股與台股較可能區間震盪，波動度偏低，尚未出現明確風向。"
            )

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
    btc, btc_source = fetch_btc_price(lookback)
    st.caption(f"資料來源：{btc_source}")

    if "yields" not in dir() or len(yields) == 0:
        raise RuntimeError("殖利率資料尚未成功載入，請先確認上方第1區塊有正常顯示。")

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
    st.caption("兩個資料來源(CoinGecko/Stooq)都嘗試過仍失敗時才會顯示這個訊息。可按左側「清除快取重新抓取」再試一次，或稍後再看。")

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

    if len(plot_df) >= 2:
        net_now = plot_df["淨部位(口)"].iloc[-1]
        net_prev = plot_df["淨部位(口)"].iloc[-2]
        net_change = net_now - net_prev
        if net_change > 0 and net_now < 0:
            st.success(
                f"🟢 淨空單較上一筆收斂了約 {abs(net_change):,.0f} 口"
                "（仍為淨空單，但空單擁擠度下降），可能是空單回補的早期訊號，"
                "留意是否搭配情境B（利差回升、BTC反彈）同時出現。"
            )
        elif net_change < 0:
            st.warning(
                f"🔴 淨空單較上一筆擴大了約 {abs(net_change):,.0f} 口，"
                "空方部位更擁擠，短期內若通膨數據不如預期，"
                "潛在回補力道會更大，但也可能代表看空情緒持續加深。"
            )
        else:
            st.info("⚪ 淨部位與上一筆變化不大，暫無明確方向。")

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
