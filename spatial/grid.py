"""Spatial trend analysis and mapping.

grid_trends needs a gridded annual field (year, lat, lon). Five city points cannot support a
spatial trend field, so the dashboard map shows the point results only.

Per cell, the same engine as the point analysis is used, so the real year coordinate drives
Sen's slope and the Hamed-Rao autocorrelation correction, and years that are missing in a
cell stay missing (they are never squeezed together).

Significance is reported in two clearly separate ways:
  significant_uncorrected  cell p < alpha, no multiplicity control (expect about alpha * n_tests
                           false positives under no trend anywhere)
  significant_fdr          cell adjusted p < alpha after FDR across all tested cells
"""
import numpy as np
import plotly.graph_objects as go
import xarray as xr

from earthscope.trends import engine


def _check_years(da):
    if "year" not in da.coords:
        raise ValueError("grid_trends needs a 'year' coordinate; refusing to assume equally spaced years")
    yrs = np.asarray(da["year"].values, dtype=float)
    if not np.allclose(yrs, np.round(yrs)):
        raise ValueError("'year' coordinate must hold integer years")
    if len(np.unique(yrs)) != len(yrs) or np.any(np.diff(yrs) <= 0):
        raise ValueError("'year' coordinate must be strictly increasing with no duplicates")
    return np.round(yrs).astype(int)


def grid_trends(da, alpha=0.05, autocorrelation="ar1_neff", fdr_method="bh",
                min_valid=engine.MIN_VALID_YEARS, min_coverage=engine.MIN_YEAR_COVERAGE):
    """da: DataArray with dims (year, lat, lon), annual values, NaN where missing.
    autocorrelation: 'ar1_neff' (default), 'hamed_rao' or 'none'; temporal, applied per cell.
    Spatial dependence between cells is handled by the FDR choice below, not by this option.
    fdr_method: 'bh' (valid under independence or positive dependence, which is the usual
    situation for neighbouring cells) or 'by' (valid under any dependence, more conservative)."""
    years = _check_years(da)
    da = da.transpose("year", "lat", "lon")
    vals = da.values
    _, nlat, nlon = vals.shape
    shape = (nlat, nlon)
    slope, p, z = (np.full(shape, np.nan) for _ in range(3))
    n_valid = np.zeros(shape, dtype=int)
    cover, hrf = np.full(shape, np.nan), np.full(shape, np.nan)
    for i in range(nlat):
        for j in range(nlon):
            r = engine.mann_kendall(_cell_series(vals[:, i, j], years), alpha, autocorrelation, min_valid, min_coverage)
            n_valid[i, j], cover[i, j] = r["n"], r["coverage"]
            if not r["reason"]:
                slope[i, j], p[i, j], z[i, j], hrf[i, j] = r["slope"] * 10, r["p"], r["z"], r["variance_factor"]
    p_fdr = engine.fdr_adjust(p.ravel(), alpha, fdr_method).reshape(shape)
    with np.errstate(invalid="ignore"):
        sig_unc, sig_fdr = p < alpha, p_fdr < alpha
    ds = xr.Dataset({
        "sen_per_decade": (("lat", "lon"), slope),
        "z": (("lat", "lon"), z),
        "p_uncorrected": (("lat", "lon"), p),
        "p_fdr": (("lat", "lon"), p_fdr),
        "significant_uncorrected": (("lat", "lon"), sig_unc),
        "significant_fdr": (("lat", "lon"), sig_fdr),
        "n_valid_years": (("lat", "lon"), n_valid),
        "year_coverage": (("lat", "lon"), cover),
        "variance_factor": (("lat", "lon"), hrf),
    }, coords={"lat": da["lat"], "lon": da["lon"]})
    ds.attrs.update(alpha=alpha, autocorrelation=autocorrelation, fdr_method=fdr_method,
                    n_tests=int(np.isfinite(p).sum()), first_year=int(years.min()), last_year=int(years.max()))
    return ds


def _cell_series(values, years):
    import pandas as pd
    return pd.Series(values, index=years)


def field_summary(ds):
    """Counts that keep uncorrected and corrected significance apart."""
    n = ds.attrs["n_tests"]
    a = ds.attrs["alpha"]
    return {"cells_tested": n,
            "significant_uncorrected": int(ds["significant_uncorrected"].values.sum()),
            "significant_fdr": int(ds["significant_fdr"].values.sum()),
            "expected_false_positives_uncorrected_if_no_trend": round(n * a, 2),
            "fdr_method": ds.attrs["fdr_method"], "autocorrelation": ds.attrs["autocorrelation"]}


def point_trend_map(trends, variable):
    """Marker map of per-location Sen's slope.
    Circle = significant after FDR; diamond = significant only before FDR; open circle = neither."""
    t = trends[trends["variable"] == variable].dropna(subset=["sen_per_decade"]).copy()
    unit = t["unit"].iat[0] if len(t) else ""
    lim = float(np.abs(t["sen_per_decade"]).max()) if len(t) else 1.0
    if "significant_uncorrected" not in t:
        t["significant_uncorrected"] = t["mk_p"] < 0.05
    groups = [("Significant after FDR", t["significant_fdr"], "circle"),
              ("Significant before FDR only", t["significant_uncorrected"] & ~t["significant_fdr"], "diamond"),
              ("Not significant", ~t["significant_uncorrected"], "circle-open")]
    fig = go.Figure()
    first = True
    for label, mask, symbol in groups:
        s = t[mask]
        if s.empty:
            continue
        fig.add_trace(go.Scattergeo(
            lat=s["latitude"], lon=s["longitude"], mode="markers+text", text=s["location"],
            textposition="top center", name=label,
            marker=dict(size=16, symbol=symbol, color=s["sen_per_decade"], cmin=-lim, cmax=lim,
                        colorscale="RdBu_r", line=dict(width=2, color="#333"),
                        colorbar=dict(title=f"{unit}/decade") if first else None, showscale=first),
            customdata=np.column_stack([s["location"].astype(str), s["sen_per_decade"], s["mk_p"], s["mk_p_fdr"]]),
            hovertemplate=("%{text}<br>Sen slope %{customdata[1]:.3f} per decade"
                           "<br>p uncorrected %{customdata[2]:.3f}<br>p FDR %{customdata[3]:.3f}"
                           "<br><i>Select point to explore location</i><extra></extra>")))
        first = False
    fig.update_geos(
        scope="africa", showcountries=True, resolution=50,
        showland=True, landcolor="#F1F3F1",
        showocean=True, oceancolor="#DCE8E8",
        showcoastlines=True, coastlinecolor="#A9B8B7",
        center=dict(lat=8.0, lon=-1.5),
        projection=dict(type="mercator", scale=7.5)
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=28, b=0), height=430,
        title=dict(text=f"{variable}: Sen's slope per decade", x=0.02, xanchor="left"),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(color="#203744"),
        legend=dict(orientation="h", y=-0.08, x=0.02),
    )
    return fig
