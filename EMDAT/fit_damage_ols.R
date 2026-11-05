# Step 1: clean EMDAT.csv
# Step 2: OLS for log(Damage) on log(1+Deaths), log(1+Affected), log(GDPpc)
# Damage is EM-DAT Total Damage, Adjusted ('000 US$).
# GDPpc is World Bank GDP per capita, current US$.
# No further price conversion. No imputation.

suppressPackageStartupMessages({
  library(sandwich)
  library(lmtest)
  library(car)
  library(ggplot2)
  library(jsonlite)
})

root <- "C:/Users/dell/Documents/EMDAT"
out_dir <- file.path(root, "output")
dir.create(out_dir, showWarnings = FALSE)

raw <- read.csv(
  file.path(root, "EMDAT.csv"),
  stringsAsFactors = FALSE,
  na.strings = c("", "NA", "#N/A"),
  fileEncoding = "UTF-8",
  check.names = FALSE
)

num <- function(x) suppressWarnings(as.numeric(x))

dat <- raw
dat$GDPpc <- num(dat$GDPpc)
dat$Damage <- num(dat$Damage)
dat$Affected <- num(dat$Affected)
dat$Deaths <- num(dat$Deaths)
dat$start_year <- as.integer(dat[["Start Year"]])

dat$log_damage <- ifelse(is.na(dat$Damage) | dat$Damage <= 0, NA_real_, log(dat$Damage))
dat$log1p_deaths <- ifelse(is.na(dat$Deaths) | dat$Deaths < 0, NA_real_, log1p(dat$Deaths))
dat$log1p_affected <- ifelse(is.na(dat$Affected) | dat$Affected < 0, NA_real_, log1p(dat$Affected))
dat$log_gdppc <- ifelse(is.na(dat$GDPpc) | dat$GDPpc <= 0, NA_real_, log(dat$GDPpc))

reg_vars <- c("log_damage", "log1p_deaths", "log1p_affected", "log_gdppc")
dat$estimation_sample <- stats::complete.cases(dat[, reg_vars])

est <- dat[dat$estimation_sample, , drop = FALSE]
est$disaster_type <- est$Disaster_type

m <- lm(log_damage ~ log1p_deaths + log1p_affected + log_gdppc, data = est)

V_hc1 <- vcovHC(m, type = "HC1")
ct_ols <- coeftest(m)
ct_hc1 <- coeftest(m, vcov. = V_hc1)
ci_ols <- confint(m, level = 0.95)
ci_hc1 <- coefci(m, vcov. = V_hc1, level = 0.95)

sm <- summary(m)
vif_vals <- vif(m)
bp <- bptest(m)
reg_cor <- cor(est[, c("log1p_deaths", "log1p_affected", "log_gdppc")])

est$resid <- residuals(m)
est$fitted <- fitted(m)
est$cooks <- cooks.distance(m)

skewness <- function(x) {
  z <- (x - mean(x)) / stats::sd(x)
  mean(z^3)
}

type_tab <- do.call(rbind, lapply(split(est, est$disaster_type), function(d) {
  data.frame(
    disaster_type = d$disaster_type[1],
    n = nrow(d),
    share = nrow(d) / nrow(est),
    mean_resid = mean(d$resid),
    sd_resid = stats::sd(d$resid),
    median_resid = median(d$resid),
    stringsAsFactors = FALSE
  )
}))
type_tab <- type_tab[order(-type_tab$n), ]
rownames(type_tab) <- NULL

est$fitted_decile <- dplyr::ntile(est$fitted, 10)
decile_tab <- do.call(rbind, lapply(split(est, est$fitted_decile), function(d) {
  data.frame(
    decile = d$fitted_decile[1],
    n = nrow(d),
    mean_fitted = mean(d$fitted),
    mean_resid = mean(d$resid),
    sd_resid = stats::sd(d$resid),
    stringsAsFactors = FALSE
  )
}))
decile_tab <- decile_tab[order(decile_tab$decile), ]
rownames(decile_tab) <- NULL

coef_names <- rownames(ct_ols)
coef_tab <- data.frame(
  term = coef_names,
  estimate = as.numeric(ct_ols[, 1]),
  se_ols = as.numeric(ct_ols[, 2]),
  t_ols = as.numeric(ct_ols[, 3]),
  p_ols = as.numeric(ct_ols[, 4]),
  ci95_ols_low = as.numeric(ci_ols[, 1]),
  ci95_ols_high = as.numeric(ci_ols[, 2]),
  se_hc1 = as.numeric(ct_hc1[, 2]),
  t_hc1 = as.numeric(ct_hc1[, 3]),
  p_hc1 = as.numeric(ct_hc1[, 4]),
  ci95_hc1_low = as.numeric(ci_hc1[, 1]),
  ci95_hc1_high = as.numeric(ci_hc1[, 2]),
  stringsAsFactors = FALSE
)

desc_vars <- c("Damage", "Deaths", "Affected", "GDPpc", reg_vars)
desc_tab <- data.frame(
  variable = desc_vars,
  n = sapply(desc_vars, function(v) sum(!is.na(est[[v]]))),
  mean = sapply(desc_vars, function(v) mean(est[[v]])),
  sd = sapply(desc_vars, function(v) stats::sd(est[[v]])),
  min = sapply(desc_vars, function(v) min(est[[v]])),
  p50 = sapply(desc_vars, function(v) stats::median(est[[v]])),
  max = sapply(desc_vars, function(v) max(est[[v]])),
  row.names = NULL
)

cook_cut <- 4 / nrow(est)
n_influential <- sum(est$cooks > cook_cut)

miss_counts <- sapply(c("Damage", "Deaths", "Affected", "GDPpc"), function(v) sum(is.na(dat[[v]])))

stats <- list(
  n_rows = nrow(dat),
  n_estimation = nrow(est),
  n_damage_observed = sum(!is.na(dat$Damage)),
  n_missing = as.list(miss_counts),
  r_squared = unname(sm$r.squared),
  adj_r_squared = unname(sm$adj.r.squared),
  sigma = unname(sm$sigma),
  f_stat = unname(sm$fstatistic[1]),
  f_df1 = unname(sm$fstatistic[2]),
  f_df2 = unname(sm$fstatistic[3]),
  f_p = unname(pf(sm$fstatistic[1], sm$fstatistic[2], sm$fstatistic[3], lower.tail = FALSE)),
  bp_stat = unname(bp$statistic),
  bp_df = unname(bp$parameter),
  bp_p = unname(bp$p.value),
  vif = as.list(vif_vals),
  cor = as.list(as.data.frame(reg_cor)),
  resid_mean = mean(est$resid),
  resid_sd = stats::sd(est$resid),
  resid_skew = skewness(est$resid),
  resid_min = min(est$resid),
  resid_max = max(est$resid),
  cook_cutoff = cook_cut,
  n_cooks_above = n_influential,
  aic = AIC(m),
  bic = BIC(m)
)

write.csv(dat[, c(
  "ISO", "Country", "GDPpc", "Damage", "Affected", "Deaths",
  "Disaster_type", "Start Year",
  "log_damage", "log1p_deaths", "log1p_affected", "log_gdppc",
  "estimation_sample"
)], file.path(root, "EMDAT_cleaned.csv"), row.names = FALSE, na = "")

write.csv(coef_tab, file.path(out_dir, "coefficients.csv"), row.names = FALSE)
write.csv(type_tab, file.path(out_dir, "residuals_by_type.csv"), row.names = FALSE)
write.csv(decile_tab, file.path(out_dir, "residuals_by_fitted_decile.csv"), row.names = FALSE)
write.csv(desc_tab, file.path(out_dir, "estimation_sample_descriptives.csv"), row.names = FALSE)
write_json(stats, file.path(out_dir, "model_stats.json"), auto_unbox = TRUE, digits = 10, pretty = TRUE)

p_fit <- ggplot(est, aes(fitted, resid)) +
  geom_hline(yintercept = 0, linewidth = 0.3) +
  geom_point(alpha = 0.25, size = 1) +
  geom_smooth(method = "loess", formula = y ~ x, se = FALSE, linewidth = 0.6) +
  labs(
    title = "Log-damage residuals against fitted values",
    subtitle = "Estimation sample. Loess curve in blue. Residual of 0 is the horizontal line.",
    x = "Fitted log damage (log of '000 US$)",
    y = "Residual (log '000 US$)"
  ) +
  theme_minimal(base_size = 12)

p_type <- ggplot(est, aes(x = reorder(disaster_type, resid, FUN = median), y = resid)) +
  geom_hline(yintercept = 0, linewidth = 0.3) +
  geom_boxplot(outlier.alpha = 0.4) +
  coord_flip() +
  labs(
    title = "Log-damage residuals by disaster type",
    subtitle = "Estimation sample. Boxes are the interquartile range of residuals.",
    x = NULL,
    y = "Residual (log '000 US$)"
  ) +
  theme_minimal(base_size = 12)

ggsave(file.path(out_dir, "resid_vs_fitted.png"), p_fit, width = 8, height = 5.5, dpi = 140)
ggsave(file.path(out_dir, "resid_by_type.png"), p_type, width = 8, height = 5.5, dpi = 140)

sink(file.path(out_dir, "ols_summary.txt"))
cat("Estimation sample:", nrow(est), "of", nrow(dat), "events\n")
cat("Missing counts in the full file:\n")
print(miss_counts)
cat("\n--- OLS summary ---\n")
print(sm)
cat("\n--- HC1 robust coefficient test ---\n")
print(ct_hc1)
cat("\n--- 95% CI, classical ---\n")
print(ci_ols)
cat("\n--- 95% CI, HC1 ---\n")
print(ci_hc1)
cat("\n--- VIF ---\n")
print(vif_vals)
cat("\n--- Regressor correlations ---\n")
print(reg_cor)
cat("\n--- Breusch-Pagan ---\n")
print(bp)
cat("\n--- Residuals by disaster type ---\n")
print(type_tab, digits = 4)
cat("\n--- Residuals by fitted decile ---\n")
print(decile_tab, digits = 4)
cat("\nCook's distance cutoff 4/n =", cook_cut, "; n above =", n_influential, "\n")
sink()

cat("Wrote cleaned data and model output.\n")
cat("N estimation =", nrow(est), "\n")
print(coef_tab)
cat("R2 =", sm$r.squared, " adjR2 =", sm$adj.r.squared, " sigma =", sm$sigma, "\n")
cat("VIF:\n")
print(vif_vals)
cat("BP p =", bp$p.value, "\n")
