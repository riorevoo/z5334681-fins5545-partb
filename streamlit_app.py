"""FinTech Project - your investment app.

The investor journey: compare the funds, open a fund's fact sheet, set an
allocation across funds, and read the sentiment analytics. Everything here
reads precomputed artifacts from results/ (written by scripts/run_part_b.py)
- this file must never run the sentiment-scoring model or recompute a
backtest, since the free deploy tier can't afford either (see
docs/STUDENT_DEPLOY.md and requirements-dev.txt).

Run locally:   streamlit run streamlit_app.py
Deploy:        push this folder to a public GitHub repo, then connect it on
               share.streamlit.io with entrypoint streamlit_app.py (see brief App. D).
"""
import sys
import pathlib
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st  # noqa: E402

from src import data_access  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
DATA_DIR = ROOT / "results" / "data"
TAB_DIR = ROOT / "results" / "tables"

CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

# A light, tiled money-emoji watermark on a grey page background - built as an
# inline SVG data URI so it needs no separate asset file.
_WATERMARK_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'>"
    "<text x='8' y='45' font-size='30' opacity='0.12' "
    "transform='rotate(-15 8 45)'>\U0001F4B5</text>"
    "<text x='108' y='28' font-size='22' opacity='0.10' "
    "transform='rotate(10 108 28)'>\U0001F4B5</text>"
    "<text x='68' y='140' font-size='26' opacity='0.11' "
    "transform='rotate(-8 68 140)'>\U0001F4B5</text>"
    "</svg>"
)
_WATERMARK_URI = "data:image/svg+xml," + urllib.parse.quote(_WATERMARK_SVG)

st.set_page_config(page_title="Folio DiversInator", layout="wide", page_icon="📊")
st.markdown(
    f"""
    <style>
    [data-testid="stAppViewContainer"] {{
        background-color: #e4e3e0;
        background-image: url("{_WATERMARK_URI}");
        background-repeat: repeat;
    }}
    [data-testid="stHeader"] {{
        background-color: rgba(0, 0, 0, 0);
    }}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Folio DiversInator")
st.caption("Built for a self-directed investor comparing systematic equity, crypto, and combined "
           "strategies. Compare funds, open a fact sheet, build an allocation, and read the "
           "sentiment analytics behind the equity funds.")


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#e5e4e0", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


@st.cache_data(ttl=86_400, show_spinner="Loading data...")
def _equities():
    return data_access.load_equity_prices()


@st.cache_data(ttl=86_400, show_spinner="Loading data...")
def _crypto():
    return data_access.load_crypto_prices()


@st.cache_data(ttl=86_400, show_spinner="Loading data...")
def _news():
    return data_access.load_news_headlines()


@st.cache_data(ttl=86_400, show_spinner=False)
def _fund_returns():
    return pd.read_csv(DATA_DIR / "fund_returns.csv", parse_dates=["date"])


@st.cache_data(ttl=86_400, show_spinner=False)
def _fund_weights():
    return pd.read_csv(DATA_DIR / "fund_weights.csv", parse_dates=["date"])


@st.cache_data(ttl=86_400, show_spinner=False)
def _performance_metrics():
    return pd.read_csv(TAB_DIR / "performance_metrics.csv", parse_dates=["first_live_date"])


@st.cache_data(ttl=86_400, show_spinner=False)
def _sector_sentiment_index():
    return pd.read_csv(DATA_DIR / "sector_sentiment_index.csv", parse_dates=["trading_date"])


@st.cache_data(ttl=86_400, show_spinner=False)
def _fusion_comparison():
    return pd.read_csv(TAB_DIR / "fusion_comparison.csv")


@st.cache_data(ttl=86_400, show_spinner=False)
def _neutral_rate():
    return pd.read_csv(TAB_DIR / "lexicon_neutral_rate.csv").iloc[0]


tab_funds, tab_sentiment, tab_data = st.tabs(["Funds", "Sentiment", "Data"])

# ---------------------------------------------------------------- Funds ----
with tab_funds:
    perf = _performance_metrics()
    returns = _fund_returns()
    weights = _fund_weights()

    st.subheader("Compare funds")
    display = perf[["fund", "asset_family", "method", "first_live_date",
                     "annualised_return", "annualised_vol", "sharpe", "max_drawdown"]].copy()
    display["annualised_return"] = (display["annualised_return"] * 100).round(1).astype(str) + "%"
    display["annualised_vol"] = (display["annualised_vol"] * 100).round(1).astype(str) + "%"
    display["max_drawdown"] = (display["max_drawdown"] * 100).round(1).astype(str) + "%"
    display["sharpe"] = display["sharpe"].round(2)
    st.dataframe(display, width="stretch", hide_index=True)

    st.subheader("Fund fact sheet")
    fund_name = st.selectbox("Choose a fund", sorted(perf["fund"].unique()))
    row = perf.loc[perf["fund"] == fund_name].iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Annualised return", f"{row['annualised_return']:.1%}")
    c2.metric("Annualised volatility", f"{row['annualised_vol']:.1%}")
    c3.metric("Sharpe (rf=0)", f"{row['sharpe']:.2f}")
    c4.metric("Max drawdown", f"{row['max_drawdown']:.1%}")
    st.caption(f"First live (out-of-sample) date: {row['first_live_date'].date()} "
               f"- window {row['window']} trading days, rebalanced monthly.")

    fund_ret = returns.loc[returns["fund"] == fund_name].sort_values("date")
    growth = (1 + fund_ret.set_index("date")["daily_return"]).cumprod()
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(growth.index, growth.values, color=CAT[0], linewidth=2)
    _style(ax)
    ax.set_title(f"Growth of $1 - {fund_name}")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    st.markdown("**Current holdings** (target weights from the most recent rebalance)")
    fw = weights.loc[weights["fund"] == fund_name]
    latest_date = fw["date"].max()
    holdings = (fw.loc[fw["date"] == latest_date]
                .query("weight > 0.001")
                .sort_values("weight", ascending=False))
    fig, ax = plt.subplots(figsize=(9, max(3, 0.25 * len(holdings))))
    ax.barh(holdings["ticker"], holdings["weight"], color=CAT[0])
    _style(ax)
    ax.invert_yaxis()
    ax.set_xlabel("Weight")
    ax.set_title(f"Holdings as of {latest_date.date()}")
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

    st.subheader("Build your own allocation")
    st.caption("Blends the already-computed daily returns of the funds you pick - pure arithmetic on "
               "precomputed series, so this runs live without recomputing any backtest.")
    chosen = st.multiselect("Funds to include", sorted(perf["fund"].unique()),
                             default=["equity_min_variance", "crypto_min_variance"])
    if chosen:
        alloc = {}
        cols = st.columns(len(chosen))
        for col, f in zip(cols, chosen):
            alloc[f] = col.slider(f, 0, 100, int(100 / len(chosen)), key=f"alloc_{f}")
        total = sum(alloc.values())
        if total == 0:
            st.warning("Set at least one allocation above 0%.")
        else:
            weights_norm = {f: v / total for f, v in alloc.items()}
            wide = returns.pivot(index="date", columns="fund", values="daily_return")
            common = wide[chosen].dropna(how="any")
            blended = sum(common[f] * w for f, w in weights_norm.items())
            blended_growth = (1 + blended).cumprod()

            ann_return = (1 + blended).prod() ** (252 / len(blended)) - 1
            ann_vol = blended.std() * (252 ** 0.5)
            sharpe = ann_return / ann_vol if ann_vol > 0 else float("nan")
            wealth = blended_growth
            drawdown = (wealth / wealth.cummax() - 1).min()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Blended annualised return", f"{ann_return:.1%}")
            c2.metric("Blended annualised volatility", f"{ann_vol:.1%}")
            c3.metric("Blended Sharpe (rf=0)", f"{sharpe:.2f}")
            c4.metric("Blended max drawdown", f"{drawdown:.1%}")

            fig, ax = plt.subplots(figsize=(9, 4))
            ax.plot(blended_growth.index, blended_growth.values, color=CAT[1], linewidth=2)
            _style(ax)
            ax.set_title("Growth of $1 - your allocation")
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
            st.caption(f"Blended over {len(common)} trading days common to all selected funds' calendars.")

# ------------------------------------------------------------ Sentiment ----
with tab_sentiment:
    st.subheader("Sector sentiment index")
    st.caption("Extended-lexicon VADER score, equal-weighted across tickers within each sector. "
               "See the report for the no-headline-day treatment and lexicon methodology.")
    sector_idx = _sector_sentiment_index()
    sectors = sorted(sector_idx["sector"].unique())
    chosen_sectors = st.multiselect("Sectors", sectors, default=sectors[:3])
    if chosen_sectors:
        fig, ax = plt.subplots(figsize=(9, 5))
        for i, sec in enumerate(chosen_sectors):
            s = sector_idx.loc[sector_idx["sector"] == sec].set_index("trading_date")["sentiment"]
            ax.plot(s.index, s.rolling(20).mean().values, color=CAT[i % len(CAT)], linewidth=1.5, label=sec)
        _style(ax)
        ax.axhline(0, color="#9a9a95", linewidth=1)
        ax.set_ylabel("Sentiment (20-day rolling mean)")
        ax.legend(frameon=False)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    st.subheader("VADER lexicon extension: neutral-headline rate")
    nr = _neutral_rate()
    c1, c2 = st.columns(2)
    c1.metric("Vanilla VADER", f"{nr['vanilla_neutral_rate']:.1%}")
    c2.metric("Extended lexicon", f"{nr['extended_neutral_rate']:.1%}",
              delta=f"{(nr['extended_neutral_rate'] - nr['vanilla_neutral_rate']):.1%}")

    st.subheader("Fusion: before vs after")
    st.caption("Equity funds only - sentiment tilt applied to the walk-forward weights, "
               "lagged at least one trading day.")
    fusion_df = _fusion_comparison()
    base_and_tilt = fusion_df[fusion_df["variant"].isin(["base", "vanilla_tilt", "extended_tilt"])]
    pivoted = base_and_tilt.pivot(index="fund", columns="variant", values="sharpe")[
        ["base", "vanilla_tilt", "extended_tilt"]]
    fig, ax = plt.subplots(figsize=(9, 5))
    x = range(len(pivoted))
    width = 0.25
    for i, variant in enumerate(["base", "vanilla_tilt", "extended_tilt"]):
        ax.bar([xi + (i - 1) * width for xi in x], pivoted[variant].values, width=width,
               color=CAT[i], label=variant.replace("_", " "))
    _style(ax)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f.replace("equity_", "") for f in pivoted.index])
    ax.set_ylabel("Sharpe ratio (rf=0)")
    ax.legend(frameon=False)
    fig.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

# ----------------------------------------------------------------- Data ----
with tab_data:
    st.caption("Previews of the three source datasets behind the funds and the sentiment index. "
               "Loaded once from the hosted data bundle and cached - the app never re-downloads "
               "or recomputes on each view.")

    eq = _equities()
    st.subheader("Equity prices")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows", f"{eq.shape[0]:,}")
    c2.metric("Tickers / sectors", f"{eq['ticker'].nunique()} / {eq['sector'].nunique()}")
    c3.metric("Date range", f"{eq['date'].min().date()} – {eq['date'].max().date()}")
    st.dataframe(eq.head(20), width="stretch", hide_index=True)

    crypto = _crypto()
    st.subheader("Crypto prices")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows", f"{crypto.shape[0]:,}")
    c2.metric("Coins", f"{crypto['ticker'].nunique()}")
    c3.metric("Date range", f"{crypto['date'].min().date()} – {crypto['date'].max().date()}")
    st.caption("Trades 7 days/week, price-only (no sector) - see the report for why crypto and "
               "equity returns are computed on their own calendars before merging.")
    st.dataframe(crypto.head(20), width="stretch", hide_index=True)

    news = _news()
    st.subheader("News headlines")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rows", f"{news.shape[0]:,}")
    c2.metric("Tickers covered", f"{news['ticker'].nunique()}")
    c3.metric("Date range", f"{news['date'].min().date()} – {news['date'].max().date()}")
    st.caption("Equity-only - this is the text the sentiment model in the Sentiment tab scores. "
               "Deduplicated on (ticker, date, title) upstream of this view.")
    st.dataframe(news.head(20), width="stretch", hide_index=True)
