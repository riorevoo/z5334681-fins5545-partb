"""Station 3 (extension) - fuse sentiment into the funds.

Tilt or factor: combine your sentiment signal with the portfolio weights,
look-ahead safe, then test whether it adds value. An honest negative result,
explained, is good work.

Tilt rule: at each rebalance date, cross-sectionally z-score the lagged
(>=1 trading day) per-ticker sentiment among the fund's own tickers, then
scale each weight by (1 + k * z), clip at 0 (long-only), and renormalise to
sum to 1. Equity funds only - sentiment has no crypto coverage. `k` (tilt
intensity) defaults to 0.5; see the report for a 0.25/0.5/1.0 sensitivity
check.

The same MAX_WEIGHT cap the optimiser enforces (src/portfolios.py) is
re-applied here after the tilt. A plain clip-then-renormalise does not
guarantee the cap survives renormalisation (pushing a near-cap weight back
above it), so any weight left over MAX_WEIGHT after the tilt is capped and
its excess is redistributed proportionally among the not-yet-capped
tickers, repeating until every weight is within bounds. Caught in an
AI-assisted audit: without this, the tilt could push a single name to ~47%
of an equity fund, well past the stated 30% concentration limit - see
ai/log_07_fusion_weight_cap.md.
"""
import numpy as np
import pandas as pd

from src.portfolios import MAX_WEIGHT

TILT_INTENSITY = 0.5


def _cap_and_renormalise(w: pd.Series, cap: float = MAX_WEIGHT, tol: float = 1e-9) -> pd.Series:
    """Project a non-negative, sum-to-1 weight vector onto {0 <= w_i <= cap,
    sum(w) = 1} by water-filling: cap every weight above `cap`, and
    redistribute the excess proportionally among the still-uncapped
    weights, repeating until nothing exceeds `cap` (or every weight is
    capped/zero, which cannot happen here since cap * n_tickers >> 1).

    Deliberately does NOT do a final blanket `w / w.sum()` rescale: that
    single division nudges weights already sitting exactly at `cap` back
    above it by floating-point drift (observed up to ~1e-6 on real
    rebalance dates), silently reintroducing the cap breach this function
    exists to remove. Instead, any leftover floating-point residual is
    folded only into the still-uncapped weights, so a weight once set to
    `cap` is never touched again."""
    w = w.copy().astype(float)
    for _ in range(200):
        over = w > cap + tol
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        under = (~over) & (w > tol)
        if not under.any():
            break
        w[under] = w[under] + excess * (w[under] / w[under].sum())

    # Unconditional backstop: the last redistribution pass above can itself
    # push a weight a hair past `cap` with no further pass left to re-catch
    # it (observed empirically, e.g. 0.300001 surviving loop exit). Clip
    # regardless of how the loop above terminated, then fix up the sum
    # using only the still-free (non-capped) weights, so a capped weight is
    # never nudged past `cap` a second time by the sum-fix step either.
    w = w.clip(upper=cap)
    residual = 1.0 - w.sum()
    free = w < cap - tol
    if abs(residual) > 1e-12 and free.any():
        w[free] = w[free] + residual * (w[free] / w[free].sum())
    return w


def apply_sentiment(weights: pd.DataFrame, sentiment: pd.DataFrame, k: float = TILT_INTENSITY) -> pd.DataFrame:
    """`weights`: rebalance-date x ticker target weights from an equity fund's
    oos_backtest(). `sentiment`: ticker-day sentiment from
    src.sentiment.ticker_sentiment_index(). Returns tilted weights on the
    same rebalance-date x ticker grid, respecting the same MAX_WEIGHT cap
    as the base optimisation.
    """
    tickers = list(weights.columns)
    wide = sentiment.pivot(index="trading_date", columns="ticker", values="compound").sort_index()
    missing = [t for t in tickers if t not in wide.columns]
    assert not missing, (
        f"apply_sentiment expects an equity fund with sentiment coverage for every "
        f"ticker; missing {missing} (crypto tickers have no news coverage)"
    )

    tilted_rows = {}
    for d in weights.index:
        prior_dates = wide.index[wide.index < d]
        assert len(prior_dates) > 0, f"no sentiment history available before {d}"
        prev_day = prior_dates[-1]
        assert prev_day < d  # the signal used at a rebalance is dated strictly before it

        s = wide.loc[prev_day, tickers]
        z = (s - s.mean()) / s.std() if s.std() > 1e-12 else pd.Series(0.0, index=tickers)

        base = weights.loc[d, tickers]
        tilted = (base * (1 + k * z)).clip(lower=0)
        tilted = tilted / tilted.sum()
        tilted = _cap_and_renormalise(tilted)
        tilted_rows[d] = tilted

    result = pd.DataFrame(tilted_rows).T
    result.index.name = "date"
    assert np.allclose(result.sum(axis=1), 1.0, atol=1e-6), "tilted weights must sum to 1"
    assert (result.values <= MAX_WEIGHT + 1e-6).all(), "tilted weights must respect the same cap as the optimiser"
    assert (result.values >= -1e-9).all(), "tilted weights must stay long-only"
    return result
