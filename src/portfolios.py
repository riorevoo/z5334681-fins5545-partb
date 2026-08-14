"""Station 3 - your funds: optimal portfolios + out-of-sample backtest.

Build at least a combined equity-plus-crypto fund with two optimisation methods.
Backtest rules: walk-forward, no look-ahead, weights from past data only, annualise
with 252 (equity) or 365 (crypto). See the brief, Part B.

Design decisions (stated here so they're auditable, not buried in code):
- Estimation window: trailing 252 trading days for equity/combined funds, 365
  for the crypto-only fund (both approximate one year of history on their own
  calendar) - strictly BEFORE the rebalance date, so no look-ahead.
- Rebalance: first trading day of each calendar month.
- Weights are held constant at the rebalance target until the next rebalance
  (no intra-period drift tracking) - this matches the fact-sheet requirement
  that "current holdings" means the target weights from the most recent
  rebalance, and is consistent with the zero-transaction-cost assumption.
- Risk-free rate: 0.0, used consistently in every Sharpe calculation.
- Constraints: long-only, fully invested (weights sum to 1), each asset capped
  at 30% to avoid degenerate concentrated solutions from estimation error.
"""
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize

RISK_FREE_RATE = 0.0  # stated assumption; used in every Sharpe calc below
MAX_WEIGHT = 0.30

# macOS's Accelerate BLAS backend raises spurious "divide by zero / overflow /
# invalid value in matmul" RuntimeWarnings on small-magnitude (~1e-4) daily
# covariance matrices during w @ cov @ w, even though the covariance itself
# has no inf/nan and the computed value is correct (checked by hand against
# the raw cov entries). Confirmed benign; suppressed only around the two
# matmul-based objectives below so a genuine warning elsewhere still surfaces.
_MATMUL_WARNINGS = ("divide by zero encountered in matmul",
                     "overflow encountered in matmul",
                     "invalid value encountered in matmul")


def _rebalance_dates(index: pd.DatetimeIndex, window: int) -> pd.DatetimeIndex:
    """First trading day of each calendar month, once `window` days of history
    exist (the out-of-sample period starts after the initial estimation window,
    not on the first date in the data)."""
    first_of_month = pd.Series(index, index=index).groupby([index.year, index.month]).first()
    candidates = pd.DatetimeIndex(sorted(first_of_month.values))
    loc = index.get_indexer(candidates)
    return candidates[loc >= window]


def _weights_min_variance(cov: np.ndarray) -> np.ndarray:
    n = cov.shape[0]
    x0 = np.repeat(1 / n, n)
    bounds = [(0.0, MAX_WEIGHT)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    # Daily variance is ~1e-4 in magnitude, which is smaller than SLSQP's
    # default ftol=1e-6 - on some estimation windows it falsely reports
    # convergence after a single iteration, right back at the equal-weight
    # starting point (verified: res.nit == 1, res.x == x0 exactly). Scaling
    # the objective by a constant doesn't change the argmin, only the
    # absolute step sizes SLSQP compares against ftol.
    with warnings.catch_warnings():
        for msg in _MATMUL_WARNINGS:
            warnings.filterwarnings("ignore", message=msg, category=RuntimeWarning)
        res = minimize(lambda w: 1e4 * (w @ cov @ w), x0, bounds=bounds, constraints=cons, method="SLSQP")
    if res.nit <= 1:
        print(f"[portfolios] warning: min-variance optimizer converged in {res.nit} "
              f"iteration(s) - suspect false convergence, check objective scaling")
    return res.x if res.success else x0


def _weights_max_sharpe(mu: np.ndarray, cov: np.ndarray, rf_per_period: float) -> np.ndarray:
    n = cov.shape[0]
    x0 = np.repeat(1 / n, n)
    bounds = [(0.0, MAX_WEIGHT)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]

    def neg_sharpe(w):
        vol = np.sqrt(w @ cov @ w)
        if vol < 1e-12:
            return 0.0
        return -(w @ mu - rf_per_period) / vol

    with warnings.catch_warnings():
        for msg in _MATMUL_WARNINGS:
            warnings.filterwarnings("ignore", message=msg, category=RuntimeWarning)
        res = minimize(neg_sharpe, x0, bounds=bounds, constraints=cons, method="SLSQP")
    return res.x if res.success else x0


def _weights_equal(n: int) -> np.ndarray:
    return np.repeat(1 / n, n)


def oos_backtest(returns: pd.DataFrame, method: str = "min_variance",
                  window: int = 252, periods_per_year: int = 252) -> dict:
    """Walk-forward out-of-sample backtest.

    `returns`: wide date x ticker daily returns for the fund's asset universe
    (no NaNs inside the backtest period). `method` in
    {"min_variance", "max_sharpe", "equal_weight"}.

    Returns a dict with:
      daily_returns   - Series of OOS portfolio daily returns
      weights         - DataFrame, rebalance-date x ticker (target weights)
      growth_of_1     - Series, growth of $1 from the first live date
      first_live_date - Timestamp of the first OOS trading day
      rebalance_dates - DatetimeIndex of rebalance dates
    """
    returns = returns.dropna(how="any")
    tickers = list(returns.columns)
    idx = returns.index

    rebal_dates = _rebalance_dates(idx, window)
    assert len(rebal_dates) > 0, "not enough history for even one rebalance"

    rf_per_period = RISK_FREE_RATE / periods_per_year
    weight_rows = {}
    for d in rebal_dates:
        loc = idx.get_loc(d)
        est = returns.iloc[loc - window: loc]  # strictly before d - no look-ahead
        cov = est.cov().values

        if method == "min_variance":
            w = _weights_min_variance(cov)
        elif method == "max_sharpe":
            w = _weights_max_sharpe(est.mean().values, cov, rf_per_period)
        elif method == "equal_weight":
            w = _weights_equal(len(tickers))
        else:
            raise ValueError(f"unknown method: {method}")
        weight_rows[d] = w

    weights = pd.DataFrame(weight_rows, index=tickers).T
    weights.index.name = "date"
    assert np.allclose(weights.sum(axis=1), 1.0, atol=1e-6), "weights must sum to 1"
    assert (weights.values >= -1e-9).all(), "weights must be non-negative (long-only)"

    result = weights_to_backtest(weights, returns)
    result.update({
        "weights": weights,
        "rebalance_dates": rebal_dates,
        "window": window,
        "periods_per_year": periods_per_year,
        "method": method,
        "tickers": tickers,
    })
    return result


def weights_to_backtest(weights: pd.DataFrame, returns: pd.DataFrame) -> dict:
    """Turn a rebalance-date x ticker weights table (e.g. from oos_backtest,
    or a fusion-tilted variant) into daily portfolio returns and growth of $1.
    Weights are held constant at their rebalance-date value until the next
    rebalance (see module docstring)."""
    idx = returns.index
    daily_w = weights.reindex(idx).ffill()
    live = daily_w.dropna(how="all")
    port_ret = (live * returns.loc[live.index]).sum(axis=1)
    port_ret.name = "portfolio_return"

    start_loc = idx.get_loc(live.index[0])
    start_date = idx[start_loc - 1]
    growth = pd.concat([pd.Series([1.0], index=[start_date]), (1 + port_ret).cumprod()])
    growth.name = "growth_of_1"

    return {
        "daily_returns": port_ret,
        "growth_of_1": growth,
        "first_live_date": live.index[0],
    }


def performance_metrics(daily_returns: pd.Series, periods_per_year: int = 252) -> dict:
    """Annualised return, annualised volatility, Sharpe (rf=0), max drawdown."""
    n = len(daily_returns)
    ann_return = (1 + daily_returns).prod() ** (periods_per_year / n) - 1
    ann_vol = daily_returns.std() * np.sqrt(periods_per_year)
    sharpe = (ann_return - RISK_FREE_RATE) / ann_vol if ann_vol > 1e-12 else np.nan

    wealth = (1 + daily_returns).cumprod()
    drawdown = wealth / wealth.cummax() - 1
    max_drawdown = drawdown.min()

    return {
        "annualised_return": ann_return,
        "annualised_vol": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
    }
