# Predictive validation

The dependent variable is the natural logarithm of total damage, adjusted, in thousands of US dollars. The main equation relates that outcome to log(1+Deaths), log(1+Affected), and log(GDP per capita). Two reduced equations drop the human-impact term that is unreported for part of the file. Each equation is estimated by ordinary least squares on events for which the included variables are recorded. Predictive checks use only those estimation samples. They do not use the filled values.

Two designs are reported. The first is the stratified 20 percent holdout already used for the median-error checks: within each disaster type, 20 percent of events are drawn at random (seed 2026) and the equation is refit on the remainder. The second is stratified five-fold cross-validation. Within each disaster type, events are randomly ordered with the same seed, in a separate draw, and assigned in rotation to five folds. Each fold is predicted from a model fit on the other four, so every estimation event is predicted once by a fit that excludes it. Drought contributes one event to each fold of the main sample. Fold sizes for that sample are 408, 407, 407, 405, and 404.

Out-of-sample fit on the log scale is summarized by two R-squared statistics. The cross-validated R-squared pools the five folds:

R²_CV = 1 − Σ_i (y_i − ŷ_i^(−k))² / Σ_i (y_i − ȳ)²,

where y_i is log damage, ŷ_i^(−k) is the prediction from the fold that excludes i, and ȳ is the mean of y over the estimation sample. The denominator is the same total sum of squares that enters the in-sample R-squared, so the difference between the two is the optimism of the in-sample fit.

The out-of-sample R-squared for a single fold, and for the 20 percent holdout, uses the training-sample mean as the benchmark, following the forecast-comparison definition in Campbell and Thompson (2008):

R²_OS = 1 − Σ_{i ∈ test} (y_i − ŷ_i)² / Σ_{i ∈ test} (y_i − ȳ_train)².

Replacing ȳ_train with the test-sample mean changes R²_OS by less than 0.01 on the main equation. The root mean squared error is reported on the log scale. On the dollar scale, the prediction is exp(ŷ), the conditional median under a symmetric error in logs. A dollar-scale R²_CV uses the same pooled formula with damage in place of log damage. Because squared dollar errors are dominated by the largest events, the median of predicted/recorded damage is reported alongside it.

**Table 1. In-sample and out-of-sample fit**

| Specification | N | In-sample R² | Five-fold R²_CV | Holdout R²_OS | Fold R²_OS, min–max | CV RMSE (log) | CV median predicted/recorded | Dollar R²_CV |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| Main | 2,031 | 0.417 | 0.415 | 0.398 | 0.376–0.436 | 1.977 | 0.85 | 0.343 |
| Deaths unreported | 2,417 | 0.294 | 0.292 | 0.229 | 0.245–0.355 | 2.179 | 0.82 | 0.022 |
| Affected unreported | 2,391 | 0.363 | 0.362 | 0.381 | 0.317–0.408 | 2.069 | 0.79 | −0.455 |

*Notes.* The main specification is log(Damage) = α + β₁ log(1+Deaths) + β₂ log(1+Affected) + β₃ log(GDPpc) + ε. “Deaths unreported” drops log(1+Deaths). “Affected unreported” drops log(1+Affected). N is the number of events with recorded damage and the predictors included in that row. In-sample R² and R²_CV are on log damage. R²_OS is the training-mean benchmark on log damage; the holdout column is the single 20 percent split, and the min–max is across the five folds. CV RMSE is the square root of the pooled mean squared error on log damage. The median ratio and the dollar R²_CV use exp(ŷ) as the prediction of damage in thousands of adjusted US dollars. Dollar R²_CV can be negative when that median prediction has a larger sum of squared dollar errors than the estimation-sample mean. All splits are stratified by disaster type. Seed 2026.

On the main equation, five-fold R²_CV is 0.415, against an in-sample R² of 0.417. The squared correlation between recorded and cross-validated log predictions is also 0.415, so the cross-validated predictions are calibrated on the log scale: they do not need a further slope adjustment to match recorded log damage. Fold-level R²_OS stays inside 0.376 to 0.436. The single holdout, at 0.398, lies inside that range. The in-sample R-squared is not an artifact of fitting and scoring the same events.

The dollar-scale results are less tight, and they move more from one split to another. The cross-validated median ratio on the main equation is 0.85, so the typical predicted damage is 15 percent below the recorded value. The corresponding figure from the single 20 percent holdout was 0.95. That holdout was a high draw. Across the five folds the median ratio runs from 0.70 to 1.14 (Table 2), while log-scale R²_OS moves only from 0.376 to 0.436. A validation summary that quotes only the holdout median ratio overstates how close the typical dollar prediction is.

Dollar R²_CV on the main equation is 0.343. On the deaths-unreported equation it is 0.022. On the affected-unreported equation it is −0.455: predicting the conditional median from deaths and GDP per capita produces a larger sum of squared dollar errors than predicting the sample mean for every event. That result is consistent with the very large predictions for high-fatality extreme-temperature events in high-income countries. Log-scale R²_CV for that equation remains 0.362, close to its in-sample value of 0.363. Fit on the log scale does not imply fit on the dollar scale once predictions are exponentiated.

**Table 2. Main equation, five folds**

| Fold | Test events | R²_OS | RMSE (log) | Median predicted/recorded |
| --- | ---: | ---: | ---: | ---: |
| 1 | 408 | 0.421 | 1.962 | 0.83 |
| 2 | 407 | 0.430 | 1.988 | 0.93 |
| 3 | 407 | 0.376 | 2.156 | 1.14 |
| 4 | 405 | 0.436 | 1.857 | 0.70 |
| 5 | 404 | 0.424 | 1.909 | 0.75 |

*Notes.* R²_OS uses the training-sample mean of log damage as the benchmark. RMSE is the root mean squared error of log damage. The median ratio is exp(ŷ) divided by recorded adjusted damage. Fold 4 contains 194 floods, 181 storms, 18 wildfires, 9 mass-movement events, 2 extreme-temperature events, and 1 drought. Other folds differ from that mix by at most one event in a type.

## Reference

Campbell, J. Y., and Thompson, S. B. (2008). Predicting excess stock returns out of sample: Can anything beat the historical average? *Review of Financial Studies*, 21(4), 1509–1531. The out-of-sample R-squared used here is their ratio of mean squared errors against the training mean, applied to log damage rather than to a return.
