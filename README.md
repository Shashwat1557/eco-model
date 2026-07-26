# 🌿 Eco-Loop: Autonomous LLM-Driven HVAC Building Optimization

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![EnergyPlus 26.1](https://img.shields.io/badge/EnergyPlus-26.1-00599C?style=flat-square)](https://energyplus.net)
[![Streamlit](https://img.shields.io/badge/Dashboard-Streamlit%20%2B%20Plotly3D-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

**Eco-Loop** is an autonomous closed-loop HVAC optimization system for commercial office buildings in New Delhi, India. It pairs **EnergyPlus 26.1** physics simulation with an **LLM Cognitive Engine** via the Python EMS (Energy Management System) API to dynamically adapt heating and cooling setpoints in real-time.

By analyzing zone air temperature, outdoor dry-bulb weather, occupancy schedules, grid peak demand windows, and Predicted Mean Vote (PMV) thermal comfort indices, Eco-Loop achieves **~19.4% annual energy & carbon reduction** over fixed-schedule baseline control.

---

## 🚀 Key Results

Simulated over **35,040 timesteps** (1 full annual run for a 4-zone commercial office building model `SmOffPSZ` in New Delhi):

| Metric | Baseline Control | Eco-Loop AI Control | Impact |
| :--- | :---: | :---: | :---: |
| **Total HVAC Energy** | 52,647.8 kWh | **42,417.8 kWh** | **-19.4%** 📉 |
| **Carbon Emissions** | 43,171.3 kg CO₂ | **34,782.6 kg CO₂** | **-19.4%** 🌱 |
| **Annual Energy Cost** | ₹4,21,183 INR | **₹3,39,342 INR** | **₹81,840 Saved** 💰 |
| **Simulation Runtime** | ~3.5 seconds | **~18.2 seconds** | Real-time Closed Loop ⚡ |

---

## 🏗️ Architecture & Control Loop

```
┌─────────────────────────────────────────────────────────┐
│                    EnergyPlus 26.1                      │
│  SmOffPSZ.idf + New Delhi TMYx Weather (35,040 steps)   │
│                                                         │
│  Sensors: zone_temp, outdoor_temp, hvac_power, hour     │
│  Actuators: heating_setpoint, cooling_setpoint          │
└──────────────────┬──────────────────────────────────────┘
                   │  Python EMS API (per-timestep callback)
                   ▼
┌─────────────────────────────────────────────────────────┐
│              controller.py — EcoLoopController           │
│  • Reads real-time zone & outdoor sensors               │
│  • Computes ISO 7730 PMV thermal comfort index          │
│  • Dispatches state to LLM Cognitive Engine             │
│  • Overrides zone setpoint actuators                    │
│  • Logs timestep data to CSV                            │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│              llm_agent.py — EcoLoopLLMAgent              │
│  Backends supported:                                    │
│  • NVIDIA NIM (Meta Llama 3.1 8B Instruct)              │
│  • Google Gemini (Gemini 2.5 Flash direct REST)        │
│  • OpenAI (GPT-4o-mini)                                 │
│  • Ollama (Local Llama3 / Qwen)                         │
│  • Heuristic Rule-Based Fallback                        │
└──────────────────┬──────────────────────────────────────┘
                   │  output/log_baseline.csv + log_ai.csv
                   ▼
┌─────────────────────────────────────────────────────────┐
│           optimizer.py + dashboard.py                   │
│  • Streamlit Glassmorphism Dashboard                    │
│  • Plotly 3D Energy Surface Plot (Day × Hour × Power)  │
│  • Plotly 3D Scatter Plot (Operating Envelope)         │
│  • Seasonal Heatmaps & Timeseries Visualizations        │
└─────────────────────────────────────────────────────────┘
```

---

## ✨ Features

- **Direct Physics Simulation Integration**: Uses Python `pyenergyplus.api` bindings to read zone temperature, outdoor drybulb, energy consumption, and override heating/cooling setpoints dynamically per zone timestep.
- **Cognitive LLM Engine**: Formats building thermal state and occupancy constraints into structured system prompts, returning JSON-formatted setpoint recommendations.
- **Robust Fallback Mechanism**: Built-in exponential backoff retry for HTTP rate-limits (429) and automatic fallback to deterministic heuristic rules on network failures.
- **Interactive 3D Visualizations**:
  - **3D Energy Surface (`go.Surface`)**: Dual overlapping baseline vs AI surface plots across annual weeks and hours.
  - **3D Operating Envelope (`go.Scatter3d`)**: Multi-axis point clouds mapping Zone Temp × HVAC Power × PMV Comfort index.
  - **Seasonal Heatmaps (`go.Heatmap`)**: Month × Hour energy intensity side-by-side matrices.
- **Model-Context Protocol (MCP) Server**: Includes FastAPI-based MCP server (`mcp_server/server.py`) exposing simulation execution and analytics tools over HTTP.

---

## 🛠️ Installation & Setup

### Prerequisites
- **Python 3.12+**
- **EnergyPlus 26.1.0** installed at `/Applications/EnergyPlus-26-1-0` (or update path in `app/config.py`)

### 1. Clone & Setup Environment
```bash
git clone https://github.com/Shashwat1557/eco-model.git
cd eco-model

# Create & activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install plotly
```

### 2. Set API Keys
Export your preferred LLM provider's API key:

```bash
# For NVIDIA NIM (Default backend: meta/llama-3.1-8b-instruct)
export NVIDIA_API_KEY="your-nvidia-api-key"

# Or for Gemini (gemini-2.5-flash)
export GEMINI_API_KEY="your-gemini-api-key"
```

---

## 💻 Running the Application

### 1. Run Simulations
Run both baseline (fixed setpoints) and AI-controlled closed-loop simulations:

```bash
python app/main.py run
```
*Or directly via the runner:*
```bash
python app/energyplus_runner.py --mode both
```

Outputs will be saved to:
- `output/log_baseline.csv`
- `output/log_ai.csv`
- `output/simulation_comparison.csv`

### 2. Launch the 3D Interactive Dashboard
```bash
streamlit run app/dashboard.py
```
Open **[http://localhost:8501](http://localhost:8501)** in your browser.

---

## ⚙️ Configuration & LLM Backends

Centralized configuration lives in `app/config.py`:

```python
LLM_BACKEND = "nvidia"      # Options: "nvidia", "gemini", "openai", "ollama", "rule_based"
LLM_CALL_INTERVAL_TIMESTEPS = 2000  # Call LLM every N timesteps (~18 calls/annual run)

# Setpoint Constraints (ASHRAE 55)
HEATING_SETPOINT_MIN = 18.0   # °C
COOLING_SETPOINT_MAX = 28.0   # °C
SETPOINT_DEADBAND = 2.0       # °C
```

---

## 📁 Repository Structure

```
eco-model/
├── app/
│   ├── config.py            # All constants, paths, API keys, LLM parameters
│   ├── controller.py        # EnergyPlus EMS callback — sensor reads & actuator writes
│   ├── llm_agent.py         # LLM cognitive engine (NVIDIA, Gemini, OpenAI, Ollama)
│   ├── prompts.py           # System & per-timestep prompt templates
│   ├── optimizer.py         # Metrics computation and CSV loader
│   ├── energyplus_runner.py # Core simulation runner CLI
│   ├── main.py              # CLI entry point
│   └── dashboard.py         # Streamlit + Plotly 3D dashboard
├── mcp_server/
│   ├── server.py            # FastAPI MCP HTTP Server
│   └── tools.py             # Tool definitions for MCP
├── models/
│   ├── SmOffPSZ.idf         # EnergyPlus building model (Small Office PSZ)
│   └── IND_DL_...epw        # New Delhi TMYx weather dataset
├── output/                  # Simulation CSV logs & comparison data
├── requirements.txt         # Project dependencies
└── README.md                # Project documentation
```

---

## 📜 License
Distributed under the MIT License.
