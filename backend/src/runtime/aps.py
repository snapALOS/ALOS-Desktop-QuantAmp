import psutil
from typing import Dict, Any
from src.core.config import system_logger
from src.core.quant_amp.doctrine import QuantAmpDoctrine

class PrecisionManager:
    """
    Project QuantAmp: APS (Adaptive Precision Superposition) Engine.
    Scales computational depth dynamically based on host environmental capabilities.
    """

    @staticmethod
    def sense_environment() -> str:
        """
        Sensors: Monitor host resources to determine processing depth.
        """
        try:
            cpu_pct = psutil.cpu_percent(interval=None)
            mem_pct = psutil.virtual_memory().percent
            
            if cpu_pct > 80 or mem_pct > 85: 
                return "SHALLOW" # Survival Mode
            elif cpu_pct < 30 and mem_pct < 50: 
                return "DEEP"    # Surge Mode
            else: 
                return "BALANCED" # Normal Operation
        except Exception as e:
            system_logger.error(f"APS SENSOR FAILURE: {e}. Defaulting to BALANCED.")
            return "BALANCED"

    @staticmethod
    def get_pulse_weights(state: str) -> Dict[str, float]:
        """
        Transmitter: Translates environment state to Algorithm 3 (QIP) Weights.
        """
        if state == "SHALLOW":
            return {
                QuantAmpDoctrine.APS_KEY_PHASE_WEIGHT: 0.8,
                QuantAmpDoctrine.APS_KEY_COMPLEXITY_WEIGHT: 0.8
            }
        elif state == "DEEP":
            return {
                QuantAmpDoctrine.APS_KEY_PHASE_WEIGHT: 1.5,
                QuantAmpDoctrine.APS_KEY_COMPLEXITY_WEIGHT: 1.2
            }
        # BALANCED
        return {
            QuantAmpDoctrine.APS_KEY_PHASE_WEIGHT: 1.1,
            QuantAmpDoctrine.APS_KEY_COMPLEXITY_WEIGHT: 1.0
        }

    @staticmethod
    def get_target_worker_count(state: str) -> int:
        """
        Claim 1: Worker Density Controller.
        """
        if state == "SHALLOW": return 2
        elif state == "DEEP": return 12
        return 4

    @staticmethod
    def biological_duty_cycle(state: str) -> float:
        """
        Claim 2: Biological Cooling Interval (Seconds).
        Prevents hardware thermal collapse during high-intensity logic ripples.
        """
        if state == "SHALLOW": return 2.0  # Cooling pause
        elif state == "DEEP": return 0.0   # Full sprint
        return 0.2                         # Normal ripple rate
