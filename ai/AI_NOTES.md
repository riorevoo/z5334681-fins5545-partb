# AI notes

Claude Code was used for the Part B implementation across Stations 3 and 4.
Detailed logs are in `log_01_build_order.md` through `log_05_check_handin.md`.
Logging was deliberately selective. An entry was kept only where something
material happened, such as a scope decision, a caught bug, or a result that
required careful interpretation. Routine implementation steps, such as
writing a function body from an already-agreed specification, were not
logged.

An implementation order and a plan were requested before any code was
written, so the whole project could be understood end-to-end rather than
approached ad hoc (`log_01`). Two scope decisions were made directly rather
than left to the assistant. The innovation angle was set to a VADER
finance-lexicon extension, chosen over a risk-parity and turnover-model
alternative and a window-length sensitivity study. The fund scope was set
to the full 3-method by 3-asset-family matrix rather than the minimum
required. It was also made explicit that the lexicon's `self_score` ratings
had to be provided personally. The assistant was not permitted to
substitute a human rating, since that would misrepresent whose judgment the
number reflects on an assignment graded in part on AI-workflow
transparency.

Every module had at least one number verified by hand before it was
trusted: a manually recomputed return, a manually recomputed Sharpe ratio,
and a spot-check of headline sentiment against clearly positive or negative
wording. Every required figure was rendered and inspected rather than
treating a successful code run as evidence of correctness. This is what
caught the most serious fault in the project. The minimum-variance
optimizer was silently converging after a single iteration on several
rebalance windows, because its objective was numerically too small relative
to SciPy's default tolerance, and was quietly returning equal weights
instead of an actual minimum-variance solution. No error or warning was
produced. The fault was only visible in the weights-over-time chart, which
was suspiciously flat and round. Fixing it changed the fund's reported
volatility and Sharpe ratio meaningfully (`log_04`).

The fusion result for the equity minimum-variance fund came back positive
on the first check, with Sharpe rising from 0.43 to 0.44. This was logged
as one data point on one fund, method, and tilt-intensity combination, and
was not treated as evidence that the sentiment signal works in general
(`log_03`). The full sweep across all equity funds and lexicon variants, in
`results/tables/fusion_comparison.csv`, is what the report draws on,
including the case where the max-Sharpe fund's tilt made performance worse.
