"""
main.py - Eco-Loop Building Agent — CLI Entry Point

Commands:
    python app/main.py run            Run both baseline and AI simulations
    python app/main.py run --mode ai  Run only AI closed-loop
    python app/main.py dashboard      Launch the Streamlit dashboard
    python app/main.py mcp            Start the MCP server
    python app/main.py report         Print performance summary from existing logs
"""

import sys
import os
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def cmd_run(mode: str):
    """Run EnergyPlus simulations."""
    script = os.path.join(os.path.dirname(__file__), "energyplus_runner.py")
    subprocess.run([sys.executable, script, "--mode", mode], check=True)


def cmd_dashboard():
    """Launch Streamlit dashboard."""
    script = os.path.join(os.path.dirname(__file__), "dashboard.py")
    subprocess.run(
        ["streamlit", "run", script, "--server.headless", "false"],
        check=True
    )


def cmd_mcp():
    """Start the MCP server."""
    script = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "server.py")
    subprocess.run([sys.executable, script], check=True)


def cmd_report():
    """Print performance report from existing simulation logs."""
    from optimizer import get_full_report
    report = get_full_report()
    baseline = report["baseline"]
    ai = report["ai_controlled"]
    savings = report["savings"]

    if not baseline or not ai:
        print("❌ No simulation data found. Run: python app/main.py run")
        return

    print("\n" + "=" * 65)
    print("  ECO-LOOP AGENT — PERFORMANCE REPORT")
    print("=" * 65)
    print(f"{'Metric':<38} {'Baseline':>10} {'AI':>10} {'Change':>10}")
    print("-" * 65)

    rows = [
        ("Total HVAC Energy (kWh)", baseline.get("total_energy_kwh"), ai.get("total_energy_kwh")),
        ("Peak Demand (kW)", baseline.get("peak_demand_kw"), ai.get("peak_demand_kw")),
        ("Carbon Emissions (kg CO₂)", baseline.get("carbon_emissions_kg"), ai.get("carbon_emissions_kg")),
        ("Energy Cost (₹)", baseline.get("energy_cost_inr"), ai.get("energy_cost_inr")),
        ("Comfort Violations (timesteps)", baseline.get("comfort_violations_timesteps"), ai.get("comfort_violations_timesteps")),
    ]
    for label, b, a in rows:
        change = f"{((a - b) / abs(b) * 100):+.1f}%" if b else "N/A"
        print(f"{label:<38} {str(b):>10} {str(a):>10} {change:>10}")

    print("=" * 65)
    print(f"\n💚 Energy savings: {savings.get('energy_savings_pct', 0):+.1f}%")
    print(f"💚 Peak demand reduction: {savings.get('peak_demand_reduction_pct', 0):+.1f}%")
    print(f"💚 Carbon reduction: {savings.get('carbon_reduction_pct', 0):+.1f}%")
    print(f"💚 Cost savings: ₹{savings.get('cost_savings_inr', 0):.2f}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Eco-Loop Building Agent — Autonomous HVAC Optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app/main.py run              # Run both simulations
  python app/main.py run --mode ai    # Run only AI mode
  python app/main.py dashboard        # Launch Streamlit UI
  python app/main.py report           # Print terminal summary
  python app/main.py mcp              # Start MCP server
        """,
    )
    subparsers = parser.add_subparsers(dest="command")

    # run
    run_parser = subparsers.add_parser("run", help="Run EnergyPlus simulations")
    run_parser.add_argument("--mode", choices=["baseline", "ai", "both"], default="both")

    # dashboard
    subparsers.add_parser("dashboard", help="Launch Streamlit dashboard")

    # mcp
    subparsers.add_parser("mcp", help="Start MCP server")

    # report
    subparsers.add_parser("report", help="Print performance report from existing logs")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args.mode)
    elif args.command == "dashboard":
        cmd_dashboard()
    elif args.command == "mcp":
        cmd_mcp()
    elif args.command == "report":
        cmd_report()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
