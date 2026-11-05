# Per-question axis ranges and labels for 1a (damages) vs 2a (scaling)

resolve_question_config <- function(question, hpp = NULL) {
  q <- tolower(trimws(as.character(question)[1]))

  if (identical(q, "2a")) {
    return(list(
      xmin = 0,
      xmax = 1,
      x_breaks = seq(0, 1, by = 0.25),
      xlab = "Scaling factor (s)",
      ylab_dens = "Density",
      ylab_cdf = "Subjective probability that s \u2264 x",
      label_digits = 2
    ))
  }

  if (identical(q, "1a")) {
    return(list(
      xmin = 0,
      xmax = 600,
      x_breaks = seq(0, 600, by = 100),
      xlab = "Total financially assessable damage\nfrom climate change ($ billion)",
      ylab_dens = "Density",
      ylab_cdf = "Subjective probability that damage \u2264 x",
      label_digits = 0
    ))
  }

  hpp <- suppressWarnings(as.numeric(hpp))
  hpp <- hpp[is.finite(hpp)]
  xmax <- if (length(hpp)) max(hpp) else 1
  if (!is.finite(xmax) || xmax <= 0) xmax <- 1
  if (xmax <= 1) {
    return(list(
      xmin = 0,
      xmax = 1,
      x_breaks = seq(0, 1, by = 0.25),
      xlab = "Probability",
      ylab_dens = "Density",
      ylab_cdf = "Cumulative probability",
      label_digits = 2
    ))
  }

  list(
    xmin = 0,
    xmax = xmax * 1.05,
    x_breaks = pretty(c(0, xmax), n = 6),
    xlab = "Value",
    ylab_dens = "Density",
    ylab_cdf = "Subjective probability that value \u2264 x",
    label_digits = 2
  )
}

format_triplet_label <- function(L, M, U, digits = 2) {
  n <- length(L)
  digits <- as.integer(digits)
  if (length(digits) == 1L) digits <- rep(digits, n)
  vapply(seq_len(n), function(i) {
    d <- digits[i]
    if (!is.finite(d) || d < 0) d <- 2L
    sprintf(paste0("[%.", d, "f, %.", d, "f, %.", d, "f]"), L[i], M[i], U[i])
  }, character(1))
}
