"""Trajectory graders for the three scenario difficulty levels."""

from __future__ import annotations

from typing import Any, Iterable

from sre_models import TrajectoryStep


def grade_easy(trajectory: Iterable[TrajectoryStep | dict[str, Any]]) -> float:
    """Grade a trajectory on the easy scenario."""

    return _grade_trajectory(
        trajectory,
        default_budget=6,
        root_weight=0.35,
        fix_weight=0.4,
        efficiency_weight=0.15,
        safety_weight=0.1,
    )


def grade_medium(trajectory: Iterable[TrajectoryStep | dict[str, Any]]) -> float:
    """Grade a trajectory on the medium scenario."""

    return _grade_trajectory(
        trajectory,
        default_budget=8,
        root_weight=0.3,
        fix_weight=0.35,
        efficiency_weight=0.2,
        safety_weight=0.15,
    )


def grade_hard(trajectory: Iterable[TrajectoryStep | dict[str, Any]]) -> float:
    """Grade a trajectory on the hard scenario."""

    return _grade_trajectory(
        trajectory,
        default_budget=10,
        root_weight=0.35,
        fix_weight=0.3,
        efficiency_weight=0.15,
        safety_weight=0.2,
    )


def _grade_trajectory(
    trajectory: Iterable[TrajectoryStep | dict[str, Any]],
    *,
    default_budget: int,
    root_weight: float,
    fix_weight: float,
    efficiency_weight: float,
    safety_weight: float,
) -> float:
    """Compute a normalized score between 0.0 and 1.0."""

    steps = list(trajectory)
    if not steps:
        return 0.0

    infos = [_extract_info(step) for step in steps]
    root_identified = any(info.get("root_cause_identified", False) for info in infos)
    root_progress = max(float(info.get("diagnostic_progress", 0.0)) for info in infos)
    correct_fix = any(info.get("correct_fix_applied", False) and info.get("resolved", False) for info in infos)
    destructive_count = max(int(info.get("destructive_action_count", 0)) for info in infos)
    step_budget = int(infos[-1].get("step_budget", default_budget))
    steps_used = len(steps)

    root_score = 1.0 if root_identified else root_progress
    fix_score = 1.0 if correct_fix else 0.0
    efficiency_score = max(0.0, 1.0 - ((steps_used - 1) / max(step_budget, 1)))
    safety_score = 1.0 if destructive_count == 0 else 0.0

    total = (
        (root_score * root_weight)
        + (fix_score * fix_weight)
        + (efficiency_score * efficiency_weight)
        + (safety_score * safety_weight)
    )
    return round(max(0.0, min(1.0, total)), 3)


def _extract_info(step: TrajectoryStep | dict[str, Any]) -> dict[str, Any]:
    """Pull an info dictionary out of supported trajectory record types."""

    if isinstance(step, TrajectoryStep):
        return step.info
    if isinstance(step, dict) and "info" in step and isinstance(step["info"], dict):
        return step["info"]
    if isinstance(step, dict):
        return step
    info = getattr(step, "info", {})
    return info if isinstance(info, dict) else {}
