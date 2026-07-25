"""
llm_agent.py - Cognitive Engine with LLM Backend and Rule-Based Fallback

Supports three backends:
  - "rule_based": deterministic heuristic (fast, no API key needed)
  - "ollama": local open-source LLM via Ollama (Llama3, Mistral, Qwen, etc.)
  - "openai": OpenAI API (GPT-4o-mini or similar)

All backends produce optimal (heating_setpoint, cooling_setpoint) outputs.
"""

import sys
import os
import json
import re
import requests
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from prompts import SYSTEM_PROMPT, CONTROL_PROMPT_TEMPLATE
from controller import compute_rule_based_setpoints


class EcoLoopLLMAgent:
    """
    Cognitive engine that decides HVAC setpoints using an LLM or rule engine.
    Falls back to rule_based automatically on any LLM error.
    """

    def __init__(self, backend: str = None):
        # How many timestep readings to buffer before calling LLM.
        # NVIDIA free tier: ~5 req/min hard limit. Annual sim = 35,040 timesteps.
        # At interval=2000 we make ~18 calls total — well within limits.
        # Gemini free tier: 60 req/min → interval=240 gives ~146 calls (safe too).
        self.LLM_CALL_INTERVAL_TIMESTEPS = 2000
        self.backend = backend or config.LLM_BACKEND
        self.call_count = 0
        self.fallback_count = 0
        print(f"[LLMAgent] Initialized with backend: '{self.backend}'")

    def decide_setpoints(
        self,
        zone_temp: float,
        outdoor_temp: float,
        hour: int,
        is_occupied: bool,
        hvac_power: float,
        current_heating_sp: float,
        current_cooling_sp: float,
        pmv: float = 0.0,
        sim_time: str = "",
    ) -> tuple[float, float]:
        """
        Returns (heating_setpoint, cooling_setpoint) for the current timestep.
        """
        self.call_count += 1

        if self.backend == "rule_based":
            return compute_rule_based_setpoints(
                zone_temp, outdoor_temp, hour, is_occupied,
                hvac_power, current_heating_sp, current_cooling_sp
            )

        # Build prompt
        is_peak = hour in config.PEAK_HOURS
        prompt = CONTROL_PROMPT_TEMPLATE.format(
            sim_time=sim_time or f"Day hour {hour:02d}:00",
            hour=hour,
            zone_temp=zone_temp,
            outdoor_temp=outdoor_temp,
            current_heating_sp=current_heating_sp,
            current_cooling_sp=current_cooling_sp,
            hvac_flow=0.0,
            hvac_power=hvac_power,
            is_occupied="Yes" if is_occupied else "No",
            is_peak_hour="Yes" if is_peak else "No",
            pmv=pmv,
        )

        try:
            if self.backend == "nvidia":
                return self._call_nvidia(prompt, zone_temp, outdoor_temp, hour, is_occupied, hvac_power, current_heating_sp, current_cooling_sp)
            elif self.backend == "gemini":
                return self._call_gemini(prompt, zone_temp, outdoor_temp, hour, is_occupied, hvac_power, current_heating_sp, current_cooling_sp)
            elif self.backend == "ollama":
                return self._call_ollama(prompt, zone_temp, outdoor_temp, hour, is_occupied, hvac_power, current_heating_sp, current_cooling_sp)
            elif self.backend == "openai":
                return self._call_openai(prompt, zone_temp, outdoor_temp, hour, is_occupied, hvac_power, current_heating_sp, current_cooling_sp)
            else:
                return compute_rule_based_setpoints(
                    zone_temp, outdoor_temp, hour, is_occupied,
                    hvac_power, current_heating_sp, current_cooling_sp
                )
        except Exception as e:
            self.fallback_count += 1
            print(f"[LLMAgent] Backend error ({self.backend}), falling back to rules: {e}")
            return compute_rule_based_setpoints(
                zone_temp, outdoor_temp, hour, is_occupied,
                hvac_power, current_heating_sp, current_cooling_sp
            )

    def _parse_llm_response(self, text: str) -> tuple[float, float] | None:
        """Extract heating and cooling setpoints from LLM JSON response."""
        try:
            # Try to extract JSON block
            match = re.search(r'\{.*?\}', text, re.DOTALL)
            if not match:
                return None
            data = json.loads(match.group())
            h = float(data.get("heating_setpoint", config.DEFAULT_HEATING_SETPOINT))
            c = float(data.get("cooling_setpoint", config.DEFAULT_COOLING_SETPOINT))

            # Validate and clamp
            h = max(config.HEATING_SETPOINT_MIN, min(h, config.HEATING_SETPOINT_MAX))
            c = max(config.COOLING_SETPOINT_MIN, min(c, config.COOLING_SETPOINT_MAX))
            if c - h < config.SETPOINT_DEADBAND:
                c = h + config.SETPOINT_DEADBAND

            reasoning = data.get("reasoning", "")
            if reasoning:
                print(f"[LLMAgent] Reasoning: {reasoning}")

            return round(h, 1), round(c, 1)
        except Exception:
            return None

    def _call_ollama(
        self, prompt, zone_temp, outdoor_temp, hour, is_occupied, hvac_power, h_sp, c_sp
    ) -> tuple[float, float]:
        """Call a locally running Ollama LLM server."""
        payload = {
            "model": config.OLLAMA_MODEL,
            "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
            "stream": False,
        }
        response = requests.post(config.OLLAMA_URL, json=payload, timeout=10)
        response.raise_for_status()
        result_text = response.json().get("response", "")
        parsed = self._parse_llm_response(result_text)
        if parsed:
            return parsed
        # Fallback if parse fails
        return compute_rule_based_setpoints(
            zone_temp, outdoor_temp, hour, is_occupied, hvac_power, h_sp, c_sp
        )

    def _call_openai(
        self, prompt, zone_temp, outdoor_temp, hour, is_occupied, hvac_power, h_sp, c_sp
    ) -> tuple[float, float]:
        """Call OpenAI-compatible API."""
        import urllib.request
        headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 200,
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        result_text = data["choices"][0]["message"]["content"]
        parsed = self._parse_llm_response(result_text)
        if parsed:
            return parsed
        return compute_rule_based_setpoints(
            zone_temp, outdoor_temp, hour, is_occupied, hvac_power, h_sp, c_sp
        )

    def _call_gemini(
        self, prompt, zone_temp, outdoor_temp, hour, is_occupied, hvac_power, h_sp, c_sp
    ) -> tuple[float, float]:
        """Call Google Gemini API via direct REST endpoint with retry/backoff."""
        import urllib.request, time as _time
        api_key = config.GEMINI_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.5-flash:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{
                "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]
            }],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 200},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )

        # Retry up to 3 times with exponential backoff for rate-limit errors
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())
                result_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = self._parse_llm_response(result_text)
                if parsed:
                    return parsed
                break  # parsed failed, don't retry
            except Exception as e:
                last_error = e
                if "429" in str(e) and attempt < 2:
                    wait = 2 ** attempt  # 1s, 2s
                    _time.sleep(wait)
                    continue
                raise  # re-raise non-429 or final attempt

        return compute_rule_based_setpoints(
            zone_temp, outdoor_temp, hour, is_occupied, hvac_power, h_sp, c_sp
        )

    def _call_nvidia(
        self, prompt, zone_temp, outdoor_temp, hour, is_occupied, hvac_power, h_sp, c_sp
    ) -> tuple[float, float]:
        """Call NVIDIA NIM API with exponential backoff retry on 429 rate-limit errors."""
        import urllib.request
        import urllib.error
        import time as _time

        api_key = config.NVIDIA_API_KEY
        if not api_key:
            raise ValueError("NVIDIA_API_KEY environment variable is not set")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": config.NVIDIA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 200,
        }
        url = f"{config.NVIDIA_BASE_URL}/chat/completions"

        max_retries = 4
        for attempt in range(max_retries):
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read())
                result_text = data["choices"][0]["message"]["content"]
                parsed = self._parse_llm_response(result_text)
                if parsed:
                    return parsed
                return compute_rule_based_setpoints(
                    zone_temp, outdoor_temp, hour, is_occupied, hvac_power, h_sp, c_sp
                )
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < max_retries - 1:
                    wait = 15 * (2 ** attempt)  # 15s, 30s, 60s
                    print(f"[LLMAgent] NVIDIA 429 rate limit — waiting {wait}s (attempt {attempt+1}/{max_retries})")
                    _time.sleep(wait)
                    continue
                raise  # re-raise on non-429 or final attempt

        return compute_rule_based_setpoints(
            zone_temp, outdoor_temp, hour, is_occupied, hvac_power, h_sp, c_sp
        )

    def stats(self) -> dict:
        """Return agent performance statistics."""
        return {
            "backend": self.backend,
            "total_calls": self.call_count,
            "fallback_count": self.fallback_count,
        }
