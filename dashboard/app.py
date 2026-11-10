import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from earthscope import config
from earthscope.dashboard.data import load_data
from earthscope.qc import checks
from earthscope.spatial.grid import point_trend_map
from earthscope.trends.pipeline import annual_series, monthly_series

st.set_page_config(page_title="EarthScope", layout="wide")
st.title("EarthScope")
st.caption("Environmental trend analysis for Ghana")

data = load_data()
if data is None:
    st.info("No data loaded yet. This dashboard only shows real downloaded data and never generates "
            "placeholder values.")
    st.markdown(
        "1. Download NASA POWER monthly files (see docs/MANUAL_DOWNLOAD.md)\n"
        "2. Run `python scripts/import_power.py <files>`\n"
        "3. Run `python scripts/run_trends.py`, then reload this page")
    st.stop()

df, trends, anoms, meta = data["df"], data["trends"], data["anoms"], data["meta"]

if (df["source"] == "SYNTHETIC TEST DATA").any():
    st.error("SYNTHETIC TEST DATA is loaded. These are software test values, not environmental "
             "observations. Do not interpret or report them.")

st.sidebar.header("Selection")
loc = st.sidebar.selectbox("Location", sorted(df["location"].unique()))
var = st.sidebar.selectbox("Variable", sorted(df["variable"].unique()),
                           format_func=lambda v: f"{v}: {config.VARIABLE_LABELS.get(v, v)}")
st.sidebar.markdown(f"**Data kind:** {', '.join(sorted(df['data_kind'].unique()))}")
st.sidebar.markdown(f"**Source:** {', '.join(sorted(df['source'].unique()))}")
if (df["unit_source"] != "response_metadata").any():
    st.sidebar.warning("Some units were ASSUMED from documentation, not read from the NASA response.")

sel = df[(df["location"] == loc) & (df["variable"] == var)]
unit = sel["unit"].iat[0]
row = trends[(trends["location"] == loc) & (trends["variable"] == var)].iloc[0]
st.sidebar.markdown(f"**Statistic:** {sel['statistic'].iat[0].replace('_', ' ')}")

tab_ts, tab_tr, tab_an, tab_map, tab_qc, tab_about = st.tabs(
    ["Time series", "Trends", "Anomalies", "Map", "Data quality", "About the data"])

with tab_ts:
    m = monthly_series(sel)
    ann = annual_series(m, how=config.annual_how(var)).dropna()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=m.index, y=m.values, mode="lines", name="Monthly", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=[f"{y}-07-01" for y in ann.index], y=ann.values, mode="markers",
                             name="Annual mean"))
    if not np.isnan(row["sen_per_decade"]):
        slope = row["sen_per_decade"] / 10
        icpt = float(np.median(ann.values - slope * ann.index.values))
        yrs = np.array([ann.index.min(), ann.index.max()])
        fig.add_trace(go.Scatter(x=[f"{y}-07-01" for y in yrs], y=icpt + slope * yrs, mode="lines",
                                 name="Sen's slope (annual)", line=dict(dash="dash", width=3)))
    fig.update_layout(yaxis_title=f"{var} ({unit})", height=450, legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")
    if pd.notna(row["mk_reason"]) and row["mk_reason"]:
        st.warning(f"No annual trend reported: {row['mk_reason']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Sen's slope per decade", "n/a" if np.isnan(row["sen_per_decade"]) else f"{row['sen_per_decade']:.3f} {unit}")
    c2.metric("Mann-Kendall", str(row["mk_trend"]))
    c3.metric("p value (FDR adjusted)", "n/a" if np.isnan(row["mk_p_fdr"]) else f"{row['mk_p_fdr']:.4f}")

with tab_tr:
    t = trends[trends["variable"] == var][[
        "location", "n_years", "n_years_span", "sen_per_decade", "mk_trend", "mk_p", "significant_uncorrected",
        "mk_p_fdr", "significant_fdr", "variance_factor", "seasonal_trend", "seasonal_sen_per_decade", "seasonal_p",
        "mk_reason", "seasonal_reason"]]
    st.dataframe(t.round(4), hide_index=True, width="stretch")
    st.download_button("Download all trend results (CSV)", trends.to_csv(index=False),
                       "trend_results.csv", "text/csv")
    st.caption("Annual Mann-Kendall inflates its variance for lag-1 autocorrelation (effective sample size); "
               "Sen's slope uses actual elapsed years, so missing years do not distort it. A year needs all 12 "
               "valid months. 'significant_uncorrected' is p < 0.05 with no multiplicity control; 'significant_fdr' "
               f"is after Benjamini-Hochberg across {int(trends['n_tests_in_family'].max())} tests. The seasonal "
               "test treats calendar months as independent, so its p value is optimistic when neighbouring "
               "months are correlated; prefer the annual test for significance statements. Series that miss "
               "the minimum-data rules are shown with a reason instead of a number.")

with tab_an:
    a = anoms[(anoms["location"] == loc) & (anoms["variable"] == var)]
    fig = go.Figure(go.Scatter(x=a["date"], y=a["z"], mode="lines", name="z score", line=dict(width=1)))
    fl = a[a["flag"]]
    fig.add_trace(go.Scatter(x=fl["date"], y=fl["z"], mode="markers", name="|z| >= 2",
                             marker=dict(size=9, color="crimson")))
    fig.update_layout(yaxis_title="Standardised anomaly (z)", height=400)
    st.plotly_chart(fig, width="stretch")
    st.caption("Anomalies are relative to a 1991 to 2020 monthly climatology of this same record.")
    st.dataframe(fl[["date", "value", "anomaly", "z"]].round({"value": 3, "anomaly": 3, "z": 3}),
                 hide_index=True, width="stretch")

with tab_map:
    st.plotly_chart(point_trend_map(trends, var), width="stretch")
    st.caption("Point results at configured locations only. This is not an interpolated spatial field. "
               "Gridded trend maps need gridded input data.")

with tab_qc:
    st.dataframe(checks.completeness(df).round({"pct_valid": 1}), hide_index=True, width="stretch")
    st.write(df["qc_flag"].value_counts().rename_axis("flag").reset_index(name="count"))

with tab_about:
    st.write("NASA POWER values are gridded estimates built from reanalysis and satellite based sources. They are not direct "
             "station observations. Each location is a separate grid cell series; five points are not a spatial trend map. "
             "No forecasts are produced in this version.")
    st.write("Variable definitions follow NASA POWER documentation as understood by the developer and are "
             "marked unverified until checked against real response metadata. Spatial resolution is shown "
             "only if the response states it.")
    st.dataframe(pd.DataFrame(meta.get("variables", {})).T.drop(columns=["response_parameter_metadata_verbatim"],
                                                               errors="ignore"), width="stretch")
    st.json(meta)
