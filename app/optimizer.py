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
