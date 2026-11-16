# -*- coding: utf-8 -*-
"""
Builds the synthetic data set used by tests/test_integration.py.

The tests need the full model dimensions (120 sectors x 10 regions, as sector ids such as electricity = 93 are
hard-coded and FTT:Power needs the 10 regions), but the real input data must not be redistributed. This script reads
the real ``Data/`` folder (not in the repository) and writes ``tests/pseudo_data/Data``, in which every numeric value
is perturbed with seeded multiplicative lognormal noise:

  * final demand and the input-output coefficients are perturbed first. The resulting output is then solved
    (q = (I - A)^-1 y), and every level variable (output, value added, capital, labour, projections ...) is scaled with
    the same per-(region, sector) factor, namely perturbed output / real output. Labour, value added and capital
    per unit of output therefore stay as in the real data, and output equals L.y as the model expects;
  * investment demand (dk_base x converter) is kept in the real proportion to capital-formation final demand;
  * energy flows get additional independent noise per entry;
  * parameters, rates and shares get small noise, and ratio matrices are re-normalised. Time series (population,
    participation ...) get one factor per series, so growth rates are unchanged;
  * the tiniest intermediate flows are dropped to keep the repository small.

The result is not a measurement of anything. It only has to have the right shape and to keep the model numerically
well behaved. Region identifiers are replaced with fictional place names; other classification lists and the empty
scenario are copied as they are.

Usage (from the repo root, with the full Data/ present):  python tests/generate_pseudo_data.py
"""

import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from synthetic_regions import (
    REGION_COLUMNS,
    REGION_RENAMES,
    rename_frame_regions,
    rename_region_lookup,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "Data"
OUT = Path(__file__).parent / "pseudo_data" / "Data"

SEED = 20240601
LEVEL_SIGMA = 0.7      # noise on final demand per (region, sector); the level factors of all other data follow from it
ENTRY_SIGMA = 0.8      # independent noise on IO coefficients, final demand, energy flows
PARAM_SIGMA = 0.25     # parameters, elasticities
RATE_SIGMA = 0.15      # rates, shares, population
MIN_Z_BP = 3000.0      # intermediate flows below this are dropped
DROP_PROB = 0.0        # share of the remaining small intermediate flows dropped at random
MAX_A_COLSUM = 0.9     # keep the technical-coefficient columns well below 1
ALIGN_PASSES = 3       # iterations to make investment demand and capital-formation demand consistent

FINAL_DEMAND = {"HH": "VIPA", "GOV": "VIGA", "FCF": "VDFA", "INV": "INV", "NPISH": "NPISH"}

ID_COLUMNS = {
    "REG_imp", "REG_exp", "PROD_COMM", "TRAD_COMM", "year", "Unnamed: 0", "Lfd_Nr_agg", "Agg_region",
    "target-country-iso3", "origin-country-iso3", "target-sector", "origin-sector", "Nr_Input", "Nr_Ind",
    "GLORIA_Ind", "GLORIA_Input", "inv_good",
}
SKIP_FILES = {".mat", ".gitignore", "README.md", "Minimal_wage.xlsx"}
COPY_AS_IS = {".xlsx", ".pkl"}


class Perturber:
    def __init__(self):
        self.rng = np.random.default_rng(SEED)
        regions = pd.read_pickle(SRC / "GLORIA_db" / "cid.pkl")
        sectors = pd.read_pickle(SRC / "GLORIA_db" / "sid.pkl")
        index = pd.MultiIndex.from_product([regions, [str(int(s)) for s in sectors]], names=["REG_imp", "PROD_COMM"])
        self.level = pd.Series(self.noise(len(index), LEVEL_SIGMA), index=index)

    def positions(self, reg, sec):
        """Row of each (region, sector) pair in the 1200-long MRIO vectors (-1 if unknown)."""
        sec = pd.to_numeric(pd.Series(np.asarray(sec)), errors="coerce").astype("Int64").astype(str).to_numpy()
        return self.level.index.get_indexer(pd.MultiIndex.from_arrays([np.asarray(reg), sec]))

    def noise(self, n, sigma):
        return self.rng.lognormal(-sigma ** 2 / 2, sigma, n)

    def level_factor(self, df, reg_col="REG_imp", sec_col="PROD_COMM"):
        """Level noise factor for each row of df; region and sector may be columns or index levels."""
        get = lambda c: df[c] if c in df.columns else df.index.get_level_values(c)
        sectors = pd.to_numeric(pd.Series(np.asarray(get(sec_col))), errors="coerce").astype("Int64").astype(str)
        keys = pd.MultiIndex.from_arrays([np.asarray(get(reg_col)), sectors.to_numpy()])
        return self.level.reindex(keys).fillna(1.0).to_numpy()

    @staticmethod
    def value_columns(df):
        return [c for c in df.columns
                if c not in ID_COLUMNS and not str(c).startswith("##") and pd.api.types.is_numeric_dtype(df[c])]

    def rate_noise(self, df, cols, sigma):
        """One noise factor per series, shared across years, so year-on-year ratios (growth rates) are preserved."""
        if "year" in df.columns:
            ids = [c for c in df.columns if c not in cols and c != "year"]
            group = df.groupby(ids, sort=False).ngroup().to_numpy()
            return self.noise(group.max() + 1, sigma)[group]
        return self.noise(len(df), sigma)

    def scale(self, df, cols, sigma, level=False, entry=False, shared=False):
        shared_factor = self.rate_noise(df, cols, sigma) if shared else None
        for c in cols:
            if shared:
                df[c] = df[c].astype(float) * shared_factor
                continue
            factor = np.ones(len(df))
            if level:
                factor = factor * self.level_factor(df)
            if entry:
                factor = factor * self.noise(len(df), sigma)
            elif not level:
                factor = factor * self.noise(len(df), sigma)
            df[c] = df[c].astype(float) * factor
        return df


def perturb_csv(p, path):
    df = pd.read_csv(path)
    name = path.name
    cols = p.value_columns(df)
    if name == "Inv_conversion.csv":
        vals = df.iloc[:, 1:].astype(float)
        vals = vals * p.noise(vals.size, PARAM_SIGMA).reshape(vals.shape) * (vals > 0)
        df.iloc[:, 1:] = vals / vals.sum().replace(0, 1)
    elif name == "full_gloria_criticality.csv":
        df["Criticality"] = (df["Criticality"] * p.noise(len(df), PARAM_SIGMA)).clip(0, 1)
    elif {"REG_imp", "PROD_COMM"} <= set(df.columns) and name not in ("parameters.csv", "cost_curves.csv"):
        if name in ("ALL_FUELS.csv",):
            p.scale(df, cols, ENTRY_SIGMA, level=True, entry=True)
        else:
            p.scale(df, cols, LEVEL_SIGMA, level=True)
    elif name == "ALL_POLLUTANTS.csv":
        p.scale(df, ["POLLUTANT_VALUE"], ENTRY_SIGMA)
    elif name == "ALL_PROCESS_EMISSIONS.csv":
        p.scale(df, ["EF_ktCO2_per_kUSD"], PARAM_SIGMA)
        p.scale(df, ["Y_2019", "output_kUSD"], LEVEL_SIGMA)
    elif name in ("parameters.csv", "cost_curves.csv"):
        p.scale(df, cols, PARAM_SIGMA)
    else:
        p.scale(df, cols, RATE_SIGMA, shared=True)
        if name == "labour_force_participation.csv":
            df[cols] = df[cols].clip(upper=100.0)
        elif name == "Unemployment_rates_initial.csv":
            df[cols] = df[cols].clip(upper=1.0)
    return df


def noisy_ind_sparse(p, ind):
    """Thin out and perturb the intermediate-flow coefficients.

    Each buyer keeps its real intermediate-input share (column sum of a_bp), which preserves its value-added share
    and keeps the multipliers realistic. Output and z_bp are filled in later by write_ind_sparse.
    """
    target_colsum = ind.groupby(level=["REG_imp", "PROD_COMM"])["a_bp"].sum().clip(upper=MAX_A_COLSUM)
    ind = ind[ind["z_bp"] >= MIN_Z_BP].copy()
    # randomly thin out the small flows, so the trade structure differs too; the large (diagonal-type) flows stay
    drop = (p.rng.random(len(ind)) < DROP_PROB) & (ind["a_bp"].to_numpy() < 0.02)
    ind = ind[~drop].copy()
    ind["a_bp"] = ind["a_bp"] * p.noise(len(ind), ENTRY_SIGMA)

    colsum = ind.groupby(level=["REG_imp", "PROD_COMM"])["a_bp"].transform("sum")
    keys = ind.index.droplevel(["REG_exp", "TRAD_COMM"])
    ind["a_bp"] = ind["a_bp"] * (target_colsum.reindex(keys).to_numpy() / colsum).fillna(1.0)
    return ind


def write_ind_sparse(p, ind, output):
    """Fill in the buyer's output and the flows z_bp = a_bp x output, so that they are consistent with a_bp."""
    ind = ind.copy()
    buyer = p.positions(ind.index.get_level_values("REG_imp"), ind.index.get_level_values("PROD_COMM"))
    ind["output"] = output[buyer]
    ind["z_bp"] = ind["a_bp"] * ind["output"]
    # a_tech is the coefficient summed over supplying regions (as in model_class)
    ind["a_tech"] = ind.groupby(level=["REG_imp", "TRAD_COMM", "PROD_COMM"])["a_bp"].transform("sum")
    return ind


def perturb_final_demand(p, df):
    """Scale with the supplying (region, commodity), plus entry noise."""
    df = df.copy()
    factor = p.level_factor(df, "REG_exp", "TRAD_COMM") * p.noise(len(df), ENTRY_SIGMA)
    df[df.columns] = df.to_numpy(dtype=float) * factor[:, None]
    # inventory-type demand can be negative in the source; keep the synthetic demand non-negative
    df[df.columns] = df.clip(lower=0.0)
    return df


def perturb_pickle(p, df):
    if isinstance(df, pd.DataFrame) and {"REG_imp", "PROD_COMM"} <= set(df.columns):
        df = df.copy()
        return p.scale(df, p.value_columns(df), LEVEL_SIGMA, level=True)
    return df


def final_demand_vector(p, fd):
    y = np.zeros(len(p.level))
    for name, col in FINAL_DEMAND.items():
        df = fd[name]
        supplier = p.positions(df.index.get_level_values("REG_exp"), df.index.get_level_values("TRAD_COMM"))
        assert (supplier >= 0).all()
        np.add.at(y, supplier, df[col].to_numpy(dtype=float))
    return y


def solve_output(p, ind, fd, real_output):
    """Output implied by the perturbed coefficients and demand, and its ratio to the real output."""
    n = len(p.level)
    A = np.zeros((n, n))
    seller = p.positions(ind.index.get_level_values("REG_exp"), ind.index.get_level_values("TRAD_COMM"))
    buyer = p.positions(ind.index.get_level_values("REG_imp"), ind.index.get_level_values("PROD_COMM"))
    np.add.at(A, (seller, buyer), ind["a_bp"].to_numpy())
    q = np.linalg.solve(np.eye(n) - A, final_demand_vector(p, fd))
    usable = (real_output > 0) & (q > 0)
    return q, np.where(usable, q / np.where(real_output > 0, real_output, 1.0), 1.0)


def implied_investment_demand(dk, conv):
    """Investment demand per (REG_imp, TRAD_COMM) implied by dk_base and the investment converter."""
    conv = conv.set_index("inv_good")
    conv.columns = conv.columns.astype(int)
    table = dk.pivot(index="REG_imp", columns="PROD_COMM", values="VDFA").reindex(columns=conv.columns).fillna(0.0)
    implied = pd.DataFrame(table.to_numpy() @ conv.to_numpy().T, index=table.index, columns=conv.index.astype(int))
    implied = implied.stack()
    implied.index.names = ["REG_imp", "TRAD_COMM"]
    return implied


def fcf_totals(fcf):
    total = fcf.groupby(level=["REG_imp", "TRAD_COMM"])["VDFA"].sum()
    total.index = total.index.set_levels(total.index.levels[1].astype(int), level=1)
    return total


def make_consistent(p):
    """Perturb final demand and coefficients, then derive the level factors from the resulting output.

    Investment demand (dk_base x converter) is also aligned with capital-formation final demand: it is kept in the
    real proportion, since a supplier would otherwise be asked to lose several times its output after an investment
    cut. The level factors depend on demand and vice versa, hence a few passes.
    """
    gloria = SRC / "GLORIA_db"
    investment = SRC / "MSET_data" / "Investment"
    real_ind = pd.read_pickle(gloria / "IND_sparse.pkl")
    real_output = np.zeros(len(p.level))
    buyer = p.positions(real_ind.index.get_level_values("REG_imp"), real_ind.index.get_level_values("PROD_COMM"))
    real_output[buyer] = real_ind["output"].to_numpy()

    ind = noisy_ind_sparse(p, real_ind)
    fd = {name: perturb_final_demand(p, pd.read_pickle(gloria / f"{name}.pkl")) for name in FINAL_DEMAND}
    conv = perturb_csv(p, investment / "Inv_conversion.csv")

    dk_real = pd.read_csv(investment / "dk_investment_data_2016-2019_gloria_v57.csv")
    dk_real = dk_real[dk_real["year"] == dk_real["year"].min()]
    real_ratio = (implied_investment_demand(dk_real, pd.read_csv(investment / "Inv_conversion.csv"))
                  / fcf_totals(pd.read_pickle(gloria / "FCF.pkl")))

    for _ in range(ALIGN_PASSES):
        _, factor = solve_output(p, ind, fd, real_output)
        p.level = pd.Series(factor, index=p.level.index)
        dk = dk_real.assign(VDFA=dk_real["VDFA"].to_numpy() * p.level_factor(dk_real))
        target = implied_investment_demand(dk, conv) / real_ratio
        rescale = (target / fcf_totals(fd["FCF"])).replace([np.inf, -np.inf], np.nan)
        rescale = rescale.where(real_ratio > 0).fillna(1.0)
        keys = pd.MultiIndex.from_arrays([fd["FCF"].index.get_level_values("REG_imp"),
                                          fd["FCF"].index.get_level_values("TRAD_COMM").astype(int)])
        fd["FCF"]["VDFA"] = fd["FCF"]["VDFA"].to_numpy() * rescale.reindex(keys).fillna(1.0).to_numpy()

    output, factor = solve_output(p, ind, fd, real_output)
    p.level = pd.Series(factor, index=p.level.index)
    return {"ind": ind, "fd": fd, "conv": conv, "output": output}


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    p = Perturber()
    made = make_consistent(p)

    for path in sorted(SRC.rglob("*")):
        if not path.is_file() or path.suffix == ".mat" or path.name in SKIP_FILES:
            continue
        if path.parent.name == "Scenarios" and path.name != "empty.xlsx":
            continue
        target = OUT / path.relative_to(SRC)
        target.parent.mkdir(parents=True, exist_ok=True)

        if path.suffix == ".csv":
            df = made["conv"] if path.name == "Inv_conversion.csv" else perturb_csv(p, path)
            df.to_csv(target, index=False)
        elif path.suffix == ".pkl":
            obj = pd.read_pickle(path)
            if path.name == "IND_sparse.pkl":
                write_ind_sparse(p, made["ind"], made["output"]).to_pickle(target)
            elif path.parent.name == "GLORIA_db" and path.stem in FINAL_DEMAND:
                made["fd"][path.stem].to_pickle(target)
            elif isinstance(obj, pd.DataFrame):
                perturb_pickle(p, obj).to_pickle(target)
            else:
                shutil.copy2(path, target)
        else:
            shutil.copy2(path, target)

    for path in OUT.rglob("*.csv"):
        df = pd.read_csv(path)
        if REGION_COLUMNS.intersection(df.columns):
            rename_frame_regions(df).to_csv(path, index=False)
    for path in OUT.rglob("*.pkl"):
        obj = pd.read_pickle(path)
        if isinstance(obj, pd.DataFrame):
            rename_frame_regions(obj).to_pickle(path)
        elif path.name == "cid.pkl":
            pd.to_pickle([REGION_RENAMES.get(region, region) for region in obj], path)
    rename_region_lookup(OUT / "MSET_data" / "Variable_list_MINDSET.xlsx")

    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) / 1e6
    print(f"Synthetic data written to {OUT} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
