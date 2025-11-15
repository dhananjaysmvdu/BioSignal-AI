#!/usr/bin/env python3
import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Tuple

RewardWeights = {
    "forecast_accuracy_improvement": 1.0,
    "reduced_high_risk_days": 2.0,
    "self_healing_success": 1.5,
    "avoided_red_escalation": 3.0,
    "unnecessary_responses": -1.0,
    "safety_brake_engagement": -5.0,
    "manual_unlocks": -3.0,
}


def _risk_level_to_int(level: str) -> int:
    m = {"low": 0, "medium": 1, "high": 2}
    return m.get(str(level).lower(), 1)


def compute_daily_reward(features: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    """
    Compute reward for a 24h window from boolean/int feature flags.
    features keys (recommended):
      - forecast_accuracy_improvement: bool
      - reduced_high_risk_days: bool
      - self_heals: int
      - avoided_red: bool
      - unnecessary_actions: int
      - safety_brake_engagements: int
      - manual_unlocks: int
    Returns: (total_reward, breakdown_by_signal)
    """
    breakdown = {}
    total = 0.0

    if features.get("forecast_accuracy_improvement"):
        breakdown["forecast_accuracy_improvement"] = RewardWeights["forecast_accuracy_improvement"]
        total += breakdown["forecast_accuracy_improvement"]
    else:
        breakdown["forecast_accuracy_improvement"] = 0.0

    if features.get("reduced_high_risk_days"):
        breakdown["reduced_high_risk_days"] = RewardWeights["reduced_high_risk_days"]
        total += breakdown["reduced_high_risk_days"]
    else:
        breakdown["reduced_high_risk_days"] = 0.0

    self_heals = max(0, int(features.get("self_heals", 0)))
    breakdown["self_healing_success"] = self_heals * RewardWeights["self_healing_success"]
    total += breakdown["self_healing_success"]

    if features.get("avoided_red"):
        breakdown["avoided_red_escalation"] = RewardWeights["avoided_red_escalation"]
        total += breakdown["avoided_red_escalation"]
    else:
        breakdown["avoided_red_escalation"] = 0.0

    unnecessary = max(0, int(features.get("unnecessary_actions", 0)))
    breakdown["unnecessary_responses"] = unnecessary * RewardWeights["unnecessary_responses"]
    total += breakdown["unnecessary_responses"]

    brake = max(0, int(features.get("safety_brake_engagements", 0)))
    breakdown["safety_brake_engagement"] = brake * RewardWeights["safety_brake_engagement"]
    total += breakdown["safety_brake_engagement"]

    unlocks = max(0, int(features.get("manual_unlocks", 0)))
    breakdown["manual_unlocks"] = unlocks * RewardWeights["manual_unlocks"]
    total += breakdown["manual_unlocks"]

    return total, breakdown


def compute_trend(values: List[float], window: int = 7) -> str:
    """
    Compute trend label over recent window of values: Improving, Stable, Degrading.
    Uses simple slope over last N points; tolerance band ±0.5.
    """
    if not values:
        return "Stable"
    vals = values[-window:]
    if len(vals) < 2:
        return "Stable"
    # simple slope: difference between last and first over count-1
    slope = (vals[-1] - vals[0]) / max(1, len(vals) - 1)
    if slope > 0.5:
        return "Improving"
    if slope < -0.5:
        return "Degrading"
    return "Stable"


def compute_confidence_state(policy_score: float) -> str:
    if policy_score > 70:
        return "Relaxed"
    if 40 <= policy_score <= 70:
        return "Normal"
    if policy_score < 20:
        return "Locked"
    return "Tightening"


def summarize_learning_window(reward_log: List[Dict[str, Any]], days: int = 7) -> Dict[str, Any]:
    """
    Summarize recent rewards and trend.
    reward_log: list of {timestamp, reward, policy_score}
    """
    recent = reward_log[-days:]
    rewards = [float(x.get("reward", 0.0)) for x in recent]
    scores = [float(x.get("policy_score", 50.0)) for x in recent]
    return {
        "avg_reward": statistics.fmean(rewards) if rewards else 0.0,
        "trend": compute_trend(scores, window=min(7, len(scores) or 1)),
        "last_reward": rewards[-1] if rewards else 0.0,
        "last_score": scores[-1] if scores else 50.0,
    }
