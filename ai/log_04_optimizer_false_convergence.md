# Prompt log: caught bug, minimum-variance optimizer silently not optimising

## What I wanted
The generated `oos_backtest()` output needed a sanity check before it could
be trusted for the report. In particular, the required weights-over-time
figure for the equity minimum-variance fund needed to be inspected to
confirm the walk-forward rebalancing looked plausible.

## Prompt(s)
No new prompt was given. The issue was caught by looking directly at the
rendered weights-over-time PNG, following the plan's instruction to render
and inspect each figure, rather than treating a code run without errors as
sufficient evidence of correctness.

## What was wrong or risky
The chart showed sector weights going perfectly flat at suspiciously round
numbers, close to 10% per sector and exactly 1/50 per ticker, from
mid-2021 onward. Investigation showed that
`scipy.optimize.minimize(..., method="SLSQP")` was reporting
`success=True` after exactly one iteration (`res.nit == 1`) on most
rebalance windows, returning the equal-weight starting guess `x0`
completely unmoved. The fund labelled minimum-variance was, in practice,
equal-weight for nearly the whole out-of-sample period. The root cause was
that the raw daily-variance objective (`w @ cov @ w`) is roughly 1e-4 in
magnitude, smaller than SLSQP's default convergence tolerance of
`ftol=1e-6`, so the tolerance check was satisfied without the solver ever
moving off its starting point. This would have silently corrupted every
minimum-variance fund's performance numbers, the weights-over-time figure,
and any report claim comparing minimum-variance to the other methods. No
error, exception, or warning was produced that would surface in a normal
test run. The fault only became visible by rendering and inspecting the
actual chart.

A scaling issue had already been suspected earlier, and a `1e4` multiplier
was added when first debugging spurious BLAS overflow warnings. A later
edit, adding the warning-suppression wrapper, accidentally dropped that
multiplier while rewriting the function, and convergence behaviour was not
re-verified after that edit. The lesson is that fixing one symptom, in
this case noisy warnings, is not the same as verifying that the underlying
computation is still correct.

## What I changed and why
The `1e4` objective rescaling was re-added in `src/portfolios.py`'s
`_weights_min_variance()`. This was verified against several rebalance
dates, restoring real movement: `nit` values in the range of 9 to 26
rather than 1, and weights moving up to roughly 0.16 to 0.28 away from
equal weight. A runtime check was also added (`if res.nit <= 1:
print(...)`) so that a similar false convergence would surface immediately
in the console rather than requiring a chart inspection to catch it. The
`max_sharpe` objective, a Sharpe ratio on a roughly 0.01 to 1 scale, was
confirmed not to have this problem at the same dates, so it was left
unscaled.

After the fix, the equity minimum-variance fund's numbers changed
meaningfully and became more economically sensible. Annualised volatility
dropped from 16.0% to 12.8%, making it genuinely lower-risk than the other
equity funds, which is the point of a minimum-variance portfolio. Sharpe
dropped from 0.59 to 0.43, reflecting lower return traded for lower risk, a
normal and expected trade-off rather than a fault. The pre-fix numbers
were not approximately correct by chance. They reflected an
accidentally-equal-weight fund mislabelled as minimum-variance, and would
have been a materially incorrect claim in the report.
