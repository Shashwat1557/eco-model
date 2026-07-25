"""
energyplus_runner.py - Run EnergyPlus simulations (Baseline + AI Closed-Loop)

Usage:
    python energyplus_runner.py              # Run both baseline and AI modes
    python energyplus_runner.py --mode baseline
    python energyplus_runner.py --mode ai
"""

import sys
import os
import json
import csv
import shutil
import argparse

# EnergyPlus Python API path
sys.path.insert(0, "/Applications/EnergyPlus-26-1-0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pyenergyplus.api import EnergyPlusAPI
import config
from controller import EcoLoopController


def run_simulation(mode: str) -> dict:
    """
    Run a single EnergyPlus simulation in either 'baseline' or 'ai' mode.
    Returns summary metrics dict.
    """
    print(f"\n{'='*60}")
    print(f"  STARTING SIMULATION — MODE: {mode.upper()}")
    print(f"{'='*60}")

    output_dir = config.OUTPUT_DIR_BASELINE if mode == "baseline" else config.OUTPUT_DIR_AI
    log_csv = os.path.join(config.PROJECT_ROOT, "output", f"log_{mode}.csv")

    os.makedirs(output_dir, exist_ok=True)

    api = EnergyPlusAPI()
    controller = EcoLoopController(api=api, mode=mode, log_csv=log_csv)

    # Create simulation state
    state = api.state_manager.new_state()

    # Register callback: end of each zone timestep
    # Signature: (state: c_void_p, callback_fn: function) -> None
    api.runtime.callback_end_zone_timestep_after_zone_reporting(
        state, controller.timestep_callback
    )

    # Launch EnergyPlus
    exit_code = api.runtime.run_energyplus(
        state,
        [
            "-w", config.EPW_FILE,
            "-d", output_dir,
            config.IDF_FILE,
        ],
    )

    if exit_code != 0:
        print(f"[Runner] EnergyPlus returned exit code {exit_code}")

    # Save timestep log
    controller.save_log()

    # Free EnergyPlus state memory
    api.state_manager.delete_state(state)

    metrics = controller.get_summary_metrics()
    print(f"\n[Runner] {mode.upper()} Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    return metrics


def save_comparison(baseline_metrics: dict, ai_metrics: dict):
    """Write side-by-side comparison CSV."""
    os.makedirs(os.path.dirname(config.COMPARISON_CSV), exist_ok=True)

    rows = []
    keys = [k for k in baseline_metrics if k != "mode"]
    for k in keys:
        bval = baseline_metrics.get(k, 0)
        aval = ai_metrics.get(k, 0)
        try:
            if isinstance(bval, (int, float)) and bval != 0:
                change_pct = round((aval - bval) / abs(bval) * 100, 1)
            else:
                change_pct = None
        except Exception:
            change_pct = None

        rows.append({
            "metric": k,
            "baseline": bval,
            "ai_controlled": aval,
            "change_pct": change_pct,
        })

    with open(config.COMPARISON_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "baseline", "ai_controlled", "change_pct"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[Runner] Comparison saved → {config.COMPARISON_CSV}")
    return rows


def print_summary(comparison_rows: list, baseline: dict, ai: dict):
    """Print a formatted performance summary to terminal."""
    print(f"\n{'='*60}")
    print("  ECO-LOOP CLOSED-LOOP PERFORMANCE SUMMARY")
    print(f"{'='*60}")
    print(f"{'Metric':<35} {'Baseline':>12} {'AI':>12} {'Change':>10}")
    print("-" * 70)
    for row in comparison_rows:
        change_str = f"{row['change_pct']:+.1f}%" if row['change_pct'] is not None else "N/A"
        print(
            f"{row['metric']:<35} {str(row['baseline']):>12} {str(row['ai_controlled']):>12} {change_str:>10}"
        )
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Eco-Loop Building Agent Simulation Runner")
    parser.add_argument(
        "--mode",
        choices=["baseline", "ai", "both"],
        default="both",
        help="Simulation mode to run (default: both)",
    )
    args = parser.parse_args()

    baseline_metrics = None
    ai_metrics = None

    if args.mode in ("baseline", "both"):
        baseline_metrics = run_simulation("baseline")

    if args.mode in ("ai", "both"):
        ai_metrics = run_simulation("ai")

    if baseline_metrics and ai_metrics:
        comparison = save_comparison(baseline_metrics, ai_metrics)
        print_summary(comparison, baseline_metrics, ai_metrics)
        print("✅ Run: streamlit run app/dashboard.py  to visualize results.")
    elif baseline_metrics:
        print("\n[Runner] Baseline complete. Run --mode ai next.")
    elif ai_metrics:
        print("\n[Runner] AI-controlled simulation complete.")


if __name__ == "__main__":
    main()