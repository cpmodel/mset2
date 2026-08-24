# Summarize PERT distributions (summarize_pert.R)
summarize_question_pert <- function(df,id_col  = "Participant", 
                                    lpp_col = "Lowest_Plausible_Pr", 
                                    bgp_col = "Best_Guess_Pr", 
                                    hpp_col = "Highest_Plausible_Pr", 
                                    lambda  = 5,Nsim    = 40000, 
                                    grid    = seq(0, 1, length.out = 1000), 
                                    seed    = NULL, 
                                    question_label = NULL) { 
  # Use a random seed if none provided 
  if (is.null(seed)) seed <- sample.int(1e9, 1) 
  set.seed(seed) 
   
  # Standardize columns (string-safe) 
  df2 <- df %>% 
    transmute( 
      id = .data[[id_col]], 
      a  = .data[[lpp_col]], 
      m  = .data[[bgp_col]], 
      b  = .data[[hpp_col]] 
    ) %>% 
    mutate( 
      a = pmin(a, b), 
      b = pmax(a, b), 
      m = pmin(pmax(m, a + 1e-8), b - 1e-8), 
      alpha = 1 + lambda * (m - a) / (b - a), 
      beta  = 1 + lambda * (b - m) / (b - a) 
    ) 
   
  # Mixture simulation (equal weights) 
  idx <- sample.int(nrow(df2), Nsim, replace = TRUE) 
  samples <- df2$a[idx] + (df2$b[idx] - df2$a[idx]) * rbeta(Nsim, df2$alpha[idx], 
df2$beta[idx]) 
   
  # Vectorized individual densities 
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
   
  # Linear opinion pool 
  dens_mixture <- dens_individual %>% 
    group_by(p) %>% 
    summarise(density = mean(density), .groups = "drop") 
   
  # Moment-matched Beta on [0,1] (guard against tiny variance) 
  m_hat <- mean(samples) 
  v_hat <- var(samples) 
  if (!is.finite(v_hat) || v_hat <= 1e-12) v_hat <- 1e-6 
  ab_term <- max(m_hat * (1 - m_hat) / v_hat - 1, 2) 
  alpha_star <- m_hat * ab_term 
  beta_star  <- (1 - m_hat) * ab_term 
  grid_beta  <- seq(0, 1, length.out = 1000) 
  df_beta_fit <- data.frame(p = grid_beta, density = dbeta(grid_beta, alpha_star, beta_star))
  # Summaries 
  summary_tbl <- tibble( 
    Question         = if (is.null(question_label)) NA_character_ else question_label, 
    Pooled_Mean      = m_hat, 
    Pooled_Median    = median(samples), 
    Hard_Union_LPP   = min(df2$a), 
    Hard_Union_HPP   = max(df2$b), 
    Mixture_5th      = as.numeric(quantile(samples, 0.05)), 
    Mixture_95th     = as.numeric(quantile(samples, 0.95)), 
    N_Participants   = nrow(df2), 
    Lambda           = lambda, 
    Nsim             = Nsim 
  ) 
   
  # CDFs 
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
  cdf_beta_fit <- data.frame(p = grid_beta, cdf = pbeta(grid_beta, alpha_star, beta_star)) 
   
  # Facet-ready helper 
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