"""
config.py - Central configuration for Eco-Loop Building Agent
All paths, limits, and settings are defined here.
"""

import os

# ──────────────────────────────────────────────
# BASE PATHS
# ──────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IDF_FILE = os.path.join(PROJECT_ROOT, "models", "SmOffPSZ.idf")
EPW_FILE = os.path.join(
    PROJECT_ROOT,
    "models",
    "IND_DL_New.Delhi-Gandhi.Intl.AP.421810_TMYx.2011-2025.epw",
)
OUTPUT_DIR_BASELINE = os.path.join(PROJECT_ROOT, "output", "baseline")
OUTPUT_DIR_AI = os.path.join(PROJECT_ROOT, "output", "ai_controlled")
LOG_CSV = os.path.join(PROJECT_ROOT, "output", "simulation_log.csv")
COMPARISON_CSV = os.path.join(PROJECT_ROOT, "output", "simulation_comparison.csv")

# ──────────────────────────────────────────────
# ENERGYPLUS INSTALLATION
# ──────────────────────────────────────────────
ENERGYPLUS_DIR = "/Applications/EnergyPlus-26-1-0"

# ──────────────────────────────────────────────
# HVAC SETPOINT LIMITS
# ──────────────────────────────────────────────
# Comfort band: [20°C, 26°C] per ASHRAE 55
HEATING_SETPOINT_MIN = 18.0   # °C — absolute minimum heating setpoint
HEATING_SETPOINT_MAX = 23.0   # °C — maximum heating setpoint
COOLING_SETPOINT_MIN = 22.0   # °C — minimum cooling setpoint
COOLING_SETPOINT_MAX = 28.0   # °C — absolute maximum cooling setpoint

DEFAULT_HEATING_SETPOINT = 21.0  # °C baseline
DEFAULT_COOLING_SETPOINT = 24.0  # °C baseline

# Setpoint deadband: heating must be < cooling by at least this amount
SETPOINT_DEADBAND = 2.0  # °C

# ──────────────────────────────────────────────
# COMFORT THRESHOLDS (ASHRAE 55 / ISO 7730)
# ──────────────────────────────────────────────
PMV_COMFORT_MIN = -0.5   # Below this → too cold
PMV_COMFORT_MAX = 0.5    # Above this → too hot
OCCUPANCY_HOURS = list(range(8, 19))  # 08:00 – 18:00

# ──────────────────────────────────────────────
# ENERGY PRICING
# ──────────────────────────────────────────────
ELECTRICITY_RATE_PER_KWH = 8.0  # INR per kWh (Indian grid tariff)
CARBON_INTENSITY_KG_PER_KWH = 0.82  # kg CO2 per kWh (India national average)

# Peak demand window (hours, 24-hr)
PEAK_HOURS = list(range(9, 12)) + list(range(17, 21))  # 09-12 and 17-21

# ──────────────────────────────────────────────
# LLM / COGNITIVE ENGINE
# ──────────────────────────────────────────────
LLM_BACKEND = "nvidia"   # "nvidia", "gemini", "openai", "ollama", or "rule_based"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o-mini"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"  # Confirmed working on this API key tier
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

# How many timestep readings to buffer before calling LLM
# At interval=2000, we make ~18 calls total per annual simulation — fast and safe for rate limits.
LLM_CALL_INTERVAL_TIMESTEPS = 2000

# ──────────────────────────────────────────────
# MCP SERVER
# ──────────────────────────────────────────────
MCP_HOST = "127.0.0.1"
MCP_PORT = 8765

# ──────────────────────────────────────────────
# SIMULATION TIMESTEP
# ──────────────────────────────────────────────
# EnergyPlus default is 6 timesteps per hour (10 min each)
TIMESTEPS_PER_HOUR = 6
