# Summarize PERT distributions (summarize_pert.R)
summarize_question_pert <- function(df, id_col  = "Participant",
                                    lpp_col = "Lowest_Plausible_Pr",
                                    bgp_col = "Best_Guess_Pr",
                                    hpp_col = "Highest_Plausible_Pr",
                                    lambda  = 5, Nsim    = 40000,
                                    xmin    = 0, xmax    = 1,
                                    grid    = NULL,
                                    seed    = NULL,
                                    question_label = NULL) {
  if (is.null(seed)) seed <- sample.int(1e9, 1)
  set.seed(seed)

  if (is.null(xmin) || !is.finite(xmin)) xmin <- 0
  if (is.null(xmax) || !is.finite(xmax) || xmax <= xmin) xmax <- xmin + 1
  if (is.null(grid)) grid <- seq(xmin, xmax, length.out = 1000)

  df2 <- df %>%
    transmute(
      id = .data[[id_col]],
      a  = suppressWarnings(as.numeric(.data[[lpp_col]])),
      m  = suppressWarnings(as.numeric(.data[[bgp_col]])),
      b  = suppressWarnings(as.numeric(.data[[hpp_col]]))
    ) %>%
    filter(is_valid_triple(a, m, b)) %>%
    mutate(
      a = pmin(a, b),
      b = pmax(a, b),
      m = pmin(pmax(m, a + 1e-8), b - 1e-8),
      alpha = 1 + lambda * (m - a) / (b - a),
      beta  = 1 + lambda * (b - m) / (b - a)
    )

  if (nrow(df2) == 0) {
    stop("No valid PERT triples for this question (need finite L < U with L \u2264 M \u2264 U).")
  }

  idx <- sample.int(nrow(df2), Nsim, replace = TRUE)
  samples <- df2$a[idx] + (df2$b[idx] - df2$a[idx]) * rbeta(Nsim, df2$alpha[idx],
df2$beta[idx])

  dens_individual <- df2 %>%
    select(id, a, b, alpha, beta) %>%
    crossing(p = grid) %>%
    mutate(
      density = if_else(
        p >= a & p <= b,
        dbeta((p - a) / (b - a), alpha, beta) / (b - a),
        0
      )
    )

  dens_mixture <- dens_individual %>%
    group_by(p) %>%
    summarise(density = mean(density), .groups = "drop")

  # Moment-matched Beta on [xmin, xmax]
  span <- xmax - xmin
  u <- pmin(pmax((samples - xmin) / span, 1e-8), 1 - 1e-8)
  m_hat <- mean(u)
  v_hat <- var(u)
  if (!is.finite(v_hat) || v_hat <= 1e-12) v_hat <- 1e-6
  ab_term <- max(m_hat * (1 - m_hat) / v_hat - 1, 2)
  alpha_star <- m_hat * ab_term
  beta_star  <- (1 - m_hat) * ab_term
  grid_u <- pmin(pmax((grid - xmin) / span, 0), 1)
  df_beta_fit <- data.frame(
    p = grid,
    density = ifelse(grid >= xmin & grid <= xmax,
                     dbeta(grid_u, alpha_star, beta_star) / span,
                     0)
  )

  to_scale <- function(u) xmin + span * u
  beta_mean   <- to_scale(alpha_star / (alpha_star + beta_star))
  beta_median <- to_scale(qbeta(0.5,  alpha_star, beta_star))
  beta_p05    <- to_scale(qbeta(0.05, alpha_star, beta_star))
  beta_p95    <- to_scale(qbeta(0.95, alpha_star, beta_star))

  q_lab <- if (is.null(question_label)) NA_character_ else question_label
  meta <- list(
    Hard_Union_LPP = min(df2$a),
    Hard_Union_HPP = max(df2$b),
    N_Participants = nrow(df2),
    Lambda = lambda,
    Nsim = Nsim
  )
  summary_tbl <- bind_rows(
    tibble(
      Question       = q_lab,
      Distribution   = "Moment-matched Beta",
      Pooled_Mean    = beta_mean,
      Pooled_Median  = beta_median,
      Hard_Union_LPP = meta$Hard_Union_LPP,
      Hard_Union_HPP = meta$Hard_Union_HPP,
      Mixture_5th    = beta_p05,
      Mixture_95th   = beta_p95,
      N_Participants = meta$N_Participants,
      Lambda         = meta$Lambda,
      Nsim           = meta$Nsim
    ),
    tibble(
      Question       = q_lab,
      Distribution   = "Mixture",
      Pooled_Mean    = mean(samples),
      Pooled_Median  = median(samples),
      Hard_Union_LPP = meta$Hard_Union_LPP,
      Hard_Union_HPP = meta$Hard_Union_HPP,
      Mixture_5th    = as.numeric(quantile(samples, 0.05)),
      Mixture_95th   = as.numeric(quantile(samples, 0.95)),
      N_Participants = meta$N_Participants,
      Lambda         = meta$Lambda,
      Nsim           = meta$Nsim
    )
  )

  cdf_individual <- df2 %>%
    select(id, a, b, alpha, beta) %>%
    crossing(p = grid) %>%
    mutate(
      cdf = case_when(
        p <= a ~ 0,
        p >= b ~ 1,
        TRUE   ~ pbeta((p - a) / (b - a), alpha, beta)
      )
    )
  cdf_mixture <- cdf_individual %>%
    group_by(p) %>%
    summarise(cdf = mean(cdf), .groups = "drop")
  ec <- ecdf(samples)
  cdf_emp <- data.frame(p = grid, cdf = ec(grid))
  cdf_beta_fit <- data.frame(
    p = grid,
    cdf = ifelse(grid <= xmin, 0,
                 ifelse(grid >= xmax, 1, pbeta(grid_u, alpha_star, beta_star)))
  )

  add_q <- function(df_fac) {
    df_fac %>%
      mutate(Question = if (is.null(question_label)) NA_character_ else question_label) %>%
      relocate(Question, .before = 1)
  }

  list(
    summary              = summary_tbl,
    densities_individual = dens_individual,
    density_mixture      = dens_mixture,
    samples              = samples,
    cdfs                 = list(individual = cdf_individual,
                                mixture = cdf_mixture,
                                empirical = cdf_emp,
                                beta_fit = cdf_beta_fit),
    facet                = list(
      mixture        = add_q(dens_mixture),
      individual     = add_q(dens_individual),
      beta           = add_q(df_beta_fit),
      cdf_mixture    = add_q(cdf_mixture),
      cdf_emp        = add_q(cdf_emp),
      cdf_beta       = add_q(cdf_beta_fit),
      cdf_individual = add_q(cdf_individual)
    ),
    beta_fit_params      = list(alpha = alpha_star, beta = beta_star)
  )
}
