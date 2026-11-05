# Concepts and definitions

Notes from this project, written for someone whose background is ordinary single and multiple linear regression. The damage equation uses natural logs. Every “log” below is the natural log, the one labelled **ln** on a calculator.

## The damage equation

log(Damage) = α + β₁ log(1+Deaths) + β₂ log(1+Affected) + β₃ log(GDPpc) + ε

Damage in the current files is EM-DAT Total Damage, Adjusted, in thousands of US dollars. The numerical examples below are from the refit on that series. GDP per capita is in current US dollars per person. The intercept α is log damage when deaths = 0, people affected = 0, and GDP per capita = 1. Those values sit outside this sample, so α is not a meaningful damage level on its own. The slopes are the quantities to read.

A slope in this equation is a partial association. β₁ says how log damage moves with log(1+Deaths) when people affected and GDP per capita are held fixed. The same reading applies to the other two slopes.

A 10 percent higher (1+Deaths) lines up with about a 10×β₁ percent change in damage. With β₁ = 0.666, that is about 6.7 percent. With β₂ = 0.199, a 10 percent higher (1+Affected) lines up with about 2.0 percent higher damage. With β₃ = 1.389, a 10 percent higher GDP per capita lines up with about 13.9 percent higher damage.

## log(1+x), and the 59 deaths example

log1p(x) means log(1+x). For 59 deaths:

1. Add 1, which gives 60.
2. Take the natural log of 60, which is 4.094344562.

The “1+” comes from the specified term log(1+Deaths). It also keeps the log defined when a count is zero, because the log of zero does not exist. In this file, recorded deaths and people affected have no zeros, so log(1+x) and log(x) are close. The formula still adds 1.

On a Casio **fx-83GT CW** there is an **ln** key. Press **ln**, then **60**, then **EXE**. The screen shows **4.094344562**. The calculator stops after 10 digits. The key labelled **log** is base 10 and shows 1.77815125 for 60.

## Turning log(damage) back into damage

The reverse of the natural log is the exponential. If L = log(damage), then

damage = e^L

where e is about 2.718. The result is in the same units as the damage column, thousands of US dollars.

Check. The median log damage in the estimation sample is 11.944811772. Raising e to that power returns about 154,000, the median recorded adjusted damage in that sample.

On the fx-83GT CW there is no eˣ key. A small **e** is printed above the **8** key.

1. Press the **↑** key at the top left. An indicator appears at the top of the screen.
2. Press **8**. The screen shows **e**.
3. Press the power key, marked **x** with a small box.
4. Type the log value.
5. Press **EXE**.

Apply that to 4.094344562 and the screen shows 60. If the small **e** is hard to see, press **CATALOG**, open **Other**, and choose **e**, then use the power key.

In Excel, if the log value is in cell A2:

```excel
=EXP(A2)
```

`=EXP(11.944811772)` returns about 154000.

## Log points and the residual standard error

A log point is a change of 1 in the natural log. A rise of 1 log point multiplies damage by e, about 2.72. A rise of 0.1 log points multiplies damage by about 1.105, which is a 10.5 percent increase.

The residual standard error, here 1.975, is the usual residual standard error from a regression printout: the typical size of the leftover ε. It is in log points because that is the unit of the dependent variable. A miss of 1.975 log points multiplies or divides dollar damage by e^1.975, about 7.2.

Example. A fitted log damage of 11.5 is about 99,000 in the file’s units. A residual of +1.97 puts recorded damage near 710,000. A residual of −1.97 puts it near 14,000.

## R-squared

R-squared is the share of variation in the dependent variable accounted for by the fitted line. Here the dependent variable is log(damage), not damage in dollars. An R-squared of 0.417 means the three predictors account for about 42 percent of the variation in log damage across the 2,031 events. The other 58 percent remains in the residuals.

Adjusted R-squared applies a penalty for extra predictors. With 2,031 events and three predictors the penalty is tiny, so adjusted R-squared is 0.417. The equation is not being propped up by useless extra terms.

For filling in a missing damage figure, 0.417 means the predictors do move with recorded damage, and a typical event still sits a long way off the line.

## Residuals

A residual is recorded log damage minus fitted log damage. A positive residual means recorded damage was higher than the equation predicted. A residual of 0 means the point sits on the line. Ordinary least squares forces the average residual over the whole estimation sample to be zero. The useful checks are whether that average stays near zero all along the fitted line, and whether the vertical spread stays even.

Large residuals mean the equation misses individual events. That is the factor of about 7.2 above. Patterned residuals mean the straight-line assumptions are off.

The plot `output/resid_vs_fitted.png` puts fitted log damage on the horizontal axis and the residual on the vertical axis. The black line is a residual of zero. The blue curve is a smooth average of the residuals. Three things show up there:

- The blue curve is above zero at the far left, where predicted damage is small, then settles on zero through the dense middle of the sample. Small predictions are systematically low. A typical event is centered in the right place.
- The cloud is taller on the left than on the right. Misses are larger when predicted damage is small. That uneven spread is why HC1 standard errors were reported.
- There is no tight band around zero anywhere. Points run from roughly −8 to +7 log points. Where the average is right, single events are still widely scattered.

## HC1 standard errors

The usual standard-error formula assumes the scatter around the line has the same spread everywhere. In this fit the cloud is wider when predicted damage is small and narrower when it is large. The Breusch-Pagan statistic of 72.0 on 3 degrees of freedom is the formal version of that check.

HC1 recalculates the standard errors so they stay valid when the spread is uneven. “HC” means heteroskedasticity-consistent, and “1” is the version of the formula. The slope estimates do not change. Only the standard errors, t-statistics, p-values, and confidence intervals change.

In this fit the HC1 standard errors are very close to the ordinary ones. The t-tests reach the same conclusion either way: each slope is estimated precisely.

## Variance inflation factors

In multiple regression, a slope is harder to pin down when its predictor moves in step with the other predictors. The variance inflation factor (VIF) measures that overlap.

VIF = 1 / (1 − R²ⱼ)

R²ⱼ is the R-squared from regressing that predictor on the other predictors. A VIF of 1 means no overlap. A VIF of 2 means the variance of that slope is twice what it would be with no overlap, so the standard error is larger by √2.

Slopes start to become unstable when a VIF gets up to around 5 to 10. The standard error is then large, and dropping a handful of events, or adding another similar predictor, can swing the coefficient. The confidence interval becomes very wide.

Here the VIFs are 1.45, 1.59, and 1.38. The 0.53 correlation between the two human-impact logs is real, and it is mild. Both slopes stayed precisely estimated.

## Conditional median, conditional mean, and smearing

e raised to the fitted log is the conditional median of damage when the errors are roughly symmetric on the log scale. It is the middle prediction, not the average prediction.

Damage is right-skewed. The conditional mean is larger than the median. Duan’s smearing estimator multiplies the median by the average of e raised to the estimation residuals. Here that factor is 5.34. A lognormal formula, exp(σ²/2), gives 7.03. The stored fills use the median only.

Adding up medians does not give expected total loss. The 3,016 medians sum to about 237 billion dollars. Scaling each by 5.34 raises the sum to about 1.27 trillion dollars.

## Prediction intervals

A 95 percent prediction interval is a range that, under the model, would contain the recorded damage of a new event about 95 percent of the time. It is wider than a confidence interval for the mean line, because it includes the residual.

The interval is built on the log scale and then exponentiated. With a residual standard error of about 1.97, a rough interval runs about 1.96×1.97 ≈ 3.9 log points either side of the fitted log. That is a factor of about 50 in dollar damage on either side of the median. In the stored intervals, the upper end of a typical fill is about 2,300 times the lower end.

The classical interval assumes the residual spread is constant. This fit violates that. On the holdout, the interval still covered 93 percent of events, close to the nominal 95 percent.

The Kenya flood with 59 deaths is a concrete case: median fill 8,516, interval 175 to 414,894, in thousands of adjusted US dollars.

## Holdout scores

A holdout sets aside part of the events that have recorded damage, refits the equation on the rest, and compares predictions with the recorded values. This one held out 20 percent at random within each disaster type (407 events), using seed 2026.

- **Median ratio**, predicted/recorded = 0.95. The typical prediction was 95 percent of recorded damage. A ratio of 1 would be an exact match on the median.
- **Median absolute error** = 130,012 in the file’s units, about 130 million dollars.
- **Median absolute percentage error** = 87 percent. The typical prediction was off by 87 percent of the recorded value.
- **Mean absolute error** is much larger than the median absolute error, because a few enormous events dominate the average.
- The 10th and 90th percentiles of the ratio (0.10 and 18.6) describe the spread: one in ten predictions was under a tenth of recorded damage, and one in ten was over 19 times it.

## Blanks are not zeros

A blank in this file means the field was not reported. The file contains no recorded zeros. Setting a blank death toll to zero would say “nobody died” when the source often means “unknown.”

A zero taken from a cited external source is different. It is a real measurement, and log(1+0) = log(1) = 0, so the deaths term drops out of the fitted equation and the prediction is driven by people affected and GDP per capita. That is how the Tuvalu 2015 check was done. It is not a license to recode every blank as zero.

## Why the existing fills are not estimation data

The original equation needs all three predictors. A row missing deaths or people affected has no fitted value from that equation.

The 3,016 fills are predictions, not recorded damage. A later equation, such as one that drops the deaths term, is estimated only on events whose damage was recorded. Putting the fills into that estimation sample would treat predictions as observations and overstate how much is known.

Those later equations are different conditional predictions. They belong in their own columns, not in `Damage_source = model` from the three-predictor fit.
