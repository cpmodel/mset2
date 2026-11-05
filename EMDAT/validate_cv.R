# Predictive validation for the adjusted-damage equations.
# 1. The existing stratified 20% holdout (seed 2026), with out-of-sample R-squared added.
# 2. Stratified 5-fold cross-validation (seed 2026, a separate draw).
# Out-of-sample R-squared is computed on log damage, which is the scale of the regression.
# A dollar-scale R-squared is stored only as a secondary statistic.

suppressPackageStartupMessages(library(jsonlite))

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

r2_vs <- function(y, yhat, ybar) {
  sse <- sum((y - yhat)^2)
  sst <- sum((y - ybar)^2)
  if (sst <= 0) return(NA_real_)
  1 - sse / sst
}

assign_folds <- function(types, k = 5) {
  fold <- integer(length(types))
  for (tp in unique(types)) {
    idx <- which(types == tp)
    idx <- sample(idx)
    fold[idx] <- rep(seq_len(k), length.out = length(idx))
  }
  fold
}

# Replicate the stratified 20% holdout in impute_damage.R.
holdout_flag <- function(data) {
  set.seed(2026)
  hold <- rep(FALSE, nrow(data))
  est_pos <- which(data$estimation_sample)
  types_est <- data$Disaster_type[est_pos]
  for (tp in unique(types_est)) {
    idx <- est_pos[types_est == tp]
    n_hold <- round(0.2 * length(idx))
    if (length(idx) >= 2 && n_hold < 1) n_hold <- 1
    if (length(idx) < 2 || n_hold < 1) next
    if (n_hold >= length(idx)) n_hold <- length(idx) - 1
    hold[sample(idx, n_hold)] <- TRUE
  }
  hold
}

score_split <- function(y_test, yhat_test, y_train, damage_test, damage_hat) {
  data.frame(
    n_test = length(y_test),
    n_train = length(y_train),
    r2_os_train_mean = r2_vs(y_test, yhat_test, mean(y_train)),
    r2_os_test_mean = r2_vs(y_test, yhat_test, mean(y_test)),
    rmse_log = sqrt(mean((y_test - yhat_test)^2)),
    median_ae = median(abs(damage_hat - damage_test)),
    median_ratio = median(damage_hat / damage_test),
    r2_dollar_test_mean = r2_vs(damage_test, damage_hat, mean(damage_test)),
    stringsAsFactors = FALSE
  )
}

run_spec <- function(est, formula, tag, hold) {
  m_full <- lm(formula, data = est)
  r2_in <- summary(m_full)$r.squared
  ybar <- mean(est$log_damage)

  # hold is the stratified 20% flag already drawn with seed 2026.
  m_ho <- lm(formula, data = est[!hold, ])
  yhat_ho <- predict(m_ho, newdata = est[hold, ])
  ho <- score_split(
    est$log_damage[hold], yhat_ho,
    est$log_damage[!hold],
    est$Damage[hold], exp(yhat_ho)
  )
  ho$design <- "holdout_20"
  ho$fold <- NA_integer_
  ho$specification <- tag

  # Stratified 5-fold. Seed is reset so this draw does not depend on the holdout.
  set.seed(2026)
  est$fold <- assign_folds(est$Disaster_type, 5)
  yhat_cv <- rep(NA_real_, nrow(est))
  fold_rows <- vector("list", 5)
  for (k in 1:5) {
    test <- est$fold == k
    m_k <- lm(formula, data = est[!test, ])
    yhat_k <- predict(m_k, newdata = est[test, ])
    yhat_cv[test] <- yhat_k
    row <- score_split(
      est$log_damage[test], yhat_k,
      est$log_damage[!test],
      est$Damage[test], exp(yhat_k)
    )
    row$design <- "fold"
    row$fold <- k
    row$specification <- tag
    fold_rows[[k]] <- row
  }
  folds <- do.call(rbind, fold_rows)

  pooled <- data.frame(
    specification = tag,
    n = nrow(est),
    r2_in_sample = unname(r2_in),
    r2_cv = r2_vs(est$log_damage, yhat_cv, ybar),
    r2_cv_dollar = r2_vs(est$Damage, exp(yhat_cv), mean(est$Damage)),
    cor2_log = unname(cor(est$log_damage, yhat_cv)^2),
    rmse_log_cv = sqrt(mean((est$log_damage - yhat_cv)^2)),
    median_ae_cv = median(abs(exp(yhat_cv) - est$Damage)),
    median_ratio_cv = median(exp(yhat_cv) / est$Damage),
    r2_os_fold_mean = mean(folds$r2_os_train_mean),
    r2_os_fold_min = min(folds$r2_os_train_mean),
    r2_os_fold_max = max(folds$r2_os_train_mean),
    r2_holdout_train_mean = ho$r2_os_train_mean,
    r2_holdout_test_mean = ho$r2_os_test_mean,
    n_holdout = ho$n_test,
    stringsAsFactors = FALSE
  )

  list(pooled = pooled, folds = folds, holdout = ho, fold_id = est$fold)
}

specs <- list(
  list(
    tag = "main",
    formula = log_damage ~ log1p_deaths + log1p_affected + log_gdppc,
    rows = dat$estimation_sample
  ),
  list(
    tag = "deaths_unreported",
    formula = log_damage ~ log1p_affected + log_gdppc,
    rows = !is.na(dat$Damage) & dat$Damage > 0 & !is.na(dat$Affected) & !is.na(dat$GDPpc) & dat$GDPpc > 0
  ),
  list(
    tag = "affected_unreported",
    formula = log_damage ~ log1p_deaths + log_gdppc,
    rows = !is.na(dat$Damage) & dat$Damage > 0 & !is.na(dat$Deaths) & !is.na(dat$GDPpc) & dat$GDPpc > 0
  )
)

hold_main_full <- holdout_flag(dat)
specs[[1]]$hold <- hold_main_full[dat$estimation_sample]
for (i in 2:3) {
  tmp <- dat[specs[[i]]$rows, , drop = FALSE]
  tmp$estimation_sample <- TRUE
  specs[[i]]$hold <- holdout_flag(tmp)
}

pooled_all <- list()
fold_all <- list()
for (sp in specs) {
  res <- run_spec(dat[sp$rows, , drop = FALSE], sp$formula, sp$tag, sp$hold)
  pooled_all[[sp$tag]] <- res$pooled
  fold_all[[sp$tag]] <- res$folds
  if (sp$tag == "main") {
    tab <- table(dat$Disaster_type[sp$rows], res$fold_id)
    write.csv(as.data.frame.matrix(tab), file.path(out_dir, "cv_fold_counts_main.csv"))
  }
}

pooled <- do.call(rbind, pooled_all)
folds <- do.call(rbind, fold_all)
rownames(pooled) <- NULL
rownames(folds) <- NULL

write.csv(pooled, file.path(out_dir, "cv_summary.csv"), row.names = FALSE)
write.csv(folds, file.path(out_dir, "cv_fold_scores.csv"), row.names = FALSE)
write_json(pooled, file.path(out_dir, "cv_summary.json"), digits = 8, pretty = TRUE, rownames = FALSE)

cat("Pooled\n")
print(pooled, digits = 4)
cat("\nFolds, main specification, log-scale OOS R-squared vs training mean\n")
print(folds[folds$specification == "main", c("fold", "n_test", "r2_os_train_mean", "r2_os_test_mean", "rmse_log", "median_ratio")], digits = 4)
