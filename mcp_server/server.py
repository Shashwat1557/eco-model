"""
mcp_server/server.py - Eco-Loop MCP Tool Server

Exposes building control tools via the Model Context Protocol (MCP):
  - get_building_telemetry: Read latest sensor readings
  - override_setpoints: Inject HVAC setpoint overrides
  - run_comfort_analysis: Evaluate thermal comfort metrics
  - get_simulation_summary: Return aggregate performance summary

Start with:
    python mcp_server/server.py
"""

import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import config
from controller import estimate_pmv
from optimizer import get_full_report, compute_metrics

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ──────────────────────────────────────────────
# SHARED STATE (updated by EnergyPlus controller)
# ──────────────────────────────────────────────
_telemetry_state: dict = {
    "zone_temp_c": 22.0,
    "outdoor_temp_c": 30.0,
    "hvac_power_w": 0.0,
    "heating_setpoint": config.DEFAULT_HEATING_SETPOINT,
    "cooling_setpoint": config.DEFAULT_COOLING_SETPOINT,
    "pmv": 0.0,
    "is_occupied": True,
    "hour": 12,
    "sim_day": 1,
    "timestep": 0,
}

_setpoint_override: dict = {
    "heating_setpoint": None,
    "cooling_setpoint": None,
}


def update_telemetry(data: dict):
    """Called by the EnergyPlus controller to push fresh sensor readings."""
    _telemetry_state.update(data)


def get_pending_overrides() -> dict:
    """Called by the EnergyPlus controller to pull pending setpoint overrides."""
    result = dict(_setpoint_override)
    _setpoint_override["heating_setpoint"] = None
    _setpoint_override["cooling_setpoint"] = None
    return result


# ──────────────────────────────────────────────
# MCP SERVER DEFINITION
# ──────────────────────────────────────────────
app = Server("eco-loop-building-agent")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_building_telemetry",
            description=(
                "Read the latest real-time sensor readings from the EnergyPlus building simulation. "
                "Returns zone temperature, outdoor temperature, HVAC power, occupancy status, "
                "PMV comfort index, and current setpoints."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="override_setpoints",
            description=(
                "Inject new HVAC heating and cooling setpoint overrides into the active EnergyPlus "
                "simulation. The values will be applied at the next timestep callback. "
                "Heating setpoint: 18–23°C. Cooling setpoint: 22–28°C. Deadband ≥ 2°C required."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "heating_setpoint": {
                        "type": "number",
                        "description": "New heating setpoint in °C (18.0–23.0)",
                        "minimum": 18.0,
                        "maximum": 23.0,
                    },
                    "cooling_setpoint": {
                        "type": "number",
                        "description": "New cooling setpoint in °C (22.0–28.0)",
                        "minimum": 22.0,
                        "maximum": 28.0,
                    },
                },
                "required": ["heating_setpoint", "cooling_setpoint"],
            },
        ),
        types.Tool(
            name="run_comfort_analysis",
            description=(
                "Run a thermal comfort analysis using the current building state. "
                "Returns Predicted Mean Vote (PMV), comfort zone status, and recommendations."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "zone_temp_c": {"type": "number", "description": "Zone temperature in °C"},
                    "outdoor_temp_c": {"type": "number", "description": "Outdoor temperature in °C"},
                    "is_occupied": {"type": "boolean", "description": "Whether the zone is currently occupied"},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_simulation_summary",
            description=(
                "Return aggregate performance summary comparing baseline vs AI closed-loop "
                "simulation runs. Includes total energy, peak demand, carbon emissions, "
                "cost, and comfort violation statistics."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_building_telemetry":
        result = {
            "status": "ok",
            "telemetry": _telemetry_state,
            "description": "Real-time EnergyPlus building sensor readings",
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "override_setpoints":
        h = float(arguments.get("heating_setpoint", config.DEFAULT_HEATING_SETPOINT))
        c = float(arguments.get("cooling_setpoint", config.DEFAULT_COOLING_SETPOINT))

        # Validate
        h = max(config.HEATING_SETPOINT_MIN, min(h, config.HEATING_SETPOINT_MAX))
        c = max(config.COOLING_SETPOINT_MIN, min(c, config.COOLING_SETPOINT_MAX))
        if c - h < config.SETPOINT_DEADBAND:
            c = h + config.SETPOINT_DEADBAND

        _setpoint_override["heating_setpoint"] = h
        _setpoint_override["cooling_setpoint"] = c

        result = {
            "status": "override_queued",
            "heating_setpoint": h,
            "cooling_setpoint": c,
            "message": f"Setpoint override queued: Heating={h}°C, Cooling={c}°C. Will apply at next EnergyPlus timestep.",
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "run_comfort_analysis":
        zone_temp = arguments.get("zone_temp_c", _telemetry_state["zone_temp_c"])
        outdoor_temp = arguments.get("outdoor_temp_c", _telemetry_state["outdoor_temp_c"])
        is_occupied = arguments.get("is_occupied", _telemetry_state["is_occupied"])

        pmv = estimate_pmv(float(zone_temp), float(outdoor_temp), bool(is_occupied))
        comfort_ok = abs(pmv) <= 0.5

        if pmv > 0.5:
            recommendation = f"Zone is too warm (PMV={pmv:.2f}). Lower cooling setpoint by {min(1.5, abs(pmv)):.1f}°C."
        elif pmv < -0.5:
            recommendation = f"Zone is too cold (PMV={pmv:.2f}). Raise heating setpoint by {min(1.5, abs(pmv)):.1f}°C."
        else:
            recommendation = f"Zone is within comfort bounds (PMV={pmv:.2f}). No action needed."

        result = {
            "status": "ok",
            "pmv": round(pmv, 3),
            "comfort_status": "WITHIN_BOUNDS" if comfort_ok else "VIOLATION",
            "pmv_lower_bound": config.PMV_COMFORT_MIN,
            "pmv_upper_bound": config.PMV_COMFORT_MAX,
            "zone_temp_c": zone_temp,
            "outdoor_temp_c": outdoor_temp,
            "is_occupied": is_occupied,
            "recommendation": recommendation,
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    elif name == "get_simulation_summary":
        report = get_full_report()
        result = {
            "status": "ok",
            "baseline": report["baseline"],
            "ai_controlled": report["ai_controlled"],
            "savings": report["savings"],
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    else:
        return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
async def main():
    print("[MCP Server] Eco-Loop Building Agent MCP Server starting...")
    print(f"[MCP Server] Listening on stdio (MCP protocol)")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
