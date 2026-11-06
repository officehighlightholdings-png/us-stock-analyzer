"""
美股分析小工具：Streamlit 網頁版（學習用，只做分析，不會下單）

本機執行：
    streamlit run streamlit_app.py

部署：把這個檔案和 requirements.txt 放到 GitHub，再到 share.streamlit.io 部署。
"""

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="美股分析小工具", page_icon="📈", layout="wide")

TRADING_DAYS = 252  # 美股一年大約 252 個交易日


# ---------- 抓資料（快取 1 小時，減少被 Yahoo 擋的機會）----------

@st.cache_data(ttl=3600, show_spinner=False)
def load_prices(ticker: str, years: int) -> pd.Series:
    df = yf.Ticker(ticker).history(period=f"{years}y", auto_adjust=True)
    if df.empty:
        return pd.Series(dtype=float, name=ticker)
    s = df["Close"].rename(ticker)
    if s.index.tz is not None:
        s.index = s.index.tz_localize(None)
    return s


@st.cache_data(ttl=3600, show_spinner=False)
def load_info(ticker: str) -> dict:
    try:
        return dict(yf.Ticker(ticker).info or {})
    except Exception:
        return {}


# ---------- 格式化 ----------

def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def pct(x):
    return "—" if _missing(x) else f"{x * 100:.2f}%"


def num(x, digits=2):
    return "—" if _missing(x) else f"{x:,.{digits}f}"


def big_money(x):
    if _missing(x):
        return "—"
    for size, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(x) >= size:
            return f"${x / size:.2f}{unit}"
    return f"${x:,.0f}"


# ---------- 計算 ----------

def price_stats(close: pd.Series) -> dict:
    daily_ret = close.pct_change().dropna()
    years = len(daily_ret) / TRADING_DAYS
    total_return = close.iloc[-1] / close.iloc[0] - 1
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else float("nan")
    volatility = daily_ret.std() * math.sqrt(TRADING_DAYS)
    drawdown = close / close.cummax() - 1
    return {
        "總報酬": total_return,
        "年化報酬 CAGR": cagr,
        "年化波動度": volatility,
        "最大回撤": drawdown.min(),
        "drawdown": drawdown,
    }


def base_layout(fig: go.Figure, title: str, y_title: str = ""):
    fig.update_layout(
        title=title,
        height=430,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis_title=y_title,
    )
    return fig


# ---------- 側邊欄：輸入 ----------

with st.sidebar:
    st.header("設定")
    with st.form("inputs"):
        ticker = st.text_input("股票代號", value="AAPL", help="例如 AAPL、MSFT、NVDA、VOO").strip().upper()
        years = st.selectbox("分析期間（年）", [1, 3, 5, 10, 20], index=2)
        benchmark = st.text_input("比較基準", value="SPY", help="SPY = 標普500，QQQ = 那斯達克100").strip().upper()
        st.form_submit_button("分析", type="primary")
    st.caption("資料來源：Yahoo Finance，可能有延遲或錯誤。重要數字請回 SEC EDGAR 官方財報核對。")


# ---------- 主畫面 ----------

st.title("📈 美股分析小工具")
st.caption("學習用的分析工具，不是投資建議。過去績效不代表未來。")

if not ticker:
    st.info("請在左邊輸入股票代號。")
    st.stop()

with st.spinner(f"正在下載 {ticker} 與 {benchmark} 的資料…"):
    try:
        close = load_prices(ticker, years)
        bench = load_prices(benchmark, years) if benchmark else pd.Series(dtype=float)
    except Exception as e:
        st.error(
            f"下載資料失敗：{e}\n\n"
            "雲端伺服器有時會被 Yahoo 暫時限制，請等幾分鐘再試。"
        )
        st.stop()
    info = load_info(ticker)

if close.empty:
    st.error(f"找不到 {ticker} 的價格資料，請確認代號是否正確。")
    st.stop()

prices = pd.concat([close, bench], axis=1).dropna() if not bench.empty else close.to_frame()
if prices.empty:
    st.error("股票和比較基準的日期對不起來，請換一個比較基準試試。")
    st.stop()
cols = list(prices.columns)

# ---- 公司標題 ----
st.subheader(f"{info.get('longName', ticker)}（{ticker}）")
st.write(f"產業：{info.get('sector', '—')} / {info.get('industry', '—')}")

# ---- 基本面 ----
st.markdown("### 基本面")
fundamentals = [
    ("市值", big_money(info.get("marketCap"))),
    ("本益比（過去12月）", num(info.get("trailingPE"))),
    ("本益比（預估）", num(info.get("forwardPE"))),
    ("每股盈餘 EPS", num(info.get("trailingEps"))),
    ("營收成長（年增）", pct(info.get("revenueGrowth"))),
    ("毛利率", pct(info.get("grossMargins"))),
    ("淨利率", pct(info.get("profitMargins"))),
    ("自由現金流", big_money(info.get("freeCashflow"))),
    ("負債 / 股東權益", num(info.get("debtToEquity"))),
    ("殖利率（過去12月）", pct(info.get("trailingAnnualDividendYield"))),
    ("Beta（相對大盤）", num(info.get("beta"))),
    ("最新收盤價", num(prices[ticker].iloc[-1])),
]
for i in range(0, len(fundamentals), 4):
    row = st.columns(4)
    for col, (label, value) in zip(row, fundamentals[i:i + 4]):
        col.metric(label, value)

if not info:
    st.warning("基本面資料暫時抓不到（可能是 Yahoo 限制），價格分析仍可使用。")

# ---- 價格表現 ----
start, end = prices.index[0].date(), prices.index[-1].date()
st.markdown(f"### 價格表現（{start} ~ {end}）")

stats = {c: price_stats(prices[c]) for c in cols}
table = pd.DataFrame(
    {c: {k: pct(v) for k, v in stats[c].items() if k != "drawdown"} for c in cols}
)
st.dataframe(table, width="stretch")

# ---- 圖表 ----
tab1, tab2, tab3 = st.tabs(["股價與均線", f"和 {benchmark or '大盤'} 比較", "回撤"])

with tab1:
    s = prices[ticker]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s.index, y=s, name=ticker, line=dict(width=1.6)))
    fig.add_trace(go.Scatter(x=s.index, y=s.rolling(50).mean(), name="50日均線", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=s.index, y=s.rolling(200).mean(), name="200日均線", line=dict(width=1)))
    st.plotly_chart(base_layout(fig, f"{ticker} 股價與均線", "價格 (USD)"), width="stretch")

with tab2:
    fig = go.Figure()
    for c in cols:
        fig.add_trace(go.Scatter(x=prices.index, y=prices[c] / prices[c].iloc[0] * 100, name=c))
    st.plotly_chart(base_layout(fig, "期初投入 100，成長到多少？", "價值"), width="stretch")

with tab3:
    dd = stats[ticker]["drawdown"] * 100
    fig = go.Figure(go.Scatter(x=dd.index, y=dd, fill="tozeroy", name="回撤 %", line=dict(color="#d62728", width=1)))
    st.plotly_chart(base_layout(fig, f"{ticker} 從前高下跌的幅度", "%"), width="stretch")

# ---- 名詞說明 ----
with st.expander("📚 這些指標是什麼意思？"):
    st.markdown(
        """
- **本益比 (P/E)**：股價 ÷ 每股盈餘。代表市場願意為每 1 元獲利付多少錢，高不一定貴，要和同業與成長率一起看。
- **EPS**：每股盈餘，公司每一股賺多少錢。
- **毛利率 / 淨利率**：每 100 元營收，扣掉成本後剩多少（毛利），扣掉所有費用和稅後剩多少（淨利）。
- **自由現金流**：營業現金流減去資本支出，公司真正能自由運用的錢。
- **負債 / 股東權益**：數字越高，公司借的錢越多（Yahoo 以百分比呈現，例如 150 代表 1.5 倍）。
- **Beta**：相對大盤的波動程度。1 = 和大盤差不多，大於 1 = 波動更大。
- **年化報酬 CAGR**：把總報酬換算成「平均每年」的複利報酬。
- **年化波動度**：價格上下震盪的幅度，越高代表風險越大。
- **最大回撤**：期間內從最高點跌到最低點的最大跌幅，代表「最慘的時候會虧多少」。
- **50 / 200 日均線**：過去 50 或 200 個交易日的平均價格，常用來看中長期趨勢。
"""
    )
