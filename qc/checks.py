"""Quality control. Flags are added, values are never altered or filled."""
import pandas as pd

LIMITS = {
    "T2M": (-10, 50), "T2M_MAX": (-10, 55), "T2M_MIN": (-15, 45),
    "RH2M": (0, 100), "PRECTOTCORR": (0, 100), "WS10M": (0, 40), "ALLSKY_SFC_SW_DWN": (0, 12),
}


def add_qc_flag(df, limits=None):
    limits = limits or LIMITS
    out = df.copy()
    flag = pd.Series("ok", index=out.index)
    flag[out["value"].isna()] = "missing"
    for var, (lo, hi) in limits.items():
        m = (out["variable"] == var) & out["value"].notna() & ((out["value"] < lo) | (out["value"] > hi))
        flag[m] = "out_of_range"
    out["qc_flag"] = flag
    return out


def completeness(df):
    g = df.groupby(["location", "variable"])
    res = g.agg(n_months=("value", "size"),
                n_valid=("qc_flag", lambda s: (s == "ok").sum()),
                n_missing=("qc_flag", lambda s: (s == "missing").sum()),
                n_out_of_range=("qc_flag", lambda s: (s == "out_of_range").sum()),
                first=("date", "min"), last=("date", "max")).reset_index()
    res["pct_valid"] = 100 * res["n_valid"] / res["n_months"]
    return res


def gaps(df):
    """Months absent from the record between its first and last date (not just NaN)."""
    out = []
    for (loc, var), g in df.groupby(["location", "variable"]):
        full = pd.date_range(g["date"].min(), g["date"].max(), freq="MS")
        absent = full.difference(pd.DatetimeIndex(g["date"]))
        out.append({"location": loc, "variable": var, "absent_months": len(absent)})
    return pd.DataFrame(out)
