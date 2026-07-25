# Eco-Loop Building Agent — System Architecture

## Overview

**Eco-Loop** is an autonomous closed-loop building energy optimization system built for the hackathon. It pairs **EnergyPlus 26.1** (physics-based simulation engine) with an **LLM-driven Cognitive Engine** and **MCP (Model Context Protocol)** server to dynamically optimize HVAC setpoints, reduce energy consumption, and maintain occupant thermal comfort.

---

## Architecture Diagram

```
 ┌─────────────────────────────────────────────────────────┐
 │               EnergyPlus Simulation Engine              │
 │  SmOffPSZ.idf + IND New Delhi TMYx EPW Weather File     │
 │                                                         │
 │  Python EMS API Callback:                               │
 │    callback_end_zone_timestep_after_zone_reporting()    │
 │                                                         │
 │  Sensors: Zone Temp · Outdoor Temp · HVAC Power         │
 │  Actuators: Heating Setpoint · Cooling Setpoint         │
 └──────────────────┬──────────────────────────────────────┘
                    │  Telemetry (every 10 min timestep)
                    ▼
 ┌─────────────────────────────────────────────────────────┐
 │            EcoLoopController (app/controller.py)        │
 │  - Reads all sensor handles via api.exchange            │
 │  - Computes PMV comfort estimate                        │
 │  - Calls LLM Agent every N timesteps                    │
 │  - Writes setpoint overrides via actuator handles       │
 │  - Logs every timestep to CSV                           │
 └──────────────────┬──────────────────────────────────────┘
                    │  Every N timesteps (default: 4)
                    ▼
 ┌─────────────────────────────────────────────────────────┐
 │         EcoLoopLLMAgent (app/llm_agent.py)              │
 │                                                         │
 │  Backend options:                                       │
 │    1. rule_based  — deterministic heuristic (default)   │
 │    2. ollama      — local LLM (Llama3/Mistral/Qwen)     │
 │    3. openai      — OpenAI GPT-4o-mini                  │
 │                                                         │
 │  Output: (heating_setpoint, cooling_setpoint)           │
 └──────────────────┬──────────────────────────────────────┘
                    │  Setpoint pair (°C)
                    ▼
 ┌─────────────────────────────────────────────────────────┐
 │       Forward Injection via EMS Actuator Handle         │
 │  api.exchange.set_actuator_value(state, handle, value)  │
 └──────────────────┬──────────────────────────────────────┘
                    │  Timestep log CSV
                    ▼
 ┌─────────────────────────────────────────────────────────┐
 │         Streamlit Dashboard (app/dashboard.py)          │
 │  - Baseline vs AI comparative charts                    │
 │  - Energy, Peak Demand, Carbon, Cost, PMV Comfort       │
 └─────────────────────────────────────────────────────────┘
```

---

## Component Descriptions

### 1. Simulation Engine — `app/energyplus_runner.py`

Runs two EnergyPlus simulation passes:

| Mode | Description |
|---|---|
| `baseline` | No actuator overrides; EnergyPlus runs scheduled setpoints |
| `ai` | EMS Python callback injects AI-computed setpoints every timestep |

The `pyenergyplus` C-extension API allows registering callbacks directly into the EnergyPlus simulation loop.

### 2. EMS Controller — `app/controller.py`

Registers a `callback_end_zone_timestep_after_zone_reporting` callback that:
1. Skips warmup days
2. Waits for `api_data_fully_ready()` before acquiring handles
3. Reads sensor variables: `Zone Mean Air Temperature`, `Site Outdoor Air Drybulb Temperature`, `Facility Total HVAC Electricity Demand Rate`, `Schedule Value` (occupancy)
4. Calls LLM agent every `LLM_CALL_INTERVAL_TIMESTEPS` timesteps
5. Writes `heating_setpoint` and `cooling_setpoint` actuators

### 3. Cognitive Engine — `app/llm_agent.py`

Three backend options configurable via `config.LLM_BACKEND`:

**Rule-Based (Default)**
- Pre-cooling strategy: pre-cool building before peak hours (09:00, 17:00)
- Setback strategy: widen deadband when unoccupied (18°C / 27°C)
- Comfort correction: nudge setpoints when PMV > ±0.5
- Peak demand reduction: relax comfort band during grid peak periods

**Ollama (Local LLM)**
- Sends structured prompt with sensor readings to `http://localhost:11434/api/generate`
- Parses JSON response for `{heating_setpoint, cooling_setpoint, reasoning}`
- Automatic fallback to rule engine on network/parse error

**OpenAI**
- Uses GPT-4o-mini with structured system + user prompt
- Same JSON parsing and fallback behavior

### 4. MCP Server — `mcp_server/server.py`

Exposes four tools over the MCP stdio protocol:

| Tool | Description |
|---|---|
| `get_building_telemetry` | Read latest real-time sensor readings |
| `override_setpoints` | Inject HVAC setpoint overrides into active simulation |
| `run_comfort_analysis` | Evaluate thermal comfort (PMV) and recommendations |
| `get_simulation_summary` | Aggregate baseline vs AI performance comparison |

### 5. Dashboard — `app/dashboard.py`

Streamlit-based visual analytics showing:
- **KPI cards**: Energy (kWh), Peak Demand (kW), Carbon (kg CO₂), Cost (₹), Comfort Violations
- **Timeseries tabs**: HVAC Power, Zone Temperature, PMV Comfort Index, AI Setpoint Overrides
- **Comparison bar chart**: Baseline vs AI side-by-side
- **Raw data tables**: Full simulation logs

---

## Prompt Engineering Strategy

All LLM prompts are structured to produce **deterministic JSON output**:

```
{
  "heating_setpoint": <float>,
  "cooling_setpoint": <float>,
  "reasoning": "<brief explanation>"
}
```

The system prompt includes explicit constraint information (setpoint bounds, deadband, comfort targets), reducing hallucination and ensuring valid numeric outputs.

**Temperature = 0.2** is used for LLM calls to minimize variance and ensure repeatability across simulation steps.

---

## Latency Management

Since EnergyPlus timesteps run in real-time (~50–200ms per timestep), LLM calls are gated by `LLM_CALL_INTERVAL_TIMESTEPS = 4` (configurable), meaning:
- The rule engine runs every single timestep (near-zero latency)
- LLM is called once every 4 timesteps (~40 minutes simulated time)
- The previous setpoint is held between calls (hysteresis)
- On any LLM timeout/error, the rule engine immediately takes over

---

## Building Model

- **File**: `models/SmOffPSZ.idf`
- **Type**: Small Office PSZ (Packaged Single Zone HVAC)
- **Location**: New Delhi, India (`IND_DL_New.Delhi-Gandhi.Intl.AP.421810_TMYx.2011-2025.epw`)
- **Thermostat type**: `ThermostatSetpoint:DualSetpoint` with EMS actuator override

---

## Energy Conservation Measures (ECMs) Implemented

| ECM | Strategy |
|---|---|
| Pre-cooling | Cool building before peak grid hours to shift load |
| Setback scheduling | Widen setpoint band during unoccupied hours |
| Demand response | Relax comfort band during peak demand windows |
| Comfort-driven correction | Nudge setpoints based on PMV feedback |

---

## Running the System

```bash
# Install dependencies
pip install -r requirements.txt

# Run both simulations (baseline + AI)
python app/main.py run

# View dashboard
streamlit run app/dashboard.py

# Start MCP server
python mcp_server/server.py

# Print terminal report
python app/main.py report
```
