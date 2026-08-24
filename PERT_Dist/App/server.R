# Server (server.R)
# Server 
server <- function(input, output, session) { 
  # Load data (reactive) and clean names without emitting "New names" message 
  raw_df <- reactive({ 
    if (isTRUE(input$use_demo) || is.null(input$file)) { 
      demo_df 
    } else { 
      df <- suppressMessages( 
        read_csv(input$file$datapath, 
                 show_col_types = FALSE, 
                 name_repair = "minimal") 
      ) 
    } 
  }) 
   
  # Column mapping UI 
  output$colmap_ui <- renderUI({ 
    req(raw_df()) 
    df <- raw_df() 
    cols <- names(df) 
    default_question <- best_question_col(df) 
     
    tagList( 
      selectInput("col_question", "Question column", choices = c("Question", cols), 
                  selected = if (default_question %in% cols) default_question else "<none>"), 
      selectInput("col_id", "Participant ID column", choices = cols, 
                  selected = if ("Participant" %in% cols) "Participant" else cols[1]), 
      selectInput("col_lpp", "Lowest plausible (LPP)", choices = cols, 
                  selected = grep("Lowest|LPP", cols, ignore.case = TRUE, value = TRUE)[1]), 
      selectInput("col_bgp", "Best guess (BGP)", choices = cols, 
                  selected = grep("Best|BGP", cols, ignore.case = TRUE, value = TRUE)[1]), 
      selectInput("col_hpp", "Highest plausible (HPP)", choices = cols, 
                  selected = grep("Highest|HPP", cols, ignore.case = TRUE, value = TRUE)[1]),
      selectInput("col_note", "Blank/exclusion label",
                  choices = c("<none>", cols),
                  selected = {
                    hit <- grep("No_value|note|reason|label", cols, ignore.case = TRUE, value = TRUE)[1]
                    if (length(hit) && !is.na(hit)) hit else "<none>"
                  })
    ) 
  }) 
   
  output$question_filter_ui <- renderUI({ 
    req(raw_df(), input$col_question) 
    if (identical(input$col_question, "<none>")) return(NULL) 
    qs <- sort(unique(as.character(raw_df()[[input$col_question]]))) 
    qs <- qs[!is.na(qs) & nzchar(qs)] 
    selectInput("question_sel", "Question to display", 
                choices = qs, selected = qs[1], multiple = FALSE) 
  }) 
   
  # Run/Refresh 
  results <- eventReactive(input$run, { 
    df <- raw_df() 
    req(input$col_id, input$col_lpp, input$col_bgp, input$col_hpp) 
     
    # Attach a question column if none provided 
    has_q <- !identical(input$col_question, "<none>") 
    if (!has_q) { 
      df <- df %>% mutate(`__Question__` = "Q1") 
    } 
    q_col <- if (has_q) input$col_question else "__Question__" 
     
    req(input$question_sel) 
    df <- df %>% filter(as.character(.data[[q_col]]) == as.character(input$question_sel)) 
     
    n_ok <- sum(is_valid_triple( 
      suppressWarnings(as.numeric(df[[input$col_lpp]])), 
      suppressWarnings(as.numeric(df[[input$col_bgp]])), 
      suppressWarnings(as.numeric(df[[input$col_hpp]])) 
    )) 
    validate(need( 
      n_ok > 0, 
      "No valid L/M/U triples for this question. Expert Scores still shows blank-row labels." 
    )) 
     
    qs <- unique(as.character(df[[q_col]])) 
    validate(need(length(qs) > 0, "No rows for the selected question.")) 
     
    res_list <- lapply(qs, function(q) { 
      df_q <- df %>% filter(as.character(.data[[q_col]]) == as.character(q)) 
      cfg <- resolve_question_config(q, hpp = suppressWarnings(as.numeric(df_q[[input$col_hpp]]))) 
      summarize_question_pert( 
        df_q, 
        id_col  = input$col_id, 
        lpp_col = input$col_lpp, 
        bgp_col = input$col_bgp, 
        hpp_col = input$col_hpp, 
        lambda  = input$lambda, 
        Nsim    = input$Nsim, 
        xmin    = cfg$xmin, 
        xmax    = cfg$xmax, 
        seed    = NULL, 
        question_label = as.character(q) 
      ) 
    }) 
    names(res_list) <- as.character(qs) 
     
    # Bind everything 
    summary_all  <- bind_rows(lapply(res_list, `[[`, "summary")) 
    dens_mix_all <- bind_rows(lapply(res_list, function(r) r$facet$mixture)) 
    dens_ind_all <- bind_rows(lapply(res_list, function(r) r$facet$individual)) 
    beta_all     <- bind_rows(lapply(res_list, function(r) r$facet$beta)) 
     
    cdf_mix_all  <- bind_rows(lapply(res_list, function(r) r$facet$cdf_mixture)) 
    cdf_emp_all  <- bind_rows(lapply(res_list, function(r) r$facet$cdf_emp)) 
    cdf_beta_all <- bind_rows(lapply(res_list, function(r) r$facet$cdf_beta)) 
    cdf_ind_all  <- bind_rows(lapply(res_list, function(r) r$facet$cdf_individual)) 
     
    samples_all  <- bind_rows(lapply(names(res_list), function(nm) { 
      tibble(Question = nm, samples = res_list[[nm]]$samples) 
    })) 
     
    cfg <- resolve_question_config(qs[1], hpp = suppressWarnings(as.numeric(df[[input$col_hpp]]))) 
    list( 
      summaries     = summary_all, 
      dens_mix_all  = dens_mix_all, 
      dens_ind_all  = dens_ind_all, 
      beta_all      = beta_all, 
      cdf_mix_all   = cdf_mix_all, 
      cdf_emp_all   = cdf_emp_all, 
      cdf_beta_all  = cdf_beta_all, 
      cdf_ind_all   = cdf_ind_all, 
      samples_all   = samples_all, 
      cfg           = cfg 
    ) 
  }, ignoreInit = TRUE) 
   
  # Single PNG downloads (use current selections in results())  
  output$download_participants_png <- downloadHandler( 
    filename = function() paste0("participants_raw_", Sys.Date(), ".png"), 
    content = function(file) { 
      req(raw_df(), input$col_id, input$col_lpp, input$col_bgp, input$col_hpp, input$question_sel) 
      g <- build_individuals_plot( 
        df_raw = raw_df(), 
        id_col = input$col_id, 
        lpp_col = input$col_lpp, 
        bgp_col = input$col_bgp, 
        hpp_col = input$col_hpp, 
        question_col = input$col_question, 
        note_col = input$col_note, 
        selected_questions = input$question_sel, 
        use_export_theme = TRUE, 
        theme_export = if (exists("theme_export")) theme_export else NULL, 
        facet_cols = 1 
      ) 
      ggsave(file, g, width = 8, height = 6, dpi = 1200, units='in', limitsize = FALSE) 
    } 
  ) 
   
  output$download_density_png <- downloadHandler( 
    filename = function() paste0("density_", Sys.Date(), ".png"), 
    content = function(file) { 
      req(results()) 
      r <- results() 
      facet_cols <- if (!is.null(input$facet_cols)) input$facet_cols else 4 
      g <- build_density_plot(r,  
                              show_individual = isTRUE(input$show_individual),  
                              facet_cols = facet_cols) 
      g_small <- g + theme_export  # <-- apply smaller export theme 
      ggsave(file, g_small, width = 8, height = 4, dpi = 1200, units='in', limitsize = FALSE) 
    } 
  ) 
   
  output$download_hist_png <- downloadHandler( 
    filename = function() paste0("histogram_", Sys.Date(), ".png"), 
    content = function(file) { 
      req(results()) 
      r <- results() 
      facet_cols <- if (!is.null(input$facet_cols)) input$facet_cols else 4 
      g <- build_hist_plot(r, facet_cols = facet_cols) 
      g_small <- g + theme_export  # smaller export theme 
     ggsave(file, g_small, width = 8, height = 4, dpi = 1200, units='in', limitsize = FALSE) 
    } 
  ) 
   
  output$download_cdf_png <- downloadHandler( 
    filename = function() paste0("cdf_", Sys.Date(), ".png"), 
    content = function(file) { 
      req(results()) 
      r <- results() 
      facet_cols <- if (!is.null(input$facet_cols)) input$facet_cols else 4 
      g <- build_cdf_plot(r, show_individual = isTRUE(input$show_individual),  
                          facet_cols = facet_cols) 
      g_small <- g + theme_export  # smaller export theme 
      ggsave(file, g_small, width = 8, height = 4, dpi = 1200, units='in', limitsize = FALSE) 
    } 
  ) 
   
  # ZIP files 
  output$download_all_plots_zip <- downloadHandler( 
    filename = function() paste0("elicitation_plots_", Sys.Date(), ".zip"), 
    content = function(file) { 
      req(results()) 
      r <- results() 
       
      # facet columns 
      facet_cols <- if (!is.null(input$facet_cols)) input$facet_cols else 4 
      show_ind   <- isTRUE(input$show_individual) 
       
      # Build plots 
      g1 <- build_density_plot(r, show_individual = show_ind, facet_cols = facet_cols) 
      g2 <- build_hist_plot(r, facet_cols = facet_cols) 
      g3 <- build_cdf_plot(r, show_individual = show_ind, facet_cols = facet_cols) 
      g4 <- build_individuals_plot( 
        df_raw            = raw_df(), 
        id_col            = input$col_id, 
        lpp_col           = input$col_lpp, 
        bgp_col           = input$col_bgp, 
        hpp_col           = input$col_hpp, 
        question_col      = input$col_question, 
        note_col          = input$col_note, 
        selected_questions= input$question_sel, 
        facet_cols        = 1, 
        use_export_theme  = TRUE, 
        theme_export      = if (exists("theme_export")) theme_export else NULL 
      ) 
       
      # Save all figures to a temp directory 
      outdir <- tempfile("plots_") 
      dir.create(outdir, showWarnings = FALSE) 
       
      f1 <- file.path(outdir, paste0("density_",   Sys.Date(), ".png")) 
      f2 <- file.path(outdir, paste0("histogram_", Sys.Date(), ".png")) 
      f3 <- file.path(outdir, paste0("cdf_",       Sys.Date(), ".png")) 
      f4 <- file.path(outdir, paste0("individuals_", Sys.Date(), ".png")) 
       
      ggsave(f1, g1, width = 8, height = 4, dpi = 1200, units = 'in', limitsize = FALSE) 
      ggsave(f2, g2, width = 8, height = 4, dpi = 1200, units = 'in', limitsize = FALSE) 
      ggsave(f3, g3, width = 8, height = 4, dpi = 1200, units = 'in', limitsize = FALSE) 
      ggsave(f4, g4, width = 8, height = 4, dpi = 1200, units = 'in', limitsize = FALSE) 
       
      # summary CSV 
      f_summary_csv <- file.path(outdir, paste0("summary_", Sys.Date(), ".csv")) 
      write_csv(r$summaries, f_summary_csv) 
       
      # Zip 
      oldwd <- setwd(outdir); on.exit(setwd(oldwd), add = TRUE) 
      zip(zipfile = file, files = basename(c(f1, f2, f3, f4,f_summary_csv))) 
    } 
  ) 
   
  output$plot_participants <- renderPlot({ 
    req(input$run, raw_df(), input$col_id, input$col_lpp, input$col_bgp, input$col_hpp) 
     
    build_individuals_plot( 
      df_raw = raw_df(), 
      id_col = input$col_id, 
      lpp_col = input$col_lpp, 
      bgp_col = input$col_bgp, 
      hpp_col = input$col_hpp, 
      question_col = input$col_question, 
      note_col = input$col_note, 
      selected_questions = input$question_sel, 
      facet_cols = 1 
    ) 
  }) 
   
  # Mixture density 
  output$plot_density <- renderPlot({ 
    req(results()) 
   
    build_density_plot( 
      r = results(), 
      show_individual = isTRUE(input$show_individual), 
      facet_cols = NULL    
    ) 
  }) 
   
  # Histogram + Beta fit 
  output$plot_hist <- renderPlot({ 
    req(results()) 
     
    build_hist_plot( 
      r = results(), 
      facet_cols = NULL    
    ) 
  }) 
   
  # CDF comparison  
  output$plot_cdf <- renderPlot({ 
    req(results()) 
     
    build_cdf_plot( 
      r = results(), 
      show_individual = isTRUE(input$show_individual), 
      facet_cols = NULL    
    ) 
  }) 
   
  # Summary table & download 
  output$summary_table <- renderTable({ 
    req(results()) 
    results()$summaries 
  }) 
  output$download_summary <- downloadHandler( 
filename = function() paste0("elicitation_summaries_", Sys.time(),".csv"), 
content = function(file) { 
req(results()) 
readr::write_csv(results()$summaries, file) 
} 
) 
} 
# shinyApp(ui, server) is called from app.R only (appendix listed it here too;
# sourcing both files would try to bind the HTTP port twice).
