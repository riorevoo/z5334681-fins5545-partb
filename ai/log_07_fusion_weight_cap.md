# Prompt log: fusion sentiment tilt was silently breaking the 30% weight cap

## What I wanted
After the funds and fusion sweep were built (`log_03`, `results/tables/fusion_comparison.csv`),
the assistant was asked to run a critical, adversarial audit of my own results and
interpretation against the brief and rubric - explicitly told not to improve the
numbers or write my report for me, just to find methodological errors, bugs, and
unsupported claims, with evidence, before anything was finalised. The audit covered
the backtest, the optimiser, the fusion mechanism, the sentiment model, and the
report's own claims.

## Prompt(s)
"Comprehensive FINS5545 Part B audit - do not modify code yet", with a full
section-by-section brief covering the backtest/portfolio implementation, the
optimiser, performance metrics, the fusion implementation, the max-Sharpe
deterioration specifically, the sentiment/lexicon model, validation, predictive
power, the sector index, date alignment, regime robustness, transaction costs, the
combined equity+crypto result, rubric compliance, and a claims audit. Followed by
"make the fix" once a concrete finding came back, then "yes, re-run
scripts/run_part_b.py", then "update §4 and Table 2 with the new numbers and log 7".

## What the assistant produced
The audit re-ran the actual pipeline code with instrumentation, rather than only
reading it, and found that `src/fusion.py`'s `apply_sentiment()` tilts weights by
`(1 + k*z)` and renormalises, but never re-applies the 30% per-asset cap the base
optimiser enforces (`portfolios.MAX_WEIGHT`). Concretely: 18 of 36
`equity_max_sharpe` rebalances at k=0.5 exceeded 30% post-tilt, with one name (UPS,
2021-03-01) reaching 47.1% of the fund from a legitimate pre-tilt 29.4%. The
audit's working hypothesis was that this uncapped concentration was the main
driver of the max-Sharpe fund's fusion Sharpe falling from 0.418 to 0.271.

## What was wrong or risky
Two things, both caught by verification rather than by the code running without
error - the same discipline that caught the optimiser bug in `log_04`:

1. The assistant's first fix (a water-filling cap-and-renormalise function) passed
   several spot checks but still let one weight slip to 0.300001 on a later
   rebalance date - a redistribution pass overshot the cap with no further loop
   iteration left to re-catch it. This only surfaced because the fix was checked
   across every rebalance date and every (fund x lexicon x k) combination, not
   just the cases already spot-checked. A few passing checks were not evidence the
   fix was correct everywhere.
2. Once the fix was actually correct (verified with zero cap violations across all
   66 fund/lexicon/k combinations) and the pipeline was re-run, the predicted
   result did not hold: capping the tilt made the fusion Sharpe *worse*, not
   better. `equity_max_sharpe` extended-tilt fell further, from 0.271 (buggy,
   uncapped) to 0.235 (fixed); `equity_min_variance` fell from 0.433 to 0.426. The
   audit's own causal story - "the cap breach explains the deterioration" - was a
   plausible hypothesis, not a demonstrated fact, and testing it directly
   disproved the strong version of that claim rather than confirming it.

## What I changed and why
`src/fusion.py`'s `apply_sentiment()` now re-applies `portfolios.MAX_WEIGHT` after
the tilt via a water-filling projection (`_cap_and_renormalise`), with assertions
confirming the sum-to-1 and cap constraints on every call, matching the base
optimiser's own constraint set - this is the correct implementation regardless of
whether it improves the numbers, since the 30% cap is a stated design constraint,
not a suggestion. `scripts/run_part_b.py` was re-run, which updated
`results/tables/fusion_comparison.csv` and `results/figures/fusion_before_after.png`;
the fund-level backtests, fact sheets, and sentiment index are untouched, since
they never call `fusion.py`. `report/report.docx` Section 4 and Table 2 were
updated to the new numbers, including softening "a negligible move either way" to
"a small decrease" for the minimum-variance fund's tilt, since that move roughly
quadrupled (0.435 -> 0.433 became 0.435 -> 0.426) once the bug was fixed. The
report's existing "plausible explanation" sentence (concentration compounding
estimation noise) was left as written, since it was not disproven, only left as an
appropriately-hedged open hypothesis rather than a demonstrated mechanism - it was
the audit's *stronger* causal claim that failed the test, not the report's own
softer one.

## Follow-up
The fix is in the code and the results are regenerated, but the underlying
question - why the sentiment tilt hurts the max-Sharpe fund even with the cap
correctly enforced - is still open, and is a more honest framing than the current
"compounds estimation noise" sentence implies. The same audit found lagged
sentiment has no measurable predictive power for future returns at any horizon
tested (1/5/21-day correlations all economically negligible, some statistically
significant only because of the ~50,000-observation sample size), so a fairly
large, well-scaled reallocation lever (z-scored, so bounded, but still moving
weights by a mean of roughly 39% of their pre-tilt value at k=0.5) is being driven
by a signal with close to zero genuine information content. That is a more
specific and better-evidenced explanation than "compounds estimation noise," and
is worth stating in the report rather than left implicit.
