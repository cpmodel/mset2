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
}

is_valid_triple <- function(a, m, b) {
  is.finite(a) & is.finite(m) & is.finite(b) & (a <= m) & (m <= b) & (a < b)
}

blank_note <- function(note, a, m, b) {
  note <- trimws(as.character(note))
  note[is.na(note)] <- ""
  dplyr::if_else(
    is_valid_triple(a, m, b),
    NA_character_,
    dplyr::if_else(nzchar(note), note, "Error in triples")
  )
}