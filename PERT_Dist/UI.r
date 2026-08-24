# User interface (UI.R)
ui <- fluidPage( 
  titlePanel("Expert Elicitation Application"), 
  sidebarLayout( 
    sidebarPanel( 
      fileInput("file", "Upload CSV", accept = c(".csv")), 
      checkboxInput("use_demo", "Use demo data instead of upload", value = TRUE), 
      tags$hr(), 
      uiOutput("colmap_ui"), 
      numericInput("lambda", "PERT shape (lambda)", value = 5, min = 1, step = 1), 
      numericInput("Nsim", "Mixture draws", value = 10000, min = 1000, step = 1000), 
      uiOutput("question_filter_ui"),  # multi-select 
      checkboxInput("show_individual", "Show individual curves in overlays", TRUE), 
      actionButton("run", "Run / Refresh", class = "btn-primary"), 
      tags$hr(), 
      downloadButton("download_summary", "Download Summary CSV"), 
      tags$hr(), 
      h4("Download plots"), 
      downloadButton("download_participants_png",  "Expert Scores (PNG)"), 
      downloadButton("download_density_png",  "Expert Distributions (PNG)"), 
      downloadButton("download_hist_png",     "Mixture Histograms (PNG)"), 
      downloadButton("download_cdf_png",      "CDFs (PNG)"), 
      br(), br(), 
      downloadButton("download_all_plots_zip","All Summaries (ZIP)") 
    ), 
    mainPanel( 
      tabsetPanel( 
        tabPanel("Expert Scores", plotOutput("plot_participants", height = "600px")), 
        tabPanel("Expert Distributions", plotOutput("plot_density", height = "600px")), 
        tabPanel("Mixture Histograms", plotOutput("plot_hist", height = "600px")), 
        tabPanel("CDF Comparisons", plotOutput("plot_cdf", height = "600px")), 
        tabPanel("Summary Table", div(style = "font-size: 20px;",  
                                      tableOutput("summary_table")), 
                 helpText("Summaries are for the equal-weight mixture of participant PERT 
distributions (hard bounds with mode at BGP).")) 
      ) 
    ) 
  ) 
) 