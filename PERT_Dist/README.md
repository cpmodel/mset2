# PERT expert-elicitation Shiny app

This folder contains the R Shiny application published as **Appendix 1** of Lamothe (2026). It aggregates three-point expert judgements (lowest plausible, best guess, highest plausible) into individual PERT distributions and an equal-weight linear opinion pool.

## Source

Lamothe, K.A. 2026. *Implementing a Three-step Expert-elicitation Approach to Inform Ecological Decision-making.* Canadian Manuscript Report of Fisheries and Aquatic Sciences 3333: vii + 33 p.

- DOI: [https://doi.org/10.60825/b7sr-pv60](https://doi.org/10.60825/b7sr-pv60)
- Official PDF: [https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/41333263.pdf](https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/41333263.pdf)
- Licence: Open Government Licence – Canada (Crown copyright, Fisheries and Oceans Canada, 2026)

The appendix is eight R scripts in three groups:

| Group | File | Role |
|-------|------|------|
| Functions | `Functions/themes.R` | Package install/load and ggplot themes |
| Functions | `Functions/helper.R` | Default “Question” column detection |
| Functions | `Functions/plotting_functions.R` | Expert-score, density, histogram, and CDF plots |
| Functions | `Functions/summarize_pert.R` | Beta-PERT densities, linear pool, mixture samples, moment-matched Beta |
| Data | `Data/demo_data.R` | Built-in demo table (6 experts × 8 questions; paper Table S1) |
| Application | `App/UI.R` | Shiny user interface |
| Application | `App/server.R` | Shiny server logic |
| Application | `app.R` | Entry point that sources the scripts above |

PERT parameterisation follows the appendix (`λ = 5` by default):

```r
alpha = 1 + lambda * (m - a) / (b - a)
beta  = 1 + lambda * (b - m) / (b - a)
```

The evaluation grid and moment-matched Beta overlay follow the selected question: **[0, 1]** for `2a` and demo probability items, **[0, 600]** for `1a` (damages, $ billion).

## Changes from the published appendix

The statistical methods, UI, server logic, demo data, and `source()` paths in `app.R` are those of Appendix 1. Differences in this copy:

1. **Folder layout restored to the appendix design.** The scripts were added as a flat set of files in `PERT_Dist/`. They are now under `Functions/`, `Data/`, and `App/`, which is what `app.R` expects (`source("Functions/themes.R")`, and so on).
2. **Missing closing brace in `helper.R`.** PDF transcription left `best_question_col()` unclosed. A final `}` was added so the file parses. Behaviour is otherwise unchanged.
3. **`shinyApp(ui, server)` removed from the end of `App/server.R`.** The appendix printed that call in both `server.R` and `app.R`. Sourcing both files under `shiny::runApp()` bound port 3838 twice (`createTcpServer: address already in use`). The app is now started only from `app.R`.
4. **`PERT_data.csv` added (not part of the appendix).** Local elicitation responses for questions `1a` (damages, $ billion) and `2a` (scaling factor). Incomplete or excluded triples are flagged in `No_value_label`.
5. **Blank rows are kept on Expert Scores and dropped from the PERT pool.** Rows without a finite L < U triple (or with `No_value_label` set) are plotted as centred grey text (`Prefer not to quantify`, `Error in triples`, or the CSV label). They are excluded from mixture sampling so `rbeta()` is not called with missing parameters. `N_Participants` counts valid triples only.
6. **One question at a time.** The question control is a single-select dropdown; the appendix “All” option is removed.
7. **Expert Scores styling.** Participant letters A–N stay on the y-axis. Intervals, modes, and `[L, M, U]` labels are drawn in black (no per-expert colour). Axis labels and ranges follow the question (`1a` damages, `2a` scaling factor).
8. **PERT grid for non-probability quantities.** `summarize_question_pert()` takes `xmin`/`xmax` so `1a` densities are evaluated on $[0, 600]$ rather than $[0, 1]$. The dashed Beta overlay is moment-matched on that same interval.
9. **Overlay line styles.** On Expert Distributions, Mixture Histograms, and CDF Comparisons the pooled mixture is a **black dotted** line and the moment-matched Beta is a **black dashed** line, both at twice the original overlay thickness. The y-axis on density plots is labelled **Density**.
10. **Summary table has two rows** per question: moment-matched Beta, then mixture, using the same columns (mean, median, 5th, 95th, hard union, N, lambda, Nsim).

Filenames use `.R` as in the appendix. R on Windows treats `.r` / `.R` as the same.

## How to run

From this folder, with R on `PATH`:

```powershell
Rscript -e "shiny::runApp('.', host = '127.0.0.1', port = 3838, launch.browser = TRUE)"
```

`themes.R` installs missing CRAN packages on first run: `shiny`, `readr`, `dplyr`, `tidyr`, `purrr`, `ggplot2`, `scales`.

In the app: keep demo data or upload a CSV with columns `Question`, `Participant`, `Lowest_Plausible_Pr`, `Best_Guess_Pr`, `Highest_Plausible_Pr`, then click **Run / Refresh**.
