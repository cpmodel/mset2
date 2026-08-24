# PERT expert-elicitation Shiny app

This folder contains the R Shiny application published as **Appendix 1** of Lamothe (2026). It aggregates three-point expert judgements (lowest plausible, best guess, highest plausible) into individual PERT distributions and an equal-weight linear opinion pool.

## Source

Lamothe, K.A. 2026. *Implementing a Three-step Expert-elicitation Approach to Inform Ecological Decision-making.* Canadian Manuscript Report of Fisheries and Aquatic Sciences 3333: vii + 33 p.

- DOI: [https://doi.org/10.60825/b7sr-pv60](https://doi.org/10.60825/b7sr-pv60)
- Official PDF: [https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/41333263.pdf](https://waves-vagues.dfo-mpo.gc.ca/library-bibliotheque/41333263.pdf)
- Licence: Open Government Licence – Canada (Crown copyright, Fisheries and Oceans Canada, 2026)

PERT parameterisation follows the appendix (`λ = 5` by default):

```r
alpha = 1 + lambda * (m - a) / (b - a)
beta  = 1 + lambda * (b - m) / (b - a)
```

The evaluation grid and moment-matched Beta overlay follow the selected question: **[0, 1]** for `2a` (and demo probability items), **[0, 600]** for `1a` (damages, $ billion).

## Folder contents

Appendix scripts (eight files in three groups), plus local additions:

| Group | File | Role |
|-------|------|------|
| Functions | `Functions/themes.R` | Package install/load and ggplot themes |
| Functions | `Functions/helper.R` | Question-column detection; valid-triple / blank-label helpers |
| Functions | `Functions/question_config.R` | Per-question axis ranges and labels (`1a`, `2a`) — **not in the appendix** |
| Functions | `Functions/plotting_functions.R` | Expert-score, density, histogram, and CDF plots |
| Functions | `Functions/summarize_pert.R` | Beta-PERT densities, linear pool, mixture samples, moment-matched Beta |
| Data | `Data/demo_data.R` | Built-in demo table (6 experts × 8 questions; paper Table S1) |
| Data | `PERT_data.csv` | Local elicitation CSV (`1a` / `2a`) — **not in the appendix** |
| Application | `App/UI.R` | Shiny user interface |
| Application | `App/server.R` | Shiny server logic |
| Application | `app.R` | Entry point that sources the scripts above |
| Results | `q1a_results/` | Saved outputs for question **1a** (damages) |
| Results | `q2a_results/` | Saved outputs for question **2a** (scaling factor) |

Filenames use `.R` as in the appendix. R on Windows treats `.r` / `.R` as the same.

## Results folders

Run outputs are stored in their own folders rather than mixed with the source scripts:

- `q1a_results/` — question 1a (total financially assessable damage from climate change, $ billion)
- `q2a_results/` — question 2a (scaling factor *s*)

Each folder currently holds:

| File | Content |
|------|---------|
| `individuals_YYYY-MM-DD.png` | Expert Scores (A–N intervals, blank-row labels) |
| `density_YYYY-MM-DD.png` | Expert Distributions (individual PERTs + mixture + Beta) |
| `histogram_YYYY-MM-DD.png` | Mixture histogram with overlays |
| `cdf_YYYY-MM-DD.png` | CDF comparison |
| `summary_YYYY-MM-DD.csv` | Two-row summary (moment-matched Beta, then mixture) |

These files come from the app’s PNG / ZIP / summary downloads after a run of `PERT_data.csv`.

## Changes from the published appendix

The core PERT maths, linear pool, demo data, and `app.R` `source()` paths are those of Appendix 1. Differences in this copy:

1. **Folder layout restored to the appendix design.** Scripts were first added as a flat set of files; they now sit under `Functions/`, `Data/`, and `App/`, which is what `app.R` expects.
2. **Missing closing brace in `helper.R`.** PDF transcription left `best_question_col()` unclosed. A final `}` was added so the file parses.
3. **`shinyApp(ui, server)` removed from the end of `App/server.R`.** The appendix listed that call in both `server.R` and `app.R`. Sourcing both under `shiny::runApp()` bound the HTTP port twice. The app is started only from `app.R`.
4. **`PERT_data.csv` added.** Local elicitation responses for `1a` and `2a`. Incomplete or excluded triples are flagged in `No_value_label`.
5. **Blank rows** stay on Expert Scores as centred grey text (`Prefer not to quantify`, `Error in triples`, or the CSV label) and are dropped from the PERT pool. `N_Participants` counts valid triples only.
6. **One question at a time.** The question control is a single-select dropdown; the appendix “All” option is removed.
7. **Expert Scores styling.** Participant letters A–N remain on the y-axis. Intervals, modes, and `[L, M, U]` labels are black (no per-expert colour). Axis labels and ranges follow the question.
8. **PERT grid for non-probability quantities.** `summarize_question_pert()` takes `xmin`/`xmax` so `1a` is evaluated on $[0, 600]$. The Beta overlay is moment-matched on that interval.
9. **Overlay line styles.** On Expert Distributions, Mixture Histograms, and CDF Comparisons the pooled mixture is a **black dotted** line and the moment-matched Beta is a **black dashed** line, both at twice the original overlay thickness. Density plots use the y-label **Density**.
10. **Summary table has two rows** per question: moment-matched Beta, then mixture, with the same columns (mean, median, 5th, 95th, hard union, N, lambda, Nsim).
11. **Results stored in their own folders.** Exports for each question are kept in `q1a_results/` and `q2a_results/` (see above), separate from the R source.

## How to run

From this folder, with R on `PATH`:

```powershell
Rscript -e "shiny::runApp('.', host = '127.0.0.1', port = 3838, launch.browser = TRUE)"
```

`themes.R` installs missing CRAN packages on first run: `shiny`, `readr`, `dplyr`, `tidyr`, `purrr`, `ggplot2`, `scales`.

In the app: uncheck demo data, upload `PERT_data.csv` (columns `Question`, `Participant`, `Lowest_Plausible_Pr`, `Best_Guess_Pr`, `Highest_Plausible_Pr`, and optionally `No_value_label`), choose **1a** or **2a**, then click **Run / Refresh**. Save plots and the summary CSV into the matching `q1a_results/` or `q2a_results/` folder.
