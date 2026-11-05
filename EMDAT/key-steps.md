# Key steps so far

This run uses the `EMDAT.csv` saved on 20 October 2026. Damage in that file is EM-DAT Total Damage, Adjusted, in thousands of US dollars: real terms, on the file’s recent price basis. GDP per capita is World Bank GDP per capita in current US dollars. No further price conversion was applied. An earlier run used the damage column as it stood on 18 October, which was smaller in earlier years by a year-specific factor. Those results have been replaced.

The source file has 9,129 events with start years from 2000 to 2026. The equation is

log(Damage) = α + β₁ log(1+Deaths) + β₂ log(1+Affected) + β₃ log(GDPpc) + ε

Logs are natural logs. Recorded damage was never overwritten. In `EMDAT_cleaned.csv` and `EMDAT_imputed.csv`, the `Damage` column now matches the adjusted source values exactly.

## 1. Cleaning

Script: `fit_damage_ols.R`. Clean file: `EMDAT_cleaned.csv`.

Blank cells and the text `#N/A` were set to missing. The four log terms were then built. `log(1+Deaths)` and `log(1+Affected)` use R’s `log1p`. `log(Damage)` and `log(GDPpc)` are defined only when the value is positive.

In the full file, damage is missing on 6,111 events, deaths on 2,573, people affected on 1,961, and GDP per capita on 146. The estimation sample is the 2,031 events where all four logs exist. That flag is the column `estimation_sample`.

## 2. Fit and diagnostics

Same script. Tables and plots are in `output/`.

Ordinary least squares on the 2,031 events:

log(Damage) = −5.128 + 0.666 log(1+Deaths) + 0.199 log(1+Affected) + 1.389 log(GDPpc)

| Term | Estimate | Classical SE | HC1 SE |
| --- | ---: | ---: | ---: |
| Intercept | −5.128 | 0.466 | 0.515 |
| log(1+Deaths) | 0.666 | 0.035 | 0.034 |
| log(1+Affected) | 0.199 | 0.016 | 0.017 |
| log(GDPpc) | 1.389 | 0.039 | 0.043 |

R-squared is 0.417 and adjusted R-squared is 0.417. The residual standard error is 1.975 log points. The regression F statistic is 484 on 3 and 2,027 degrees of freedom. Every slope has an HC1 p-value below 0.001.

Variance inflation factors are 1.45, 1.59, and 1.38. The correlation between log(1+Deaths) and log(1+Affected) is 0.53. Both correlate negatively with log(GDPpc), at −0.41 and −0.49. Those figures depend only on the predictors, so they are unchanged from the earlier run.

The Breusch-Pagan statistic is 75.8 on 3 degrees of freedom, so the residual spread is not constant. It is wider at low fitted values (residual SD about 2.48 in the lowest fitted decile, 1.56 in the highest). HC1 standard errors stay close to the classical ones, so the significance calls do not change.

The average residual bends at the bottom of the fitted range: the lowest decile sits about 0.57 log points above the fit, and the next two sit about 0.38 below it. Floods and storms are 92 percent of the estimation sample (970 and 904 events). Mass-movement events (48) have a mean residual of −0.96, so fitted damage there runs about 2.6 times recorded damage. Drought (5) and extreme temperature (13) are too thin to judge from the mean residual alone.

Plots: `output/resid_vs_fitted.png` and `output/resid_by_type.png`.

## 3. Back-transformation

Script: `impute_damage.R`. Output file: `EMDAT_imputed.csv`.

Where the three predictors are present, the fitted log is turned back into damage with the exponential. That stored number is the conditional median of adjusted damage, not the conditional mean. The Duan smearing factor on the estimation residuals is 5.34. The lognormal factor exp(σ²/2) is 7.03. Neither factor was applied to the stored fills.

A classical 95 percent prediction interval is stored on the log scale (`log_pi_lwr`, `log_pi_upr`) and on the damage scale (`Damage_pi_lwr`, `Damage_pi_upr`). For a typical fill, the upper end is about 2,300 times the lower end, which is about a factor of 50 either side of the median.

## 4. Writing the fills

`EMDAT_imputed.csv` has 9,129 rows.

- 3,018 events keep the recorded adjusted damage. `Damage_source` is `observed`.
- 3,016 events with blank damage and all three predictors receive exp(fitted log). `Damage_source` is `model`.
- 3,095 events stay blank because at least one predictor is missing.

The 3,016 medians sum to 237.0 million in the file’s units, about 237 billion of today’s dollars. Scaling each by the smearing factor of 5.34 would raise that sum to about 1.27 trillion dollars. The median filled value is about 19,800, against a median recorded damage of about 155,000, in thousands of adjusted US dollars.

Example. The Kenya 2026 flood has 59 deaths and 27 people affected. The fill is 8,516, with a 95 percent interval from 175 to 414,894, in thousands of adjusted US dollars.

Among the 3,095 still blank:

- 1,621 are missing deaths only
- 1,049 are missing people affected only
- 349 are missing both deaths and people affected, with GDP present
- 30 are missing GDP per capita only
- 46 are missing GDP per capita and at least one human-impact field

## 5. Holdout check

A 20 percent holdout, stratified by disaster type, seed 2026: 407 events held out, 1,624 used to refit. Scores are on the adjusted damage scale. Full table: `output/holdout_scores.csv`. Plot: `output/holdout_pred_vs_actual.png`.

On the 407 events, the median of predicted/recorded damage is 0.95. The median absolute error is 130,012 in the file’s units (about 130 million dollars). The median absolute percentage error is 87 percent. The mean absolute error is about 809 million dollars, pulled up by a few very large events. The 10th and 90th percentiles of predicted/recorded are 0.10 and 18.6. The 95 percent prediction interval covers 93 percent of held-out events.

By type, where the holdout is large enough to read: floods 1.16 (194 events), storms 0.79 (181), wildfire 0.69 (18), mass movement 1.40 (10). All three held-out extreme-temperature events were predicted far above recorded damage (median ratio 44). Drought contributed one held-out event.

Filled medians sit below recorded medians. For floods and storms that gap is mostly the mix of events: uncosted floods have fewer deaths, fewer people affected, and lower GDP per capita than floods that already have damage. Comparison table: `output/observed_vs_imputed_by_type.csv`.

### Five-fold cross-validation and out-of-sample R-squared

Script: `validate_cv.R`. Numbers: `output/cv_summary.csv` and `output/cv_fold_scores.csv`. The write-up for a paper is `validation-results.md`.

The same three equations are checked. Each estimation sample is split by disaster type. Within a type, events are shuffled (seed 2026) and dealt in turn into five folds, so each fold has nearly the same mix of types. Drought contributes one event to each fold. For each fold the equation is fit on the other four and used to predict the held-out fold. Every estimation event is predicted once, by a fit that did not include it.

Two R-squared calculations are used, both on log damage.

- **Cross-validated R-squared.** Pool the five folds. Divide the sum of squared prediction errors by the sum of squared deviations of log damage from the mean of the whole estimation sample, and subtract that ratio from 1. The denominator matches in-sample R-squared, so the two numbers can be compared directly.
- **Out-of-sample R-squared.** Within one fold, or within the 20 percent holdout, divide the sum of squared prediction errors by the sum of squared deviations from the mean of the training sample, and subtract from 1. The training mean is the benchmark a forecast would have if it ignored the predictors. The same statistic using the test-sample mean is stored beside it. On the main equation the two benchmarks differ by at most about 0.01.

A dollar-scale version of the pooled cross-validated R-squared is also stored. There the outcome is adjusted damage and the prediction is e raised to the fitted log, which is a conditional median. Squared dollar errors put most of their weight on the largest events.

On the main equation the in-sample R-squared is 0.417 and the cross-validated R-squared is 0.415. Fold-level out-of-sample R-squared runs from 0.376 to 0.436. The original 20 percent holdout has an out-of-sample R-squared of 0.398. The dollar-scale cross-validated R-squared is 0.343. The cross-validated median of predicted/recorded damage is 0.85, against 0.95 on the single holdout, so that holdout was a high draw for the median ratio.

## 6. External check: Tuvalu 2015

The file’s Tuvalu 2015 storm has 4,613 people affected, GDP per capita 6,041, and deaths blank, so the original equation cannot score it. An external source reported about 92 million dollars of damage and 0 deaths.

Setting deaths to 0 and using the file’s other two values in the refitted equation gives

log(damage) = −5.128 + 0.666·log(1+0) + 0.199·log(1+4613) + 1.389·log(6041) = 8.643

damage = e^8.643 ≈ 5,668 thousand adjusted US dollars, about 5.7 million of today’s dollars.

The deaths-unreported equation, which does not assume a death toll of zero, fills this event at about 29 million dollars. See section 8.

## 7. What remains outside these fills

1. Keep the 3,016 fills as the primary result. Do not recode blanks as zeros.
2. Where a cited source supplies a missing predictor, including a true zero death toll, enter that cited value and use the same equation. The 30 events missing only GDP per capita can be completed from the World Bank and then scored with the same equation.
3. The 3,016 modelled damage values were not used as estimation data for the reduced equations.
4. The 349 events missing both human impacts, and the 46 also missing GDP, stay out of both fills.

## 8. Reduced equations

Script: `impute_damage_reduced.R`. Coefficients and holdout scores: `output/reduced_coefficients.csv` and `output/reduced_model_summary.csv`. New columns are on `EMDAT_imputed.csv`. The original `Damage_imputed` column is unchanged.

Deaths unreported, fit on 2,417 events with recorded damage, applied to 1,621 events:

log(Damage) = −3.147 + 0.348 log(1+Affected) + 1.206 log(GDPpc)

R-squared 0.294. Residual standard error 2.177. Holdout median predicted/recorded 0.73. Median fill about 35,500. The fills sum to about 143 billion dollars. The Tuvalu 2015 storm is in this group: fill about 29,300, with a 95 percent interval from about 409 to about 2,095,000, in thousands of adjusted US dollars.

People affected unreported, fit on 2,391 events with recorded damage, applied to 1,049 events:

log(Damage) = −1.559 + 0.784 log(1+Deaths) + 1.178 log(GDPpc)

R-squared 0.363. Residual standard error 2.069. Holdout median predicted/recorded 0.97. Median fill about 105,000. The fills sum to about 2.64 trillion dollars, pulled up by extreme-temperature events with very large death tolls in high-income countries. Italy’s 2024 heatwave, with 19,038 deaths, is filled at about 138 billion dollars.

Both stored values are conditional medians in adjusted thousands of US dollars. Smearing factors are 7.56 and 4.86. Disaster-type indicators were not added.
