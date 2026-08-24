# Plotting functions (plotting_functions.R)

build_individuals_plot <- function(df_raw,
                                   id_col, lpp_col, bgp_col, hpp_col,
                                   question_col = NULL,
                                   note_col = NULL,
                                   selected_questions = NULL,
                                   use_export_theme = FALSE,
                                   theme_export = NULL,
                                   facet_cols = 1) {
  has_q <- !is.null(question_col) && !identical(question_col, "<none>")
  if (!has_q) {
    q_col <- "__Question__"
    df <- df_raw %>% mutate(`__Question__` = "Q1")
  } else {
    q_col <- question_col
    df <- df_raw
  }

  if (!is.null(selected_questions) && length(selected_questions) > 0) {
    sel <- setdiff(as.character(selected_questions), c("All", ""))
    if (length(sel) > 0) {
      df <- df %>% filter(as.character(.data[[q_col]]) %in% sel)
    }
  }

  has_note <- !is.null(note_col) && !identical(note_col, "<none>") &&
    note_col %in% names(df)

  dfp <- df %>%
    transmute(
      Question    = as.character(.data[[q_col]]),
      Participant = as.character(.data[[id_col]]),
      L           = suppressWarnings(as.numeric(.data[[lpp_col]])),
      M           = suppressWarnings(as.numeric(.data[[bgp_col]])),
      U           = suppressWarnings(as.numeric(.data[[hpp_col]])),
      note_raw    = if (has_note) as.character(.data[[note_col]]) else NA_character_
    ) %>%
    mutate(
      valid = is_valid_triple(L, M, U),
      note  = blank_note(note_raw, L, M, U)
    )

  q_lab <- dfp$Question[1]
  cfg <- resolve_question_config(q_lab, hpp = dfp$U)
  id_levels <- rev(sort(unique(as.character(dfp$Participant))))
  dfp <- dfp %>%
    mutate(
      Participant = factor(Participant, levels = id_levels),
      triplet = if_else(
        valid,
        format_triplet_label(L, M, U, cfg$label_digits),
        NA_character_
      )
    )

  df_ok   <- dfp %>% filter(valid)
  df_miss <- dfp %>% filter(!valid)
  x_mid   <- (cfg$xmin + cfg$xmax) / 2
  x_pad   <- 0.28 * (cfg$xmax - cfg$xmin)
  txt_size <- if (isTRUE(use_export_theme)) 2.8 else 4.2

  g <- ggplot() +
    geom_segment(
      data = df_ok,
      aes(y = Participant, yend = Participant, x = L, xend = U),
      linewidth = 0.6, colour = "black"
    ) +
    geom_point(
      data = df_ok,
      aes(y = Participant, x = M),
      size = 2, colour = "black"
    ) +
    geom_text(
      data = df_ok,
      aes(y = Participant, x = U, label = triplet),
      hjust = -0.08, size = txt_size, colour = "black"
    ) +
    geom_text(
      data = df_miss,
      aes(y = Participant, x = x_mid, label = note),
      size = txt_size, colour = "grey50"
    ) +
    scale_x_continuous(
      limits = c(cfg$xmin, cfg$xmax + x_pad),
      breaks = cfg$x_breaks,
      expand = c(0, 0)
    ) +
    scale_y_discrete(limits = id_levels, drop = FALSE) +
    labs(x = cfg$xlab, y = "Participant") +
    facet_wrap(~ Question, ncol = if (is.null(facet_cols)) 1 else facet_cols)

  if (isTRUE(use_export_theme) && !is.null(theme_export)) {
    g <- g + theme_export
  }
  g
}

plot_cfg <- function(r) {
  if (!is.null(r$cfg)) return(r$cfg)
  resolve_question_config(r$summaries$Question[1], hpp = r$summaries$Hard_Union_HPP)
}

overlay_lwd <- 1.0  # 2x the original 0.5 overlay thickness

build_density_plot <- function(r, show_individual = TRUE, facet_cols = NULL) {
  cfg <- plot_cfg(r)
  p <- ggplot()
  if (isTRUE(show_individual)) {
    p <- p +
      geom_line(data = r$dens_ind_all, aes(x = p, y = density, color = id),
                alpha = 0.5, linewidth = 0.5) +
      guides(color = "none")
  }
  p <- p +
    geom_line(data = r$dens_mix_all, aes(x = p, y = density),
              colour = "black", linewidth = overlay_lwd, linetype = "dotted") +
    geom_line(data = r$beta_all, aes(x = p, y = density),
              colour = "black", linewidth = overlay_lwd, linetype = "dashed") +
    labs(x = cfg$xlab, y = cfg$ylab_dens) +
    coord_cartesian(xlim = c(cfg$xmin, cfg$xmax))
  if (is.null(facet_cols)) {
    p <- p + facet_wrap(~ Question, scales = "free_y")
  } else {
    p <- p + facet_wrap(~ Question, ncol = facet_cols, scales = "free_y")
  }
  p
}

build_hist_plot <- function(r, facet_cols = 1) {
  cfg <- plot_cfg(r)
  ggplot() +
    geom_histogram(data = r$samples_all,
                   aes(x = samples, y = after_stat(density)),
                   bins = 50, fill = "grey85", color = "white") +
    geom_line(data = r$dens_mix_all, aes(x = p, y = density),
              colour = "black", linewidth = overlay_lwd, linetype = "dotted") +
    geom_line(data = r$beta_all, aes(x = p, y = density),
              colour = "black", linewidth = overlay_lwd, linetype = "dashed") +
    labs(x = cfg$xlab, y = cfg$ylab_dens) +
    coord_cartesian(xlim = c(cfg$xmin, cfg$xmax)) +
    facet_wrap(~ Question, ncol = facet_cols) + theme_export +
    theme(axis.text.y = element_blank(), axis.ticks.y = element_blank())
}

build_cdf_plot <- function(r, show_individual = TRUE, facet_cols = 1) {
  cfg <- plot_cfg(r)
  p <- ggplot()
  if (isTRUE(show_individual)) {
    p <- p +
      geom_line(data = r$cdf_ind_all, aes(p, cdf, color = id),
                alpha = 0.5, linewidth = 0.5) + guides(color = "none")
  }
  p <- p +
    geom_line(data = r$cdf_mix_all, aes(p, cdf),
              colour = "black", linewidth = overlay_lwd, linetype = "dotted") +
    geom_line(data = r$cdf_beta_all, aes(p, cdf),
              colour = "black", linewidth = overlay_lwd, linetype = "dashed") +
    labs(x = cfg$xlab, y = cfg$ylab_cdf) +
    coord_cartesian(xlim = c(cfg$xmin, cfg$xmax))
  p + facet_wrap(~ Question, ncol = facet_cols) + theme_export
}
