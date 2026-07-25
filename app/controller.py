"""
controller.py - EnergyPlus EMS Callback Handler & Sensor/Actuator Bridge

Probed variable names for SmOffPSZ.idf:
  - Zone temperature: "Zone Air Temperature" @ ZSF1/ZNF1/ZSF2/ZNF2
  - Outdoor temp:     "Site Outdoor Air Drybulb Temperature" @ "Environment"
  - HVAC energy:      Meter "Electricity:HVAC"
  - Actuators:        "Zone Temperature Control" / "Heating Setpoint" & "Cooling Setpoint"
"""

import sys
import os
import csv
import json
import math

sys.path.insert(0, "/Applications/EnergyPlus-26-1-0")

from pyenergyplus.api import EnergyPlusAPI

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# ──────────────────────────────────────────────
# ZONES IN THIS IDF (SmOffPSZ)
# ──────────────────────────────────────────────
ZONES = ["ZSF1", "ZNF1", "ZSF2", "ZNF2"]

# ──────────────────────────────────────────────
# PMV CALCULATION (ISO 7730 simplified)
# ──────────────────────────────────────────────

def estimate_pmv(zone_temp: float, outdoor_temp: float, is_occupied: bool) -> float:
    """
    Simplified Predicted Mean Vote (PMV) estimate for office sedentary work.
    Comfort zone: PMV in [-0.5, +0.5] per ASHRAE 55 / ISO 7730.
    """
    if not is_occupied:
        return 0.0
    neutral_temp = 22.5
    outdoor_bias = (outdoor_temp - 20.0) * 0.05
    pmv = (zone_temp - neutral_temp - outdoor_bias) * 0.4
    return max(-3.0, min(3.0, pmv))


# ──────────────────────────────────────────────
# RULE-BASED SETPOINT OPTIMIZER
# ──────────────────────────────────────────────

def compute_rule_based_setpoints(
    zone_temp: float,
    outdoor_temp: float,
    hour: int,
    is_occupied: bool,
    hvac_power: float,
    current_heating_sp: float,
    current_cooling_sp: float,
) -> tuple[float, float]:
    """
    Heuristic rule engine for optimal heating/cooling setpoints.
    Strategy: pre-cooling, setback, demand response, PMV correction.
    """
    pmv = estimate_pmv(zone_temp, outdoor_temp, is_occupied)
    is_peak = hour in config.PEAK_HOURS

    if is_occupied:
        target_heating = 21.0
        target_cooling = 24.0
    else:
        # Setback: widen deadband when unoccupied
        target_heating = 18.0
        target_cooling = 27.0

    # Pre-cooling before morning peak
    if hour == 7 and outdoor_temp > 28:
        target_cooling = 22.5

    # Demand response: relax comfort band during peak hours
    if is_peak and is_occupied:
        if outdoor_temp > 30:
            target_cooling = min(target_cooling + 1.0, config.COOLING_SETPOINT_MAX)
        else:
            target_heating = max(target_heating - 1.0, config.HEATING_SETPOINT_MIN)

    # Comfort correction: nudge toward comfort if PMV is extreme
    if is_occupied:
        if pmv > config.PMV_COMFORT_MAX:
            target_cooling = max(target_cooling - 0.5, config.COOLING_SETPOINT_MIN)
        elif pmv < config.PMV_COMFORT_MIN:
            target_heating = min(target_heating + 0.5, config.HEATING_SETPOINT_MAX)

    # Clamp to bounds
    heating_sp = max(config.HEATING_SETPOINT_MIN, min(target_heating, config.HEATING_SETPOINT_MAX))
    cooling_sp = max(config.COOLING_SETPOINT_MIN, min(target_cooling, config.COOLING_SETPOINT_MAX))

    # Enforce deadband
    if cooling_sp - heating_sp < config.SETPOINT_DEADBAND:
        cooling_sp = heating_sp + config.SETPOINT_DEADBAND

    return round(heating_sp, 1), round(cooling_sp, 1)


# ──────────────────────────────────────────────
# ECOLOOP CONTROLLER CLASS
# ──────────────────────────────────────────────

class EcoLoopController:
    """
    Hooks into EnergyPlus via Python API callbacks.
    Reads sensor data every timestep and injects LLM/rule-based setpoints.
    """

    def __init__(self, api: EnergyPlusAPI, mode: str = "ai", log_csv: str = None):
        self.api = api
        self.mode = mode
        self.log_csv = log_csv or config.LOG_CSV
        self.log_rows = []

        self.handles_initialized = False
        self.timestep_count = 0

        # Sensor handles
        self.h_zone_temps = {}      # zone_name → handle
        self.h_outdoor_temp = None
        self.h_hvac_meter = None    # Electricity:HVAC meter

        # Actuator handles per zone
        self.h_heat_sp = {}         # zone_name → handle
        self.h_cool_sp = {}         # zone_name → handle

        # Current applied setpoints (shared across zones)
        self.current_heating_sp = config.DEFAULT_HEATING_SETPOINT
        self.current_cooling_sp = config.DEFAULT_COOLING_SETPOINT

        # Track last HVAC meter reading for delta energy calculation
        self._last_meter_j = 0.0

        self._agent = None

    def _get_agent(self):
        if self._agent is None:
            from llm_agent import EcoLoopLLMAgent
            self._agent = EcoLoopLLMAgent()
        return self._agent

    def _init_handles(self, state) -> bool:
        """Initialize sensor and actuator handles once EnergyPlus is ready."""
        dt = self.api.exchange

        try:
            # Zone temperature variables
            for zone in ZONES:
                h = dt.get_variable_handle(state, "Zone Air Temperature", zone)
                if h >= 0:
                    self.h_zone_temps[zone] = h

            # Outdoor temperature
            self.h_outdoor_temp = dt.get_variable_handle(
                state, "Site Outdoor Air Drybulb Temperature", "Environment"
            )

            # Energy: use Zone Air System Sensible Cooling/Heating Rates (W) summed across zones
            # SmOffPSZ uses gas heating + DX cooling — Electricity:HVAC may be 0
            # We track total thermal load (cooling + heating) as a proxy for HVAC energy
            self.h_cooling_rate = {}  # zone → handle (W)
            self.h_heating_rate = {}  # zone → handle (W)
            for zone in ZONES:
                hc = dt.get_variable_handle(state, "Zone Air System Sensible Cooling Rate", zone)
                hh = dt.get_variable_handle(state, "Zone Air System Sensible Heating Rate", zone)
                if hc >= 0:
                    self.h_cooling_rate[zone] = hc
                if hh >= 0:
                    self.h_heating_rate[zone] = hh

            # Facility electricity meter (Building = lights + plugs, used for delta energy)
            self.h_elec_bld = dt.get_meter_handle(state, "Electricity:Building")

            # Actuators for each zone
            for zone in ZONES:
                hh = dt.get_actuator_handle(
                    state, "Zone Temperature Control", "Heating Setpoint", zone
                )
                hc = dt.get_actuator_handle(
                    state, "Zone Temperature Control", "Cooling Setpoint", zone
                )
                if hh >= 0:
                    self.h_heat_sp[zone] = hh
                if hc >= 0:
                    self.h_cool_sp[zone] = hc

            # Require at least one zone temp + outdoor + at least one actuator
            ok = (
                len(self.h_zone_temps) > 0
                and self.h_outdoor_temp is not None
                and self.h_outdoor_temp >= 0
                and len(self.h_heat_sp) > 0
            )
            if ok:
                print(f"[Controller] Handles initialized: {len(self.h_zone_temps)} zones, "
                      f"{len(self.h_heat_sp)} actuator pairs, "
                      f"{len(self.h_cooling_rate)} cooling rate handles")
            else:
                print("[Controller] WARNING: Some handles failed to initialize")
            return ok

        except Exception as e:
            print(f"[Controller] Handle init error: {e}")
            return False

    def timestep_callback(self, state) -> None:
        """Called by EnergyPlus at end of each zone timestep."""
        dt = self.api.exchange

        # Skip warmup
        if dt.warmup_flag(state):
            return

        # Initialize handles once
        if not self.handles_initialized:
            if dt.api_data_fully_ready(state):
                success = self._init_handles(state)
                if success:
                    self.handles_initialized = True
                else:
                    return
            else:
                return

        self.timestep_count += 1

        # ── Read sensors ──
        try:
            # Average zone temperature across all zones
            zone_temps = {}
            for zone, h in self.h_zone_temps.items():
                zone_temps[zone] = dt.get_variable_value(state, h)

            avg_zone_temp = sum(zone_temps.values()) / len(zone_temps) if zone_temps else 22.0
            outdoor_temp = dt.get_variable_value(state, self.h_outdoor_temp)

            # Sum sensible cooling + heating rates across all zones (W)
            total_cooling_w = sum(
                dt.get_variable_value(state, h)
                for h in self.h_cooling_rate.values()
            ) if hasattr(self, 'h_cooling_rate') else 0.0
            total_heating_w = sum(
                dt.get_variable_value(state, h)
                for h in self.h_heating_rate.values()
            ) if hasattr(self, 'h_heating_rate') else 0.0

            # Total HVAC thermal power (W) — cooling + heating load
            hvac_power_w = total_cooling_w + total_heating_w

            # Convert power to energy per timestep (kWh)
            seconds_per_timestep = 3600.0 / config.TIMESTEPS_PER_HOUR
            hvac_energy_kwh = hvac_power_w * seconds_per_timestep / 3_600_000.0

            # Also track electricity meter delta for facility electricity
            if hasattr(self, 'h_elec_bld') and self.h_elec_bld and self.h_elec_bld >= 0:
                current_elec_j = dt.get_meter_value(state, self.h_elec_bld)
                delta_elec_j = max(0.0, current_elec_j - self._last_meter_j)
                self._last_meter_j = current_elec_j
                # Add facility electricity to energy accounting
                hvac_energy_kwh += delta_elec_j / 3_600_000.0
                hvac_power_w += delta_elec_j / seconds_per_timestep if seconds_per_timestep > 0 else 0.0

        except Exception as e:
            print(f"[Controller] Sensor read error: {e}")
            return

        hour = dt.hour(state)
        sim_day = dt.day_of_year(state)
        # Determine occupancy based on hour (08:00–18:00)
        is_occupied = hour in config.OCCUPANCY_HOURS

        pmv = estimate_pmv(avg_zone_temp, outdoor_temp, is_occupied)

        if self.mode == "ai":
            if self.timestep_count % config.LLM_CALL_INTERVAL_TIMESTEPS == 0:
                agent = self._get_agent()
                new_h, new_c = agent.decide_setpoints(
                    zone_temp=avg_zone_temp,
                    outdoor_temp=outdoor_temp,
                    hour=hour,
                    is_occupied=is_occupied,
                    hvac_power=hvac_power_w,
                    current_heating_sp=self.current_heating_sp,
                    current_cooling_sp=self.current_cooling_sp,
                    pmv=pmv,
                    sim_time=f"Day {sim_day} Hour {hour:02d}",
                )
                self.current_heating_sp = new_h
                self.current_cooling_sp = new_c

            # Inject setpoint overrides for all zones
            try:
                for zone in ZONES:
                    if zone in self.h_heat_sp:
                        dt.set_actuator_value(state, self.h_heat_sp[zone], self.current_heating_sp)
                    if zone in self.h_cool_sp:
                        dt.set_actuator_value(state, self.h_cool_sp[zone], self.current_cooling_sp)
            except Exception as e:
                print(f"[Controller] Actuator write error: {e}")
        else:
            self.current_heating_sp = config.DEFAULT_HEATING_SETPOINT
            self.current_cooling_sp = config.DEFAULT_COOLING_SETPOINT

        # ── Log timestep ──
        comfort_violation = 1 if (is_occupied and abs(pmv) > 0.5) else 0
        is_peak = 1 if hour in config.PEAK_HOURS else 0

        self.log_rows.append({
            "mode": self.mode,
            "sim_day": sim_day,
            "hour": hour,
            "timestep": self.timestep_count,
            "zone_temp_c": round(avg_zone_temp, 3),
            "outdoor_temp_c": round(outdoor_temp, 3),
            "hvac_power_w": round(hvac_power_w, 2),
            "hvac_energy_kwh": round(hvac_energy_kwh, 6),
            "heating_setpoint": self.current_heating_sp,
            "cooling_setpoint": self.current_cooling_sp,
            "pmv": round(pmv, 3),
            "is_occupied": int(is_occupied),
            "is_peak": is_peak,
            "comfort_violation": comfort_violation,
        })

        # Progress print every ~1000 timesteps
        if self.timestep_count % 1000 == 0:
            print(f"[{self.mode.upper()}] Timestep {self.timestep_count} | "
                  f"Zone: {avg_zone_temp:.1f}°C | Outdoor: {outdoor_temp:.1f}°C | "
                  f"HVAC: {hvac_power_w:.0f}W | SP: {self.current_heating_sp}/{self.current_cooling_sp}°C")

    def save_log(self):
        """Write timestep log to CSV."""
        if not self.log_rows:
            print("[Controller] No data to save.")
            return
        os.makedirs(os.path.dirname(self.log_csv), exist_ok=True)
        with open(self.log_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.log_rows[0].keys())
            writer.writeheader()
            writer.writerows(self.log_rows)
        print(f"[Controller] {len(self.log_rows)} timestep rows saved → {self.log_csv}")

    def get_summary_metrics(self) -> dict:
        """Compute summary metrics from timestep log."""
        if not self.log_rows:
            return {}
        total_energy_kwh = sum(r["hvac_energy_kwh"] for r in self.log_rows)
        peak_rows = [r for r in self.log_rows if r["is_peak"]]
        peak_power_kw = max((r["hvac_power_w"] for r in peak_rows), default=0) / 1000.0
        comfort_violations = sum(r["comfort_violation"] for r in self.log_rows)
        carbon_kg = total_energy_kwh * config.CARBON_INTENSITY_KG_PER_KWH
        cost_inr = total_energy_kwh * config.ELECTRICITY_RATE_PER_KWH

        return {
            "mode": self.mode,
            "total_energy_kwh": round(total_energy_kwh, 2),
            "peak_demand_kw": round(peak_power_kw, 2),
            "comfort_violations_timesteps": comfort_violations,
            "carbon_emissions_kg": round(carbon_kg, 2),
            "energy_cost_inr": round(cost_inr, 2),
            "total_timesteps": len(self.log_rows),
        }
