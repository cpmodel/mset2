"""
Build the FTT:Power <-> MSET technology IO matrices from Liang et al. (2023) CEFIO.

Outputs, written to the folder above src/ (Data/MSET_data/Energy_IO/):
    A_elec_MSET_FTT_12.csv            120 GLORIA commodities x 12 MSET-FTT technologies (input coefficients)
    L_elec_MSET_FTT_12.csv            labour intensity per MSET-FTT technology

Method (see README.md in this folder):
  1. Read the raw 166x166 CEFIO table; take the 12 electricity technology columns S100-S111.
  2. Distribute each supplying CEFIO sector's flow over its GLORIA code(s) (crosswalk a). A range
     such as 1-15 is split in proportion to what GLORIA sector 93 buys of each code (default), or
     evenly with --even-split.
  3. A = flow / technology gross output;  L = VA001 (labour compensation) / gross output.
  4. Roll up to the 12 MSET-FTT technologies (crosswalk b): sum flows and gross output over the
     CEFIO technologies sharing a target, then recompute the coefficient. Catch-all S106 / S111
     recipes are broadcast unchanged to every target they stand in for.

The raw table is read from src/2018CEFIO_166.xlsx and downloaded from figshare
(https://doi.org/10.6084/m9.figshare.20456868, CC BY 4.0) if missing, then checked against the
published MD5.

    python Data/MSET_data/Energy_IO/src/build_energy_io.py [--even-split] [--raw FILE]
                                                           [--weights IND_sparse.pkl] [--debug]
"""
import argparse
import hashlib
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent
REPO = HERE.parents[3]

RAW_URL = "https://ndownloader.figshare.com/files/41151335"
RAW_MD5 = "bdc8063fc16935ff5bd7a12bf2438acd"
RAW_NAME = "2018CEFIO_166.xlsx"

TECH_COLS = [f"S{n}" for n in range(100, 112)]  # S100..S111
GO_COL = 181                                    # "Gross Output" column of the raw sheet
N_GLORIA = 120
TARGET_TAG = "MSET_FTT_12"
TARGET_CROSSWALK = HERE / "b_cefio_tech_to_MSET_FTT_12.csv"
TARGET_COL = "MSET_FTT_12_tech"


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get_raw(path):
    """Return the raw CEFIO xlsx, downloading it (and verifying the MD5) if it is not there."""
    path = Path(path)
    if not path.exists():
        print(f"{path} not found, downloading {RAW_URL}")
        tmp = path.with_suffix(".part")
        try:
            req = urllib.request.Request(RAW_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                f.write(r.read())
        except Exception as e:
            tmp.unlink(missing_ok=True)
            sys.exit(f"Download failed ({e}). Get {RAW_NAME} from https://doi.org/10.6084/m9.figshare.20456868 "
                     f"and place it at {path}.")
        tmp.replace(path)
    if md5(path) != RAW_MD5:
        sys.exit(f"{path} does not match the expected MD5 {RAW_MD5} (the sheet layout is read by position); "
                 f"delete it to re-download.")
    return path


def read_cefio(raw):
    """Return (Z, GO, VA001): Z is 166 x 12 (supplying CEFIO sector x technology), indexed by S-code."""
    df = pd.read_excel(raw, sheet_name="EN_Version", header=None)
    row_codes = {v: i for i, v in enumerate(df.iloc[:, 2]) if isinstance(v, str) and re.match(r"^S\d{3}$", v)}
    col_codes = {v: j for j, v in enumerate(df.iloc[5, :]) if isinstance(v, str) and re.match(r"^S\d{3}$", v)}
    assert len(row_codes) == 166 and len(col_codes) == 166
    Z = pd.DataFrame({t: [df.iat[ri, col_codes[t]] for ri in row_codes.values()] for t in TECH_COLS},
                     index=list(row_codes)).fillna(0.0).astype(float)
    GO = pd.Series({t: df.iat[row_codes[t], GO_COL] for t in TECH_COLS}, dtype=float)
    va_row = max(row_codes.values()) + 2  # +1 = TII, +2 = VA001 (labour compensation)
    VA = pd.Series({t: 0.0 if pd.isna(df.iat[va_row, col_codes[t]]) else df.iat[va_row, col_codes[t]]
                    for t in TECH_COLS}, dtype=float)
    return Z, GO, VA


def expand(spec):
    """'50' -> [50]; '16-20' -> [16..20]; '73,76' -> [73, 76]; '1-3,5' -> [1, 2, 3, 5]."""
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            out += range(int(lo), int(hi) + 1)
        else:
            out.append(int(part))
    return out


def sector93_weights(path):
    """Purchases of each GLORIA commodity by sector 93, summed over all buyer/supplier regions."""
    z = pd.read_pickle(path)["z_bp"].reset_index()
    z = z[z["PROD_COMM"].astype(int) == 93]
    return z.groupby(z["TRAD_COMM"].astype(int))["z_bp"].sum().reindex(range(1, N_GLORIA + 1), fill_value=0.0)


def to_gloria(Z, crosswalk_a, weights):
    """166 x 12 CEFIO flows -> 120 x 12 GLORIA flows. weights=None means an even split."""
    cw = pd.read_csv(crosswalk_a).set_index("CEFIO_S_code")
    missing = set(Z.index) - set(cw.index)
    if missing:
        sys.exit(f"Crosswalk a is missing rows for: {sorted(missing)}")
    A = pd.DataFrame(0.0, index=range(1, N_GLORIA + 1), columns=Z.columns)
    for code, row in Z.iterrows():
        codes = expand(cw.at[code, "GLORIA_code_or_range"])
        if weights is not None and len(codes) > 1:
            w = weights.loc[codes].to_numpy()
            if w.sum() > 0:
                share = w / w.sum()
            else:
                print(f"warning: sector 93 buys none of GLORIA {codes} (CEFIO {code}); using an even split")
                share = np.full(len(codes), 1 / len(codes))
        else:
            share = np.full(len(codes), 1 / len(codes))
        for g, s in zip(codes, share):
            A.loc[g] += row.to_numpy() * s
    A.index.name = "GLORIA_code"
    return A


def roll_up(crosswalk, target_col, *quantities):
    """Sum each quantity (DataFrame/Series with CEFIO tech labels along the last axis) over the CEFIO
    technologies mapped to each target, once per (CEFIO tech, target) pair."""
    cw = crosswalk.drop_duplicates(["CEFIO_S_code", target_col])
    targets = sorted(cw[target_col].unique(), key=lambda s: int(str(s).split()[0]))
    outs = []
    for q in quantities:
        if isinstance(q, pd.DataFrame):
            o = pd.DataFrame(0.0, index=q.index, columns=targets)
            for _, r in cw.iterrows():
                o[r[target_col]] += q[r["CEFIO_S_code"]]
        else:
            o = pd.Series(0.0, index=targets)
            for _, r in cw.iterrows():
                o[r[target_col]] += q[r["CEFIO_S_code"]]
        outs.append(o)
    return outs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=HERE / RAW_NAME, help="raw CEFIO xlsx (downloaded if missing)")
    ap.add_argument("--weights", default=REPO / "Data" / "GLORIA_db" / "IND_sparse.pkl",
                    help="MSET intermediate-flow table giving sector 93's purchases")
    ap.add_argument("--even-split", action="store_true", help="split code ranges evenly instead")
    ap.add_argument("--debug", action="store_true", help="also write the native 120 x 12 matrices and weights to src/debug/")
    args = ap.parse_args()

    Z, GO, VA = read_cefio(get_raw(args.raw))

    weights = None
    if not args.even_split:
        if not Path(args.weights).exists():
            sys.exit(f"{args.weights} not found; pass --weights, or --even-split to skip the weighting.")
        weights = sector93_weights(args.weights)
    A_flow = to_gloria(Z, HERE / "a_cefio_sector_to_GLORIA.csv", weights)

    cw = pd.read_csv(TARGET_CROSSWALK)
    flows, go, va = roll_up(cw, TARGET_COL, A_flow, GO, VA)
    A = flows.div(go)
    A.index.name = "GLORIA_code"
    L = (va / go).rename("labour_intensity")
    A.to_csv(OUT_DIR / f"A_elec_{TARGET_TAG}.csv")
    L.to_csv(OUT_DIR / f"L_elec_{TARGET_TAG}.csv")
    print(f"{TARGET_TAG}: A column sums (1 - value-added share) {A.sum().min():.3f}-{A.sum().max():.3f}")

    if args.debug:
        d = HERE / "debug"
        d.mkdir(exist_ok=True)
        A_flow.to_csv(d / "A_flow_120xtech_10kYuan.csv")
        A_flow.div(GO).to_csv(d / "A_coef_120xtech.csv")
        (weights if weights is not None else pd.Series(dtype=float)).to_csv(d / "sector93_weights.csv")


if __name__ == "__main__":
    main()
