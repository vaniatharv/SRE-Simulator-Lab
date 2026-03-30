"""Pydantic models used across the simulator."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Observation(BaseModel):
    """What the agent can currently see about the incident."""

    alert: str
    service_health: dict[str, str] = Field(default_factory=dict)
    logs: dict[str, list[str]] = Field(default_factory=dict)
    metrics: dict[str, dict[str, float]] = Field(default_factory=dict)
    runbook: list[str] = Field(default_factory=list)


class Action(BaseModel):
    """A generic action issued by the agent."""

    action_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class Reward(BaseModel):
    """Reward value plus a plain-language explanation."""

    value: float
    reason: str


class TrajectoryStep(BaseModel):
    """One recorded transition in the environment."""

    step: int
    action: Action
    reward: Reward
    observation: Observation
    done: bool
    info: dict[str, Any] = Field(default_factory=dict)
