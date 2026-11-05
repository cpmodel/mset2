# Reduced damage equations, fit only on recorded damage.
# Deaths unreported:
#   log(Damage) = a + b1 log(1+Affected) + b2 log(GDPpc) + e
# People affected unreported:
#   log(Damage) = a + b1 log(1+Deaths) + b2 log(GDPpc) + e
# Stored values are conditional medians, exp(fitted log), in their own columns.
# The original Damage_imputed column is left unchanged.

suppressPackageStartupMessages({
  library(sandwich)
  library(lmtest)
  library(jsonlite)
})

root <- "C:/Users/dell/Documents/EMDAT"
out_dir <- file.path(root, "output")
dir.create(out_dir, showWarnings = FALSE)

dat <- read.csv(
  file.path(root, "EMDAT_imputed.csv"),
  stringsAsFactors = FALSE,
  na.strings = c("", "NA"),
  check.names = FALSE
)

has_damage <- !is.na(dat$Damage) & dat$Damage > 0
has_death <- !is.na(dat$Deaths)
has_aff <- !is.na(dat$Affected)
has_g <- !is.na(dat$GDPpc) & dat$GDPpc > 0
miss_damage <- is.na(dat$Damage)

fit_one <- function(est, formula, apply_rows, tag) {
  m <- lm(formula, data = est)
  sm <- summary(m)
  V <- vcovHC(m, type = "HC1")
  ct <- coeftest(m, vcov. = V)
  ci <- coefci(m, vcov. = V, level = 0.95)
  coef_tab <- data.frame(
    specification = tag,
    term = rownames(ct),
    estimate = as.numeric(ct[, 1]),
    se_ols = summary(m)$coefficients[, 2],
    se_hc1 = as.numeric(ct[, 2]),
    p_hc1 = as.numeric(ct[, 4]),
    ci95_hc1_low = as.numeric(ci[, 1]),
    ci95_hc1_high = as.numeric(ci[, 2]),
    stringsAsFactors = FALSE
  )
  pi <- predict(m, newdata = dat[apply_rows, ], interval = "prediction", level = 0.95)
  smear <- mean(exp(residuals(m)))

  # Stratified 20% holdout on recorded-damage rows used to fit this equation.
  set.seed(2026)
  hold <- rep(FALSE, nrow(est))
  for (tp in unique(est$Disaster_type)) {
    idx <- which(est$Disaster_type == tp)
    n_hold <- round(0.2 * length(idx))
    if (length(idx) >= 2 && n_hold < 1) n_hold <- 1
    if (length(idx) < 2 || n_hold < 1) next
    if (n_hold >= length(idx)) n_hold <- length(idx) - 1
    hold[sample(idx, n_hold)] <- TRUE
  }
  m_ho <- lm(formula, data = est[!hold, ])
  test <- est[hold, ]
  pred <- exp(predict(m_ho, newdata = test))
  ratio <- pred / test$Damage
  abs_err <- abs(pred - test$Damage)
  pi_ho <- predict(m_ho, newdata = test, interval = "prediction", level = 0.95)
  covered <- test$Damage >= exp(pi_ho[, "lwr"]) & test$Damage <= exp(pi_ho[, "upr"])

  list(
    model = m,
    coef_tab = coef_tab,
    n_fit = nrow(est),
    n_apply = sum(apply_rows),
    r_squared = unname(sm$r.squared),
    adj_r_squared = unname(sm$adj.r.squared),
    sigma = unname(sm$sigma),
    smear = smear,
    n_holdout = sum(hold),
    n_train = sum(!hold),
    median_ae = median(abs_err),
    mean_ae = mean(abs_err),
    median_ape = median(abs_err / test$Damage),
    median_ratio = median(ratio),
    ratio_p10 = unname(quantile(ratio, 0.10)),
    ratio_p90 = unname(quantile(ratio, 0.90)),
    coverage = mean(covered),
    fit = pi[, "fit"],
    lwr = pi[, "lwr"],
    upr = pi[, "upr"]
  )
}

est_deaths_missing <- dat[has_damage & has_aff & has_g, ]
apply_deaths_missing <- miss_damage & !has_death & has_aff & has_g
res_a <- fit_one(
  est_deaths_missing,
  log_damage ~ log1p_affected + log_gdppc,
  apply_deaths_missing,
  "deaths_unreported"
)

est_aff_missing <- dat[has_damage & has_death & has_g, ]
apply_aff_missing <- miss_damage & has_death & !has_aff & has_g
res_b <- fit_one(
  est_aff_missing,
  log_damage ~ log1p_deaths + log_gdppc,
  apply_aff_missing,
  "affected_unreported"
)

dat$log_hat_deaths_unreported <- NA_real_
dat$Damage_imputed_deaths_unreported <- NA_real_
dat$Damage_pi_lwr_deaths_unreported <- NA_real_
dat$Damage_pi_upr_deaths_unreported <- NA_real_
dat$log_hat_deaths_unreported[apply_deaths_missing] <- res_a$fit
dat$Damage_imputed_deaths_unreported[apply_deaths_missing] <- exp(res_a$fit)
dat$Damage_pi_lwr_deaths_unreported[apply_deaths_missing] <- exp(res_a$lwr)
dat$Damage_pi_upr_deaths_unreported[apply_deaths_missing] <- exp(res_a$upr)

dat$log_hat_affected_unreported <- NA_real_
dat$Damage_imputed_affected_unreported <- NA_real_
dat$Damage_pi_lwr_affected_unreported <- NA_real_
dat$Damage_pi_upr_affected_unreported <- NA_real_
dat$log_hat_affected_unreported[apply_aff_missing] <- res_b$fit
dat$Damage_imputed_affected_unreported[apply_aff_missing] <- exp(res_b$fit)
dat$Damage_pi_lwr_affected_unreported[apply_aff_missing] <- exp(res_b$lwr)
dat$Damage_pi_upr_affected_unreported[apply_aff_missing] <- exp(res_b$upr)

write.csv(dat, file.path(root, "EMDAT_imputed.csv"), row.names = FALSE, na = "")

coef_tab <- rbind(res_a$coef_tab, res_b$coef_tab)
write.csv(coef_tab, file.path(out_dir, "reduced_coefficients.csv"), row.names = FALSE)

summarise_spec <- function(res, tag) {
  data.frame(
    specification = tag,
    n_fit = res$n_fit,
    n_filled = res$n_apply,
    r_squared = res$r_squared,
    adj_r_squared = res$adj_r_squared,
    sigma = res$sigma,
    smear = res$smear,
    n_train = res$n_train,
    n_holdout = res$n_holdout,
    median_ae = res$median_ae,
    mean_ae = res$mean_ae,
    median_ape = res$median_ape,
    median_ratio = res$median_ratio,
    ratio_p10 = res$ratio_p10,
    ratio_p90 = res$ratio_p90,
    coverage_95 = res$coverage,
    median_fill = median(exp(res$fit)),
    sum_fill = sum(exp(res$fit)),
    stringsAsFactors = FALSE
  )
}

spec_tab <- rbind(
  summarise_spec(res_a, "deaths_unreported"),
  summarise_spec(res_b, "affected_unreported")
)
write.csv(spec_tab, file.path(out_dir, "reduced_model_summary.csv"), row.names = FALSE)
write_json(spec_tab, file.path(out_dir, "reduced_model_summary.json"), digits = 8, pretty = TRUE)

sink(file.path(out_dir, "reduced_model_summary.txt"))
cat("Deaths unreported: fit", res_a$n_fit, "filled", res_a$n_apply, "\n")
print(coef(res_a$model))
cat("\nAffected unreported: fit", res_b$n_fit, "filled", res_b$n_apply, "\n")
print(coef(res_b$model))
cat("\n")
print(spec_tab, digits = 4)
sink()

cat("Filled deaths-unreported", res_a$n_apply, " affected-unreported", res_b$n_apply, "\n")
print(spec_tab, digits = 4)
print(coef_tab, digits = 4)
