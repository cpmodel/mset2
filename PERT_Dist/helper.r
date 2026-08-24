# Helper function (helper.R)
# Choose a reasonable default for "Question" column if multiple exist 
best_question_col <- function(df) { 
cols <- names(df) 
cand <- grep("^question(\\.{3}\\d+)?$", tolower(cols), value = TRUE) 
if (length(cand) == 0) { 
cand <- grep("^q(uestion)?", tolower(cols), value = TRUE) 
} 
if (length(cand) <= 1) { 
return(ifelse(length(cand) == 1, cand, "<none>")) 
} 
# Prefer the one with most non-missing + unique values 
score <- sapply(cand, function(cc) { 
v <- df[[cc]] 
sum(!is.na(v)) + 0.001 * length(unique(na.omit(v))) 
}) 
cand[order(score, decreasing = TRUE)][1] 