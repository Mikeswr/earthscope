"""Figures from the processed data and the analysis tables. Run scripts/run_analysis.py first.

    python scripts/make_figures.py [--out-dir reports]

Every figure carries the data source note. If the data are synthetic test data, a large watermark says so.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from earthscope import config
from earthscope.ingest import pipeline
from earthscope.trends import engine
from earthscope.trends.pipeline import annual_series, monthly_series

NOTE = "Source: NASA POWER gridded estimates (reanalysis and satellite based), not station observations."
ORDER = ["Takoradi", "Accra", "Kumasi", "Tamale", "Wa"]        # roughly south to north
VARS = ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "WS10M", "ALLSKY_SFC_SW_DWN"]
COLORS = {"significant_after_fdr": "#b2182b", "significant_before_fdr_only": "#ef8a62", "not_significant": "#444444", "insufficient_data": "#999999"}
LABEL = {"significant_after_fdr": "significant after FDR", "significant_before_fdr_only": "significant before FDR only (not a finding)",
         "not_significant": "not significant (descriptive slope only)", "insufficient_data": "insufficient data"}


def stamp(fig, synthetic):
    fig.text(0.01, 0.005, NOTE, fontsize=7, color="black", ha="left", va="bottom")
    if synthetic:
        fig.text(0.5, 0.5, "SYNTHETIC TEST DATA", fontsize=48, color="red", alpha=0.25, ha="center", va="center", rotation=25)


def unit_of(df, var):
    return df[df.variable == var].unit.iat[0]


def series_figure(df, trends, var, out, synthetic):
    how = config.annual_how(var)
    locs = [l for l in ORDER if l in set(df.location)]
    fig, axes = plt.subplots(1, len(locs), figsize=(3.3 * len(locs), 3.6), sharey=True, squeeze=False)
    for ax, loc in zip(axes[0], locs):
        g = df[(df.location == loc) & (df.variable == var)]
        ann = annual_series(monthly_series(g), how=how)
        r = trends[(trends.location == loc) & (trends.variable == var)].iloc[0]
        ax.plot(ann.index, ann.values, "o-", color="#555555", markersize=3, linewidth=0.9)
        if pd.notna(r.sen_per_decade):
            t, x = ann.dropna().index.values.astype(float), ann.dropna().values
            slope = r.sen_per_decade / 10
            icpt = np.median(x - slope * t)
            sig = r.evidence_class == "significant_after_fdr"
            ax.plot([t.min(), t.max()], icpt + slope * np.array([t.min(), t.max()]), color=COLORS[r.evidence_class],
                    linewidth=2.6 if sig else 1.4, linestyle="-" if sig else "--")
            ax.set_title(f"{loc}\n{r.sen_per_decade:+.3f} per decade [{r.sen_ci_low_per_decade:+.3f}, {r.sen_ci_high_per_decade:+.3f}]\n{LABEL[r.evidence_class].split(' (')[0]}",
                         fontsize=8, color="black")
        else:
            ax.set_title(f"{loc}\ninsufficient data", fontsize=8)
        ax.grid(alpha=0.25)
        ax.set_xlabel("year", fontsize=8)
    stat = {"day_weighted_mean": "annual mean", "max": "annual maximum of the monthly values", "min": "annual minimum of the monthly values"}[how]
    axes[0][0].set_ylabel(f"{var} ({unit_of(df, var)}), {stat}", fontsize=8)
    fig.suptitle(f"{config.VARIABLE_LABELS.get(var, var)}: annual series with Sen's slope", fontsize=10, color="black")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    stamp(fig, synthetic)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def forest_figure(trends, out, synthetic, units):
    vs = [v for v in VARS if v in set(trends.variable)]
    fig, axes = plt.subplots(2, 4, figsize=(15, 7.5))
    for ax, var in zip(axes.ravel(), vs):
        t = trends[trends.variable == var].set_index("location").reindex([l for l in ORDER if l in set(trends.location)])
        for i, (loc, r) in enumerate(t.iterrows()):
            if pd.isna(r.sen_per_decade):
                continue
            c = COLORS[r.evidence_class]
            filled = r.evidence_class == "significant_after_fdr"
            ax.errorbar(r.sen_per_decade, i, xerr=[[r.sen_per_decade - r.sen_ci_low_per_decade], [r.sen_ci_high_per_decade - r.sen_per_decade]],
                        fmt="o", color=c, markerfacecolor=c if filled else "white", markersize=7, capsize=3)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_yticks(range(len(t)))
        ax.set_yticklabels(t.index, fontsize=8)
        ax.set_title(f"{var} ({units[var]} per decade)", fontsize=9, color="black")
        ax.grid(alpha=0.25, axis="x")
        ax.xaxis.set_major_locator(MaxNLocator(5))
        ax.tick_params(axis="x", labelsize=8)
        ax.invert_yaxis()
    for ax in axes.ravel()[len(vs):]:
        ax.axis("off")
    handles = [plt.Line2D([], [], marker="o", color=COLORS[k], markerfacecolor=COLORS[k] if k == "significant_after_fdr" else "white", linestyle="", label=LABEL[k])
               for k in ("significant_after_fdr", "significant_before_fdr_only", "not_significant")]
    fig.legend(handles=handles, loc="lower right", fontsize=8, frameon=False, bbox_to_anchor=(0.98, 0.12))
    fig.suptitle("Sen's slope per decade with 95 percent interval, five separate locations (not a spatial field)", fontsize=11, color="black")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    stamp(fig, synthetic)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def flagged_precip_figure(df, out, synthetic, threshold=5.0):
    locs = [l for l in ORDER if l in set(df.location)]
    fig, axes = plt.subplots(len(locs), 1, figsize=(11, 1.9 * len(locs)), sharex=True, sharey=True)
    for ax, loc in zip(np.atleast_1d(axes), locs):
        m = monthly_series(df[(df.location == loc) & (df.variable == "PRECTOTCORR")])
        a = engine.climatology_anomalies(m)
        ax.plot(m.index, m.values, color="#555555", linewidth=0.7)
        hit = a[a.anomaly > threshold]
        ax.plot(hit.index, m.loc[hit.index], "o", color="#b2182b", markersize=5)
        for d in hit.index:
            ax.annotate(d.strftime("%Y-%m"), (d, m.loc[d]), fontsize=6, xytext=(2, 2), textcoords="offset points")
        ax.set_ylabel(f"{loc}\nmm/day", fontsize=8)
        ax.grid(alpha=0.25)
    fig.suptitle(f"PRECTOTCORR monthly values; red = more than {threshold:g} mm/day above the calendar-month mean (flagged, not removed)", fontsize=10, color="black")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    stamp(fig, synthetic)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def anomaly_figure(df, out, synthetic):
    locs = [l for l in ORDER if l in set(df.location)]
    fig, axes = plt.subplots(len(locs), 1, figsize=(11, 1.9 * len(locs)), sharex=True, sharey=True)
    for ax, loc in zip(np.atleast_1d(axes), locs):
        m = monthly_series(df[(df.location == loc) & (df.variable == "T2M")])
        a = engine.climatology_anomalies(m)
        ax.plot(a.index, a.anomaly, color="#555555", linewidth=0.6)
        ax.plot(a.index, a.anomaly.rolling(60, min_periods=48, center=True).mean(), color="#b2182b", linewidth=2)
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set_ylabel(f"{loc}\nC", fontsize=8)
        ax.grid(alpha=0.25)
    fig.suptitle("T2M monthly anomaly against the 1991 to 2020 calendar-month mean of the same record; red = 5 year running mean", fontsize=10, color="black")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    stamp(fig, synthetic)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(config.ROOT / "reports"))
    args = ap.parse_args(argv)
    df = pd.read_csv(config.processed_dir() / pipeline.PROCESSED_NAME, parse_dates=["date"])
    trends = pd.read_csv(Path(args.out_dir) / "tables" / "trend_results_primary.csv")
    synthetic = bool((df.source == "SYNTHETIC TEST DATA").any())
    fig_dir = Path(args.out_dir) / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    units = {v: unit_of(df, v) for v in df.variable.unique()}
    made = []
    for var in [v for v in VARS if v in set(df.variable)]:
        p = fig_dir / f"trend_{var}.png"
        series_figure(df, trends, var, p, synthetic)
        made.append(p.name)
    for name, fn in (("trend_summary_forest.png", lambda p: forest_figure(trends, p, synthetic, units)),
                     ("qc_precipitation_flagged_months.png", lambda p: flagged_precip_figure(df, p, synthetic)),
                     ("t2m_monthly_anomalies.png", lambda p: anomaly_figure(df, p, synthetic))):
        fn(fig_dir / name)
        made.append(name)
    print(f"{len(made)} figures written to {fig_dir}: {', '.join(made)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
