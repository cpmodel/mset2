# FUNCTIONS Themes (themes.R)
# List of packages being used 
list.of.packages <- c('shiny', 'readr', 'dplyr', 'tidyr', 'purrr', 'ggplot2', 'scales') 
 
# Identify packages in the list that are not on the computer 
new.packages <- list.of.packages[!(list.of.packages %in% installed.packages()[,"Package"])] 
 
# Install packages in "new.packages" 
if(length(new.packages)) install.packages(new.packages); rm(list.of.packages); 
rm(new.packages) 
 
# packages 
suppressPackageStartupMessages({ 
  library(shiny) 
  library(readr) 
  library(dplyr) 
  library(tidyr) 
  library(purrr) 
  library(ggplot2) 
  library(scales) 
}) 
 
options(scipen=999) # Remove scientific notation 
 
#APP THEME (on-screen) 
theme_app <- theme_bw() + 
  theme(axis.title   = element_text(size=24, family="sans", colour="black"), 
        axis.text.x  = element_text(size=20, family="sans", colour="black"), 
        axis.text.y  = element_text(size=20, family="sans", colour="black"), 
        strip.text   = element_text(size=20, family="sans", colour="black"), 
        plot.title   = element_text(size=24, family="sans", colour="black"), 
        panel.border = element_rect(colour="black"), 
        legend.position = "none") 
 
# Apply it app-wide 
theme_set(theme_app) 
 
#EXPORT THEME (smaller text) 
theme_export <- theme_bw() + 
  theme(axis.title   = element_text(size=11,   family="sans", colour="black"), 
        axis.text.x  = element_text(size=10.5, angle=45, vjust=0.7, family="sans", 
colour="black"), 
        axis.text.y  = element_text(size=10.5, family="sans", colour="black"), 
        strip.text   = element_text(size=11,   family="sans", colour="black"), 
        plot.title   = element_text(size=11,   family="sans", colour="black"), 
        panel.border = element_rect(colour="black"), 
        legend.position = "none")