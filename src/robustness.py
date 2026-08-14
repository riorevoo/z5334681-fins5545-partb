"""Station 3 (extension) - robustness checks for the sentiment fusion.

The fusion comparison in src/fusion.py + scripts/run_part_b.py answers "did
the tilt change the Sharpe ratio". It does not answer two harder questions
the report also makes claims about:

1. Predictive power - does lagged sentiment actually forecast subsequent
   equity returns at any horizon, or does it only describe the return that
   already happened (contemporaneous, not predictive)?
2. Placebo test - is the *specific ticker-level mapping* of real sentiment
   scores doing anything different from a random relabelling of the same
   day's sentiment values across tickers?

Both are built as reproducible functions here, consumed by
scripts/run_part_b.py, so every number they produce traces to a re-runnable
computation rather than a one-off scratch calculation (see CLAUDE.md).
"""
import numpy as np
import pandas as pd
from scipy import stats

from src import fusion, portfolios

HORIZONS = (1, 5, 21)


def _pooled_corr(a: pd.DataFrame, b: pd.DataFrame) -> tuple:
    x = a.values.ravel()
    y = b.values.ravel()
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask], y[mask]
    r, p = stats.pearsonr(x, y)
    return float(r), float(p), int(mask.sum())


def predictive_power(tsi: pd.DataFrame, daily_ret_long: pd.DataFrame) -> pd.DataFrame:
    """Pool every (ticker, trading_date) observation and correlate that
    day's sentiment against the same-day return and against forward h-day
    cumulative returns, for h in HORIZONS.

    `tsi`: [ticker, trading_date, compound] (sentiment.ticker_sentiment_index).
    `daily_ret_long`: [ticker, date, ret] (features.daily_returns).

    A horizon-h forward return at date t is the cumulative return from t+1
    to t+h - strictly after the sentiment observation date, so this is a
    genuine predictive (not look-ahead) test.
    """
    ret_wide = daily_ret_long.pivot(index="date", columns="ticker", values="ret").sort_index()
    sent_wide = tsi.pivot(index="trading_date", columns="ticker", values="compound").sort_index()
    tickers = [t for t in sent_wide.columns if t in ret_wide.columns]
    sent_wide = sent_wide[tickers]
    ret_wide = ret_wide[tickers]

    rows = []
    same_day_ret = ret_wide.reindex(sent_wide.index)
    r, p, n = _pooled_corr(sent_wide, same_day_ret)
    rows.append({"horizon": "same_day", "correlation": r, "p_value": p, "n_obs": n})

    cumgrowth = (1 + ret_wide.fillna(0)).cumprod()
    for h in HORIZONS:
        fwd = (cumgrowth.shift(-h) / cumgrowth - 1).reindex(sent_wide.index)
        r, p, n = _pooled_corr(sent_wide, fwd)
        rows.append({"horizon": f"{h}d", "correlation": r, "p_value": p, "n_obs": n})

    return pd.DataFrame(rows)


def _shuffle_wide(wide: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Permute values across tickers within each trading date independently -
    preserves that date's cross-sectional distribution of sentiment while
    destroying which ticker each score belonged to."""
    arr = wide.to_numpy(copy=True)
    for i in range(arr.shape[0]):
        rng.shuffle(arr[i])
    return pd.DataFrame(arr, index=wide.index, columns=wide.columns)


def placebo_test(weights: pd.DataFrame, sentiment: pd.DataFrame, wide_returns: pd.DataFrame,
                  k: float = fusion.TILT_INTENSITY, n_shuffles: int = 300, seed: int = 0) -> dict:
    """Real sentiment-tilt Sharpe vs the distribution of Sharpe ratios from
    `n_shuffles` cross-sectionally-shuffled sentiment placebos, same fund,
    same k, same backtest mechanics - only the ticker-sentiment mapping
    changes."""
    rng = np.random.default_rng(seed)
    wide_sent = sentiment.pivot(index="trading_date", columns="ticker", values="compound").sort_index()

    real_tw = fusion.apply_sentiment(weights, sentiment, k=k)
    real_bt = portfolios.weights_to_backtest(real_tw, wide_returns)
    real_sharpe = portfolios.performance_metrics(real_bt["daily_returns"])["sharpe"]

    shuffled_sharpes = np.empty(n_shuffles)
    for i in range(n_shuffles):
        shuffled_sent = _shuffle_wide(wide_sent, rng).reset_index().melt(
            id_vars="trading_date", var_name="ticker", value_name="compound")
        tw = fusion.apply_sentiment(weights, shuffled_sent, k=k)
        bt = portfolios.weights_to_backtest(tw, wide_returns)
        shuffled_sharpes[i] = portfolios.performance_metrics(bt["daily_returns"])["sharpe"]

    percentile = float((shuffled_sharpes < real_sharpe).mean() * 100)
    return {
        "real_sharpe": float(real_sharpe),
        "shuffle_mean": float(shuffled_sharpes.mean()),
        "shuffle_std": float(shuffled_sharpes.std(ddof=1)),
        "percentile": percentile,
        "n_shuffles": n_shuffles,
    }


def weight_tilt_correlation(weights: pd.DataFrame, sentiment: pd.DataFrame) -> dict:
    """At each rebalance date, correlate the fund's pre-tilt (baseline)
    weight per ticker against the same lagged sentiment z-score
    fusion.apply_sentiment tilts by - i.e. was the tilt systematically
    pulling weight away from (or toward) the optimiser's already-favoured
    names. Reports the mean Pearson and mean Spearman correlation across
    all rebalance dates, each with a one-sample t-test of whether that mean
    differs from zero."""
    tickers = list(weights.columns)
    wide_sent = sentiment.pivot(index="trading_date", columns="ticker", values="compound").sort_index()

    pearsons, spearmans = [], []
    for d in weights.index:
        z = fusion.lagged_zscore(wide_sent, tickers, d)
        w = weights.loc[d, tickers]
        if w.std() < 1e-12:
            # Equal-weight funds hold a constant weight across tickers at every
            # rebalance, so there is no cross-sectional weight variation to
            # correlate against sentiment - undefined by construction, not a bug.
            continue
        pearsons.append(stats.pearsonr(w, z)[0])
        spearmans.append(stats.spearmanr(w, z)[0])

    if not pearsons:
        return {"n_dates": 0, "mean_pearson": float("nan"), "pearson_pvalue": float("nan"),
                "mean_spearman": float("nan"), "spearman_pvalue": float("nan")}

    pearsons = np.array(pearsons)
    spearmans = np.array(spearmans)
    _, p_pearson = stats.ttest_1samp(pearsons, popmean=0.0)
    _, p_spearman = stats.ttest_1samp(spearmans, popmean=0.0)
    return {
        "n_dates": len(pearsons),
        "mean_pearson": float(pearsons.mean()),
        "pearson_pvalue": float(p_pearson),
        "mean_spearman": float(spearmans.mean()),
        "spearman_pvalue": float(p_spearman),
    }
