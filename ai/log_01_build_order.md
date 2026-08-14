# Prompt log: project build order and scope decisions

## What I wanted
Before any code was written, the assistant was asked to propose an
implementation order for Part B, so the whole project could be understood
end-to-end rather than approached ad hoc. It was also asked to help resolve
the two largest open scope decisions: the innovation angle for the
30%-weighted criterion, and how many funds to build.

## Prompt(s)
"help me implement part b while meeting all the requirements specified...
give me what steps i should go in to implement this, what decisions i
should make and how i should demonstrate them." This was followed by
clarifying questions on the innovation-angle options and the fund-scope
options, then explicit choices were made.

## What the assistant produced
A plan was produced after reading `PROJECT_BRIEF.md`, `context/DATA_GUIDE.md`,
and the `src/` stubs. The proposed sequence was etl, then features, then
portfolios and sentiment (built independently of each other), then fusion,
then the `run_part_b.py` exports, then `streamlit_app.py`, then the report.
The stated rationale was that fusion requires both a verified backtest and
a verified sentiment index before it is meaningful, and that the app cannot
be built before `results/` exists, since it is a pure CSV reader under the
deploy constraint. Three innovation options were proposed: a VADER
finance-lexicon extension, risk parity combined with a turnover model, and
a window-length sensitivity study. Two fund-scope options were proposed: a
minimal set, and the full 3x3 method by asset-family matrix.

## What was wrong or risky
Nothing was factually wrong, but the first pass toward the lexicon-extension
innovation assumed a single AI rater without flagging that the taught rule,
"keep if rating std-dev < 2.5," requires multiple raters. The question "how
would I rate those terms?" was needed before this surfaced. A sole-rater
setup cannot use that rule as stated, and disguising an AI score as an
independent human rating would violate the course's own
`verify_ai_output.md` policy.

## What I changed and why
Two decisions were made. First, the innovation angle was set to the VADER
finance-lexicon extension, rated by two clearly labelled raters, self and
AI, so a disclosed dispersion check is possible instead of a single
unverified opinion. Second, the fund scope was set to the full 3x3 matrix:
minimum-variance, maximum-Sharpe, and equal-weight, each applied to
equity-only, crypto-only, and combined universes, for nine funds in total.
This reuses the same backtest function and earns the rubric's named credit
for "equity-only and crypto-only funds, extra methods." A further
requirement was added: the assistant was to report what changed and why
after each build stage, and what, if anything, was logged, so the
AI-workflow record stays accurate as the project proceeds rather than being
reconstructed at the end.
