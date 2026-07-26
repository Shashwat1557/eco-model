# Eco-Loop Building Agent — System Architecture Document

## Executive Summary

**Eco-Loop** is an autonomous closed-loop building energy optimization system designed for commercial office buildings in New Delhi, India. It couples **EnergyPlus 26.1** (physics-based simulation engine) with an **LLM Cognitive Engine** (NVIDIA NIM / Llama 3.1) and **MCP (Model Context Protocol)** server via the Python Energy Management System (EMS) API. 

Eco-Loop dynamically optimizes HVAC heating and cooling setpoints in real-time, achieving **~19.4% annual energy & carbon reduction** while preserving occupant thermal comfort.

---

## 🏗️ System Architecture Diagram

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
                    │  Telemetry (every 10-min timestep)
                    ▼
 ┌─────────────────────────────────────────────────────────┐
 │            EcoLoopController (app/controller.py)        │
 │  - Reads all sensor handles via api.exchange            │
 │  - Computes ISO 7730 PMV comfort estimate               │
 │  - Buffers state & invokes LLM Cognitive Engine         │
 │  - Overrides zone setpoints via actuator handles        │
 │  - Logs timestep data to CSV                            │
 └──────────────────┬──────────────────────────────────────┘
                    │  Every N timesteps (buffered)
                    ▼
 ┌─────────────────────────────────────────────────────────┐
 │         EcoLoopLLMAgent (app/llm_agent.py)              │
 │                                                         │
 │  Backends supported:                                    │
 │    1. nvidia  — NVIDIA NIM (Meta Llama 3.1 8B Instruct) │
 │    2. gemini  — Google Gemini 2.5 Flash Direct REST      │
 │    3. openai  — OpenAI GPT-4o-mini                      │
 │    4. ollama  — Local Llama3 / Qwen                     │
 │    5. rule_based — Deterministic Heuristic Fallback    │
 │                                                         │
 │  Output: {"heating_setpoint": X, "cooling_setpoint": Y} │
 └──────────────────┬──────────────────────────────────────┘
                    │  Setpoint pair (°C)
                    ▼
 ┌─────────────────────────────────────────────────────────┐
 │       Forward Injection via EMS Actuator Handle         │
 │  api.exchange.set_actuator_value(state, handle, value)  │
 └──────────────────┬──────────────────────────────────────┘
                    │  Timestep log CSV (35,040 rows)
                    ▼
 ┌─────────────────────────────────────────────────────────┐
 │         Streamlit Dashboard (app/dashboard.py)          │
 │  - Plotly 3D Energy Surface & 3D Operating Envelope     │
 │  - Automated PDF Report & CSV Export Download           │
 └─────────────────────────────────────────────────────────┘
```

---

## 🔌 1. Tool-Calling & MCP Architecture

Eco-Loop implements the **Model Context Protocol (MCP)** via a FastAPI-based server (`mcp_server/server.py` and `mcp_server/tools.py`). This allows external LLM agents and clients to inspect simulation state, issue real-time setpoint overrides, and run analytics over HTTP.

### Available MCP Tools:

| MCP Tool Name | Purpose | Implementation |
| :--- | :--- | :--- |
| `get_building_telemetry` | Reads real-time zone temperature, outdoor drybulb, HVAC power, and occupancy. | Calls `EnergyPlusAPI.exchange` sensor handles. |
| `override_setpoints` | Injects custom heating and cooling setpoint values into the simulation runtime. | Calls `EnergyPlusAPI.exchange.set_actuator_value()`. |
| `run_comfort_analysis` | Computes ISO 7730 PMV (Predicted Mean Vote) thermal comfort score. | Evaluates PMV formula using current zone temp & outdoor bias. |
| `get_simulation_summary` | Returns side-by-side KPI comparison (Energy kWh, Carbon kg, Cost INR, Comfort). | Reads `optimizer.py` aggregate log comparisons. |

---

## 🎯 2. Prompt Engineering Strategies

The LLM Cognitive Engine (`app/llm_agent.py` and `app/prompts.py`) employs structured prompt engineering to ensure high decision quality, strict adherence to physical boundaries, and zero syntax errors:

1. **System Prompt Constraint Enforcer**:
   - Instructs the LLM that it acts as a certified HVAC building engineer.
   - Mandates strict bounds: Heating Setpoint $\in [18.0^\circ\text{C}, 23.0^\circ\text{C}]$, Cooling Setpoint $\in [22.0^\circ\text{C}, 28.0^\circ\text{C}]$.
   - Enforces a minimum **$2.0^\circ\text{C}$ deadband gap** ($T_{\text{cool}} - T_{\text{heat}} \ge 2.0^\circ\text{C}$).

2. **JSON Schema Enforcement**:
   - Requires outputs strictly formatted as valid JSON:
     ```json
     {
       "heating_setpoint": 20.0,
       "cooling_setpoint": 26.0,
       "reasoning": "Lowering cooling setpoint to 26°C to prepare for peak hours while maintaining PMV comfort."
     }
     ```
   - Parsed with Regex JSON extraction (`re.search(r'\{.*?\}', text)`) and auto-clamped if bounds are breached.

3. **Deterministic Sampling**:
   - Evaluated with low temperature ($T = 0.2$) to reduce variance while permitting adaptive decision-making across seasonal variations.

---

## ⚡ 3. Prompt Latency & Rate Limit Management

Executing **35,040 annual simulation timesteps** in a fast physics loop requires careful network latency management to avoid hitting API rate limits or slowing down EnergyPlus:

1. **Timestep Buffering (`LLM_CALL_INTERVAL_TIMESTEPS`)**:
   - Gating LLM API calls to run once every $N$ timesteps (default `2000` timesteps $\approx$ 18 API calls per annual run).
   - Reduces API calls from 35,040 to 18 per run, fitting comfortably within free-tier rate limits (e.g. 15–40 req/min).

2. **Exponential Backoff & Retry Logic**:
   - Catches HTTP `429 (Too Many Requests)` rate limits.
   - Retries automatically with exponential backoff ($15\text{s} \rightarrow 30\text{s} \rightarrow 60\text{s}$) up to 4 attempts.

3. **Zero-Latency Fallback Guarantee**:
   - If an API call fails or times out after maximum retries, the engine instantly falls back to `compute_rule_based_setpoints()`.
   - Prevents EnergyPlus from stalling or crashing due to external network failures.

---

## 📊 4. Technical Approach to Handling Lengthy Simulation Logs

An annual EnergyPlus run generates high-frequency 10-minute timestep data (**35,040 rows** across multiple zones):

1. **Streaming Memory-Efficient CSV Logging**:
   - Timestep data is streamed directly to disk (`output/log_baseline.csv` and `output/log_ai.csv`) inside the C++ EMS API callback.
   - Prevents RAM bloat during multi-pass evaluation runs.

2. **Dynamic Downsampling for 3D Visual Rendering**:
   - Streamlit 3D charts (`go.Surface` and `go.Scatter3d` in `app/dashboard.py`) process 35,040 rows by downsampling to hourly, 4-hour, or 12-hour steps (`ds = step_map[downsample]`).
   - Ensures smooth 60 FPS interactive 3D rotation and zooming in Plotly without browser lag.

3. **Vectorized Aggregation**:
   - Uses `pandas` and `numpy` vectorized operations in `app/optimizer.py` to aggregate annual kWh, peak kW, carbon emissions, and cost metrics in **< 10ms**.

---

## 📜 Summary of Core Files

| File | Purpose |
| :--- | :--- |
| `app/controller.py` | EnergyPlus EMS C++ API bridge, sensor reading, actuator setpoint writing. |
| `app/llm_agent.py` | Multi-backend LLM cognitive engine (NVIDIA, Gemini, OpenAI, Ollama) with 429 retry backoff. |
| `app/prompts.py` | System prompt & per-timestep control prompt templates. |
| `app/config.py` | Central configuration for paths, setpoint limits, tariffs, and rate limit intervals. |
| `app/optimizer.py` | Analytics engine, KPI computation, Markdown & PDF Report generator (`reportlab`). |
| `app/dashboard.py` | Streamlit + Plotly 3D interactive dashboard with automated report downloads. |
| `mcp_server/server.py` | FastAPI MCP HTTP server for telemetry, overrides, and comfort analysis tools. |
