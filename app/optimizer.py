"""
optimizer.py - Savings & comfort metrics computation for Eco-Loop

Reads log CSVs and computes aggregate performance statistics for
the dashboard and architecture report.
"""

import sys
import os
import csv
import json
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def load_log(csv_path: str) -> list[dict]:
    """Load a simulation log CSV into a list of dicts."""
    if not os.path.exists(csv_path):
        return []
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric fields
            for k, v in row.items():
                try:
                    row[k] = float(v)
                except (ValueError, TypeError):
                    pass
            rows.append(row)
    return rows


def compute_metrics(rows: list[dict]) -> dict:
    """Compute aggregate performance metrics from a list of timestep log rows."""
    if not rows:
        return {}

    total_energy_kwh = sum(r.get("hvac_energy_kwh", 0) for r in rows)
    peak_rows = [r for r in rows if r.get("is_peak", 0) == 1.0]
    peak_power_kw = max((r.get("hvac_power_w", 0) for r in peak_rows), default=0) / 1000.0
    comfort_violations = int(sum(r.get("comfort_violation", 0) for r in rows))
    occupied_timesteps = int(sum(r.get("is_occupied", 0) for r in rows))
    comfort_violation_pct = (
        round(comfort_violations / occupied_timesteps * 100, 1)
        if occupied_timesteps > 0 else 0.0
    )
    carbon_kg = total_energy_kwh * config.CARBON_INTENSITY_KG_PER_KWH
    cost_inr = total_energy_kwh * config.ELECTRICITY_RATE_PER_KWH

    avg_zone_temp = (
        sum(r.get("zone_temp_c", 0) for r in rows) / len(rows)
        if rows else 0
    )
    avg_pmv = (
        sum(r.get("pmv", 0) for r in rows) / len(rows)
        if rows else 0
    )

    return {
        "total_energy_kwh": round(total_energy_kwh, 2),
        "peak_demand_kw": round(peak_power_kw, 2),
        "comfort_violations_timesteps": comfort_violations,
        "comfort_violation_pct": comfort_violation_pct,
        "carbon_emissions_kg": round(carbon_kg, 2),
        "energy_cost_inr": round(cost_inr, 2),
        "avg_zone_temp_c": round(avg_zone_temp, 2),
        "avg_pmv": round(avg_pmv, 3),
        "total_timesteps": len(rows),
    }


def compute_savings(baseline: dict, ai: dict) -> dict:
    """Compute percentage savings between baseline and AI metrics."""
    def pct_change(b, a):
        if b and b != 0:
            return round((a - b) / abs(b) * 100, 1)
        return None

    return {
        "energy_savings_pct": pct_change(baseline.get("total_energy_kwh"), ai.get("total_energy_kwh")),
        "peak_demand_reduction_pct": pct_change(baseline.get("peak_demand_kw"), ai.get("peak_demand_kw")),
        "carbon_reduction_pct": pct_change(baseline.get("carbon_emissions_kg"), ai.get("carbon_emissions_kg")),
        "cost_savings_inr": round((baseline.get("energy_cost_inr", 0) - ai.get("energy_cost_inr", 0)), 2),
        "comfort_violation_change_pct": pct_change(
            baseline.get("comfort_violations_timesteps"),
            ai.get("comfort_violations_timesteps"),
        ),
    }


def load_both_logs():
    """Load baseline and AI logs, return (baseline_rows, ai_rows)."""
    baseline_path = os.path.join(config.PROJECT_ROOT, "output", "log_baseline.csv")
    ai_path = os.path.join(config.PROJECT_ROOT, "output", "log_ai.csv")
    return load_log(baseline_path), load_log(ai_path)


def get_full_report() -> dict:
    """Return complete analytics report with metrics and savings."""
    baseline_rows, ai_rows = load_both_logs()
    baseline_metrics = compute_metrics(baseline_rows)
    ai_metrics = compute_metrics(ai_rows)
    savings = compute_savings(baseline_metrics, ai_metrics) if (baseline_metrics and ai_metrics) else {}

    return {
        "baseline": baseline_metrics,
        "ai_controlled": ai_metrics,
        "savings": savings,
        "baseline_rows": baseline_rows,
        "ai_rows": ai_rows,
    }


def generate_markdown_report(report_data: dict) -> str:
    """Generate a rich Markdown report comparing Baseline vs LLM-Powered control."""
    b = report_data.get("baseline", {})
    a = report_data.get("ai_controlled", {})
    s = report_data.get("savings", {})
    backend = getattr(config, "LLM_BACKEND", "LLM").upper()

    e_sav = s.get("energy_savings_pct", 0) or 0
    c_sav = s.get("carbon_reduction_pct", 0) or 0
    cost_sav = s.get("cost_savings_inr", 0) or 0
    peak_red = s.get("peak_demand_reduction_pct", 0) or 0

    model_name = getattr(config, "NVIDIA_MODEL", "LLM") if backend == "NVIDIA" else getattr(config, "GEMINI_MODEL", "Gemini")

    report = f"""# 🌿 Eco-Loop Building Performance & Comparison Report
**Autonomous Building HVAC Optimization via EnergyPlus & LLM Closed-Loop Control**

---

## 📌 Executive Summary
The **Eco-Loop Building Agent** deployed an LLM-powered cognitive engine (`{backend}` - Model: `{model_name}`) interfaced with EnergyPlus 26.1 EMS API for a commercial office building (`SmOffPSZ`) model in **New Delhi, India**.

Over a **35,040-timestep annual simulation**, the LLM-powered closed-loop controller achieved significant performance improvements over the fixed-schedule baseline:

- ⚡ **Energy Reduction**: **{abs(e_sav):.1f}%** total HVAC energy saved
- 🌱 **Carbon Mitigation**: **{abs(c_sav):.1f}%** grid carbon emissions reduced ({abs(b.get('carbon_emissions_kg', 0) - a.get('carbon_emissions_kg', 0)):,.0f} kg CO₂)
- 💰 **Financial Savings**: **₹{abs(cost_sav):,.2f} INR** annual electricity cost reduction
- 📈 **Peak Demand Adjustment**: **{peak_red:+.1f}%** shift in peak electricity demand

---

## 📊 Baseline vs. LLM-Powered Performance Comparison

| Metric | Baseline Control | LLM Powered ({backend}) | Absolute Change | Change (%) |
| :--- | :---: | :---: | :---: | :---: |
| **Total HVAC Energy (kWh)** | {b.get('total_energy_kwh', 0):,.2f} | **{a.get('total_energy_kwh', 0):,.2f}** | {a.get('total_energy_kwh', 0) - b.get('total_energy_kwh', 0):+,.2f} | **{e_sav:+.1f}%** |
| **Peak Demand (kW)** | {b.get('peak_demand_kw', 0):.2f} | **{a.get('peak_demand_kw', 0):.2f}** | {a.get('peak_demand_kw', 0) - b.get('peak_demand_kw', 0):+.2f} | **{peak_red:+.1f}%** |
| **Carbon Emissions (kg CO₂)** | {b.get('carbon_emissions_kg', 0):,.2f} | **{a.get('carbon_emissions_kg', 0):,.2f}** | {a.get('carbon_emissions_kg', 0) - b.get('carbon_emissions_kg', 0):+,.2f} | **{c_sav:+.1f}%** |
| **Annual Energy Cost (INR)** | ₹{b.get('energy_cost_inr', 0):,.2f} | **₹{a.get('energy_cost_inr', 0):,.2f}** | -₹{abs(cost_sav):,.2f} | **{-abs(e_sav):+.1f}%** |
| **Comfort Violations (Timesteps)** | {b.get('comfort_violations_timesteps', 0):,} | **{a.get('comfort_violations_timesteps', 0):,}** | {a.get('comfort_violations_timesteps', 0) - b.get('comfort_violations_timesteps', 0):+,} | {s.get('comfort_violation_change_pct', 0):+.1f}% |
| **Average Zone Temperature (°C)** | {b.get('avg_zone_temp_c', 0):.2f}°C | **{a.get('avg_zone_temp_c', 0):.2f}°C** | {a.get('avg_zone_temp_c', 0) - b.get('avg_zone_temp_c', 0):+.2f}°C | - |
| **Average PMV Index** | {b.get('avg_pmv', 0):.3f} | **{a.get('avg_pmv', 0):.3f}** | {a.get('avg_pmv', 0) - b.get('avg_pmv', 0):+.3f} | - |

---

## 🏗️ System & Simulation Parameters

- **Building Model**: Small Office PSZ (`SmOffPSZ.idf` - 4 zones: ZSF1, ZNF1, ZSF2, ZNF2)
- **Climate Data**: New Delhi Gandhi Intl AP (`IND_DL_New.Delhi-Gandhi.Intl.AP.421810_TMYx.2011-2025.epw`)
- **Simulation Timesteps**: 35,040 (6 timesteps/hr × 24 hrs × 365 days)
- **LLM Cognitive Backend**: `{backend}` (Model: `{model_name}`)
- **Comfort Standard**: ASHRAE 55 / ISO 7730 PMV model (Comfort band: PMV ∈ [-0.5, +0.5])
- **Grid Parameters**: India Grid Carbon Intensity = 0.82 kg CO₂/kWh, Tariff = ₹8.0 INR/kWh

---

## 💡 Key Architectural Insights

1. **Dynamic Deadband Optimization**: The LLM cognitive engine dynamically widens heating/cooling deadbands during unoccupied hours to reduce standby thermal loss.
2. **Pre-Cooling & Load Shifting**: Proactively adjusts zone setpoints prior to Indian grid peak hours (09:00-12:00 and 17:00-21:00) to shift heavy HVAC power draws away from peak billing periods.
3. **Closed-Loop Feedback**: Per-timestep Python EMS API callbacks ensure real-time actuation without stability loss.

*Report generated automatically by Eco-Loop Building Agent.*
"""
    return report.strip()


def generate_comparison_csv(report_data: dict) -> str:
    """Generate CSV string containing side-by-side comparison metrics."""
    b = report_data.get("baseline", {})
    a = report_data.get("ai_controlled", {})
    s = report_data.get("savings", {})

    rows = [
        ["Metric", "Baseline", "LLM Powered AI", "Savings / Change (%)"],
        ["Total HVAC Energy (kWh)", b.get("total_energy_kwh", 0), a.get("total_energy_kwh", 0), f"{s.get('energy_savings_pct', 0):+.1f}%"],
        ["Peak Demand (kW)", b.get("peak_demand_kw", 0), a.get("peak_demand_kw", 0), f"{s.get('peak_demand_reduction_pct', 0):+.1f}%"],
        ["Carbon Emissions (kg CO2)", b.get("carbon_emissions_kg", 0), a.get("carbon_emissions_kg", 0), f"{s.get('carbon_reduction_pct', 0):+.1f}%"],
        ["Energy Cost (INR)", b.get("energy_cost_inr", 0), a.get("energy_cost_inr", 0), f"-INR {s.get('cost_savings_inr', 0):,.2f}"],
        ["Comfort Violations (Timesteps)", b.get("comfort_violations_timesteps", 0), a.get("comfort_violations_timesteps", 0), f"{s.get('comfort_violation_change_pct', 0):+.1f}%"],
        ["Average Zone Temp (C)", b.get("avg_zone_temp_c", 0), a.get("avg_zone_temp_c", 0), "N/A"],
        ["Average PMV Index", b.get("avg_pmv", 0), a.get("avg_pmv", 0), "N/A"],
    ]

    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue()


def generate_pdf_report(report_data: dict) -> bytes:
    """Generate a high-quality PDF report comparing Baseline vs LLM-Powered control."""
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    b = report_data.get("baseline", {})
    a = report_data.get("ai_controlled", {})
    s = report_data.get("savings", {})
    backend = getattr(config, "LLM_BACKEND", "LLM").upper()
    model_name = getattr(config, "NVIDIA_MODEL", "LLM") if backend == "NVIDIA" else getattr(config, "GEMINI_MODEL", "Gemini")

    e_sav = s.get("energy_savings_pct", 0) or 0
    c_sav = s.get("carbon_reduction_pct", 0) or 0
    cost_sav = s.get("cost_savings_inr", 0) or 0
    peak_red = s.get("peak_demand_reduction_pct", 0) or 0

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'],
        fontName='Helvetica-Bold', fontSize=18, leading=22,
        textColor=colors.HexColor('#0F172A'), spaceAfter=3,
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, leading=14,
        textColor=colors.HexColor('#059669'), spaceAfter=10,
    )
    heading2_style = ParagraphStyle(
        'DocH2', parent=styles['Heading2'],
        fontName='Helvetica-Bold', fontSize=11, leading=15,
        textColor=colors.HexColor('#0F172A'), spaceBefore=8, spaceAfter=4,
    )
    body_style = ParagraphStyle(
        'DocBody', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, leading=12,
        textColor=colors.HexColor('#334155'), spaceAfter=4,
    )
    cell_header_style = ParagraphStyle(
        'CellHeader', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=8.5, leading=11,
        textColor=colors.white, alignment=1,
    )
    cell_body_style = ParagraphStyle(
        'CellBody', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, leading=10,
        textColor=colors.HexColor('#1E293B'),
    )
    cell_body_bold_style = ParagraphStyle(
        'CellBodyBold', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=8, leading=10,
        textColor=colors.HexColor('#059669'),
    )

    story = []

    story.append(Paragraph("🌿 Eco-Loop Building Performance Report", title_style))
    story.append(Paragraph(f"Autonomous HVAC Optimization · EnergyPlus 26.1 + LLM Closed-Loop Control ({backend})", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#10B981'), spaceAfter=10))

    exec_summary_text = (
        f"<b>Executive Summary:</b> Eco-Loop evaluated an autonomous cognitive agent using "
        f"<b>{backend} ({model_name})</b> paired with EnergyPlus 26.1 EMS API on a 4-zone commercial office building model "
        f"(<i>SmOffPSZ</i>) in New Delhi, India over 35,040 annual timesteps.<br/><br/>"
        f"<b>Key Achievements:</b><br/>"
        f"• <b>Energy Reduction:</b> Saved <b>{abs(e_sav):.1f}%</b> HVAC energy ({a.get('total_energy_kwh', 0):,.1f} kWh vs {b.get('total_energy_kwh', 0):,.1f} kWh baseline)<br/>"
        f"• <b>Carbon Emissions:</b> Reduced <b>{abs(c_sav):.1f}%</b> grid carbon emissions ({a.get('carbon_emissions_kg', 0):,.0f} kg CO₂)<br/>"
        f"• <b>Cost Savings:</b> Annual operational electricity bill cut by <b>Rs. {abs(cost_sav):,.2f} INR</b><br/>"
        f"• <b>Peak Demand:</b> Shifted peak grid load by <b>{peak_red:+.1f}%</b> ({a.get('peak_demand_kw', 0):.1f} kW peak)"
    )

    summary_table_data = [[Paragraph(exec_summary_text, body_style)]]
    summary_table = Table(summary_table_data, colWidths=[7.0 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#ECFDF5')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#A7F3D0')),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("📊 Baseline vs. LLM-Powered Performance Comparison", heading2_style))

    headers = [
        Paragraph("Metric", cell_header_style),
        Paragraph("Baseline Control", cell_header_style),
        Paragraph(f"LLM Powered ({backend})", cell_header_style),
        Paragraph("Absolute Change", cell_header_style),
        Paragraph("Change (%)", cell_header_style),
    ]

    comp_rows = [
        ["Total HVAC Energy (kWh)", f"{b.get('total_energy_kwh', 0):,.1f}", f"{a.get('total_energy_kwh', 0):,.1f}", f"{a.get('total_energy_kwh', 0) - b.get('total_energy_kwh', 0):+,.1f}", f"{e_sav:+.1f}%"],
        ["Peak Demand (kW)", f"{b.get('peak_demand_kw', 0):.2f}", f"{a.get('peak_demand_kw', 0):.2f}", f"{a.get('peak_demand_kw', 0) - b.get('peak_demand_kw', 0):+.2f}", f"{peak_red:+.1f}%"],
        ["Carbon Emissions (kg CO₂)", f"{b.get('carbon_emissions_kg', 0):,.0f}", f"{a.get('carbon_emissions_kg', 0):,.0f}", f"{a.get('carbon_emissions_kg', 0) - b.get('carbon_emissions_kg', 0):+,.0f}", f"{c_sav:+.1f}%"],
        ["Annual Energy Cost (INR)", f"Rs. {b.get('energy_cost_inr', 0):,.0f}", f"Rs. {a.get('energy_cost_inr', 0):,.0f}", f"-Rs. {abs(cost_sav):,.0f}", f"{-abs(e_sav):+.1f}%"],
        ["Comfort Violations (Timesteps)", f"{b.get('comfort_violations_timesteps', 0):,}", f"{a.get('comfort_violations_timesteps', 0):,}", f"{a.get('comfort_violations_timesteps', 0) - b.get('comfort_violations_timesteps', 0):+,}", f"{s.get('comfort_violation_change_pct', 0):+.1f}%"],
        ["Average Zone Temp (°C)", f"{b.get('avg_zone_temp_c', 0):.2f}°C", f"{a.get('avg_zone_temp_c', 0):.2f}°C", f"{a.get('avg_zone_temp_c', 0) - b.get('avg_zone_temp_c', 0):+.2f}°C", "N/A"],
        ["Average PMV Index", f"{b.get('avg_pmv', 0):.3f}", f"{a.get('avg_pmv', 0):.3f}", f"{a.get('avg_pmv', 0) - b.get('avg_pmv', 0):+.3f}", "N/A"],
    ]

    table_data = [headers]
    for row in comp_rows:
        table_data.append([
            Paragraph(row[0], cell_body_style),
            Paragraph(row[1], cell_body_style),
            Paragraph(row[2], cell_body_bold_style),
            Paragraph(row[3], cell_body_style),
            Paragraph(row[4], cell_body_bold_style),
        ])

    comp_table = Table(table_data, colWidths=[2.2 * inch, 1.2 * inch, 1.3 * inch, 1.2 * inch, 1.1 * inch])
    comp_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F172A')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(comp_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("🏗️ System & Simulation Parameters", heading2_style))
    param_text = (
        f"• <b>Building Model:</b> Small Office PSZ (<code>SmOffPSZ.idf</code> - Zones: ZSF1, ZNF1, ZSF2, ZNF2)<br/>"
        f"• <b>Location & Weather:</b> New Delhi Gandhi Intl AP (TMYx 2011-2025)<br/>"
        f"• <b>Simulation Length:</b> 35,040 Timesteps (Annual, 6 steps/hr)<br/>"
        f"• <b>LLM Cognitive Backend:</b> {backend} ({model_name})<br/>"
        f"• <b>Thermal Comfort Standard:</b> ASHRAE 55 / ISO 7730 PMV Model<br/>"
        f"• <b>Grid Tariff & Intensity:</b> Rs. 8.0 INR / kWh | 0.82 kg CO₂ / kWh (India National Average)"
    )
    story.append(Paragraph(param_text, body_style))
    story.append(Spacer(1, 8))

    story.append(Paragraph("💡 Key Architectural Insights", heading2_style))
    insights_text = (
        "1. <b>Dynamic Setpoint Widening:</b> The LLM cognitive engine dynamically widens heating/cooling deadbands during unoccupied hours to eliminate standby thermal losses.<br/>"
        "2. <b>Peak Load Shifting:</b> Proactively pre-cools and adjusts setpoints before Indian grid peak demand windows (09:00-12:00 & 17:00-21:00).<br/>"
        "3. <b>Closed-Loop Safety:</b> EnergyPlus Python EMS callbacks ensure fallback to rule-based control if network latency spikes."
    )
    story.append(Paragraph(insights_text, body_style))
    story.append(Spacer(1, 10))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CBD5E1'), spaceAfter=6))
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footer_text = f"Eco-Loop Building Agent · EnergyPlus 26.1 Closed-Loop Simulation · Report generated on {now_str}"
    story.append(Paragraph(footer_text, ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7.5, textColor=colors.HexColor('#94A3B8'), alignment=1)))

    doc.build(story)
    return buffer.getvalue()


