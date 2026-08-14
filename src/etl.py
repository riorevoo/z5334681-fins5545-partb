"""Station 1 - your ETL: load and clean the data.

Load raw data through src.data_access (see context/DATA_GUIDE.md). Add your own
integrity checks. Do not commit data files.
"""
import pandas as pd

from src import data_access

CRYPTO_SAMPLE_END = pd.Timestamp("2023-12-31")


def load_clean_equities() -> pd.DataFrame:
    """Load equity prices and run Station 1 integrity checks.

    Checks: every ticker shares the same trading calendar (flags any that
    don't), no duplicate (ticker, date) rows, and a |return| > 5 std-dev
    outlier flag (kept, not dropped - these can be real events).
    """
    df = data_access.load_equity_prices().copy()

    dup = df.duplicated(subset=["ticker", "date"]).sum()
    assert dup == 0, f"{dup} duplicate (ticker, date) rows in equity_prices"

    calendars = df.groupby("ticker")["date"].apply(lambda s: frozenset(s))
    modal_calendar = calendars.value_counts().idxmax()
    missing = {t: len(modal_calendar - c) for t, c in calendars.items() if c != modal_calendar}
    if missing:
        print(f"[etl] equities: {len(missing)} ticker(s) off the modal {len(modal_calendar)}-day "
              f"calendar: {missing}")
    else:
        print(f"[etl] equities: all {df['ticker'].nunique()} tickers share one "
              f"{len(modal_calendar)}-day trading calendar")

    ret = df.sort_values(["ticker", "date"]).groupby("ticker")["adjClose"].pct_change()
    z = (ret - ret.mean()) / ret.std()
    df["outlier_return"] = z.abs() > 5
    n_out = int(df["outlier_return"].sum())
    print(f"[etl] equities: {n_out} return observations flagged as outliers (|z| > 5), kept")

    return df


def load_clean_crypto() -> pd.DataFrame:
    """Load crypto prices (365-day calendar), cap at 2023-12-31, dedup, outlier flag."""
    df = data_access.load_crypto_prices().copy()

    before = len(df)
    df = df[df["date"] <= CRYPTO_SAMPLE_END].copy()
    dropped = before - len(df)
    print(f"[etl] crypto: dropped {dropped} rows after {CRYPTO_SAMPLE_END.date()} "
          f"(stray sample-end rows)")
    assert df["date"].max() == CRYPTO_SAMPLE_END, "crypto sample not capped at 2023-12-31"

    dup = df.duplicated(subset=["ticker", "date"]).sum()
    assert dup == 0, f"{dup} duplicate (ticker, date) rows in crypto_prices"

    ret = df.sort_values(["ticker", "date"]).groupby("ticker")["adjClose"].pct_change()
    z = (ret - ret.mean()) / ret.std()
    df["outlier_return"] = z.abs() > 5
    n_out = int(df["outlier_return"].sum())
    print(f"[etl] crypto: {n_out} return observations flagged as outliers (|z| > 5), kept")

    return df
