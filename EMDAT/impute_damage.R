# Steps 3-5. Uses the equation already fit in fit_damage_ols.R.
# Step 3: back-transform log predictions with exp(xb). That is the
#         conditional median of Damage, in '000 US$.
# Step 4: write imputations beside recorded damage. Recorded values stay.
#         Rows missing a predictor stay blank.
# Step 5: 20% stratified holdout, scored on the original damage scale,
#         plus a comparison of imputed and recorded distributions.

suppressPackageStartupMessages({
  library(ggplot2)
  library(jsonlite)
})

root <- "C:/Users/dell/Documents/EMDAT"
out_dir <- file.path(root, "output")
dir.create(out_dir, showWarnings = FALSE)

dat <- read.csv(
  file.path(root, "EMDAT_cleaned.csv"),
  stringsAsFactors = FALSE,
  na.strings = c("", "NA"),
  check.names = FALSE
)
dat$estimation_sample <- dat$estimation_sample == TRUE

pred_vars <- c("log1p_deaths", "log1p_affected", "log_gdppc")
dat$predictors_ok <- stats::complete.cases(dat[, pred_vars])

est <- dat[dat$estimation_sample, , drop = FALSE]
m <- lm(log_damage ~ log1p_deaths + log1p_affected + log_gdppc, data = est)

# --- Step 3 and 4: predictions and the output file ---
ok <- dat$predictors_ok
pi <- predict(m, newdata = dat[ok, ], interval = "prediction", level = 0.95)

dat$log_damage_hat <- NA_real_
dat$log_pi_lwr <- NA_real_
dat$log_pi_upr <- NA_real_
dat$log_damage_hat[ok] <- pi[, "fit"]
dat$log_pi_lwr[ok] <- pi[, "lwr"]
dat$log_pi_upr[ok] <- pi[, "upr"]
dat$Damage_pi_lwr <- exp(dat$log_pi_lwr)
dat$Damage_pi_upr <- exp(dat$log_pi_upr)

dat$Damage_imputed <- dat$Damage
dat$Damage_source <- ifelse(is.na(dat$Damage), NA_character_, "observed")
imputable <- is.na(dat$Damage) & ok
dat$Damage_imputed[imputable] <- exp(dat$log_damage_hat[imputable])
dat$Damage_source[imputable] <- "model"

# Duan smearing is reported only as a check on the conditional mean.
# The stored imputation remains exp(xb).
smear <- mean(exp(residuals(m)))
sigma <- summary(m)$sigma
lognormal_factor <- exp(sigma^2 / 2)

out_cols <- c(
  "ISO", "Country", "GDPpc", "Damage", "Affected", "Deaths",
  "Disaster_type", "Start Year",
  "log_damage", "log1p_deaths", "log1p_affected", "log_gdppc",
  "estimation_sample", "log_damage_hat", "log_pi_lwr", "log_pi_upr",
  "Damage_imputed", "Damage_source", "Damage_pi_lwr", "Damage_pi_upr"
)
write.csv(
  dat[, out_cols],
  file.path(root, "EMDAT_imputed.csv"),
  row.names = FALSE,
  na = ""
)

# --- Step 5: stratified 20% holdout ---
set.seed(2026)
hold_flag <- rep(FALSE, nrow(dat))
est_pos <- which(dat$estimation_sample)
types_est <- dat$Disaster_type[est_pos]
for (tp in unique(types_est)) {
  idx <- est_pos[types_est == tp]
  n_hold <- round(0.2 * length(idx))
  if (length(idx) >= 2 && n_hold < 1) n_hold <- 1
  if (length(idx) < 2 || n_hold < 1) next
  if (n_hold >= length(idx)) n_hold <- length(idx) - 1
  hold_flag[sample(idx, n_hold)] <- TRUE
}

train <- dat[dat$estimation_sample & !hold_flag, , drop = FALSE]
test <- dat[hold_flag, , drop = FALSE]
m_ho <- lm(log_damage ~ log1p_deaths + log1p_affected + log_gdppc, data = train)
pi_ho <- predict(m_ho, newdata = test, interval = "prediction", level = 0.95)
test$pred <- exp(pi_ho[, "fit"])
test$pi_lwr <- exp(pi_ho[, "lwr"])
test$pi_upr <- exp(pi_ho[, "upr"])
test$abs_err <- abs(test$pred - test$Damage)
test$ape <- test$abs_err / test$Damage
test$ratio <- test$pred / test$Damage
test$covered <- test$Damage >= test$pi_lwr & test$Damage <= test$pi_upr

score_block <- function(d) {
  data.frame(
    n = nrow(d),
    median_ae = median(d$abs_err),
    mean_ae = mean(d$abs_err),
    median_ape = median(d$ape),
    median_ratio = median(d$ratio),
    ratio_p10 = unname(quantile(d$ratio, 0.10)),
    ratio_p90 = unname(quantile(d$ratio, 0.90)),
    coverage_95 = mean(d$covered),
    stringsAsFactors = FALSE
  )
}

holdout_overall <- score_block(test)
holdout_overall$disaster_type <- "All held-out events"
holdout_by_type <- do.call(rbind, lapply(split(test, test$Disaster_type), function(d) {
  out <- score_block(d)
  out$disaster_type <- d$Disaster_type[1]
  out
}))
holdout_tab <- rbind(holdout_overall, holdout_by_type)
holdout_tab <- holdout_tab[, c(
  "disaster_type", "n", "median_ae", "mean_ae", "median_ape",
  "median_ratio", "ratio_p10", "ratio_p90", "coverage_95"
)]
rownames(holdout_tab) <- NULL

# Recorded vs imputed distributions, by disaster type.
# Imputed figures are the ones written to the file, from the full-sample fit.
qrow <- function(x) {
  c(
    n = length(x),
    median = median(x),
    mean = mean(x),
    p10 = unname(quantile(x, 0.10)),
    p90 = unname(quantile(x, 0.90))
  )
}
dist_rows <- lapply(sort(unique(dat$Disaster_type)), function(tp) {
  obs <- dat$Damage[which(dat$Disaster_type == tp & !is.na(dat$Damage))]
  imp <- dat$Damage_imputed[which(dat$Disaster_type == tp & dat$Damage_source == "model")]
  ro <- if (length(obs)) qrow(obs) else c(n = 0, median = NA, mean = NA, p10 = NA, p90 = NA)
  ri <- if (length(imp)) qrow(imp) else c(n = 0, median = NA, mean = NA, p10 = NA, p90 = NA)
  data.frame(
    disaster_type = tp,
    n_observed = ro["n"],
    median_observed = ro["median"],
    mean_observed = ro["mean"],
    p10_observed = ro["p10"],
    p90_observed = ro["p90"],
    n_imputed = ri["n"],
    median_imputed = ri["median"],
    mean_imputed = ri["mean"],
    p10_imputed = ri["p10"],
    p90_imputed = ri["p90"],
    row.names = NULL
  )
})
dist_tab <- do.call(rbind, dist_rows)
rownames(dist_tab) <- NULL

model_rows <- dat[which(dat$Damage_source == "model"), , drop = FALSE]
interval_ratio <- model_rows$Damage_pi_upr / model_rows$Damage_pi_lwr

stats <- list(
  n_rows = nrow(dat),
  n_observed = sum(dat$Damage_source == "observed", na.rm = TRUE),
  n_imputed = sum(dat$Damage_source == "model", na.rm = TRUE),
  n_left_blank = sum(is.na(dat$Damage_source)),
  n_train = nrow(train),
  n_holdout = nrow(test),
  smear = smear,
  lognormal_factor = lognormal_factor,
  sum_imputed_median = sum(model_rows$Damage_imputed),
  sum_imputed_smearing = sum(model_rows$Damage_imputed * smear),
  median_imputed = median(model_rows$Damage_imputed),
  median_observed = median(dat$Damage, na.rm = TRUE),
  median_interval_ratio = median(interval_ratio),
  holdout_median_ae = holdout_overall$median_ae,
  holdout_mean_ae = holdout_overall$mean_ae,
  holdout_median_ape = holdout_overall$median_ape,
  holdout_median_ratio = holdout_overall$median_ratio,
  holdout_ratio_p10 = holdout_overall$ratio_p10,
  holdout_ratio_p90 = holdout_overall$ratio_p90,
  holdout_coverage = holdout_overall$coverage_95
)

write.csv(holdout_tab, file.path(out_dir, "holdout_scores.csv"), row.names = FALSE)
write.csv(dist_tab, file.path(out_dir, "observed_vs_imputed_by_type.csv"), row.names = FALSE)
write_json(stats, file.path(out_dir, "imputation_stats.json"), auto_unbox = TRUE, digits = 8, pretty = TRUE)

p_hold <- ggplot(test, aes(log(Damage), log(pred))) +
  geom_abline(slope = 1, intercept = 0, linewidth = 0.3) +
  geom_point(alpha = 0.35, size = 1) +
  labs(
    title = "Held-out damage: predicted median against recorded damage",
    subtitle = "Both axes are natural logs of damage in '000 US$. The line is exact agreement.",
    x = "Recorded log damage",
    y = "Predicted log damage, exp(xb) then logged"
  ) +
  theme_minimal(base_size = 12)
ggsave(file.path(out_dir, "holdout_pred_vs_actual.png"), p_hold, width = 8, height = 5.5, dpi = 140)

sink(file.path(out_dir, "imputation_summary.txt"))
cat("Imputed rows:", stats$n_imputed, "\n")
cat("Observed rows left unchanged:", stats$n_observed, "\n")
cat("Rows left blank:", stats$n_left_blank, "\n")
cat("Holdout events:", stats$n_holdout, " trained on ", stats$n_train, "\n")
cat("Duan smearing factor:", smear, "\n")
cat("Lognormal factor exp(sigma^2/2):", lognormal_factor, "\n")
cat("Sum of stored median imputations:", stats$sum_imputed_median, "\n")
cat("Sum if smearing were applied:", stats$sum_imputed_smearing, "\n")
cat("Median upper/lower prediction-interval ratio:", stats$median_interval_ratio, "\n\n")
cat("--- Holdout scores, damage in '000 US$ ---\n")
print(holdout_tab, digits = 4)
cat("\n--- Recorded vs imputed by disaster type ---\n")
print(dist_tab, digits = 4)
sink()

cat("Imputed", stats$n_imputed, "left blank", stats$n_left_blank, "\n")
cat("Holdout n", stats$n_holdout, "median AE", stats$holdout_median_ae,
    "median ratio", stats$holdout_median_ratio, "coverage", stats$holdout_coverage, "\n")
cat("Smearing", smear, "lognormal", lognormal_factor, "\n")
print(holdout_tab, digits = 4)
