# Energy_IO: CEFIO technology matrices for the FTT:Power coupling

Technology-specific input and labour coefficients for electricity generation, used by
`ftt_power_io_mode = tech_matrix` (`SourceCode/ftt_power.py`). Built from **Liang et al. (2023),
*2018 Chinese Electricity-focused Input-Output Table* (CEFIO), 166 x 166, producer prices, with 12
electricity technologies (S100-S111)**. Data: https://doi.org/10.6084/m9.figshare.20456868 (CC BY 4.0).

## Layout

```
Energy_IO/
  A_elec_MSET_FTT_12.csv         outputs (read by the model)
  L_elec_MSET_FTT_12.csv
  src/
    build_energy_io.py           the only script
    a_cefio_sector_to_GLORIA.csv crosswalks (reviewed by hand)
    b_cefio_tech_to_MSET_FTT_12.csv
    README.md                    this file
    2018CEFIO_166.xlsx           raw table, downloaded on first run (gitignored)
```

## Rebuild

```
python Data/MSET_data/Energy_IO/src/build_energy_io.py            # proportional split (default)
python Data/MSET_data/Energy_IO/src/build_energy_io.py --even-split
```

Options: `--raw FILE` (raw xlsx), `--weights FILE` (default `Data/GLORIA_db/IND_sparse.pkl`),
`--debug` (also writes the native 120 x 12 matrices and the weights to `src/debug/`).
If `src/2018CEFIO_166.xlsx` is missing it is downloaded from figshare and checked against the
published MD5; the sheet layout is read by position, so any other version is rejected.

## Outputs

- `A_elec_MSET_FTT_12.csv`: rows = GLORIA commodity 1-120, columns = the 12 MSET-FTT technologies. `a[g, k]` = purchases of commodity `g` per unit of gross output of technology `k`
  (CEFIO value units cancel). Column sums are 1 minus the value-added share (0.08 hydro to 0.73).
- `L_elec_MSET_FTT_12.csv`: one column `labour_intensity` = VA001 (labour compensation) / gross output.
- There is no 22-technology (FTT_StandAlone) version; add a crosswalk and a second target in
  `build_energy_io.py` if a 22-technology run needs one.

## Method

1. Take the 12 technology columns S100-S111 of the 166 x 166 flow table.
2. Distribute each supplying CEFIO sector's flow over its GLORIA code(s) (crosswalk `a`, column
   `GLORIA_code_or_range`: a code `50`, a range `16-20`, or a list `73,76`). A range is **split in
   proportion to the purchases of GLORIA sector 93 (electricity)** of each code, summed over all
   regions in the MSET base year: if sector 93 buys 8 wheat and 2 spices out of 10, the split is
   80/20. If sector 93 buys none of the codes in a range, the split is even and a warning is printed.
   `--even-split` gives the previous rule (1/n each).
3. Sum flows landing on the same GLORIA code; divide by each technology's gross output.
4. Roll up to the 12 MSET-FTT technologies (crosswalk `b`): sum flows and gross output over the
   CEFIO technologies sharing a target, then recompute the coefficient (never average coefficients).
   The catch-all technologies S106 and S111 are broadcast unchanged to every target they stand in
   for (one real CEFIO recipe behind several targets).
