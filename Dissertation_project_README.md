# Dissertation project repository

This repository supports the MSc dissertation of **Ben Mayer**, University of Exeter — *Global Sustainability Solutions*.

For enquiries, contact: [bm638@exeter.ac.uk](mailto:bm638@exeter.ac.uk)

---

## Overview

This repository is a working copy of the **mset2** (MINDSET) modelling codebase, forked from the upstream main branch and extended with materials developed for this dissertation. In addition to the core model and a graphic user interface, it includes tools and anonymised outputs related to an expert elicitation exercise.

For licensing and redistribution reasons, restricted model databases and large simulation result files are **not** included. Readers who wish to reproduce model runs will need to obtain the underlying data sources separately (see the READMEs under `Data/`) and run the model locally.

---

## MINDSET model (mset2)

The core modelling code is forked from the `mset2` main branch.

| Component | Location / notes |
|-----------|------------------|
| Graphic user interface | Based on a live pull request by Cormac Lynch (`GUI/`; launch with `run_frontend.py`) |
| Scenario assumption files | `Data/MSET_data/Scenarios/` (CVF and G77+C variants, plus the empty baseline scenario) |
| Model configuration | Root-level `.ini` files (for example `s_CVF_upper.ini`, `s_base.ini`) |

Within `Data/MSET_data/`, only the scenario workbooks are redistributed here. Other parameter and input files used in a full local installation are omitted. Folders such as `Data/GLORIA_db/` and `Data/Energy_db/` retain their upstream documentation but do not contain redistributable databases (see those folders’ README files for access and licensing information).

Bulk model outputs under `Results/` are likewise not included in this repository.

For general model setup and command-line use, see the project `README.md` and `CLAUDE.md`.

---

## PERT distribution Shiny app (`PERT_dist/`)

This folder contains the Shiny application published as Appendix 1 of Lamothe (2026), with local adaptations for this project.

| Path | Contents |
|------|----------|
| `App/`, `Data/`, `Functions/` | R code for the Shiny application |
| `q1a_results/`, `q2a_results/` | Saved plots and summary tables from the app |
| `PERT_data.csv` | Anonymised expert elicitation responses (participants coded as letters; no personal identifiers) |
| `README.md` | How to run the app, and a record of changes from the published appendix (prepared with support from Cursor AI) |

---

## Qualtrics survey scripts (`Elicitation_Javascript_code/`)

Custom JavaScript used in the Qualtrics expert-elicitation survey.

| Path | Contents |
|------|----------|
| `Qualtrics-JavaScript-reference.md` | Question-by-question summary of the scripts entered manually into Qualtrics. The scripts and this reference were produced with assistance from a Cursor AI agent. |

Raw Qualtrics response exports are not included in this repository.

---

## Supporting materials (`Supporting/`)

| File | Contents |
|------|----------|
| `MSET_results.xlsx` | Selected tables and figures exported from the MINDSET graphic user interface for use in the dissertation |

Interim quantitative workbooks used during analysis (including raw survey downloads) are not redistributed here.

---

## Attribution and tools

- MINDSET / mset2 core model: upstream project authors (MIT Licence; see `LICENSE`)
- GUI: Cormac Lynch (pull request)
- PERT Shiny application: Lamothe (2026), Open Government Licence – Canada; local adaptations documented in `PERT_dist/README.md`
- Qualtrics JavaScript and reference notes: developed with Cursor AI assistance
- PERT app documentation: prepared with support from Cursor AI
