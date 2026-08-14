# CLAUDE.md: working rules for this project

This is the Part B submission for FINS5545, covering Stations 3 and 4 of
the Data Factory Floor: optimal portfolios and an out-of-sample backtest, a
sentiment model and index built from news headlines, with a VADER
finance-lexicon extension as the innovation piece, a fusion of sentiment
into the equity funds, and a Streamlit app for the investor journey. The
full brief is in `PROJECT_BRIEF.md`. Data conventions are in
`context/DATA_GUIDE.md`. The product framing is in
`context/project_context.md`. Data loads through `src/data_access.py`
(provided, do not edit) from one hosted ZIP. The source files should never
be fetched any other way.

## Folder layout and where things go

- `src/etl.py`: integrity checks on top of `data_access`, covering the
  missing-date audit, dedup asserts, the crypto 2023-12-31 cap, and outlier
  flags.
- `src/features.py`: `daily_returns` (long format, `adjClose`, `pct_change`
  within each ticker) and `assemble_headline_panel` (dedup,
  timezone-normalise, align to the trading calendar). Scoring the text
  belongs to Station 3, not here.
- `src/portfolios.py`: `oos_backtest` (walk-forward, 252-day window for
  equity and combined, 365 for crypto-only, monthly rebalance, long-only,
  30%-per-asset cap) and `performance_metrics`.
- `src/sentiment.py`: `score_headlines` (VADER, with an optional extended
  lexicon from `context/finance_lexicon.json`) and `sector_sentiment_index`
  and `ticker_sentiment_index` (equal-weight, forward-fill-then-neutral for
  no-headline days).
- `src/fusion.py`: `apply_sentiment`, the sentiment tilt applied to equity
  fund weights only.
- `scripts/run_part_b.py`: the only place that writes to `results/`. This
  wires the modules above together and produces the four required files
  (`results/data/fund_returns.csv`, `fund_weights.csv`,
  `sector_sentiment_index.csv`, `results/tables/performance_metrics.csv`),
  along with supporting figures and tables.
- `streamlit_app.py`: reads only precomputed `results/` files and never
  runs VADER or a backtest live, since the deployed app cannot afford
  either.

## Rules for the assistant to follow

- No look-ahead, anywhere. Portfolio weights at a rebalance date use only
  data strictly before that date. The sentiment signal used in any decision
  is lagged by at least one trading day. The lag should be implemented at
  the point of use, in fusion, rather than baked into the stored sentiment
  index, so the index stays interpretable as same-day news mood and the lag
  step stays auditable.
- Use `adjClose`, not `close`, for every return calculation.
- Compute crypto returns on crypto's own calendar first, then left-merge
  onto the equity trading calendar for the combined fund. Price levels
  should never be merged first and differenced afterwards.
- Cap the crypto sample at 2023-12-31. Ten stray rows are dated
  2024-01-01 and should be dropped.
- Annualise with the factor appropriate to the calendar in use: 252 for
  the equity and combined funds, 365 for the crypto-only fund.
- Dedup headlines on `(ticker, date, title)`, not on `(ticker, date)`
  alone.
- `streamlit_app.py` must never import the sentiment-scoring library or
  recompute a backtest. It should only read from `results/`.
- Every assumption should be stated explicitly in code, including the
  risk-free rate, transaction costs, estimation window, and rebalance
  frequency, rather than left implicit, since each one needs to be named
  and justified in the report.
- The lexicon extension's `self_score` ratings in
  `context/finance_lexicon.json` are to be filled in personally and should
  not be fabricated or inferred by the assistant. An AI-authored score
  belongs in `ai_score`, labelled as such.
- Prompt logs in `ai/` are selective. Only material decisions,
  instructions, and corrections are logged, not routine implementation
  steps. A caught bug, a scope decision, or a result that needs careful
  interpretation warrants a log entry. A syntax fix does not.

## How output is checked and corrected

- Every stage requires at least one hand-verified number before it is
  trusted: a manually recomputed daily return, a manually recomputed
  Sharpe ratio on a short slice, a spot-check of obviously positive or
  negative headlines against their sentiment score, and an explicit
  assertion that weights sum to 1 and that sentiment used at a rebalance
  date is dated before that date.
- Every required figure is rendered and inspected before the numbers
  behind it are trusted. This is how a real bug was caught: the
  minimum-variance optimizer was silently converging after one iteration
  on several rebalance windows, because its objective was too small
  relative to SciPy's default tolerance, and was quietly falling back to
  equal weights for most of the backtest. It ran without any exception or
  warning and only became visible in the weights-over-time chart. See
  `ai/log_04_optimizer_false_convergence.md`.
- Numbers stated in the report must trace back to a re-runnable
  computation in `scripts/run_part_b.py`. No number is typed into the
  report from memory or from a one-off scratch calculation outside the
  reproducible pipeline (see `context/verify_ai_output.md`).
- `python scripts/check_handin.py` must pass cleanly before submission.
