# Prompt log: self-rating the finance lexicon

## What I wanted
Personal -4 to +4 ratings for all 32 terms in `context/finance_lexicon.json`,
to replace the AI-score-only fallback and give the lexicon a genuine second
rater.

## Prompt(s)
"how do i rate the lexicon terms myself" and "yes but like how does vader
do it? how do i pick." The assistant explained VADER's own construction
method (a panel of independent raters scoring each word on the same -4 to
+4 scale, averaged, kept only where raters agreed closely enough) and gave
calibration points from VADER's actual lexicon. The 32 terms were then
listed without the `ai_score` values visible, so the rating would be
independent rather than anchored to the assistant's numbers.

## What the assistant produced
A full set of 32 ratings was supplied and written into
`context/finance_lexicon.json`'s `self_score` field.

## What was wrong or risky
Nothing was wrong. The dispersion between the two raters was checked before
accepting the ratings, since a large or uniform gap could indicate the
self-ratings were not actually independent. The mean absolute difference
across all 32 terms was 0.65, with a spread from 0.0 to 2.8, which reads as
genuine independent judgment rather than a copy of the AI scores. The
largest disagreement was on "going concern" (AI -3.8, self -1.0). A
smaller but notable pattern appeared on the two deliberate
Loughran-McDonald corrections: the AI score set `debt` and `liability` to
0.0, but the self-ratings placed them at -1.5 and -1.7, meaning the
averaged `mean_score` used by the pipeline only partially applies the
intended correction rather than fully neutralising these terms. This is
worth stating plainly in the report rather than treated as a flaw to
smooth over.

## What I changed and why
`scripts/run_part_b.py` was re-run with the completed lexicon. Fund
performance numbers are unaffected, since they do not depend on sentiment.
The neutral-headline rate moved from 47.7% to 47.6%, and the equity
minimum-variance fund's extended-tilt Sharpe moved from 0.437 to 0.433,
both small shifts consistent with the moderate rater dispersion. `report/report.docx`
was regenerated from the updated tables and figures so every number in it
traces to this final run rather than the earlier AI-score-only version.
