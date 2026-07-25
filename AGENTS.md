# Eco-Loop Building Agent — AGENTS.md

> **Purpose:** This file explains the full architecture, design decisions, and current state of the project so that any AI model or developer can understand and extend it without re-reading the entire codebase.

---

## What This Project Does

Eco-Loop is an **autonomous HVAC optimization agent** for a commercial office building in New Delhi, India. It uses:

1. **EnergyPlus 26.1** — physics-based building energy simulation engine
2. **Python EMS API** — hooks into EnergyPlus at every timestep to read sensors and override actuators
3. **LLM Cognitive Engine** — calls an LLM (NVIDIA NIM, Gemini, OpenAI, Ollama, or rule-based) to decide optimal heating/cooling setpoints
4. **Streamlit + Plotly Dashboard** — 3D interactive visualization of baseline vs AI-controlled performance

**Core loop (closed-loop control):**
```
EnergyPlus timestep → read zone temp, outdoor temp, HVAC power, hour
    → call LLM (or rule engine) with building state
    → LLM returns (heating_setpoint, cooling_setpoint)
    → write setpoints to EnergyPlus actuators
    → EnergyPlus advances physics
    → repeat for all 35,040 annual timesteps
```

**Result:** ~11.5% annual energy and carbon reduction vs fixed-schedule baseline.

---

## Directory Structure

```
eco-loop-agent/
├── app/
│   ├── config.py            # All constants, paths, API keys, LLM settings
│   ├── controller.py        # EnergyPlus EMS callback — sensor reads & actuator writes
│   ├── llm_agent.py         # LLM cognitive engine (NVIDIA, Gemini, OpenAI, Ollama, rules)
│   ├── prompts.py           # System prompt + per-timestep control prompt template
│   ├── optimizer.py         # Metrics computation and CSV loading for dashboard
│   ├── energyplus_runner.py # CLI entry point — runs baseline and/or AI simulation
│   ├── main.py              # Alternative CLI entry point (wraps energyplus_runner)
│   ├── dashboard.py         # Streamlit + Plotly 3D dashboard
│   └── tools.py             # (reserved for MCP tool registration)
├── mcp_server/
│   ├── server.py            # FastAPI MCP server exposing simulation tools via HTTP
│   └── tools.py             # MCP tool definitions (run_sim, get_report, etc.)
├── models/
│   ├── SmOffPSZ.idf         # EnergyPlus IDF: Small Office PSZ building model
│   └── IND_DL_New.Delhi-Gandhi.Intl.AP.421810_TMYx.2011-2025.epw  # Weather file
├── output/
│   ├── log_baseline.csv     # Per-timestep log: baseline simulation (~35,040 rows)
│   ├── log_ai.csv           # Per-timestep log: AI-controlled simulation (~35,040 rows)
│   └── simulation_comparison.csv  # Side-by-side metric comparison
├── docs/                    # Additional documentation
├── requirements.txt         # Python dependencies
├── venv/                    # Python 3.12 virtual environment
└── AGENTS.md                # This file
```

---

## File-by-File Reference

### `app/config.py`
Central configuration. **All tunable parameters live here.** Key settings:

| Variable | Current Value | Purpose |
|---|---|---|
| `LLM_BACKEND` | `"nvidia"` | Active backend: `"nvidia"`, `"gemini"`, `"openai"`, `"ollama"`, `"rule_based"` |
| `NVIDIA_API_KEY` | hardcoded | NVIDIA NIM API key — move to env var for production |
| `NVIDIA_MODEL` | `"deepseek-ai/deepseek-v4-flash"` | NVIDIA NIM model name |
| `GEMINI_API_KEY` | from `$GEMINI_API_KEY` env | Gemini API key |
| `GEMINI_MODEL` | `"gemini-2.5-flash"` | Gemini model name |
| `LLM_CALL_INTERVAL_TIMESTEPS` | `4` | How often to call the LLM (every N EnergyPlus steps) |
| `ENERGYPLUS_DIR` | `/Applications/EnergyPlus-26-1-0` | EnergyPlus install path (Mac) |
| `HEATING_SETPOINT_MIN/MAX` | `18.0 / 23.0 °C` | Allowed heating setpoint range |
| `COOLING_SETPOINT_MIN/MAX` | `22.0 / 28.0 °C` | Allowed cooling setpoint range |
| `SETPOINT_DEADBAND` | `2.0 °C` | Minimum gap between heating and cooling setpoints |
| `PEAK_HOURS` | `9–12, 17–21` | Peak electricity demand hours |
| `ELECTRICITY_RATE_PER_KWH` | `8.0 INR` | Indian grid tariff |
| `CARBON_INTENSITY_KG_PER_KWH` | `0.82` | India national average grid intensity |

---

### `app/controller.py`
**EnergyPlus EMS bridge.** Called once per zone timestep via Python API callback.

Key class: `EcoLoopController`

- **`timestep_callback(state)`** — main callback registered with EnergyPlus. Reads all sensors, computes PMV, calls `LLMAgent.decide_setpoints()`, writes setpoints to actuators, logs the timestep.
- **`_read_sensors(state)`** — reads zone air temperature, outdoor temp, HVAC energy meter, occupancy, hour-of-day from EnergyPlus.
- **`_write_setpoints(state, h_sp, c_sp)`** — writes heating/cooling setpoints to all zones via actuators.
- **`compute_rule_based_setpoints()`** — deterministic heuristic fallback used when LLM is unavailable.
- **`get_summary_metrics()`** — computes aggregate KPIs at end of simulation.

**Zones:** `ZSF1`, `ZNF1`, `ZSF2`, `ZNF2` (4 zones in SmOffPSZ model).

**PMV formula:** Simplified ISO 7730 — `pmv = (zone_temp - 22.5 - outdoor_bias) * 0.4`, clamped to `[-3, +3]`.

---

### `app/llm_agent.py`
**Cognitive engine.** Decides HVAC setpoints using an LLM or falls back to rules.

Key class: `EcoLoopLLMAgent`

- **`decide_setpoints(...)`** — main entry point. Formats the prompt, dispatches to the active backend, parses JSON response, validates setpoint bounds.
- **`_call_nvidia()`** — OpenAI-compatible REST call to `https://integrate.api.nvidia.com/v1/chat/completions`.
- **`_call_gemini()`** — Direct REST call to `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent`. Uses exponential backoff retry for 429 errors. **Bypasses the google-genai SDK** (which had a bug sending old model name causing 404s).
- **`_call_openai()`** — OpenAI API call.
- **`_call_ollama()`** — Local Ollama server call.
- **`_parse_llm_response(text)`** — extracts `{"heating_setpoint": X, "cooling_setpoint": Y, "reasoning": "..."}` JSON from LLM output. Clamps values to config limits.
- **`self.LLM_CALL_INTERVAL_TIMESTEPS = 240`** — **hardcoded in `__init__` (line 35)**, overrides config.py. For NVIDIA this can safely be 4.

> **IMPORTANT — Gemini 429 fix:** `_call_gemini` uses direct REST, NOT the google-genai SDK. The SDK sent `models/gemini-1.5-flash` (wrong/stale model) causing 404.

> **IMPORTANT — Rate limiting:** Gemini free tier ~60 req/min. At interval=4 the sim makes ~8,750 calls — instant 429. Interval=240 gives ~146 calls total (safe). NVIDIA NIM has no such strict limit.

---

### `app/prompts.py`
Contains two string constants:

- **`SYSTEM_PROMPT`** — tells the LLM it is an HVAC optimization agent, defines constraints, mandates JSON output.
- **`CONTROL_PROMPT_TEMPLATE`** — per-timestep prompt with: `sim_time`, `hour`, `zone_temp`, `outdoor_temp`, `current_heating_sp`, `current_cooling_sp`, `hvac_power`, `is_occupied`, `is_peak_hour`, `pmv`.

**Expected LLM output format:**
```json
{"heating_setpoint": 21.0, "cooling_setpoint": 24.0, "reasoning": "brief explanation"}
```

---

### `app/optimizer.py`
Pure analytics — no EnergyPlus dependency. Used by the dashboard.

- **`load_log(csv_path)`** — reads a simulation log CSV, coerces numerics.
- **`compute_metrics(rows)`** — returns `total_energy_kwh`, `peak_demand_kw`, `comfort_violations_timesteps`, `carbon_emissions_kg`, `energy_cost_inr`, `avg_zone_temp_c`, `avg_pmv`, `total_timesteps`.
- **`compute_savings(baseline, ai)`** — computes percentage changes.
- **`get_full_report()`** — loads both CSVs and returns combined report dict used by dashboard.

---

### `app/energyplus_runner.py`
**Primary CLI entry point.**

```bash
./venv/bin/python app/energyplus_runner.py --mode both      # baseline + AI
./venv/bin/python app/energyplus_runner.py --mode baseline
./venv/bin/python app/energyplus_runner.py --mode ai
```

Output: `output/log_baseline.csv`, `output/log_ai.csv`, `output/simulation_comparison.csv`.

---

### `app/dashboard.py`
**Streamlit + Plotly 3D dashboard.** Full rewrite from matplotlib → Plotly.

Sections:
1. **Hero header** — glassmorphism banner with LLM backend badge
2. **KPI cards** — 5 metrics with delta vs baseline, hover-lift glass effect
3. **3D Energy Surface** (`go.Surface`) — dual blue/green surfaces: HVAC Power by Day x Hour x kW
4. **3D Operating Envelope** (`go.Scatter3d`) — 1,500 sampled hourly points: Zone Temp x HVAC Power x PMV
5. **Timeseries tabs** — HVAC Power / Zone Temperature / PMV / AI Setpoints (interactive Plotly)
6. **Comparison tab** — grouped bar chart + 4 savings pills
7. **Seasonal Heatmaps** — side-by-side Monthly x Hourly energy intensity (baseline vs AI)

**Sidebar:** Chart opacity slider, time resolution selector (hourly/4hr/12hr downsampling), quick summary metrics.

**Plotly colorbar API note:** Use `title=dict(text="kW", font=dict(color=...))` — NOT the deprecated `titlefont=` kwarg (causes `ValueError`).

```bash
./venv/bin/streamlit run app/dashboard.py --server.port 8501
```

---

## Run Commands Cheatsheet

```bash
# Activate venv
source venv/bin/activate

# Full simulation (both modes, ~5–10 min)
python app/energyplus_runner.py --mode both

# View dashboard
streamlit run app/dashboard.py

# Test NVIDIA API
python -c "
import sys; sys.path.insert(0,'app')
from llm_agent import EcoLoopLLMAgent
agent = EcoLoopLLMAgent('nvidia')
print(agent.decide_setpoints(24.0, 30.0, 10, True, 5000, 21.0, 24.0))
"

# Test Gemini API
python -c "
import sys; sys.path.insert(0,'app')
from llm_agent import EcoLoopLLMAgent
agent = EcoLoopLLMAgent('gemini')
print(agent.decide_setpoints(24.0, 30.0, 10, True, 5000, 21.0, 24.0))
"
```

---

## Switching LLM Backends

Edit `app/config.py` line 63:
```python
LLM_BACKEND = "nvidia"      # NVIDIA NIM DeepSeek Flash (current default)
LLM_BACKEND = "gemini"      # Google Gemini 2.5 Flash (free tier — rate limits apply)
LLM_BACKEND = "openai"      # OpenAI GPT-4o-mini
LLM_BACKEND = "ollama"      # Local Llama3 via Ollama
LLM_BACKEND = "rule_based"  # Pure deterministic (no LLM, fastest)
```

For Gemini free tier, also edit `llm_agent.py` line 35:
```python
self.LLM_CALL_INTERVAL_TIMESTEPS = 240  # safe for free tier
```

---

## Simulation Output CSV Schema

Both `log_baseline.csv` and `log_ai.csv` — one row per EnergyPlus timestep:

| Column | Type | Description |
|---|---|---|
| `mode` | str | `"baseline"` or `"ai"` |
| `sim_day` | int | Simulation day (1–365) |
| `hour` | int | Hour of day (0–23) |
| `timestep` | int | Global timestep index (1–35040) |
| `zone_temp_c` | float | Mean zone air temperature (°C) |
| `outdoor_temp_c` | float | Outdoor dry-bulb temperature (°C) |
| `hvac_power_w` | float | HVAC electricity demand rate (W) |
| `hvac_energy_kwh` | float | HVAC energy for this timestep (kWh) |
| `heating_setpoint` | float | Heating setpoint applied (°C) |
| `cooling_setpoint` | float | Cooling setpoint applied (°C) |
| `pmv` | float | Predicted Mean Vote comfort index (−3 to +3) |
| `is_occupied` | int | 1 if occupied hours (08:00–18:00), else 0 |
| `is_peak` | int | 1 if peak electricity hour, else 0 |
| `comfort_violation` | int | 1 if PMV outside [−0.5, +0.5] during occupied hours |

---

## Latest Simulation Results

| Metric | Baseline | AI-Controlled | Change |
|---|---|---|---|
| Total Energy (kWh) | 52,647.9 | 46,592.0 | **−11.5%** |
| Peak Demand (kW) | 38.66 | 39.44 | +2.0% |
| Carbon Emissions (kg) | 43,171 | 38,205 | **−11.5%** |
| Energy Cost (INR) | 421,183 | 372,736 | **−11.5%** |
| Comfort Violations | 6,859 | 12,202 | +77.9% |

> Comfort violations are higher in AI mode because it aggressively pre-cools/pre-heats during unoccupied hours to reduce peak-hour load. Tune via `app/prompts.py` SYSTEM_PROMPT constraints.

---

## Known Issues & Gotchas

| Issue | Cause | Fix |
|---|---|---|
| `404 NOT_FOUND` from Gemini | google-genai SDK sends old model name `gemini-1.5-flash` | `_call_gemini()` bypasses SDK, uses direct REST to `gemini-2.5-flash` |
| `429 Too Many Requests` | Gemini free tier limit; interval=4 → ~8,750 calls/sim | Set `self.LLM_CALL_INTERVAL_TIMESTEPS = 240` in `llm_agent.py __init__` |
| `ValueError: titlefont` in Plotly | `titlefont` deprecated in newer Plotly | Use `title=dict(text="...", font=dict(color=...))` in `colorbar=dict(...)` |
| Stale Streamlit error after code fix | Process cached old code | `pkill -f "streamlit run"` and restart |
| `LLM_CALL_INTERVAL_TIMESTEPS` mismatch | `llm_agent.py line 35` hardcodes `240`, overriding config.py | Edit `llm_agent.py` directly, not just config.py |
| EnergyPlus exit code != 0 | Warmup period failures (usually benign) | Check `output/baseline/eplusout.err` |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    EnergyPlus 26.1                      │
│  SmOffPSZ.idf + New Delhi TMYx weather (35,040 steps)  │
│  Sensors: zone_temp, outdoor_temp, hvac_power, hour     │
│  Actuators: heating_setpoint, cooling_setpoint          │
└──────────────────┬──────────────────────────────────────┘
                   │  Python EMS API (per-timestep callback)
                   ▼
┌─────────────────────────────────────────────────────────┐
│              controller.py — EcoLoopController           │
│  Reads sensors → computes PMV → calls LLM every N steps │
│  Writes setpoints back to EnergyPlus → logs to CSV      │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│              llm_agent.py — EcoLoopLLMAgent              │
│  NVIDIA NIM (default) / Gemini / OpenAI / Ollama / Rules│
│  Output: (heating_setpoint °C, cooling_setpoint °C)     │
│  Fallback: rule_based on any API error                  │
└──────────────────┬──────────────────────────────────────┘
                   │  output/log_baseline.csv + log_ai.csv
                   ▼
┌─────────────────────────────────────────────────────────┐
│           optimizer.py + dashboard.py                   │
│  Streamlit dashboard with Plotly 3D charts:             │
│  - go.Surface: HVAC Power by Day × Hour                 │
│  - go.Scatter3d: Zone Temp × Power × PMV               │
│  - go.Heatmap: Monthly × Hourly energy intensity        │
│  - go.Scatter: Timeseries (Power/Temp/PMV/Setpoints)    │
└─────────────────────────────────────────────────────────┘
```
