# -*- coding: utf-8 -*-
"""
Live region mapping between MSET (coarse regions, e.g. IPCC-10) and an FTT
module running on its own, finer regions (e.g. FTT's native 71).

TEMPORARY. This is a workaround for MSET and FTT not sharing a region set. The
mapping is approximate (a few FTT regions straddle several MSET regions and are
split by a GVA proxy). The best practice is to align the two region mappings, so
that no conversion is needed: with identical regions, RegionMap.identity() turns
every method below into a plain reordering.

Everything that crosses the MSET/FTT boundary goes through one RegionMap.

The mapping is a weight matrix W (n_ftt x n_mset), each row summing to 1: W[r, b]
is the share of FTT region r that belongs to MSET region b (1.0 for regions nesting
cleanly, fractional for the few "Rest of ..." FTT regions straddling several MSET
regions).

Rules by type of variable:
    MSET -> FTT   intensive (prices, rates):  broadcast  (weighted mean for split regions)
                  extensive (levels):         split      (shared in proportion to a reference)
    FTT -> MSET   additive (flows, stocks):   collapse_sum
                  growth of an additive:      growth     (ratio of the collapsed sums)
                  intensive outputs:          collapse_mean (explicit activity weights)
"""

import numpy as np
import pandas as pd


class RegionMap:

    def __init__(self, ftt_codes, mset_codes, W):
        self.ftt_codes = list(ftt_codes)
        self.mset_codes = list(mset_codes)
        W = np.asarray(W, dtype=float)
        if W.shape != (len(self.ftt_codes), len(self.mset_codes)):
            raise ValueError(f"W has shape {W.shape}, expected "
                             f"({len(self.ftt_codes)}, {len(self.mset_codes)})")
        if not np.allclose(W.sum(axis=1), 1.0):
            bad = [c for c, s in zip(self.ftt_codes, W.sum(axis=1)) if not np.isclose(s, 1.0)]
            raise ValueError(f"Crosswalk weights do not sum to 1 for FTT regions: {bad}")
        empty = [c for c, s in zip(self.mset_codes, W.sum(axis=0)) if s == 0]
        if empty:
            raise ValueError(f"No FTT region maps to MSET regions: {empty}")
        self.W = W
        self.is_identity = (W.shape[0] == W.shape[1]) and np.array_equal(W, np.eye(W.shape[0]))

    @classmethod
    def identity(cls, ftt_codes, mset_codes=None):
        """FTT and MSET share the same regions (possibly in a different order)."""
        ftt_codes = list(ftt_codes)
        mset_codes = ftt_codes if mset_codes is None else list(mset_codes)
        if set(ftt_codes) != set(mset_codes):
            raise ValueError("Identity map needs identical region sets: "
                             f"{sorted(set(ftt_codes) ^ set(mset_codes))}")
        W = np.zeros((len(ftt_codes), len(mset_codes)))
        for i, c in enumerate(ftt_codes):
            W[i, mset_codes.index(c)] = 1.0
        return cls(ftt_codes, mset_codes, W)

    @classmethod
    def from_crosswalk(cls, path, ftt_codes, mset_codes):
        """Long-format csv with columns FTT_code, MSET_code, weight (one row per pair)."""
        cw = pd.read_csv(path)
        ftt_codes, mset_codes = list(ftt_codes), list(mset_codes)
        unknown_ftt = sorted(set(cw['FTT_code']) - set(ftt_codes))
        missing_ftt = sorted(set(ftt_codes) - set(cw['FTT_code']))
        unknown_mset = sorted(set(cw['MSET_code']) - set(mset_codes))
        if unknown_ftt or missing_ftt or unknown_mset:
            raise ValueError(f"Crosswalk {path} inconsistent with model regions: "
                             f"FTT codes not in titles {unknown_ftt}, FTT codes without a row "
                             f"{missing_ftt}, MSET codes not in MSET {unknown_mset}")
        W = np.zeros((len(ftt_codes), len(mset_codes)))
        for _, row in cw.iterrows():
            W[ftt_codes.index(row['FTT_code']), mset_codes.index(row['MSET_code'])] += row['weight']
        return cls(ftt_codes, mset_codes, W)

    # ------------------------------------------------------------------ helpers
    def _mset_array(self, by_mset):
        if isinstance(by_mset, (pd.Series, pd.DataFrame)):
            return by_mset.reindex(self.mset_codes).fillna(0.0).to_numpy(dtype=float)
        arr = np.asarray(by_mset, dtype=float)
        if arr.shape[0] != len(self.mset_codes):
            raise ValueError(f"Leading axis {arr.shape[0]} != {len(self.mset_codes)} MSET regions")
        return arr

    def _ftt_array(self, arr):
        arr = np.asarray(arr, dtype=float)
        if arr.shape[0] != len(self.ftt_codes):
            raise ValueError(f"Leading axis {arr.shape[0]} != {len(self.ftt_codes)} FTT regions")
        return arr

    # ------------------------------------------------------------ MSET -> FTT
    def broadcast(self, by_mset):
        """Intensive variables (prices, tax rates, price-index changes): every FTT region
        takes the value of its MSET region; straddling regions take the weighted mean."""
        x = self._mset_array(by_mset)
        return np.tensordot(self.W, x, axes=(1, 0))

    def split(self, by_mset, ref=None):
        """Extensive variables (levels such as electricity demand): an MSET region total is
        shared across its FTT regions in proportion to ref (FTT's own values, e.g. the
        previous year's level), so collapse_sum(split(X)) reproduces X."""
        X = self._mset_array(by_mset)
        ref = np.ones(len(self.ftt_codes)) if ref is None else self._ftt_array(ref)
        size = self.W * ref[:, None]                     # (n_ftt, n_mset)
        tot = size.sum(axis=0)
        equal = self.W / self.W.sum(axis=0)              # fallback when the reference is all zero
        share = np.where(tot > 0, size / np.where(tot > 0, tot, 1.0), equal)
        return np.tensordot(share, X, axes=(1, 0))

    # ------------------------------------------------------------ FTT -> MSET
    def collapse_sum(self, arr):
        """Additive flows and stocks (fuel use, investment, emissions, fleet)."""
        return np.tensordot(self.W.T, self._ftt_array(arr), axes=(1, 0))

    def collapse_mean(self, arr, weights):
        """Weighted mean of intensive FTT variables; weights are FTT-region activity (>= 0)."""
        a = self._ftt_array(arr)
        w = self._ftt_array(weights).astype(float)
        w = w.reshape(w.shape + (1,) * (a.ndim - w.ndim))
        num = np.tensordot(self.W.T, a * w, axes=(1, 0))
        den = np.tensordot(self.W.T, np.broadcast_to(w, a.shape), axes=(1, 0))
        return np.divide(num, den, out=np.zeros_like(num), where=den != 0)

    def growth(self, arr_t, arr_t0):
        """Year-on-year ratio of the collapsed sums; 1.0 where the previous sum is zero."""
        s1, s0 = self.collapse_sum(arr_t), self.collapse_sum(arr_t0)
        return np.divide(s1, s0, out=np.ones_like(s1), where=s0 != 0)

    def to_series(self, arr_by_mset):
        return pd.Series(np.asarray(arr_by_mset, dtype=float), index=self.mset_codes)
