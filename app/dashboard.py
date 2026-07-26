"""
dashboard.py - Eco-Loop Premium 3D Dashboard (Streamlit + Plotly)

Visualizes baseline vs AI-controlled simulation performance with
3D interactive charts, glassmorphism UI, and animated transitions.

Run with:
    streamlit run app/dashboard.py
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from optimizer import get_full_report, generate_markdown_report, generate_comparison_csv

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ──────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Eco-Loop Building Agent | Dashboard",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# PREMIUM CSS — Glassmorphism + Animated Dark UI
# ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #050a14 !important;
}
.stApp {
    background: radial-gradient(ellipse at top left, #0a1628 0%, #050a14 50%, #000d1a 100%) !important;
}
.block-container { padding-top: 1rem; padding-bottom: 2rem; }

.hero-wrap {
    background: linear-gradient(135deg, rgba(16,185,129,0.15) 0%, rgba(59,130,246,0.1) 50%, rgba(139,92,246,0.15) 100%);
    border: 1px solid rgba(16,185,129,0.25);
    border-radius: 20px;
    padding: 2.2rem 2.8rem;
    margin-bottom: 1.8rem;
    position: relative;
    overflow: hidden;
    backdrop-filter: blur(10px);
}
.hero-wrap::before {
    content: '';
    position: absolute;
    top: -60px; right: -60px;
    width: 220px; height: 220px;
    background: radial-gradient(circle, rgba(16,185,129,0.2) 0%, transparent 70%);
    border-radius: 50%;
}
.hero-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2.4rem;
    font-weight: 700;
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, #10b981, #34d399, #60a5fa);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.hero-sub { color: #94a3b8; font-size: 0.95rem; margin: 0; }
.hero-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(16,185,129,0.15);
    border: 1px solid rgba(16,185,129,0.4);
    border-radius: 999px;
    padding: 4px 14px;
    font-size: 0.75rem; font-weight: 600; color: #34d399;
    margin-top: 0.8rem;
    letter-spacing: 0.05em; text-transform: uppercase;
}

.kpi-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 1.3rem 1.4rem;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s, transform 0.2s;
    cursor: default;
}
.kpi-card:hover { border-color: rgba(16,185,129,0.4); transform: translateY(-2px); }
.kpi-card::before {
    content: '';
    position: absolute; inset: 0;
    background: linear-gradient(135deg, rgba(16,185,129,0.05), transparent);
    pointer-events: none;
}
.kpi-icon { font-size: 1.5rem; margin-bottom: 0.5rem; display: block; }
.kpi-label { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #64748b; margin-bottom: 0.3rem; }
.kpi-value { font-family: 'Space Grotesk', sans-serif; font-size: 1.75rem; font-weight: 700; color: #f1f5f9; line-height: 1.1; margin-bottom: 0.4rem; }
.kpi-delta-good { font-size: 0.78rem; font-weight: 600; color: #10b981; }
.kpi-delta-good::before { content: '▼ '; }
.kpi-delta-bad { font-size: 0.78rem; font-weight: 600; color: #f43f5e; }
.kpi-delta-bad::before { content: '▲ '; }
.kpi-delta-neutral { font-size: 0.78rem; color: #64748b; }
.kpi-baseline { font-size: 0.7rem; color: #475569; margin-top: 0.2rem; }

.section-header {
    display: flex; align-items: center; gap: 10px;
    margin: 1.5rem 0 1rem 0;
}
.section-header .line {
    flex: 1; height: 1px;
    background: linear-gradient(to right, rgba(16,185,129,0.4), transparent);
}
.section-header h3 {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1rem; font-weight: 600; color: #e2e8f0;
    margin: 0; white-space: nowrap;
}

[data-testid="stSidebar"] {
    background: rgba(5, 10, 20, 0.95) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
[data-testid="stSidebar"] * { color: #cbd5e1 !important; }

[data-testid="stTabs"] button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 500 !important; color: #64748b !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #10b981 !important; border-bottom-color: #10b981 !important;
}

.eco-footer {
    text-align: center; color: #334155; font-size: 0.78rem;
    padding: 2rem 0 1rem;
    border-top: 1px solid rgba(255,255,255,0.05);
    margin-top: 2rem;
}
.eco-footer span { color: #10b981; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# PLOTLY THEME CONSTANTS
# ──────────────────────────────────────────────
PAPER_BG = "rgba(5,10,20,0)"
PLOT_BG   = "rgba(10,18,35,0.95)"
GRID_COLOR = "rgba(255,255,255,0.06)"
FONT_COLOR = "#94a3b8"
BASELINE_COLOR = "#60a5fa"
AI_COLOR       = "#10b981"
ACCENT_COLOR   = "#f59e0b"
DANGER_COLOR   = "#f43f5e"
PURPLE_COLOR   = "#a78bfa"


def base_layout(title="", height=460):
    return dict(
        title=dict(text=title, font=dict(family="Space Grotesk", size=15, color="#e2e8f0"), x=0.01),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(family="Inter", color=FONT_COLOR, size=11),
        height=height,
        margin=dict(l=50, r=30, t=50, b=40),
        legend=dict(
            bgcolor="rgba(15,23,42,0.85)",
            bordercolor="rgba(255,255,255,0.1)",
            borderwidth=1,
            font=dict(color="#cbd5e1", size=11),
        ),
        hoverlabel=dict(
            bgcolor="rgba(15,23,42,0.95)",
            bordercolor="rgba(16,185,129,0.5)",
            font=dict(family="Inter", color="white", size=12),
        ),
    )


def section(emoji, title):
    st.markdown(f"""
    <div class="section-header">
        <h3>{emoji} {title}</h3>
        <div class="line"></div>
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────────
# LOAD DATA
# ──────────────────────────────────────────────
report        = get_full_report()
baseline_m    = report["baseline"]
ai_m          = report["ai_controlled"]
savings       = report["savings"]
baseline_rows = report["baseline_rows"]
ai_rows       = report["ai_rows"]
has_data      = bool(baseline_m and ai_m)

if not has_data:
    st.error("No simulation data found. Run: `./venv/bin/python app/energyplus_runner.py --mode both`")
    st.stop()

# Generate report strings
md_report = generate_markdown_report(report)
csv_report = generate_comparison_csv(report)

b_df = pd.DataFrame(baseline_rows)
a_df = pd.DataFrame(ai_rows)

for df in (b_df, a_df):
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(df[col])
        except Exception:
            pass

# ──────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎛️ Dashboard Controls")
    st.markdown("---")
    chart_opacity = st.slider("Chart Opacity", 0.3, 1.0, 0.85, 0.05)
    downsample = st.selectbox("Time Resolution", ["Every hour (fast)", "Every 4 hrs", "Every 12 hrs"], index=0)
    step_map = {"Every hour (fast)": 6, "Every 4 hrs": 24, "Every 12 hrs": 72}
    ds = step_map[downsample]
    b_ds = b_df.iloc[::ds].reset_index(drop=True)
    a_ds = a_df.iloc[::ds].reset_index(drop=True)

    st.markdown("---")
    st.markdown("### 📊 Quick Summary")
    energy_saved = savings.get("energy_savings_pct") or 0
    carbon_saved = savings.get("carbon_reduction_pct") or 0
    cost_saved   = savings.get("cost_savings_inr") or 0
    st.metric("Energy Saved", f"{abs(energy_saved):.1f}%", delta="vs Baseline", delta_color="normal")
    st.metric("Carbon Reduced", f"{abs(carbon_saved):.1f}%", delta="kg CO₂", delta_color="normal")
    st.metric("Cost Saved", f"Rs.{abs(cost_saved):,.0f}", delta="INR/year", delta_color="normal")

    st.markdown("---")
    st.markdown("### 📥 Download Reports")
    st.download_button(
        label="📄 Download Report (.md)",
        data=md_report,
        file_name=f"EcoLoop_Report_{config.LLM_BACKEND}.md",
        mime="text/markdown",
        key="btn_sidebar_md",
    )
    st.download_button(
        label="📊 Download Metrics (.csv)",
        data=csv_report,
        file_name=f"EcoLoop_Comparison_{config.LLM_BACKEND}.csv",
        mime="text/csv",
        key="btn_sidebar_csv",
    )

    st.markdown("---")
    st.markdown("""
    <div style="color:#475569;font-size:0.72rem;line-height:1.7;">
    <b style="color:#64748b;">Data Sources:</b><br>
    EnergyPlus 26.1 simulation<br>
    NVIDIA / Gemini LLM decisions<br>
    ASHRAE 55 comfort model<br>
    India grid: 0.82 kg CO2/kWh
    </div>
    """, unsafe_allow_html=True)
    b_ds = b_df.iloc[::ds].reset_index(drop=True)
    a_ds = a_df.iloc[::ds].reset_index(drop=True)

# ──────────────────────────────────────────────
# HERO HEADER
# ──────────────────────────────────────────────
backend_name = config.LLM_BACKEND.upper()
st.markdown(f"""
<div class="hero-wrap">
    <div class="hero-title">🌿 Eco-Loop Building Agent</div>
    <div class="hero-sub">Autonomous HVAC Optimization · EnergyPlus + LLM Closed-Loop Control · New Delhi Office Model</div>
    <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:0.8rem;">
        <div class="hero-badge">⚡ LLM: {backend_name}</div>
        <div class="hero-badge">🏢 SmOffPSZ — New Delhi</div>
        <div class="hero-badge">📅 Annual · 35,040 Timesteps</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# KPI CARDS
# ──────────────────────────────────────────────
section("📊", "Key Performance Indicators")

kpis = [
    {"icon": "⚡", "label": "Total HVAC Energy",
     "value": f"{ai_m.get('total_energy_kwh', 0):,.1f}", "unit": " kWh",
     "delta": savings.get("energy_savings_pct") or 0,
     "baseline": f"Baseline: {baseline_m.get('total_energy_kwh', 0):,.1f} kWh",
     "lower_is_better": True},
    {"icon": "📈", "label": "Peak Demand",
     "value": f"{ai_m.get('peak_demand_kw', 0):.1f}", "unit": " kW",
     "delta": savings.get("peak_demand_reduction_pct") or 0,
     "baseline": f"Baseline: {baseline_m.get('peak_demand_kw', 0):.1f} kW",
     "lower_is_better": True},
    {"icon": "🌱", "label": "Carbon Emissions",
     "value": f"{ai_m.get('carbon_emissions_kg', 0):,.0f}", "unit": " kg",
     "delta": savings.get("carbon_reduction_pct") or 0,
     "baseline": f"Baseline: {baseline_m.get('carbon_emissions_kg', 0):,.0f} kg",
     "lower_is_better": True},
    {"icon": "💰", "label": "Energy Cost",
     "value": f"Rs.{ai_m.get('energy_cost_inr', 0):,.0f}", "unit": "",
     "delta": savings.get("energy_savings_pct") or 0,
     "baseline": f"Saved Rs.{abs(savings.get('cost_savings_inr', 0)):,.0f}",
     "lower_is_better": True},
    {"icon": "🧍", "label": "Comfort Violations",
     "value": f"{ai_m.get('comfort_violations_timesteps', 0):,}", "unit": "",
     "delta": None,
     "baseline": f"Baseline: {baseline_m.get('comfort_violations_timesteps', 0):,} timesteps",
     "lower_is_better": True},
]

cols = st.columns(5)
for col, k in zip(cols, kpis):
    d = k["delta"]
    if d is not None:
        is_good = (d < 0 and k["lower_is_better"]) or (d > 0 and not k["lower_is_better"])
        delta_cls = "kpi-delta-good" if is_good else "kpi-delta-bad"
        delta_html = f'<div class="{delta_cls}">{abs(d):.1f}% vs baseline</div>'
    else:
        delta_html = '<div class="kpi-delta-neutral">—</div>'
    col.markdown(f"""
    <div class="kpi-card">
        <span class="kpi-icon">{k['icon']}</span>
        <div class="kpi-label">{k['label']}</div>
        <div class="kpi-value">{k['value']}<span style="font-size:0.9rem;color:#475569;">{k['unit']}</span></div>
        {delta_html}
        <div class="kpi-baseline">{k['baseline']}</div>
    </div>
    """, unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 3D ENERGY SURFACE
# ──────────────────────────────────────────────
section("🗻", "3D Energy Surface — Day x Hour x HVAC Power")

if "sim_day" in a_df.columns and "hour" in a_df.columns and "hvac_power_w" in a_df.columns:
    col_3d, col_info = st.columns([3, 1])
    with col_3d:
        pivot_b = b_df.groupby(["sim_day", "hour"])["hvac_power_w"].mean().unstack(fill_value=0) / 1000
        pivot_a = a_df.groupby(["sim_day", "hour"])["hvac_power_w"].mean().unstack(fill_value=0) / 1000

        days_b = pivot_b.index[::7]
        days_a = pivot_a.index[::7]
        hours  = list(range(24))

        Z_b = pivot_b.reindex(hours, axis=1).fillna(0).loc[days_b].values
        Z_a = pivot_a.reindex(hours, axis=1).fillna(0).loc[days_a].values

        fig3d = go.Figure()
        fig3d.add_trace(go.Surface(
            x=hours, y=list(range(len(days_b))), z=Z_b,
            name="Baseline",
            colorscale=[[0, "rgba(37,99,235,0.2)"], [0.5, "rgba(96,165,250,0.6)"], [1, "rgba(147,197,253,0.9)"]],
            opacity=0.55, showscale=False,
            hovertemplate="Hour: %{x}h<br>Week: %{y}<br>Power: %{z:.2f} kW<extra>Baseline</extra>",
        ))
        fig3d.add_trace(go.Surface(
            x=hours, y=list(range(len(days_a))), z=Z_a,
            name="AI Controlled",
            colorscale=[[0, "rgba(5,150,105,0.2)"], [0.5, "rgba(16,185,129,0.6)"], [1, "rgba(110,231,183,0.95)"]],
            opacity=0.85, showscale=False,
            hovertemplate="Hour: %{x}h<br>Week: %{y}<br>Power: %{z:.2f} kW<extra>AI Closed-Loop</extra>",
        ))

        layout_3d = base_layout("HVAC Power Surface: Baseline (blue) vs AI (green)", height=520)
        layout_3d.update(dict(
            scene=dict(
                xaxis=dict(title="Hour of Day", color=FONT_COLOR, gridcolor=GRID_COLOR, showbackground=False, tickmode="linear", dtick=4),
                yaxis=dict(title="Week of Year", color=FONT_COLOR, gridcolor=GRID_COLOR, showbackground=False),
                zaxis=dict(title="HVAC Power (kW)", color=FONT_COLOR, gridcolor=GRID_COLOR, showbackground=False),
                bgcolor="rgba(10,18,35,0.0)",
                camera=dict(eye=dict(x=1.5, y=-1.8, z=1.0)),
            ),
            scene_aspectmode="manual",
            scene_aspectratio=dict(x=1.5, y=2, z=0.8),
        ))
        fig3d.update_layout(**layout_3d)
        st.plotly_chart(fig3d, use_container_width=True, config={"displayModeBar": True})

    with col_info:
        st.markdown("""
        <div style="background:rgba(16,185,129,0.07);border:1px solid rgba(16,185,129,0.2);border-radius:12px;padding:1.2rem;margin-top:1rem;">
            <div style="color:#34d399;font-weight:700;font-size:0.85rem;margin-bottom:0.8rem;">How to read this</div>
            <div style="color:#94a3b8;font-size:0.78rem;line-height:1.7;">
                <b style="color:#cbd5e1;">X axis:</b> Hour of day (0-23)<br>
                <b style="color:#cbd5e1;">Y axis:</b> Week of year<br>
                <b style="color:#cbd5e1;">Z axis:</b> Mean HVAC power (kW)<br><br>
                <b style="color:#60a5fa;">Blue surface</b> = Baseline<br>
                <b style="color:#10b981;">Green surface</b> = AI Controlled<br><br>
                AI surface sits lower, showing energy reduction across all seasons and hours.<br><br>
                Drag to rotate · Scroll to zoom
            </div>
        </div>
        """, unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 3D SCATTER — Operating Envelope
# ──────────────────────────────────────────────
section("🔬", "3D Operating Envelope — Zone Temp x HVAC Power x Comfort PMV")

if all(c in a_df.columns for c in ["zone_temp_c", "hvac_power_w", "pmv"]):
    b_ds_full = b_df.iloc[::6].reset_index(drop=True)
    a_ds_full = a_df.iloc[::6].reset_index(drop=True)
    n = min(1500, len(b_ds_full), len(a_ds_full))
    b_sample = b_ds_full.sample(n=n, random_state=42)
    a_sample = a_ds_full.sample(n=n, random_state=42)

    fig_scatter3d = go.Figure()
    fig_scatter3d.add_trace(go.Scatter3d(
        x=b_sample["zone_temp_c"], y=b_sample["hvac_power_w"] / 1000, z=b_sample["pmv"],
        mode="markers", name="Baseline",
        marker=dict(size=2.5, color=b_sample["pmv"].values,
                    colorscale=[[0, "#1e40af"], [0.5, "#60a5fa"], [1, "#93c5fd"]],
                    opacity=0.6, line=dict(width=0)),
        hovertemplate="Zone: %{x:.1f}C<br>Power: %{y:.2f}kW<br>PMV: %{z:.2f}<extra>Baseline</extra>",
    ))
    fig_scatter3d.add_trace(go.Scatter3d(
        x=a_sample["zone_temp_c"], y=a_sample["hvac_power_w"] / 1000, z=a_sample["pmv"],
        mode="markers", name="AI Closed-Loop",
        marker=dict(size=3, color=a_sample["pmv"].values,
                    colorscale=[[0, "#065f46"], [0.5, "#10b981"], [1, "#6ee7b7"]],
                    opacity=0.85, line=dict(width=0)),
        hovertemplate="Zone: %{x:.1f}C<br>Power: %{y:.2f}kW<br>PMV: %{z:.2f}<extra>AI Closed-Loop</extra>",
    ))

    layout_sc = base_layout("Operating Envelope: Each point = one simulated hour", height=520)
    layout_sc.update(dict(
        scene=dict(
            xaxis=dict(title="Zone Temp (C)", color=FONT_COLOR, gridcolor=GRID_COLOR, showbackground=False),
            yaxis=dict(title="HVAC Power (kW)", color=FONT_COLOR, gridcolor=GRID_COLOR, showbackground=False),
            zaxis=dict(title="PMV Comfort Index", color=FONT_COLOR, gridcolor=GRID_COLOR, showbackground=False),
            bgcolor="rgba(10,18,35,0.0)",
            camera=dict(eye=dict(x=1.8, y=-1.5, z=0.9)),
        ),
        scene_aspectmode="auto",
    ))
    fig_scatter3d.update_layout(**layout_sc)
    st.plotly_chart(fig_scatter3d, use_container_width=True, config={"displayModeBar": True})

# ──────────────────────────────────────────────
# TIMESERIES — Interactive Plotly Tabs
# ──────────────────────────────────────────────
section("📈", "Interactive Timeseries")

tab_pow, tab_temp, tab_pmv, tab_sp, tab_compare = st.tabs([
    "⚡ HVAC Power", "🌡️ Zone Temperature", "🧍 Comfort (PMV)", "🎛️ AI Setpoints", "📊 Comparison"
])

with tab_pow:
    fig_pow = go.Figure()
    if "hvac_power_w" in b_ds.columns:
        fig_pow.add_trace(go.Scatter(
            x=b_ds["timestep"], y=b_ds["hvac_power_w"] / 1000,
            name="Baseline", line=dict(color=BASELINE_COLOR, width=1), opacity=0.6,
            hovertemplate="Timestep %{x}<br>Power: %{y:.2f} kW<extra>Baseline</extra>",
        ))
    if "hvac_power_w" in a_ds.columns:
        fig_pow.add_trace(go.Scatter(
            x=a_ds["timestep"], y=a_ds["hvac_power_w"] / 1000,
            name="AI Closed-Loop", line=dict(color=AI_COLOR, width=1.2), opacity=chart_opacity,
            hovertemplate="Timestep %{x}<br>Power: %{y:.2f} kW<extra>AI Closed-Loop</extra>",
            fill="tozeroy", fillcolor="rgba(16,185,129,0.04)",
        ))
    layout_pw = base_layout("HVAC Electricity Demand Rate (kW)")
    layout_pw.update(xaxis=dict(gridcolor=GRID_COLOR, showgrid=True, title="Timestep", color=FONT_COLOR),
                     yaxis=dict(gridcolor=GRID_COLOR, showgrid=True, title="HVAC Power (kW)", color=FONT_COLOR))
    fig_pow.update_layout(**layout_pw)
    st.plotly_chart(fig_pow, use_container_width=True, config={"displayModeBar": True})

with tab_temp:
    fig_temp = go.Figure()
    if "zone_temp_c" in b_ds.columns:
        fig_temp.add_trace(go.Scatter(
            x=b_ds["timestep"], y=b_ds["zone_temp_c"],
            name="Baseline", line=dict(color=BASELINE_COLOR, width=1), opacity=0.55,
        ))
    if "zone_temp_c" in a_ds.columns:
        fig_temp.add_trace(go.Scatter(
            x=a_ds["timestep"], y=a_ds["zone_temp_c"],
            name="AI Closed-Loop", line=dict(color=AI_COLOR, width=1.2), opacity=chart_opacity,
        ))
    fig_temp.add_hrect(y0=20, y1=26, fillcolor="rgba(16,185,129,0.05)", line_width=0,
                       annotation_text="Comfort Band (20-26C)", annotation_position="top left",
                       annotation_font=dict(color=AI_COLOR, size=10))
    layout_t = base_layout("Zone Mean Air Temperature (C)")
    layout_t.update(xaxis=dict(gridcolor=GRID_COLOR, title="Timestep", color=FONT_COLOR),
                    yaxis=dict(gridcolor=GRID_COLOR, title="Temperature (C)", color=FONT_COLOR))
    fig_temp.update_layout(**layout_t)
    st.plotly_chart(fig_temp, use_container_width=True, config={"displayModeBar": True})

with tab_pmv:
    fig_pmv = go.Figure()
    if "pmv" in b_ds.columns:
        fig_pmv.add_trace(go.Scatter(
            x=b_ds["timestep"], y=b_ds["pmv"],
            name="Baseline PMV", line=dict(color=BASELINE_COLOR, width=1), opacity=0.55,
        ))
    if "pmv" in a_ds.columns:
        fig_pmv.add_trace(go.Scatter(
            x=a_ds["timestep"], y=a_ds["pmv"],
            name="AI PMV", line=dict(color=AI_COLOR, width=1.2), opacity=chart_opacity,
        ))
    fig_pmv.add_hrect(y0=-0.5, y1=0.5, fillcolor="rgba(16,185,129,0.07)", line_width=0,
                      annotation_text="ASHRAE Comfort Zone (-0.5 to +0.5)",
                      annotation_position="top right",
                      annotation_font=dict(color=AI_COLOR, size=10))
    fig_pmv.add_hline(y=0.5, line_dash="dash", line_color=DANGER_COLOR, opacity=0.6)
    fig_pmv.add_hline(y=-0.5, line_dash="dash", line_color=DANGER_COLOR, opacity=0.6)
    layout_pmv = base_layout("Predicted Mean Vote — Thermal Comfort Index")
    layout_pmv.update(xaxis=dict(gridcolor=GRID_COLOR, title="Timestep", color=FONT_COLOR),
                      yaxis=dict(gridcolor=GRID_COLOR, title="PMV Index", color=FONT_COLOR, range=[-3, 3]))
    fig_pmv.update_layout(**layout_pmv)
    st.plotly_chart(fig_pmv, use_container_width=True, config={"displayModeBar": True})

with tab_sp:
    fig_sp = go.Figure()
    if "heating_setpoint" in a_ds.columns:
        fig_sp.add_trace(go.Scatter(
            x=a_ds["timestep"], y=a_ds["heating_setpoint"],
            name="Heating Setpoint", line=dict(color="#f43f5e", width=1.2), opacity=chart_opacity,
            fill="tozeroy", fillcolor="rgba(244,63,94,0.04)",
        ))
    if "cooling_setpoint" in a_ds.columns:
        fig_sp.add_trace(go.Scatter(
            x=a_ds["timestep"], y=a_ds["cooling_setpoint"],
            name="Cooling Setpoint", line=dict(color=BASELINE_COLOR, width=1.2), opacity=chart_opacity,
        ))
    if "zone_temp_c" in a_ds.columns:
        fig_sp.add_trace(go.Scatter(
            x=a_ds["timestep"], y=a_ds["zone_temp_c"],
            name="Actual Zone Temp", line=dict(color=AI_COLOR, width=1, dash="dot"), opacity=0.7,
        ))
    layout_sp = base_layout("AI Closed-Loop HVAC Setpoint Overrides")
    layout_sp.update(xaxis=dict(gridcolor=GRID_COLOR, title="Timestep", color=FONT_COLOR),
                     yaxis=dict(gridcolor=GRID_COLOR, title="Temperature (C)", color=FONT_COLOR))
    fig_sp.update_layout(**layout_sp)
    st.plotly_chart(fig_sp, use_container_width=True, config={"displayModeBar": True})

with tab_compare:
    metrics_labels = ["Energy (kWh)", "Peak Demand (kW)", "Carbon (kg CO2)", "Cost (Rs/100)", "Comfort Violations"]
    b_vals = [
        baseline_m.get("total_energy_kwh", 0),
        baseline_m.get("peak_demand_kw", 0),
        baseline_m.get("carbon_emissions_kg", 0),
        baseline_m.get("energy_cost_inr", 0) / 100,
        baseline_m.get("comfort_violations_timesteps", 0),
    ]
    a_vals = [
        ai_m.get("total_energy_kwh", 0),
        ai_m.get("peak_demand_kw", 0),
        ai_m.get("carbon_emissions_kg", 0),
        ai_m.get("energy_cost_inr", 0) / 100,
        ai_m.get("comfort_violations_timesteps", 0),
    ]

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=metrics_labels, y=b_vals, name="Baseline",
        marker=dict(
            color=b_vals,
            colorscale=[[0, "rgba(37,99,235,0.5)"], [1, "rgba(96,165,250,0.95)"]],
            line=dict(color=BASELINE_COLOR, width=1),
        ),
        opacity=0.8,
        text=[f"{v:,.1f}" for v in b_vals], textposition="outside",
        textfont=dict(color=BASELINE_COLOR, size=10),
        hovertemplate="%{x}<br>Baseline: %{y:,.1f}<extra></extra>",
    ))
    fig_bar.add_trace(go.Bar(
        x=metrics_labels, y=a_vals, name="AI Closed-Loop",
        marker=dict(
            color=a_vals,
            colorscale=[[0, "rgba(5,150,105,0.5)"], [1, "rgba(16,185,129,0.95)"]],
            line=dict(color=AI_COLOR, width=1),
        ),
        opacity=0.9,
        text=[f"{v:,.1f}" for v in a_vals], textposition="outside",
        textfont=dict(color=AI_COLOR, size=10),
        hovertemplate="%{x}<br>AI: %{y:,.1f}<extra></extra>",
    ))
    layout_bar = base_layout("Performance Comparison: Baseline vs AI Closed-Loop", height=480)
    layout_bar.update(
        barmode="group", bargap=0.25, bargroupgap=0.08,
        xaxis=dict(gridcolor=GRID_COLOR, color=FONT_COLOR),
        yaxis=dict(gridcolor=GRID_COLOR, color=FONT_COLOR, title="Value"),
    )
    fig_bar.update_layout(**layout_bar)
    st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": True})

    scols = st.columns(4)
    savings_data = [
        ("Energy Saved", f"{abs(savings.get('energy_savings_pct') or 0):.1f}%", BASELINE_COLOR),
        ("Carbon Cut", f"{abs(savings.get('carbon_reduction_pct') or 0):.1f}%", AI_COLOR),
        ("Cost Saved", f"Rs.{abs(savings.get('cost_savings_inr') or 0):,.0f}", ACCENT_COLOR),
        ("Peak Shift", f"{abs(savings.get('peak_demand_reduction_pct') or 0):.1f}%", PURPLE_COLOR),
    ]
    for scol, (label, val, color) in zip(scols, savings_data):
        scol.markdown(f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid {color}55;border-radius:12px;padding:1rem;text-align:center;margin-top:1rem;">
            <div style="font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;">{label}</div>
            <div style="font-family:'Space Grotesk',sans-serif;font-size:1.8rem;font-weight:700;color:{color};margin:0.3rem 0;">{val}</div>
        </div>
        """, unsafe_allow_html=True)

# ──────────────────────────────────────────────
# SEASONAL HEATMAPS
# ──────────────────────────────────────────────
section("🗓️", "Seasonal Heatmap — Monthly Energy Intensity (Month x Hour)")

if "sim_day" in a_df.columns and "hour" in a_df.columns and "hvac_power_w" in a_df.columns:
    col_heat_b, col_heat_a = st.columns(2)

    def make_heatmap(df, title, colorscale, zmax=None):
        df = df.copy()
        df["month"] = ((df["sim_day"] // 30) % 12).astype(int)
        pivot = df.groupby(["month", "hour"])["hvac_power_w"].mean().unstack(fill_value=0) / 1000
        pivot = pivot.reindex(range(12), fill_value=0).reindex(range(24), axis=1, fill_value=0)
        month_names = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
        fig = go.Figure(go.Heatmap(
            z=pivot.values, x=list(range(24)), y=month_names,
            colorscale=colorscale, zmin=0, zmax=zmax or pivot.values.max(),
            hovertemplate="Hour: %{x}h<br>Month: %{y}<br>Avg Power: %{z:.2f} kW<extra></extra>",
            colorbar=dict(
                title=dict(text="kW", font=dict(color=FONT_COLOR)),
                tickfont=dict(color=FONT_COLOR),
                bgcolor="rgba(10,18,35,0.8)", bordercolor="rgba(255,255,255,0.1)", thickness=12),
        ))
        layout_h = base_layout(title, height=340)
        layout_h.update(
            xaxis=dict(title="Hour of Day", color=FONT_COLOR, gridcolor=GRID_COLOR, dtick=4),
            yaxis=dict(title="Month", color=FONT_COLOR, gridcolor=GRID_COLOR),
        )
        fig.update_layout(**layout_h)
        return fig

    zmax_shared = max(
        float(b_df["hvac_power_w"].max()) / 1000 if "hvac_power_w" in b_df.columns else 1,
        float(a_df["hvac_power_w"].max()) / 1000 if "hvac_power_w" in a_df.columns else 1,
    )
    with col_heat_b:
        fig_hb = make_heatmap(b_df, "Baseline — Monthly Energy Pattern",
            [[0, "rgba(10,18,35,1)"], [0.4, "rgba(37,99,235,0.7)"], [1, "rgba(147,197,253,1)"]], zmax=zmax_shared)
        st.plotly_chart(fig_hb, use_container_width=True, config={"displayModeBar": False})
    with col_heat_a:
        fig_ha = make_heatmap(a_df, "AI Closed-Loop — Monthly Energy Pattern",
            [[0, "rgba(10,18,35,1)"], [0.4, "rgba(5,150,105,0.7)"], [1, "rgba(110,231,183,1)"]], zmax=zmax_shared)
        st.plotly_chart(fig_ha, use_container_width=True, config={"displayModeBar": False})

# ──────────────────────────────────────────────
# EXECUTIVE REPORT & COMPARISON DOWNLOAD
# ──────────────────────────────────────────────
section("📑", "Executive Report & Baseline vs LLM Comparison")

rep_col1, rep_col2 = st.columns([2, 1])

with rep_col1:
    st.markdown(f"""
    <div style="background:rgba(16,185,129,0.05);border:1px solid rgba(16,185,129,0.2);border-radius:14px;padding:1.4rem;margin-bottom:1rem;">
        <h4 style="color:#34d399;margin-top:0;font-family:'Space Grotesk',sans-serif;">🌿 Baseline vs LLM-Powered Performance Summary</h4>
        <p style="color:#cbd5e1;font-size:0.88rem;line-height:1.6;">
            The LLM-powered closed-loop controller (Active Backend: <b style="color:#60a5fa;">{config.LLM_BACKEND.upper()}</b>) actively adapts setpoint boundaries per timestep.
            Download the comprehensive Markdown report or raw CSV comparison dataset below for technical audit.
        </p>
    </div>
    """, unsafe_allow_html=True)

with rep_col2:
    st.markdown("<div style='height:5px;'></div>", unsafe_allow_html=True)
    st.download_button(
        label="📥 Download Full Report (.md)",
        data=md_report,
        file_name=f"EcoLoop_Executive_Report_{config.LLM_BACKEND}.md",
        mime="text/markdown",
        key="btn_main_md",
        use_container_width=True,
    )
    st.download_button(
        label="📊 Download Comparison CSV (.csv)",
        data=csv_report,
        file_name=f"EcoLoop_Comparison_{config.LLM_BACKEND}.csv",
        mime="text/csv",
        key="btn_main_csv",
        use_container_width=True,
    )

with st.expander("📖 Live Report Preview (Markdown)", expanded=False):
    st.markdown(md_report)

# ──────────────────────────────────────────────
# RAW DATA
# ──────────────────────────────────────────────
with st.expander("📋 Raw Metrics Table", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Baseline Metrics**")
        st.dataframe(pd.DataFrame([baseline_m]).T.rename(columns={0: "Value"}), use_container_width=True)
    with c2:
        st.markdown("**AI Closed-Loop Metrics**")
        st.dataframe(pd.DataFrame([ai_m]).T.rename(columns={0: "Value"}), use_container_width=True)

with st.expander("📄 Simulation Log — AI Closed-Loop (first 200 rows)", expanded=False):
    st.dataframe(a_df.head(200), use_container_width=True)

# ──────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────
st.markdown("""
<div class="eco-footer">
    <span>Eco-Loop Building Agent</span> · EnergyPlus 26.1 + Python EMS · LLM Closed-Loop HVAC<br>
    SmOffPSZ · New Delhi, India · Dashboard built with Streamlit + Plotly
</div>
""", unsafe_allow_html=True)
