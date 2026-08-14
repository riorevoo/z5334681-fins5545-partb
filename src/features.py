"""Station 2 - your features: return features and text assembly.

Build your return features here, and assemble the headlines into a daily text
panel. Scoring the text is the Station 3 sentiment model (see src/sentiment.py).
"""
import pandas as pd


def daily_returns(prices: pd.DataFrame, price_col: str = "adjClose") -> pd.DataFrame:
    """Simple daily returns per ticker, long format [ticker, date, ret].

    Uses adjClose so splits/dividends don't show up as spurious return
    jumps. pct_change() is computed within each ticker's own calendar
    (groupby before pct_change), so the first observation per ticker is NaN
    and no return ever crosses a ticker boundary.
    """
    out = prices[["ticker", "date", price_col]].sort_values(["ticker", "date"]).copy()
    out["ret"] = out.groupby("ticker")[price_col].pct_change()
    return out[["ticker", "date", "ret"]]


def assemble_headline_panel(headlines: pd.DataFrame) -> pd.DataFrame:
    """Assemble the headlines into a daily panel per ticker and sector.

    Station 2 is assembly only: dedup, normalise the timezone, and align each
    headline to the trading day it should count for (same day if it's a
    trading day, else the next trading day). Scoring the text - and lagging
    the resulting signal - is the Station 3 model (src/sentiment.py).
    """
    from src import etl

    df = headlines.copy()
    before = len(df)
    df = df.drop_duplicates(subset=["ticker", "date", "title"])
    print(f"[features] headlines: dropped {before - len(df)} exact duplicates "
          f"on (ticker, date, title)")

    # news `date` is tz-aware UTC; price dates are tz-naive - normalise to
    # a plain calendar date before aligning to the trading calendar.
    df["news_date"] = df["date"].dt.tz_localize(None).dt.normalize()

    trading_days = pd.DatetimeIndex(
        sorted(etl.load_clean_equities()["date"].unique())
    )

    # Drop headlines dated after the last trading day - there's no "next
    # trading day" in-sample to attribute them to (a handful of headlines
    # trail the Dec-29 last trading day into the Dec 30-31 weekend).
    beyond = df["news_date"] > trading_days[-1]
    if beyond.any():
        print(f"[features] headlines: dropped {int(beyond.sum())} dated after "
              f"the last trading day {trading_days[-1].date()} (no next trading "
              f"day in-sample)")
        df = df.loc[~beyond].copy()

    # Map each calendar date to the trading day it should be attributed to:
    # itself if it IS a trading day, else the next trading day on/after it.
    positions = trading_days.searchsorted(df["news_date"], side="left")
    trading_date = pd.Series(trading_days[positions], index=df.index)

    shifted = (trading_date.values != df["news_date"].values).sum()
    print(f"[features] headlines: {shifted} of {len(df)} rolled forward onto "
          f"the next trading day (fell on a non-trading date)")

    df["trading_date"] = trading_date
    return df[["ticker", "sector", "trading_date", "title", "news_date"]]
