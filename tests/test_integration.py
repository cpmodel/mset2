# -*- coding: utf-8 -*-
"""
Integration checks for MINDSET, with FTT:Power switched off and on.

The model is run in a scratch directory on the reduced data in ``tests/pseudo_data`` (see
``tests/generate_pseudo_data.py``), using the settings in ``s_base.ini`` except for ``ftt_run``, ``model_end`` and
``CALIBRATING`` (False, so that the run is endogenous and fast). The run covers ``MSET_TEST_YEARS`` years (default 3)
from the model start year, which is read from ``s_base.ini``. For each run we check that:

  * the model completes every year
  * there are no NaN values in the results after the model start year (the start year itself is the base year)
  * there are no infinite values in the results

The FTT-on test needs the FTT:Power input data, which is not part of the repository. It is taken from
``MINDSET_FTT_Power/Inputs`` or from the folder in the ``MSET_FTT_INPUTS`` environment variable (the folder holding
``S0``), and the test is skipped if neither has data.

Run with:  pytest tests/test_integration.py -v
"""

import configparser
import importlib
import os
import pdb
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from synthetic_regions import REGION_RENAMES

REPO_ROOT = Path(__file__).resolve().parents[1]
PSEUDO_DATA = Path(__file__).parent / "pseudo_data" / "Data"
N_YEARS = int(os.environ.get("MSET_TEST_YEARS", 3))

# Columns that are structurally sparse (only defined for some region/sector/fuel combinations)
ALLOWED_NAN = {"dy_hh_exog", "fuel_implicit_price", "fuel_implicit_price_fd"}


def _base_settings():
    config = configparser.ConfigParser()
    config.read(REPO_ROOT / "s_base.ini")
    return config


def _ftt_inputs_dir():
    candidates = [Path(p) for p in (os.environ.get("MSET_FTT_INPUTS"),) if p]
    candidates.append(REPO_ROOT / "MINDSET_FTT_Power" / "Inputs")
    for path in candidates:
        if path.is_dir() and any(path.rglob("*.csv")):
            return path
    return None


def _build_workdir(workdir, ftt_run):
    """Assemble a self-contained working directory, since the model resolves all paths from the cwd."""
    shutil.copytree(PSEUDO_DATA, workdir / "Data")
    shutil.copy(REPO_ROOT / "variables.xlsx", workdir / "variables.xlsx")
    for folder in ("Results", "Residuals", "Temp", "Log"):
        (workdir / folder).mkdir()

    config = _base_settings()
    model_start = int(config.get("settings", "model_start"))
    model_end = model_start + N_YEARS - 1
    config.set("settings", "ftt_run", str(ftt_run))
    config.set("settings", "model_end", str(model_end))
    config.set("settings", "CALIBRATING", "False")
    with open(workdir / "s_test.ini", "w") as f:
        config.write(f)

    if ftt_run:
        utilities_dir = workdir / "MINDSET_FTT_Power" / "Utilities"
        inputs_dir = workdir / "MINDSET_FTT_Power" / "Inputs"
        shutil.copytree(REPO_ROOT / "MINDSET_FTT_Power" / "Utilities", utilities_dir)
        shutil.copytree(_ftt_inputs_dir(), inputs_dir)

    return model_start, model_end


def _run_model(workdir, ftt_run):
    model_start, model_end = _build_workdir(workdir, ftt_run)

    original_cwd, original_argv = Path.cwd(), sys.argv
    sys.path.insert(0, str(REPO_ROOT))
    os.chdir(workdir)
    sys.argv = ["MINDSET_dynamic_run.py", "s_test.ini"]
    # The model drops into pdb on a validation error, which would hang the test run
    original_set_trace = pdb.set_trace

    def _fail_on_breakpoint(*args, **kwargs):
        raise RuntimeError("Model validation failed (see 'Validation error' in the captured output)")

    pdb.set_trace = _fail_on_breakpoint
    try:
        model_class = importlib.import_module("SourceCode.model_class")
        model = model_class.ModelRun()
        if ftt_run:
            model.ftt_model.titles["RTI_short"] = tuple(REGION_RENAMES.values())
        model.run()
    finally:
        pdb.set_trace = original_set_trace
        os.chdir(original_cwd)
        sys.argv = original_argv
        sys.path.remove(str(REPO_ROOT))

    return workdir / "Results", model_start, model_end


def _read_result(path):
    return pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, na_values=["NA"])


def _collect_problems(results_dir, model_start):
    """Return (nan_report, inf_report) for all result files, for years after model_start."""
    nan_report, inf_report = [], []
    for path in sorted(results_dir.iterdir()):
        if path.suffix not in (".parquet", ".csv"):
            continue
        df = _read_result(path)
        if "year" in df.columns:
            df = df[pd.to_numeric(df["year"]) > model_start]

        for col in df.select_dtypes("number").columns:
            values = df[col].to_numpy(dtype=float)
            n_nan, n_inf = int(np.isnan(values).sum()), int(np.isinf(values).sum())
            if n_nan and col not in ALLOWED_NAN:
                nan_report.append(f"  {path.name}/{col}: {n_nan} NaN value(s)")
            if n_inf:
                inf_report.append(f"  {path.name}/{col}: {n_inf} infinite value(s)")
    return nan_report, inf_report


@pytest.fixture(scope="module", params=[False, True], ids=["ftt_off", "ftt_on"])
def model_results(request, tmp_path_factory):
    ftt_run = request.param
    if ftt_run and _ftt_inputs_dir() is None:
        pytest.skip("FTT:Power inputs not found (MINDSET_FTT_Power/Inputs or MSET_FTT_INPUTS)")
    workdir = tmp_path_factory.mktemp("mset_ftt_on" if ftt_run else "mset_ftt_off")
    return _run_model(workdir, ftt_run)


def test_model_runs_all_years(model_results):
    results_dir, model_start, model_end = model_results
    years = _read_result(next(results_dir.glob("*_0.csv")))["year"]
    assert years.max() == model_end
    assert years.min() <= model_start


def test_no_nans_in_output(model_results):
    results_dir, model_start, _ = model_results
    nan_report, _ = _collect_problems(results_dir, model_start)
    if nan_report:
        pytest.fail(f"NaN values found in model output after {model_start}:\n" + "\n".join(nan_report))


def test_no_infs_in_output(model_results):
    results_dir, model_start, _ = model_results
    _, inf_report = _collect_problems(results_dir, model_start)
    if inf_report:
        pytest.fail(f"Infinite values found in model output after {model_start}:\n" + "\n".join(inf_report))
