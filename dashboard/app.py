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
from earthscope.ingest import openweather as owm
from earthscope.ingest import agromonitoring as agro
from earthscope.ingest import http as api_http
from earthscope.forecasting.engine import ForecastError, forecast_monthly

st.set_page_config(page_title="EarthScope | Environmental intelligence", page_icon="🌍", layout="wide")

st.markdown("""
<style>

/* Accessible contrast: dark body copy, readable secondary text and form labels */
html, body, [class*="css"], .stApp, .stMarkdown, .stText, p, li, label,
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] {
 color:#203744 !important;
}
.stCaption, [data-testid="stCaptionContainer"], small {
 color:#526875 !important;
}
[data-testid="stMetricLabel"] { color:#425B68 !important; }
[data-testid="stMetricValue"] { color:#173344 !important; }
[data-testid="stMetricDelta"] { color:#365765 !important; }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
 color:#203744 !important;
}
[data-baseweb="select"] *, [data-baseweb="input"] *, textarea {
 color:#203744 !important;
}
.stAlert p, .stAlert li { color:#243B48 !important; }
[data-testid="stDataFrame"] { color:#203744 !important; }
.stApp{background:#F7F8F6}.block-container{padding:2rem 2rem 3rem;max-width:1450px}
[data-testid="stSidebar"]{background:#EEF3F1}
/* Keep Streamlit's sidebar close/collapse control visible on mobile and desktop */
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebar"] button[kind="header"],
[data-testid="stHeader"] button[kind="header"] {
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  color: #173344 !important;
  background: #E1ECE8 !important;
  border: 1px solid #B8CEC6 !important;
  border-radius: 8px !important;
  min-width: 36px !important;
  min-height: 36px !important;
  z-index: 1001 !important;
}
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebar"] button[kind="header"] svg,
[data-testid="stHeader"] button[kind="header"] svg {
  color: #173344 !important;
  fill: #173344 !important;
  stroke: #173344 !important;
  opacity: 1 !important;
}
[data-testid="stMetric"]{background:white;border:1px solid #E2EAE6;padding:14px;border-radius:13px;min-width:0}
.hero{background:linear-gradient(115deg,#102F40,#176E73);color:white;padding:30px 34px;border-radius:18px;margin-bottom:22px}
.hero h1{color:white;font-size:2.4rem;margin:0 0 6px}.hero p{color:#D7EAE7;margin:0;font-size:1.05rem}
.eyebrow{text-transform:uppercase;letter-spacing:.12em;color:#A8DCD0;font-size:.72rem;font-weight:700;margin-bottom:8px}
.note{background:#EAF3F0;border-left:4px solid #238B83;padding:12px 16px;border-radius:7px;margin:8px 0 18px}
div[data-testid="stTabs"] button[aria-selected="true"]{color:#147C78}
div[data-testid="stPlotlyChart"]{width:100%;min-width:0}
[data-testid="stDataFrame"]{max-width:100%;overflow-x:auto}
@media (max-width: 768px){
 .block-container{padding:.85rem .8rem 2rem}
 .hero{padding:22px 18px;border-radius:14px;margin-bottom:16px}
 .hero h1{font-size:1.85rem;line-height:1.12}
 .hero p{font-size:.94rem;line-height:1.45}
 .eyebrow{font-size:.62rem;letter-spacing:.09em}
 h2{font-size:1.25rem!important} h3{font-size:1.08rem!important}
 [data-testid="stHorizontalBlock"]{flex-wrap:wrap;gap:.55rem}
 [data-testid="stHorizontalBlock"]>[data-testid="column"]{flex:1 1 calc(50% - .55rem)!important;min-width:calc(50% - .55rem)!important}
 [data-testid="stMetric"]{padding:10px;border-radius:10px}
 [data-testid="stMetricLabel"]{font-size:.72rem}
 [data-testid="stMetricValue"]{font-size:1.25rem}
 div[data-testid="stTabs"]>div{overflow-x:auto;white-space:nowrap;scrollbar-width:thin}
 div[data-testid="stTabs"] button{font-size:.76rem;padding:.45rem .65rem;min-width:max-content}
 div[data-testid="stPlotlyChart"]{margin-left:-.25rem;margin-right:-.25rem}
 [data-testid="stDataFrame"]{font-size:.78rem}
 .note{font-size:.88rem;line-height:1.5;padding:10px 12px}
}
@media (max-width: 390px){
 .block-container{padding-left:.55rem;padding-right:.55rem}
 .hero h1{font-size:1.65rem}
 [data-testid="stHorizontalBlock"]>[data-testid="column"]{flex-basis:100%!important;min-width:100%!important}
 div[data-testid="stTabs"] button{font-size:.7rem;padding:.4rem .5rem}
}

/* Strong, consistent contrast for Streamlit's rendered text and controls */
.stApp, .stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stMarkdownContainer"] li,
.stApp [data-testid="stWidgetLabel"],
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stText"],
.stApp label,
.stApp small,
.stApp .stRadio,
.stApp .stCheckbox,
.stApp [data-testid="stMetricLabel"],
.stApp [data-testid="stMetricDelta"] {
  color: #203744 !important;
  opacity: 1 !important;
}
.stApp [data-testid="stCaptionContainer"],
.stApp .stCaption,
.stApp small {
  color: #425B68 !important;
}
.stApp [data-testid="stMetricValue"] {
  color: #173344 !important;
  opacity: 1 !important;
}
/* Keep every part of the branded hero readable, including the EarthScope title */
.stApp .hero,
.stApp .hero * {
  opacity: 1 !important;
}
.stApp .hero h1,
.stApp .hero h1 span,
.stApp .hero h1 p,
.stApp .hero h1 strong {
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
  opacity: 1 !important;
  text-shadow: 0 1px 2px rgba(0,0,0,.18);
}
.stApp .hero p {
  color: #F0F8F6 !important;
  -webkit-text-fill-color: #F0F8F6 !important;
}
.stApp .hero .eyebrow {
  color: #C5F0E5 !important;
  -webkit-text-fill-color: #C5F0E5 !important;
}
.stApp [data-testid="stTabs"] button,
.stApp [data-testid="stTabs"] button p {
  color: #294653 !important;
  opacity: 1 !important;
}
.stApp [data-testid="stTabs"] button[aria-selected="true"],
.stApp [data-testid="stTabs"] button[aria-selected="true"] p {
  color: #08766F !important;
  opacity: 1 !important;
}
.stApp [data-testid="stSidebar"] *,
.stApp [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] * {
  opacity: 1 !important;
}
.stApp [data-baseweb="select"] *,
.stApp [data-baseweb="input"] *,
.stApp textarea {
  color: #203744 !important;
  opacity: 1 !important;
}
.stApp [data-testid="stAlert"] *,
.stApp [data-testid="stDataFrame"] * {
  opacity: 1 !important;
}

</style>
""", unsafe_allow_html=True)

INFO = {
"T2M":("Air temperature at 2 metres","Average air temperature about 2 metres above the surface.","°C"),
"T2M_MAX":("Highest air temperature at 2 metres","Highest hourly air-temperature value within each month.","°C"),
"T2M_MIN":("Lowest air temperature at 2 metres","Lowest hourly air-temperature value within each month.","°C"),
"PRECTOTCORR":("Corrected precipitation rate","Bias-corrected average daily precipitation rate. This is not the month's accumulated rainfall total.","mm/day"),
"RH2M":("Relative humidity at 2 metres","How close the air is to saturation with water vapour, expressed as a percentage.","%"),
"WS10M":("Wind speed at 10 metres","Wind speed estimated 10 metres above the surface.","m/s"),
"ALLSKY_SFC_SW_DWN":("Solar energy reaching the surface","Downward shortwave solar energy at the surface under all-sky conditions.","kWh/m²/day")
}
def name(code): return INFO.get(code,(config.VARIABLE_LABELS.get(code,code),"",""))[0]
def desc(code): return INFO.get(code,("","Definition not yet available.",""))[1]
def number(v,d=3): return "Not available" if pd.isna(v) else f"{v:,.{d}f}"

@st.cache_data(ttl=600, show_spinner=False)
def fetch_openweather_current(lat, lon):
    """Fetch one current-conditions snapshot; cache for ten minutes."""
    return owm.current_weather(float(lat), float(lon), units="metric")

@st.cache_data(ttl=600, show_spinner=False)
def fetch_openweather_history_probe(lat, lon):
    """Request a small, recent historical sample to verify account entitlement."""
    end = pd.Timestamp.now(tz="UTC").floor("h")
    start = end - pd.Timedelta(hours=3)
    payload = owm.history_hourly(
        float(lat), float(lon), int(start.timestamp()), int(end.timestamp()), units="metric"
    )
    parsed = owm.parse_history_hourly(payload, "Selected location", float(lat), float(lon))
    return payload, parsed, start, end


@st.cache_data(ttl=600, show_spinner=False)
def fetch_agromonitoring_current(lat, lon):
    return agro.current_weather(float(lat), float(lon))

@st.cache_data(ttl=900, show_spinner=False)
def fetch_agromonitoring_history(lat, lon):
    end = pd.Timestamp.now(tz="UTC").floor("h")
    start = end - pd.Timedelta(hours=23)
    payload = agro.weather_history(float(lat), float(lon), int(start.timestamp()), int(end.timestamp()))
    parsed = agro.parse_weather_history(payload, "Selected location", float(lat), float(lon))
    return payload, parsed, start, end


data=load_data()
if data is None:
    st.markdown('<div class="hero"><div class="eyebrow">Ghana · Earth observation</div><h1>EarthScope</h1><p>Understand how environmental conditions change across time and place.</p></div>',unsafe_allow_html=True)
    st.info("No processed dataset is available. EarthScope does not generate placeholder environmental values.")
    st.stop()
df,trends,anoms,meta=data["df"],data["trends"],data["anoms"],data["meta"]
if (df["source"]=="SYNTHETIC TEST DATA").any():
    st.error("SYNTHETIC TEST DATA is loaded. Do not interpret or report these values.")

st.sidebar.markdown("## Explore the data")
st.sidebar.caption("Choose a location and environmental variable.")
loc=st.sidebar.selectbox("Study location",sorted(df["location"].unique()))
var=st.sidebar.selectbox("Environmental variable",sorted(df["variable"].unique()),format_func=lambda v:f"{name(v)} · {v}")
sel=df[(df.location==loc)&(df.variable==var)]
unit=sel.unit.iat[0]
row=trends[(trends.location==loc)&(trends.variable==var)].iloc[0]
st.sidebar.markdown(f"**{name(var)}**")
st.sidebar.caption(f"NASA parameter: {var}")
st.sidebar.write(desc(var))
st.sidebar.caption(f"Source: {', '.join(sorted(sel.source.unique()))}")
st.sidebar.caption(f"Data type: {', '.join(sorted(sel.data_kind.unique())).replace('_',' ')}")
if (df.unit_source!="response_metadata").any():
    st.sidebar.warning("Some units were assumed from documentation rather than read from source metadata.")

st.markdown('<div class="hero"><div class="eyebrow">Ghana · Earth observation · Environmental change</div><h1>EarthScope</h1><p>Environmental change, made understandable. Explore what is changing, where it is happening, and what the evidence means.</p></div>',unsafe_allow_html=True)

st.markdown("## Understand the change around you")
st.markdown(
    "EarthScope is for everyone: people who are curious about the environment, as well as "
    "researchers, solar energy professionals, planners and public institutions who need "
    "reliable evidence. You do not need a climate-science background to explore the findings."
)

# Lead with a verified example so first-time visitors immediately see what the platform does.
featured_solar = trends[
    (trends["location"] == "Accra")
    & (trends["variable"] == "ALLSKY_SFC_SW_DWN")
]
if not featured_solar.empty:
    solar = featured_solar.iloc[0]
    st.markdown("### Featured example: Accra solar energy")
    st.caption("This is a fixed introductory case study. It does not change when you select a different location or variable below.")
    solar_metric, solar_story = st.columns([1, 2])
    solar_metric.metric(
        "Estimated change in surface solar energy",
        f"{solar['sen_per_decade']:.4f} kWh/m²/day per decade",
        help="Sen's slope estimated from annual values. A negative value indicates a decline."
    )
    solar_story.markdown(
        f"NASA POWER estimates show a **declining long-term trend** in the amount of "
        f"shortwave solar energy reaching the surface at the Accra grid point between "
        f"**{int(solar['first_year'])} and {int(solar['last_year'])}**. "
        f"The 95% confidence interval is **{solar['sen_ci_low_per_decade']:.4f} to "
        f"{solar['sen_ci_high_per_decade']:.4f} kWh/m²/day per decade**."
    )
    st.markdown(
        "**Why this matters:** changes in estimated surface solar energy are worth "
        "investigating when assessing solar resources and planning energy systems. "
        "This finding is a reason to look more closely, not a direct measurement of "
        "electricity generated by solar panels."
    )
    st.caption(
        f"Evidence: FDR-adjusted p-value {solar['mk_p_fdr']:.4f}. "
        "This is a NASA POWER gridded estimate, not a ground-based radiation measurement. "
        "Independent validation is still needed, and this analysis does not establish the cause."
    )
    with st.expander("What does this mean in everyday language?"):
        st.write(
            "The data estimate how much solar energy reaches the Earth's surface each day. "
            "The long-term statistical pattern at the Accra grid point is downward. "
            "It does not mean that every day is becoming less sunny, that solar panels "
            "are producing less electricity, or that the cause is known."
        )

st.markdown("### Who EarthScope is for")
public_col, specialist_col = st.columns(2)
with public_col:
    st.markdown("**The general public**")
    st.write(
        "Explore local environmental changes, learn what the measurements mean, "
        "and understand the difference between short-term weather and long-term climate patterns."
    )
with specialist_col:
    st.markdown("**People working with environmental evidence**")
    st.write(
        "Investigate trends and uncertainty for research, solar resource assessment, "
        "energy planning, policy and environmental management."
    )

with st.expander("A quick guide: weather, variability and climate trends"):
    guide_a, guide_b, guide_c = st.columns(3)
    guide_a.markdown("**Weather**")
    guide_a.write("What the atmosphere is doing over hours or days.")
    guide_b.markdown("**Variability**")
    guide_b.write("The natural ups and downs from one day, season or year to another.")
    guide_c.markdown("**Climate trend**")
    guide_c.write("A sustained direction of change measured across many years.")

st.divider()
st.markdown(f"### {loc} / {name(var)}")
st.markdown(f'<div class="note">{desc(var)} <b>NASA parameter:</b> {var} · <b>Unit:</b> {unit}</div>',unsafe_allow_html=True)

m=monthly_series(sel)
ann=annual_series(m,how=config.annual_how(var)).dropna()
a,b,c,d=st.columns(4)
a.metric("Valid years",str(int(row["n_years"])) if pd.notna(row["n_years"]) else "n/a")
b.metric("Trend direction",str(row["mk_trend"]).replace("_"," ").title())
c.metric("Estimated change per decade",f"{number(row['sen_per_decade'])} {unit}" if pd.notna(row["sen_per_decade"]) else "n/a")
d.metric("FDR-adjusted p-value",number(row["mk_p_fdr"],4),help="Multiple-testing-adjusted statistical evidence, not the probability that a trend is true.")

# This interpretation is driven by the sidebar selections and updates on every rerun.
st.markdown("### Your selected result")
direction = str(row.get("mk_trend", "not assessed")).lower()
evidence = str(row.get("evidence_class", "insufficient_data")).lower()
slope = row.get("sen_per_decade", np.nan)
ci_low = row.get("sen_ci_low_per_decade", np.nan)
ci_high = row.get("sen_ci_high_per_decade", np.nan)
start_year = row.get("first_year", np.nan)
end_year = row.get("last_year", np.nan)
period_text = (
    f"from {int(start_year)} to {int(end_year)}"
    if pd.notna(start_year) and pd.notna(end_year)
    else "over the available analysis period"
)
if evidence == "significant_after_fdr" and direction in ("increasing", "decreasing"):
    direction_word = "upward" if direction == "increasing" else "downward"
    plain_result = (
        f"For **{loc}**, the long-term pattern in **{name(var).lower()}** is {direction_word} "
        f"{period_text}. The estimated rate of change is **{number(slope)} {unit} per decade**. "
        "The trend remains statistically significant after adjustment for multiple testing."
    )
    st.success(plain_result)
elif evidence == "significant_before_fdr_only" and direction in ("increasing", "decreasing"):
    direction_word = "upward" if direction == "increasing" else "downward"
    plain_result = (
        f"For **{loc}**, the estimated pattern in **{name(var).lower()}** is {direction_word} "
        f"{period_text}, at **{number(slope)} {unit} per decade**. However, the evidence does "
        "not remain statistically significant after accounting for multiple comparisons. "
        "Treat this as a possible signal, not a confirmed trend."
    )
    st.warning(plain_result)
elif evidence == "not_significant":
    plain_result = (
        f"For **{loc}**, this analysis does not find sufficient statistical evidence of a "
        f"consistent long-term upward or downward trend in **{name(var).lower()}** {period_text}. "
        "That does not mean the variable never changes. It means the long-term direction is "
        "not clear enough in this analysis."
    )
    st.info(plain_result)
else:
    plain_result = (
        f"A reliable trend classification is not available for **{name(var).lower()}** at "
        f"**{loc}** because the available data do not meet the analysis requirements."
    )
    st.info(plain_result)

if pd.notna(slope) and pd.notna(ci_low) and pd.notna(ci_high):
    st.caption(
        f"Estimated change: {number(slope)} {unit} per decade · "
        f"95% confidence interval: {number(ci_low)} to {number(ci_high)} · "
        f"FDR-adjusted p-value: {number(row.get('mk_p_fdr', np.nan), 4)}."
    )
st.caption(
    "These results describe NASA POWER gridded estimates at the selected grid point, "
    "not direct station measurements. Statistical evidence does not identify the cause "
    "of the observed pattern."
)
st.caption("NASA POWER historical monthly data. These are gridded estimates, not direct weather-station observations.")

ts,tr,fu,an,mp,qc,about,owtab,agtab=st.tabs(["Explore time series","Compare trends","Future outlook","Unusual conditions","Location map","Data quality","Methods & sources","OpenWeather now","Agromonitoring"])
with ts:
    st.markdown("### How has this variable changed?")
    st.write("The line shows monthly values. Dots show annual summaries. The dashed line shows the estimated long-term Sen's slope.")
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=m.index,y=m.values,mode="lines",name="Monthly values",line=dict(width=1.2,color="#2386C8")))
    fig.add_trace(go.Scatter(x=[f"{y}-07-01" for y in ann.index],y=ann.values,mode="markers",name="Annual summary",marker=dict(size=6,color="#F2A65A")))
    if not np.isnan(row["sen_per_decade"]) and len(ann):
        slope=row["sen_per_decade"]/10
        intercept=float(np.median(ann.values-slope*ann.index.values))
        years=np.array([ann.index.min(),ann.index.max()])
        fig.add_trace(go.Scatter(x=[f"{y}-07-01" for y in years],y=intercept+slope*years,mode="lines",name="Sen's slope",line=dict(dash="dash",width=3,color="#D95745")))
    fig.update_layout(yaxis_title=f"{name(var)} ({unit})",height=440,legend=dict(orientation="h",y=-.2),hovermode="x unified",plot_bgcolor="white",paper_bgcolor="white")
    st.plotly_chart(fig,width="stretch")
    st.info("Short-term peaks and dips do not, by themselves, establish a long-term climate trend.")
    if pd.notna(row["mk_reason"]) and row["mk_reason"]: st.warning(f"No annual trend reported: {row['mk_reason']}")
    with st.expander("What do the statistics mean?"):
        st.markdown("- **Sen's slope:** estimated rate of change per decade.\n- **Mann-Kendall:** tests evidence of a monotonic upward or downward trend.\n- **FDR-adjusted p-value:** accounts for testing several location-variable combinations.\n- Statistical significance does not identify the physical cause of a change.")

with tr:
    st.markdown("### How do locations compare?")
    st.write(f"Trend estimates for {name(var)} across the study locations.")
    cols=["location","n_years","sen_per_decade","sen_ci_low_per_decade","sen_ci_high_per_decade","mk_trend","mk_p","mk_p_fdr","evidence_class"]
    table=trends[trends.variable==var][cols].copy().rename(columns={"location":"Location","n_years":"Valid years","sen_per_decade":f"Sen's slope ({unit}/decade)","sen_ci_low_per_decade":"95% CI lower","sen_ci_high_per_decade":"95% CI upper","mk_trend":"Trend direction","mk_p":"Raw p-value","mk_p_fdr":"FDR-adjusted p-value","evidence_class":"Evidence classification"})
    st.dataframe(table.round(4),hide_index=True,width="stretch")
    st.download_button("Download complete trend results (CSV)",trends.to_csv(index=False),"earthscope_trend_results.csv","text/csv")
    fam=trends[trends.variable==var].fdr_family.iloc[0]
    family_n=int(trends[trends.fdr_family==fam].mk_p.notna().sum())
    st.caption(f"FDR correction family: {fam.replace('_',' ')} ({family_n} valid tests). Annual Mann-Kendall approximately accounts for lag-1 autocorrelation. A year requires all 12 valid months. Seasonal p-values are not used for significance claims because neighbouring months are correlated.")
    with st.expander("How should I read the evidence classification?"):
        st.markdown("- **Significant after FDR:** adjusted p-value below 0.05.\n- **Significant before FDR only:** raw p-value below 0.05, but adjusted result is not.\n- **Not significant:** insufficient statistical evidence of a monotonic trend.\n- **Insufficient data:** minimum data requirements were not met.")


with fu:
    st.markdown("### What might happen next?")
    st.write("EarthScope compares forecasting methods against withheld historical observations, then uses the best-performing method for a statistical outlook.")
    st.warning("These are statistical extrapolations from NASA POWER grid-cell data, not climate-model projections or guaranteed future conditions. They do not account for future emissions, policy, land-use change or climate scenarios.")
    horizon = st.select_slider("Forecast horizon", options=[12, 24, 36, 48, 60], value=24,
                               format_func=lambda n: f"{n // 12} year" if n == 12 else f"{n // 12} years")
    bounds = {
        "PRECTOTCORR": (0.0, None),
        "RH2M": (0.0, 100.0),
        "WS10M": (0.0, None),
        "ALLSKY_SFC_SW_DWN": (0.0, None),
    }
    try:
        lower, upper = bounds.get(var, (None, None))
        forecast, forecast_info = forecast_monthly(
            m, horizon_months=int(horizon), lower_bound=lower, upper_bound=upper
        )
        chosen = forecast_info["selected_model"]
        chosen_metrics = forecast_info["metrics"][chosen]
        baseline_metrics = forecast_info["metrics"]["seasonal_naive"]
        x1, x2, x3 = st.columns(3)
        x1.metric("Selected method", chosen.replace("_", " ").title())
        x2.metric("Backtest MAE", f"{chosen_metrics['mae']:.3f} {unit}")
        x3.metric("Backtest RMSE", f"{chosen_metrics['rmse']:.3f} {unit}")
        skill = forecast_info["skill_vs_seasonal_naive"] * 100
        if chosen == "seasonal_naive":
            st.info("The seasonal-naive baseline performed best. EarthScope has not found evidence that a more complex model improves the one-year backtest.")
        elif skill > 0:
            st.success(f"The selected method reduced backtest MAE by {skill:.1f}% compared with the seasonal-naive baseline.")
        else:
            st.warning(f"The selected method did not outperform the seasonal-naive baseline on MAE ({skill:.1f}% skill). Treat this outlook cautiously.")
        hist = m.iloc[-60:]
        fig_f = go.Figure()
        fig_f.add_trace(go.Scatter(x=hist.index, y=hist.values, mode="lines",
                                   name="Observed monthly values", line=dict(color="#2386C8", width=1.5)))
        fig_f.add_trace(go.Scatter(x=forecast.date, y=forecast.upper_95, mode="lines",
                                   line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig_f.add_trace(go.Scatter(x=forecast.date, y=forecast.lower_95, mode="lines",
                                   line=dict(width=0), fill="tonexty", fillcolor="rgba(28,114,147,0.10)",
                                   name="95% empirical error band", hoverinfo="skip"))
        fig_f.add_trace(go.Scatter(x=forecast.date, y=forecast.upper_80, mode="lines",
                                   line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig_f.add_trace(go.Scatter(x=forecast.date, y=forecast.lower_80, mode="lines",
                                   line=dict(width=0), fill="tonexty", fillcolor="rgba(28,114,147,0.20)",
                                   name="80% empirical error band", hoverinfo="skip"))
        fig_f.add_trace(go.Scatter(x=forecast.date, y=forecast.forecast, mode="lines",
                                   name="Forecast", line=dict(color="#D95745", width=2.5, dash="dash")))
        fig_f.add_vline(x=m.index.max(), line_dash="dot", line_color="#526875")
        fig_f.update_layout(title=f"{loc} · {var} statistical outlook",
                            yaxis_title=f"{name(var)} ({unit})", xaxis_title="Month",
                            height=460, hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white",
                            legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig_f, width="stretch")
        metrics_table = pd.DataFrame([
            {"Method": model.replace("_", " ").title(), **values}
            for model, values in forecast_info["metrics"].items()
        ]).rename(columns={"mae": f"MAE ({unit})", "rmse": f"RMSE ({unit})",
                           "bias": f"Bias ({unit})", "n_predictions": "Withheld months",
                           "n_origins": "Backtest origins"})
        st.markdown("#### Historical backtest comparison")
        st.dataframe(metrics_table.round(3), hide_index=True, width="stretch")
        st.caption(f"Training period: {forecast_info['training_start']} to {forecast_info['training_end']} · "
                   f"{forecast_info['n_training_months']} monthly observations · "
                   f"{forecast_info['n_origins']} rolling-origin backtests.")
        st.caption(forecast_info["interval_warning"])
        st.download_button("Download monthly outlook (CSV)", forecast.to_csv(index=False),
                           f"earthscope_{loc}_{var}_outlook.csv", "text/csv")
        with st.expander("How EarthScope produces this outlook"):
            st.markdown("Three candidates are evaluated: seasonal-naive, linear trend with calendar-month effects, and damped additive exponential smoothing. Each backtest trains only on earlier data and predicts the next 12 months. The method with the lowest pooled one-year mean absolute error is selected. The 80% and 95% bands are approximate empirical bands calibrated from withheld absolute errors and widened with lead time. They are not formal climate projection intervals.")
    except ForecastError as exc:
        st.warning(f"A forecast is not available for this series: {exc}")
    except Exception as exc:
        st.error(f"The forecasting run could not be completed safely: {exc}")

with an:
    st.markdown("### When did unusual conditions occur?")
    st.write("An anomaly differs from the typical value for that calendar month in the 1991–2020 reference period.")
    z=anoms[(anoms.location==loc)&(anoms.variable==var)]
    flagged=z[z.flag]
    fig=go.Figure(go.Scatter(x=z.date,y=z.z,mode="lines",name="Standardised anomaly",line=dict(width=1.1,color="#2386C8")))
    fig.add_trace(go.Scatter(x=flagged.date,y=flagged.z,mode="markers",name="Flagged |z| ≥ 2",marker=dict(size=8,color="#D95745")))
    fig.add_hline(y=2,line_dash="dot",line_color="#D95745",opacity=.6)
    fig.add_hline(y=-2,line_dash="dot",line_color="#D95745",opacity=.6)
    fig.update_layout(yaxis_title="Standardised anomaly (z-score)",height=400,plot_bgcolor="white",paper_bgcolor="white")
    st.plotly_chart(fig,width="stretch")
    st.caption("Red markers identify observations at least two standard deviations from the calendar-month climatology. An anomaly is not automatically a long-term trend or proof of an extreme event.")
    st.metric("Flagged observations",f"{len(flagged):,}")
    st.dataframe(flagged[["date","value","anomaly","z"]].round({"value":3,"anomaly":3,"z":3}),hide_index=True,width="stretch")

with mp:
    st.markdown("### Where do the location results differ?")
    st.write("Each marker represents one configured NASA POWER grid-cell location.")
    st.plotly_chart(point_trend_map(trends,var),width="stretch")
    st.warning("This is a map of five point results, not an interpolated continuous spatial trend field.")

with qc:
    st.markdown("### How complete and reliable is the dataset?")
    st.dataframe(checks.completeness(df).round({"pct_valid":1}),hide_index=True,width="stretch")
    st.dataframe(df.qc_flag.value_counts().rename_axis("Flag").reset_index(name="Records"),hide_index=True,width="stretch")
    st.caption("Missing or flagged values remain at their original calendar positions and are excluded from calculations. They are not interpolated.")

with about:
    st.markdown("### Understand the data behind EarthScope")
    st.markdown("**NASA POWER** provides gridded environmental estimates derived from satellite observations and modelling/reanalysis systems. These are not direct weather-station measurements. Each selected location represents a separate grid-cell time series. Five locations do not form a continuous map of Ghana. No forecasts are produced by this analysis.")
    glossary=pd.DataFrame([{"NASA code":k,"Plain-language name":v[0],"What it measures":v[1],"Unit":v[2]} for k,v in INFO.items() if k in set(df.variable)])
    st.markdown("#### Variable reference")
    st.dataframe(glossary,hide_index=True,width="stretch")
    st.markdown("#### Source metadata")
    st.dataframe(pd.DataFrame(meta.get("variables",{})).T.drop(columns=["response_parameter_metadata_verbatim"],errors="ignore"),width="stretch")




with owtab:
    st.markdown("### OpenWeather nowcast")
    st.write("Live conditions plus an interactive view of the latest four hourly observations. The four-hour series is recent weather history, not a forecast.")
    if not config.get_key(config.ENV_OPENWEATHER):
        st.info('Add OPENWEATHER_API_KEY to Streamlit Cloud Secrets to enable OpenWeather.')
    else:
        if st.button("Refresh current conditions", key="load_openweather_current"):
            st.session_state["ow_current_requested"] = True
        if st.session_state.get("ow_current_requested", False):
            try:
                ow = fetch_openweather_current(row["latitude"], row["longitude"])
                main, wind = ow["main"], ow.get("wind", {})
                weather_items = ow.get("weather") or []
                condition = weather_items[0].get("description", "Conditions not described") if weather_items else "Conditions not described"
                st.markdown(f"**{loc}** · {condition.title()}")
                w1, w2, w3, w4 = st.columns(4)
                w1.metric("Air temperature", f"{number(main.get('temp'), 1)} °C")
                w2.metric("Feels like", f"{number(main.get('feels_like'), 1)} °C")
                w3.metric("Relative humidity", f"{number(main.get('humidity'), 0)} %")
                w4.metric("Wind speed", f"{number(wind.get('speed'), 1)} m/s")
                offset = int(ow.get("timezone", 0) or 0)
                observed_at = pd.to_datetime(ow["dt"], unit="s", utc=True) + pd.to_timedelta(offset, unit="s")
                st.caption(f"OpenWeather current conditions · {observed_at:%Y-%m-%d %H:%M} local time · Cached for up to 10 minutes.")
            except api_http.ApiError as e:
                st.warning(f"OpenWeather request failed: {str(e)}")
            except (KeyError, TypeError, ValueError) as e:
                st.warning(f"OpenWeather response could not be read: {e}")

        st.markdown("### Latest four hours")
        st.write("Select a variable to inspect its hourly movement. The endpoint has already returned four hourly records for Accra in the live access test.")
        if st.button("Load latest four hours", key="load_openweather_4h"):
            st.session_state["ow_history_requested"] = True
        if st.session_state.get("ow_history_requested", False):
            try:
                payload, history_sample, start, end = fetch_openweather_history_probe(row["latitude"], row["longitude"])
                if not history_sample.empty:
                    variables = sorted(history_sample["variable"].unique())
                    labels = {
                        "temp": ("Air temperature", "°C"),
                        "humidity": ("Relative humidity", "%"),
                        "pressure": ("Air pressure", "hPa"),
                        "wind_speed": ("Wind speed", "m/s"),
                        "cloud_cover": ("Cloud cover", "%"),
                        "rain_1h": ("Rainfall in previous hour", "mm"),
                    }
                    selected = st.selectbox("Plot variable", variables, format_func=lambda v: f"{labels.get(v, (v, ''))[0]} ({labels.get(v, ('', ''))[1]})", key="ow_4h_variable")
                    series = history_sample[history_sample["variable"] == selected].sort_values("date")
                    title, unit_label = labels.get(selected, (selected, series["unit"].iloc[0]))
                    fig4 = go.Figure()
                    fig4.add_trace(go.Scatter(
                        x=series["date"], y=series["value"], mode="lines+markers",
                        name=title, line=dict(width=3), marker=dict(size=8),
                        hovertemplate="%{x|%H:%M UTC}<br>%{y:.2f} " + unit_label + "<extra></extra>"
                    ))
                    fig4.update_layout(
                        title=f"{title} over the latest four hourly observations",
                        xaxis_title="Time (UTC)", yaxis_title=unit_label, height=390,
                        hovermode="x unified", plot_bgcolor="white", paper_bgcolor="white"
                    )
                    st.plotly_chart(fig4, width="stretch")
                    latest = series.iloc[-1]
                    st.metric(f"Latest {title.lower()}", f"{number(latest['value'], 2)} {unit_label}")
                    st.caption(f"Retrieved {len(payload.get('list', []))} hourly records from {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC. This is an observed/recent-history series, not a forecast.")
                    st.dataframe(series[["date", "value", "unit"]], hide_index=True, width="stretch")
                else:
                    st.warning("The API returned no usable hourly observations for this time window.")
            except api_http.ApiError as e:
                st.warning(f"Recent hourly data could not be retrieved: {str(e)}")
            except (KeyError, TypeError, ValueError) as e:
                st.warning(f"Hourly response could not be parsed: {e}")

    with st.expander("Source and interpretation"):
        st.markdown("OpenWeather current conditions and recent hourly history are displayed separately from NASA POWER. They are not merged into the long-term trend calculations.")
        
with agtab:
    st.markdown("### Agromonitoring weather")
    st.write("A second weather source for current conditions and historical hourly data. Historical archive depth depends on the API subscription.")
    if not config.get_key(config.ENV_AGROMONITORING):
        st.info('Agromonitoring is not connected yet. Add AGROMONITORING_API_KEY to Streamlit Cloud Secrets. Keep the key private.')
        st.markdown("Historical weather is documented at a one-hour time step. Access to older periods depends on the subscription.")
    else:
        if st.button("Load Agromonitoring current conditions", key="load_agro_current"):
            st.session_state["agro_current_requested"] = True
        if st.session_state.get("agro_current_requested", False):
            try:
                aw = fetch_agromonitoring_current(row["latitude"], row["longitude"])
                main, wind = aw.get("main", {}), aw.get("wind", {})
                weather_items = aw.get("weather") or []
                condition = weather_items[0].get("description", "Conditions not described") if weather_items else "Conditions not described"
                st.markdown(f"**{loc}** · {condition.title()}")
                c1, c2, c3, c4 = st.columns(4)
                # Agromonitoring current weather returns Kelvin by default.
                temp_c = None if main.get("temp") is None else float(main["temp"]) - 273.15
                feels_c = None if main.get("feels_like") is None else float(main["feels_like"]) - 273.15
                c1.metric("Air temperature", f"{number(temp_c, 1)} °C")
                c2.metric("Feels like", f"{number(feels_c, 1)} °C")
                c3.metric("Relative humidity", f"{number(main.get('humidity'), 0)} %")
                c4.metric("Wind speed", f"{number(wind.get('speed'), 1)} m/s")
                st.caption("Agromonitoring current weather API. Current conditions are not a historical observation series.")
            except api_http.ApiError as e:
                st.warning(f"Agromonitoring current-weather request failed: {str(e)}")
            except (KeyError, TypeError, ValueError) as e:
                st.warning(f"Agromonitoring response could not be read: {e}")

        st.markdown("### Recent hourly weather")
        st.write("Loads the latest 24 hourly timestamps available to your account. This short recent-history view is for live monitoring only. Older archive access was tested and is not available for the requested historical date under the current subscription.")
        if st.button("Load last 24 hours", key="load_agro_history"):
            st.session_state["agro_history_requested"] = True
        if st.session_state.get("agro_history_requested", False):
            try:
                with st.spinner("Requesting Agromonitoring hourly history..."):
                    agro_payload, agro_sample, agro_start, agro_end = fetch_agromonitoring_history(
                        row["latitude"], row["longitude"]
                    )
                if not agro_sample.empty:
                    available = sorted(agro_sample["variable"].unique())
                    labels = {"temp":"Air temperature","humidity":"Relative humidity","pressure":"Air pressure","wind_speed":"Wind speed","cloud_cover":"Cloud cover"}
                    chosen = st.selectbox("Historical variable", available, format_func=lambda v: f"{labels.get(v,v)} ({agro_sample.loc[agro_sample.variable==v,'unit'].iloc[0]})", key="agro_history_variable")
                    series = agro_sample[agro_sample.variable==chosen].sort_values("date")
                    fig_ag = go.Figure(go.Scatter(x=series.date,y=series.value,mode="lines+markers",name=labels.get(chosen,chosen)))
                    fig_ag.update_layout(title=f"{labels.get(chosen,chosen)} · Agromonitoring hourly history",xaxis_title="Time (UTC)",yaxis_title=series.unit.iloc[0],height=390,hovermode="x unified",plot_bgcolor="white",paper_bgcolor="white")
                    st.plotly_chart(fig_ag,width="stretch")
                    st.success(f"Historical access confirmed. Returned {len(agro_payload)} hourly records.")
                    st.caption(f"Requested UTC window: {agro_start:%Y-%m-%d %H:%M} to {agro_end:%Y-%m-%d %H:%M}.")
                    st.dataframe(series[["date","value","unit"]],hide_index=True,width="stretch")
                else:
                    st.warning("The endpoint responded but returned no usable hourly observations.")
            except api_http.ApiError as e:
                st.warning(f"Agromonitoring historical access was not confirmed: {str(e)}")
            except (KeyError, TypeError, ValueError) as e:
                st.warning(f"Agromonitoring historical response could not be parsed: {e}")
    with st.expander("How Agromonitoring data is used"):
        st.markdown("Agromonitoring weather is kept separate from NASA POWER and OpenWeather. It is not added to climate trend calculations. Temperature in the historical API is converted from Kelvin to Celsius by the ingestion parser.")

st.divider()
st.caption("EarthScope · Research prototype · Interpret results with the documented data and methodological limitations.")
