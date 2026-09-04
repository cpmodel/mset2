# Dissertation project repository

This repository supports the MSc dissertation of **Ben Mayer**, University of Exeter — *Global Sustainability Solutions*.

For enquiries, contact: [bm638@exeter.ac.uk](mailto:bm638@exeter.ac.uk)

---

## Overview

The repository is a fork of the main **mset2** (MINDSET) codebase, extended with additional materials for this dissertation. Alongside the core model, it includes a graphic user interface, expert-elicitation tools, and supporting analysis.

---

## MINDSET model (mset2)

The core modelling code is forked from the `mset2` main branch.

| Addition | Description |
|----------|-------------|
| Graphic user interface | Based on a live pull request by Cormac Lynch (`GUI/`, launched with `run_frontend.py`) |
| Scenario files | Policy and scenario assumptions live in `Data/MSET_data/Scenarios/` |

For general model setup and command-line runs, see the project `README.md` and `CLAUDE.md`.

---

## PERT distribution Shiny app (`PERT_dist/`)

This folder contains the Shiny application code from Lamothe (2026).

| Path | Contents |
|------|----------|
| `App/`, `Data/`, `Functions/` | R code and supporting data for the Shiny application |
| `q1a_results/`, `q2a_results/` | Application results |
| `PERT_data.csv` | Expert elicitation data |
| `README.md` | How to run the app, and notes on changes from the original (prepared with support from Cursor AI) |

---

## Qualtrics survey scripts (`Elicitation_Javascript_code/`)

JavaScript used in the Qualtrics expert-elicitation survey.

| Path | Contents |
|------|----------|
| `Qualtrics-JavaScript-reference.md` | Question-by-question summary of the scripts entered manually into Qualtrics. The scripts and this reference were produced with a Cursor AI agent. |

---

## Supporting analysis (`Supporting/`)

Additional analysis and outputs used in the dissertation.

| File | Contents |
|------|----------|
| `Quantitative_analysis.xlsx` | Expert elicitation downloads, data cleaning, and interim PERT results, plus scenario-sheet templates with linked supporting calculations |
| `MSET_results.xlsx` | Tables and graphs exported from the MINDSET graphic user interface |

---

## Attribution and tools

- MINDSET / mset2 core model: upstream project authors  
- GUI: Cormac Lynch (pull request)  
- PERT Shiny application: Lamothe (2026), with local adaptations documented in `PERT_dist/README.md`  
- Qualtrics JavaScript and reference notes: developed with Cursor AI assistance  
- PERT app documentation: prepared with support from Cursor AI  
