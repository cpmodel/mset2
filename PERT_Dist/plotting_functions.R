# Plotting functions (plotting_functions.R)
# LPP / BGP / HPP per participant faceted by Question 
build_individuals_plot <- function(df_raw, 
                                   id_col, lpp_col, bgp_col, hpp_col, 
                                   question_col = NULL, 
                                   selected_questions = NULL, 
                                   use_export_theme = FALSE, 
                                   theme_export = NULL,  
                                   facet_cols = 4) { 
  # Ensure we have a Question column (or synthesize one) 
  has_q <- !is.null(question_col) && !identical(question_col, "<none>") 
  if (!has_q) { 
    q_col <- "__Question__" 
    df <- df_raw %>% mutate(`__Question__` = "Q1") 
  } else { 
    q_col <- question_col 
    df <- df_raw 
  } 
   
  # Filter to the selected subset of questions (if provided) 
  if (!is.null(selected_questions) && length(selected_questions) > 0) { 
    # When app has an "All" option, remove it before filtering 
    sel <- setdiff(selected_questions, "All") 
    if (length(sel) > 0) { 
      df <- df %>% filter(.data[[q_col]] %in% sel) 
    } 
  } 
   
  # Build plotting frame using raw values 
  dfp <- df %>% 
    transmute( 
      Question             = .data[[q_col]], 
      Participant          = as.character(.data[[id_col]]), 
      Lowest_Plausible_Pr  = suppressWarnings(as.numeric(.data[[lpp_col]])), 
      Best_Guess_Pr        = suppressWarnings(as.numeric(.data[[bgp_col]])), 
      Highest_Plausible_Pr = suppressWarnings(as.numeric(.data[[hpp_col]])) 
    ) 
     
  g <- ggplot() + 
    geom_linerange(data = dfp, aes(x = Participant,  
                                   ymin = Lowest_Plausible_Pr,  
                                   ymax = Highest_Plausible_Pr),lwd = 0.5) + 
    geom_point(data = dfp, aes(x = Participant, y = Best_Guess_Pr), size = 1) + 
    coord_flip() + ylim(0,1)+ 
    labs(x = "Participant", y = "Probability") + 
    facet_wrap(~ Question, ncol = facet_cols, scales = "fixed")+ 
    theme(axis.text.y = element_blank(),  
          axis.ticks.y = element_blank()) 
   
  # Apply export theme 
  if (isTRUE(use_export_theme) && !is.null(theme_export)) { 
    g <- g + theme_export + theme(axis.text.y = element_blank(),  
                                  axis.ticks.y = element_blank()) 
  } 
  g 
} 
 
build_density_plot <- function(r, show_individual = TRUE, facet_cols = NULL) { 
  p <- ggplot() + 
    geom_line(data = r$dens_mix_all, aes(x = p, y = density), lwd = 0.5) +
    labs(x = "Probability", y = "Density") 
  if (isTRUE(show_individual)) { 
    p <- p + 
      geom_line(data = r$dens_ind_all, aes(x = p, y = density, color = id), 
                alpha = 0.5, lwd = 0.5) + 
      guides(color = "none") 
  } 
  p <- p + 
    geom_line(data = r$beta_all, aes(x = p, y = density), 
              color = "blue", lwd = 0.5, lty = "dashed") 
  if (is.null(facet_cols)) { 
    p <- p + facet_wrap(~ Question, scales = "free_y") 
  } else { 
    p <- p + facet_wrap(~ Question, ncol = facet_cols, scales = "free_y") 
  } 
  p 
} 
 
build_hist_plot <- function(r, facet_cols = 4) { 
  ggplot() + 
    geom_histogram(data = r$samples_all, 
                   aes(x = samples, y = after_stat(density)), 
                   bins = 50, fill = "grey85", color = "white") + 
    geom_line(data = r$beta_all, aes(x = p, y = density), 
              color = "blue", lwd = 0.5, lty = "dashed") + 
    geom_line(data = r$dens_mix_all, aes(x = p, y = density), lwd = 0.5) + 
    labs(x = "Probability", y = "Density") +  
    facet_wrap(~ Question, ncol = facet_cols) + theme_export + 
    theme(axis.text.y = element_blank(), axis.ticks.y = element_blank()) 
} 
 
build_cdf_plot <- function(r, show_individual = TRUE, facet_cols = 4) { 
  p <- ggplot() + 
    geom_line(data = r$cdf_mix_all, aes(p, cdf), lwd = 0.5) + 
    geom_line(data = r$cdf_beta_all, aes(p, cdf), 
              color = "blue", lwd = 0.5, lty = "dashed") + 
    #geom_line(data = r$cdf_emp_all, aes(p, cdf), 
    #          color = "darkgrey", lwd = 0.5, lty = "dotdash") + 
    labs(x = "Probability", y = "Cumulative probability") 
   
  if (isTRUE(show_individual)) { 
    p <- p + 
      geom_line(data = r$cdf_ind_all, aes(p, cdf, color = id), 
                alpha = 0.5, lwd = 0.5) + guides(color = "none") 
  } 
  p + facet_wrap(~ Question, ncol = facet_cols) + theme_export 
}
