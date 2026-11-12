import json
import numbers
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

st.set_page_config(page_title="Mint Terminal", page_icon="📈", layout="wide")
st.markdown("""
<style>
#MainMenu, footer, .stDeployButton, .stAppDeployButton,
[data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {visibility: hidden;}
.block-container {padding-top: 2rem;}
[data-testid="stMetric"] {background: #161b22; border: 1px solid #30363d;
  border-radius: 10px; padding: 10px 14px;}
</style>
""", unsafe_allow_html=True)

MARKETS = {"S&P 500": "^GSPC", "Nasdaq": "^IXIC", "Dow": "^DJI", "VIX": "^VIX",
           "10Y Yield": "^TNX", "Oil": "CL=F", "Gold": "GC=F", "Bitcoin": "BTC-USD"}
RANGES = {"1D": ("1d", "5m"), "5D": ("5d", "30m"), "1M": ("1mo", "1d"),
          "6M": ("6mo", "1d"), "1Y": ("1y", "1d"), "5Y": ("5y", "1wk"),
          "MAX": ("max", "1mo")}
SECTORS = ["Technology", "Communication Services", "Consumer Cyclical", "Consumer Defensive",
           "Healthcare", "Financial Services", "Industrials", "Energy", "Utilities",
           "Real Estate", "Basic Materials"]
BACKUP_MAP = {
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "IBM",
                   "QCOM", "TXN", "INTC"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "TMUS", "VZ", "T"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "LOW", "BKNG", "NKE", "SBUX"],
    "Consumer Defensive": ["WMT", "COST", "PG", "KO", "PEP", "PM"],
    "Healthcare": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "PFE"],
    "Financial Services": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP"],
    "Industrials": ["GE", "CAT", "RTX", "HON", "UNP", "BA", "DE", "UPS"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
    "Utilities": ["NEE", "SO", "DUK"],
    "Real Estate": ["PLD", "AMT", "EQIX"],
    "Basic Materials": ["LIN", "SHW", "APD"],
}
SECTIONS = ["📊 Chart", "🔢 Key stats", "💰 Financials", "🎯 Analysts", "🧾 Options",
            "🕵️ Insiders", "📰 News", "🏢 Profile"]
HERE = Path(__file__).parent
GREEN, RED, BLUE, GREY = "#26a69a", "#ef5350", "#58a6ff", "#8b949e"
LAYOUT = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
              plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=10, b=10))


def load(name, default):
    try:
        return json.loads((HERE / name).read_text())
    except Exception:
        return default


def save(name, value):
    (HERE / name).write_text(json.dumps(value))


for key, default in (("watchlist", ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]),
                     ("portfolio", []), ("alerts", [])):
    if key not in st.session_state:
        st.session_state[key] = load(f"{key}.json", default)


@st.cache_data(ttl=15)
def price_change(ticker):
    try:
        closes = yf.Ticker(ticker).history(period="5d")["Close"].dropna()
        price, prev = closes.iloc[-1], closes.iloc[-2]
        return float(price), float((price - prev) / prev * 100)
    except Exception:
        return None, None


@st.cache_data(ttl=60)
def get_history(ticker, period, interval):
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        return df.dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_info(ticker):
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def get_statement(ticker, kind, quarterly):
    names = {"Income statement": "income_stmt", "Balance sheet": "balance_sheet",
             "Cash flow": "cashflow"}
    attr = ("quarterly_" if quarterly else "") + names[kind]
    try:
        return getattr(yf.Ticker(ticker), attr)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_extra(ticker, names):
    stock = yf.Ticker(ticker)
    out = {}
    for name in names:
        try:
            out[name] = getattr(stock, name)
        except Exception:
            out[name] = None
    return out


@st.cache_data(ttl=3600)
def get_expiries(ticker):
    try:
        return list(yf.Ticker(ticker).options)
    except Exception:
        return []


@st.cache_data(ttl=300)
def get_chain(ticker, expiry):
    try:
        chain = yf.Ticker(ticker).option_chain(expiry)
        return chain.calls, chain.puts
    except Exception:
        return pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=300)
def get_news(ticker):
    try:
        return yf.Ticker(ticker).news or []
    except Exception:
        return []


@st.cache_data(ttl=120)
def get_movers(kind):
    try:
        quotes = yf.screen(kind)["quotes"]
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame([{"Ticker": q.get("symbol"),
                          "Name": q.get("shortName"),
                          "Price": q.get("regularMarketPrice"),
                          "Change %": q.get("regularMarketChangePercent"),
                          "Volume": q.get("regularMarketVolume"),
                          "Market cap": q.get("marketCap")} for q in quotes])


@st.cache_data(ttl=120)
def get_heatmap():
    rows = []
    try:
        for sector in SECTORS:
            query = yf.EquityQuery("and", [
                yf.EquityQuery("eq", ["region", "us"]),
                yf.EquityQuery("eq", ["sector", sector]),
                yf.EquityQuery("gt", ["intradaymarketcap", 20_000_000_000])])
            result = yf.screen(query, sortField="intradaymarketcap", sortAsc=False, size=20)
            for q in result.get("quotes", []):
                cap, chg = q.get("marketCap"), q.get("regularMarketChangePercent")
                if is_num(cap) and is_num(chg):
                    rows.append({"Ticker": q.get("symbol"),
                                 "Name": q.get("shortName") or q.get("symbol"),
                                 "Sector": sector, "Cap": float(cap), "Change": float(chg)})
    except Exception:
        rows = []
    if len(rows) >= 30:
        return pd.DataFrame(rows).drop_duplicates("Ticker"), True

    rows = []
    try:
        tickers = [t for group in BACKUP_MAP.values() for t in group]
        closes = yf.download(tickers, period="5d", progress=False, auto_adjust=True)["Close"]
    except Exception:
        return pd.DataFrame(), False
    for sector, group in BACKUP_MAP.items():
        for t in group:
            if t not in closes:
                continue
            s = closes[t].dropna()
            if len(s) >= 2:
                rows.append({"Ticker": t, "Name": t, "Sector": sector, "Cap": 1.0,
                             "Change": float((s.iloc[-1] / s.iloc[-2] - 1) * 100)})
    return pd.DataFrame(rows), False


def is_num(n):
    return isinstance(n, numbers.Real) and not isinstance(n, bool) and not pd.isna(n)


def has(df):
    return isinstance(df, pd.DataFrame) and not df.empty


def big(n):
    if not is_num(n):
        return "n/a"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(n) >= size:
            return f"{n / size:.2f}{unit}"
    return f"{n:,.0f}" if float(n).is_integer() else f"{n:,.2f}"


def pct(n):
    return f"{n * 100:.1f}%" if is_num(n) else "n/a"


def qty(n):
    return f"{n:,.4f}".rstrip("0").rstrip(".") if is_num(n) else "n/a"


def safe(text):
    return str(text).replace("$", "\\$")


def sign_color(v):
    return f"color: {GREEN if v >= 0 else RED}" if is_num(v) else ""


def pick(df, names):
    keep = {k: v for k, v in names.items() if k in df.columns}
    return df[list(keep)].rename(columns=keep).reset_index(drop=True)


def choose(label, options, default, key):
    return st.segmented_control(label, options, default=default, key=key,
                                label_visibility="collapsed") or default


def tile(where, label, ticker, inverse=False):
    price, chg = price_change(ticker)
    if price is None:
        where.metric(label, "n/a")
    else:
        where.metric(label, f"{price:,.2f}", f"{chg:+.2f}%",
                     delta_color="inverse" if inverse else "normal")


@st.fragment(run_every=15)
def market_bar():
    cols = st.columns(len(MARKETS))
    for col, (name, ticker) in zip(cols, MARKETS.items()):
        tile(col, name, ticker, inverse=(name == "VIX"))
    st.caption(f"🟢 Live · updated {time.strftime('%H:%M:%S')}")


@st.fragment(run_every=15)
def watchlist_panel():
    for ticker in st.session_state.watchlist:
        tile(st, ticker, ticker)


@st.fragment(run_every=15)
def alert_checker():
    changed = False
    for a in st.session_state.alerts:
        if a.get("hit"):
            continue
        price, _ = price_change(a["ticker"])
        if price is None:
            continue
        if (a["op"] == "Above" and price >= a["price"]) or (a["op"] == "Below" and price <= a["price"]):
            a["hit"] = time.strftime("%H:%M")
            changed = True
            st.toast(f"**{a['ticker']}** is now {price:,.2f}, "
                     f"{a['op'].lower()} your {a['price']:,.2f} alert", icon="🔔")
    if changed:
        save("alerts.json", st.session_state.alerts)


def draw_chart(df, symbol, interval):
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.78, 0.22], vertical_spacing=0.02)
    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"],
                                 low=df["Low"], close=df["Close"], name="Price",
                                 increasing_line_color=GREEN,
                                 decreasing_line_color=RED), row=1, col=1)
    for days, color in ((50, "#ff9900"), (200, BLUE)):
        if len(df) > days:
            fig.add_trace(go.Scatter(x=df.index, y=df["Close"].rolling(days).mean(),
                                     name=f"{days} avg",
                                     line=dict(width=1.5, color=color)), row=1, col=1)
    colors = [GREEN if c >= o else RED for o, c in zip(df["Open"], df["Close"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=colors,
                         name="Volume"), row=2, col=1)
    stock = not (symbol.endswith("-USD") or "=" in symbol)
    if stock and interval in ("5m", "30m", "1d"):
        breaks = [dict(bounds=["sat", "mon"])]
        if interval != "1d":
            breaks.append(dict(bounds=[16, 9.5], pattern="hour"))
        fig.update_xaxes(rangebreaks=breaks)
    fig.update_layout(**LAYOUT, height=620, showlegend=False,
                      xaxis_rangeslider_visible=False, hovermode="x unified")
    st.plotly_chart(fig, theme=None)


def show_chart(symbol):
    choice = choose("Range", list(RANGES), "6M", "chart_range")
    period, interval = RANGES[choice]
    df = get_history(symbol, period, interval)
    if df.empty:
        st.warning("No chart data for that range.")
    else:
        draw_chart(df, symbol, interval)


def show_stats(info, price):
    rate = info.get("dividendRate")
    rating = str(info.get("recommendationKey") or "n/a").replace("_", " ").title()
    stats = [("Market cap", big(info.get("marketCap"))),
             ("Revenue", big(info.get("totalRevenue"))),
             ("P/E", big(info.get("trailingPE"))),
             ("Forward P/E", big(info.get("forwardPE"))),
             ("EPS", big(info.get("trailingEps"))),
             ("Profit margin", pct(info.get("profitMargins"))),
             ("52W high", big(info.get("fiftyTwoWeekHigh"))),
             ("52W low", big(info.get("fiftyTwoWeekLow"))),
             ("Beta", big(info.get("beta"))),
             ("Avg volume", big(info.get("averageVolume"))),
             ("Dividend yield", pct(rate / price) if is_num(rate) and rate > 0 else "None"),
             ("Analyst rating", rating)]
    cols = st.columns(4)
    for i, (label, value) in enumerate(stats):
        cols[i % 4].metric(label, value)


def show_financials(symbol):
    left, right = st.columns([3, 1])
    with left:
        kind = choose("Statement", ["Income statement", "Balance sheet", "Cash flow"],
                      "Income statement", "fin_kind")
    with right:
        freq = choose("Period", ["Annual", "Quarterly"], "Annual", "fin_freq")
    fin = get_statement(symbol, kind, freq == "Quarterly")
    if not has(fin):
        st.info("No financials for this one.")
        return
    dates = [pd.Timestamp(d).strftime("%b %Y") for d in fin.columns]
    if kind == "Income statement" and {"Total Revenue", "Net Income"} <= set(fin.index):
        fig = go.Figure()
        for row, color in (("Total Revenue", BLUE), ("Net Income", GREEN)):
            fig.add_trace(go.Bar(x=dates[::-1], y=fin.loc[row].tolist()[::-1],
                                 name=row, marker_color=color))
        fig.update_layout(**LAYOUT, height=320, barmode="group")
        st.plotly_chart(fig, theme=None)
    table = fin.map(big)
    table.columns = dates
    st.dataframe(table, height=500)


def show_analysts(symbol, price):
    data = get_extra(symbol, ("analyst_price_targets", "recommendations", "upgrades_downgrades"))
    targets = data.get("analyst_price_targets")
    targets = targets if isinstance(targets, dict) else {}
    recs = data.get("recommendations")
    ups = data.get("upgrades_downgrades")
    if not targets and not has(recs) and not has(ups):
        st.info("No analyst coverage for this one.")
        return

    low, mean, high = targets.get("low"), targets.get("mean"), targets.get("high")
    if is_num(mean):
        c = st.columns(4)
        c[0].metric("Price now", f"{price:,.2f}")
        c[1].metric("Lowest target", big(low))
        c[2].metric("Average target", big(mean), f"{(mean / price - 1) * 100:+.1f}% vs now")
        c[3].metric("Highest target", big(high))
    if is_num(low) and is_num(high) and is_num(mean):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[low, high], y=[0, 0], mode="lines", hoverinfo="skip",
                                 line=dict(color="#30363d", width=12)))
        for label, x, color in (("Now", price, "#ff9900"), ("Average target", mean, BLUE)):
            fig.add_trace(go.Scatter(x=[x], y=[0], mode="markers+text", text=[label],
                                     textposition="top center", name=label,
                                     marker=dict(size=16, color=color)))
        fig.update_layout(**LAYOUT, height=150, showlegend=False,
                          yaxis=dict(visible=False, range=[-1, 1.6]))
        st.plotly_chart(fig, theme=None)

    if has(recs) and "period" in recs.columns:
        st.markdown("#### What analysts say")
        when = {"0m": "This month", "-1m": "1 month ago", "-2m": "2 months ago",
                "-3m": "3 months ago"}
        recs = recs.iloc[::-1]
        x = [when.get(p, p) for p in recs["period"]]
        fig = go.Figure()
        for col, label, color in (("strongSell", "Strong sell", "#b71c1c"), ("sell", "Sell", RED),
                                  ("hold", "Hold", GREY), ("buy", "Buy", GREEN),
                                  ("strongBuy", "Strong buy", "#00897b")):
            if col in recs.columns:
                fig.add_trace(go.Bar(x=x, y=recs[col], name=label, marker_color=color))
        fig.update_layout(**LAYOUT, height=340, barmode="stack",
                          legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, theme=None)

    if has(ups):
        st.markdown("#### Latest upgrades and downgrades")
        table = pick(ups.reset_index().head(25),
                     {"GradeDate": "Date", "Firm": "Firm", "Action": "Action",
                      "FromGrade": "Old rating", "ToGrade": "New rating",
                      "currentPriceTarget": "Target"})
        if "Date" in table.columns:
            table["Date"] = pd.to_datetime(table["Date"], errors="coerce").dt.strftime("%d %b %Y")
        if "Action" in table.columns:
            names = {"up": "⬆️ Upgrade", "down": "⬇️ Downgrade", "main": "Maintained",
                     "init": "🆕 Started", "reit": "Reiterated"}
            table["Action"] = [names.get(a, a) for a in table["Action"]]
        if "Target" in table.columns:
            table["Target"] = table["Target"].map(lambda v: big(v) if is_num(v) and v > 0 else "")
        st.dataframe(table, hide_index=True)


def option_table(df, price, show_all):
    if not has(df):
        st.info("Nothing here.")
        return
    if not show_all and "strike" in df.columns:
        df = df[df["strike"].between(price * 0.8, price * 1.2)]
    itm = (df["inTheMoney"].fillna(False).astype(bool).to_numpy()
           if "inTheMoney" in df.columns else [False] * len(df))
    table = pick(df, {"strike": "Strike", "lastPrice": "Last", "bid": "Bid", "ask": "Ask",
                      "percentChange": "Chg %", "volume": "Volume",
                      "openInterest": "Open int", "impliedVolatility": "IV"})
    shade = pd.DataFrame("", index=table.index, columns=table.columns)
    shade.loc[list(itm)] = "background-color: rgba(88, 166, 255, 0.15)"
    formats = {"Strike": "{:,.2f}", "Last": "{:,.2f}", "Bid": "{:,.2f}", "Ask": "{:,.2f}",
               "Chg %": "{:+.2f}%", "Volume": "{:,.0f}", "Open int": "{:,.0f}",
               "IV": lambda v: f"{v * 100:.1f}%"}
    styled = (table.style.apply(lambda _: shade, axis=None)
              .format({k: v for k, v in formats.items() if k in table.columns}, na_rep="-"))
    if "Chg %" in table.columns:
        styled = styled.map(sign_color, subset=["Chg %"])
    st.dataframe(styled, hide_index=True, height=560)


def show_options(symbol, price):
    expiries = get_expiries(symbol)
    if not expiries:
        st.info("No options for this one.")
        return
    left, right = st.columns([3, 1], vertical_alignment="bottom")
    expiry = left.selectbox("Expiry date", expiries)
    show_all = right.toggle("Show all strikes")
    calls, puts = get_chain(symbol, expiry)
    call_vol = calls["volume"].sum() if has(calls) and "volume" in calls.columns else 0
    put_vol = puts["volume"].sum() if has(puts) and "volume" in puts.columns else 0
    m = st.columns(3)
    m[0].metric("Call volume", big(float(call_vol)))
    m[1].metric("Put volume", big(float(put_vol)))
    m[2].metric("Put/call ratio", f"{put_vol / call_vol:.2f}" if call_vol else "n/a")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 📈 Calls")
        option_table(calls, price, show_all)
    with c2:
        st.markdown("#### 📉 Puts")
        option_table(puts, price, show_all)
    st.caption("Highlighted rows are in the money. Option prices can be delayed.")


def show_insiders(symbol):
    data = get_extra(symbol, ("major_holders", "insider_transactions", "institutional_holders"))
    major, trades, inst = (data.get("major_holders"), data.get("insider_transactions"),
                           data.get("institutional_holders"))
    if not (has(major) or has(trades) or has(inst)):
        st.info("No ownership data for this one.")
        return

    if has(major) and "Value" in major.columns:
        v = major["Value"]
        count = v.get("institutionsCount")
        c = st.columns(3)
        c[0].metric("Owned by insiders", pct(v.get("insidersPercentHeld")))
        c[1].metric("Owned by institutions", pct(v.get("institutionsPercentHeld")))
        c[2].metric("Institutions holding", f"{int(count):,}" if is_num(count) else "n/a")

    if has(trades):
        st.markdown("#### Insider trades")
        t = trades.copy()
        text = t["Text"].fillna("").astype(str) if "Text" in t.columns else [""] * len(t)
        t["Type"] = ["Buy" if "Purchase" in s else "Sell" if "Sale" in s else "Other"
                     for s in text]
        m = st.columns(2)
        m[0].metric("Recent buys", int((t["Type"] == "Buy").sum()))
        m[1].metric("Recent sells", int((t["Type"] == "Sell").sum()))
        table = pick(t, {"Start Date": "Date", "Insider": "Insider", "Position": "Role",
                         "Type": "Type", "Shares": "Shares", "Value": "Value",
                         "Text": "Details"})
        if "Date" in table.columns:
            table["Date"] = pd.to_datetime(table["Date"], errors="coerce").dt.strftime("%d %b %Y")
        colors = {"Buy": GREEN, "Sell": RED}
        styled = (table.style
                  .map(lambda v: f"color: {colors.get(v, GREY)}", subset=["Type"])
                  .format({c: big for c in ("Shares", "Value") if c in table.columns},
                          na_rep="-"))
        st.dataframe(styled, hide_index=True, height=420)

    if has(inst):
        st.markdown("#### Biggest institutional holders")
        table = pick(inst, {"Holder": "Holder", "pctHeld": "% held", "Shares": "Shares",
                            "Value": "Value", "pctChange": "Change"})
        formats = {"% held": pct, "Shares": big, "Value": big,
                   "Change": lambda v: f"{v * 100:+.1f}%"}
        styled = table.style.format({k: v for k, v in formats.items() if k in table.columns},
                                    na_rep="-")
        if "Change" in table.columns:
            styled = styled.map(sign_color, subset=["Change"])
        st.dataframe(styled, hide_index=True)


def show_news(symbol):
    items = get_news(symbol)
    if not items:
        st.info("No news found right now.")
    for item in items[:15]:
        c = item.get("content", item)
        title = c.get("title")
        if not title:
            continue
        url = (c.get("canonicalUrl") or {}).get("url") or c.get("link") or ""
        source = (c.get("provider") or {}).get("displayName") or c.get("publisher") or ""
        when = str(c.get("pubDate") or "")[:16].replace("T", " ")
        headline = f"[{safe(title)}]({url})" if url else safe(title)
        st.markdown(f"**{headline}**  \n:gray[{safe(source)} · {when}]")
        st.divider()


def show_profile(info):
    p1, p2, p3 = st.columns(3)
    p1.metric("Sector", info.get("sector") or "n/a")
    p2.metric("Industry", info.get("industry") or "n/a")
    staff = info.get("fullTimeEmployees")
    p3.metric("Employees", f"{staff:,}" if is_num(staff) else "n/a")
    if info.get("website"):
        st.markdown(f"🌐 [{info['website']}]({info['website']})")
    st.write(safe(info.get("longBusinessSummary") or "No description found."))


def keep_symbol():
    st.session_state.saved_symbol = st.session_state.symbol


def stock_page():
    st.session_state.symbol = st.session_state.get("saved_symbol", "AAPL")
    symbol = st.text_input("Search", key="symbol", on_change=keep_symbol,
                           label_visibility="collapsed",
                           placeholder="Type a ticker like AAPL and press Enter").strip().upper()
    price, chg = price_change(symbol) if symbol else (None, None)
    if price is None:
        st.error(f"Couldn't find {symbol}. Check the ticker and try again.")
        return
    info = get_info(symbol)
    st.subheader(safe(info.get("longName") or info.get("shortName") or symbol))
    st.metric(symbol, f"{price:,.2f}", f"{chg:+.2f}%")

    section = choose("Section", SECTIONS, SECTIONS[0], "stock_section")
    if section == "📊 Chart":
        show_chart(symbol)
    elif section == "🔢 Key stats":
        show_stats(info, price)
    elif section == "💰 Financials":
        show_financials(symbol)
    elif section == "🎯 Analysts":
        show_analysts(symbol, price)
    elif section == "🧾 Options":
        show_options(symbol, price)
    elif section == "🕵️ Insiders":
        show_insiders(symbol)
    elif section == "📰 News":
        show_news(symbol)
    else:
        show_profile(info)


def compare_page():
    raw = st.text_input("Tickers to compare", "AAPL, MSFT, NVDA, SPY")
    choice = choose("Range", ["1M", "6M", "1Y", "5Y", "MAX"], "1Y", "cmp_range")
    period, interval = RANGES[choice]
    tickers = list(dict.fromkeys(
        t.strip().upper() for t in raw.replace(" ", ",").split(",") if t.strip()))
    fig = go.Figure()
    results = []
    for t in tickers:
        df = get_history(t, period, interval)
        if df.empty:
            st.warning(f"Couldn't find {t}.")
            continue
        closes = df["Close"].copy()
        if closes.index.tz is not None:
            closes.index = closes.index.tz_localize(None)
        growth = (closes / closes.iloc[0] - 1) * 100
        fig.add_trace(go.Scatter(x=growth.index, y=growth, name=t, mode="lines"))
        results.append((t, float(growth.iloc[-1])))
    if not results:
        return
    fig.update_layout(**LAYOUT, height=520, hovermode="x unified", yaxis_ticksuffix="%")
    st.plotly_chart(fig, theme=None)
    cols = st.columns(len(results))
    for col, (t, g) in zip(cols, sorted(results, key=lambda r: -r[1])):
        col.metric(t, f"{g:+.2f}%")


def draw_heatmap(df):
    def avg(group):
        return float((group["Change"] * group["Cap"]).sum() / group["Cap"].sum())

    overall = avg(df)
    ids, labels, parents, values = ["All"], ["US market"], [""], [0.0]
    colors, texts, names = [overall], [f"{overall:+.2f}%"], ["Whole market"]
    for sector, group in df.groupby("Sector"):
        move = avg(group)
        ids.append(sector)
        labels.append(sector)
        parents.append("All")
        values.append(0.0)
        colors.append(move)
        texts.append(f"{move:+.2f}%")
        names.append(f"{len(group)} stocks")
        for r in group.itertuples():
            ids.append(f"{sector}/{r.Ticker}")
            labels.append(r.Ticker)
            parents.append(sector)
            values.append(r.Cap)
            colors.append(r.Change)
            texts.append(f"{r.Change:+.2f}%")
            names.append(r.Name)
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="remainder",
        text=texts, customdata=names, textposition="middle center",
        texttemplate="<b>%{label}</b><br>%{text}",
        hovertemplate="<b>%{label}</b><br>%{customdata}<br>%{text}<extra></extra>",
        marker=dict(colors=colors, cmin=-3, cmax=3,
                    colorscale=[[0, "#c62828"], [0.5, "#3a3f47"], [1, "#2e7d32"]],
                    line=dict(color="#0e1117", width=1)),
        textfont=dict(color="white"), root_color="#0e1117"))
    fig.update_layout(**LAYOUT, height=720)
    st.plotly_chart(fig, theme=None)


def heatmap_page():
    with st.spinner("Loading the market map..."):
        df, live = get_heatmap()
    if not has(df):
        st.info("Couldn't load the market map right now. Try again in a minute.")
        return
    best = df.loc[df["Change"].idxmax()]
    worst = df.loc[df["Change"].idxmin()]
    c = st.columns(4)
    c[0].metric("Stocks up", int((df["Change"] > 0).sum()))
    c[1].metric("Stocks down", int((df["Change"] < 0).sum()))
    c[2].metric("Best", best["Ticker"], f"{best['Change']:+.2f}%")
    c[3].metric("Worst", worst["Ticker"], f"{worst['Change']:+.2f}%")
    draw_heatmap(df)
    if live:
        st.caption("Biggest US-listed companies, sized by market value and coloured by "
                   "today's move. Click a sector to zoom in, click the top bar to zoom out.")
    else:
        st.caption("Big US companies coloured by today's move. Click a sector to zoom in, "
                   "click the top bar to zoom out.")


def movers_page():
    choice = choose("List", ["🚀 Top gainers", "📉 Top losers", "🔥 Most active"],
                    "🚀 Top gainers", "movers_list")
    kind = {"🚀 Top gainers": "day_gainers", "📉 Top losers": "day_losers",
            "🔥 Most active": "most_actives"}[choice]
    df = get_movers(kind)
    if df.empty:
        st.info("Couldn't load this list right now.")
        return
    styled = (df.style
              .map(sign_color, subset=["Change %"])
              .format({"Price": "{:,.2f}", "Change %": "{:+.2f}%",
                       "Volume": big, "Market cap": big}, na_rep="n/a"))
    st.dataframe(styled, hide_index=True, height=600)


def portfolio_page():
    pf = st.session_state.portfolio
    with st.form("holding", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1], vertical_alignment="bottom")
        ticker = c1.text_input("Ticker", placeholder="e.g. AAPL").strip().upper()
        shares = c2.number_input("Shares", min_value=0.0, step=1.0, format="%.4f")
        cost = c3.number_input("Price you paid per share", min_value=0.0, step=1.0,
                               format="%.2f")
        added = c4.form_submit_button("Add")
    st.caption("Leave the price at 0 to use today's price. Adding a stock you already "
               "own averages it in.")
    if added and ticker and shares > 0:
        now, _ = price_change(ticker)
        if now is None:
            st.warning(f"Couldn't find {ticker}.")
        else:
            cost = cost or now
            old = next((h for h in pf if h["ticker"] == ticker), None)
            if old:
                total = old["shares"] + shares
                old["cost"] = (old["shares"] * old["cost"] + shares * cost) / total
                old["shares"] = total
            else:
                pf.append({"ticker": ticker, "shares": shares, "cost": cost})
            save("portfolio.json", pf)

    if not pf:
        st.info("Add your first holding above to start tracking it.")
        return

    rows = []
    for h in pf:
        price, chg = price_change(h["ticker"])
        if price is None:
            continue
        value = h["shares"] * price
        basis = h["shares"] * h["cost"]
        prev = price / (1 + chg / 100)
        rows.append({"Ticker": h["ticker"], "Shares": h["shares"], "Avg cost": h["cost"],
                     "Price": price, "Value": value, "P/L": value - basis,
                     "P/L %": (value / basis - 1) * 100 if basis else 0.0,
                     "Today": h["shares"] * (price - prev)})
    if not rows:
        st.warning("Couldn't load prices right now.")
        return
    df = pd.DataFrame(rows).sort_values("Value", ascending=False)
    value, basis, today = df["Value"].sum(), (df["Value"] - df["P/L"]).sum(), df["Today"].sum()
    m = st.columns(3)
    m[0].metric("Portfolio value", f"{value:,.2f}", f"{today:+,.2f} today")
    m[1].metric("Total profit/loss", f"{value - basis:+,.2f}",
                f"{(value / basis - 1) * 100:+.2f}%" if basis else None)
    m[2].metric("Holdings", len(df))

    left, right = st.columns([3, 2])
    with left:
        styled = (df.style
                  .map(sign_color, subset=["P/L", "P/L %", "Today"])
                  .format({"Shares": qty, "Avg cost": "{:,.2f}", "Price": "{:,.2f}",
                           "Value": "{:,.2f}", "P/L": "{:+,.2f}", "P/L %": "{:+.2f}%",
                           "Today": "{:+,.2f}"}))
        st.dataframe(styled, hide_index=True)
        a, b = st.columns([3, 1], vertical_alignment="bottom")
        gone = a.selectbox("Remove a holding", [h["ticker"] for h in pf], index=None,
                           placeholder="Pick one")
        if b.button("Remove", key="pf_remove") and gone:
            st.session_state.portfolio = [h for h in pf if h["ticker"] != gone]
            save("portfolio.json", st.session_state.portfolio)
            st.rerun()
    with right:
        fig = go.Figure(go.Pie(labels=df["Ticker"], values=df["Value"], hole=0.55,
                               textinfo="label+percent", sort=False))
        fig.update_layout(**LAYOUT, height=360, showlegend=False)
        st.plotly_chart(fig, theme=None)


def alerts_page():
    alerts = st.session_state.alerts
    with st.form("alert", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1], vertical_alignment="bottom")
        ticker = c1.text_input("Ticker", placeholder="e.g. NVDA").strip().upper()
        op = c2.selectbox("When the price goes", ["Above", "Below"])
        target = c3.number_input("Price", min_value=0.0, step=1.0, format="%.2f")
        added = c4.form_submit_button("Add")
    st.caption("Alerts are checked every 15 seconds while this app is open, and pop up "
               "in the corner on any page.")
    if added and ticker and target > 0:
        if price_change(ticker)[0] is None:
            st.warning(f"Couldn't find {ticker}.")
        else:
            alerts.append({"ticker": ticker, "op": op, "price": target, "hit": None})
            save("alerts.json", alerts)

    if not alerts:
        st.info("No alerts yet. Add one above.")
        return
    for i, a in enumerate(alerts):
        price, _ = price_change(a["ticker"])
        c1, c2, c3, c4 = st.columns([2, 3, 3, 1], vertical_alignment="center")
        c1.markdown(f"**{a['ticker']}**")
        c2.write(f"{a['op']} {a['price']:,.2f}")
        if a.get("hit"):
            c3.write(f"🔔 Hit at {a['hit']}")
        else:
            c3.write(f"⏳ Waiting · now {price:,.2f}" if price is not None else "⏳ Waiting")
        if c4.button("✕", key=f"alert_{i}_{a['ticker']}_{a['price']}"):
            alerts.pop(i)
            save("alerts.json", alerts)
            st.rerun()


st.title("📈 Mint Terminal")
market_bar()
alert_checker()

with st.sidebar:
    st.header("⭐ Watchlist")
    with st.form("edit", clear_on_submit=True):
        entry = st.text_input("Add or remove a ticker", placeholder="e.g. AMD").strip().upper()
        add_col, remove_col = st.columns(2)
        add = add_col.form_submit_button("Add")
        remove = remove_col.form_submit_button("Remove")
    wl = st.session_state.watchlist
    if add and entry:
        if entry in wl:
            st.info(f"{entry} is already on your list.")
        elif price_change(entry)[0] is None:
            st.warning(f"Couldn't find {entry}.")
        else:
            wl.append(entry)
            save("watchlist.json", wl)
    if remove and entry in wl:
        wl.remove(entry)
        save("watchlist.json", wl)
    watchlist_panel()

PAGES = {"🔎 Stock": stock_page, "⚖️ Compare": compare_page, "🗺️ Heatmap": heatmap_page,
         "🚀 Top movers": movers_page, "💼 Portfolio": portfolio_page, "🔔 Alerts": alerts_page}
PAGES[choose("Page", list(PAGES), "🔎 Stock", "nav")]()
