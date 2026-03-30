"""Core environment logic for the SRE simulator."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sre_models import Action, Observation, Reward, TrajectoryStep
from sre_scenarios import ScenarioDefinition, get_scenario


class SREEnvironment:
    """A reinforcement learning-style environment for SRE incident response."""

    def __init__(self, difficulty: str = "easy", seed: int | None = None) -> None:
        self.difficulty = difficulty
        self.seed = seed
        self.scenario: ScenarioDefinition | None = None
        self.trajectory: list[TrajectoryStep] = []
        self.reset()

    def reset(self) -> Observation:
        """Reset the environment and return the initial observation."""

        self.scenario = get_scenario(self.difficulty)
        self.services = deepcopy(self.scenario.incident_service_health)
        self.dependencies = deepcopy(self.scenario.dependencies)
        self.logs = deepcopy(self.scenario.initial_logs)
        self.visible_logs = deepcopy(self.scenario.initial_visible_logs)
        self.metrics = deepcopy(self.scenario.incident_metrics)
        self.runbook = list(self.scenario.runbook)
        self.step_count = 0
        self.done = False
        self.resolved = False
        self.root_cause_identified = False
        self.cache_dropped = False
        self.destructive_action_count = 0
        self.trajectory = []
        self.queried_services: set[str] = set(self.visible_logs)
        self.last_log_windows: dict[str, int] = {
            service: max(len(lines), 1) for service, lines in self.visible_logs.items()
        }
        self.relevant_log_queries: set[str] = set()
        self.discovered_services: set[str] = set()
        self.discovered_edges: set[str] = set()
        self.escalated_teams: set[str] = set()
        self._derive_service_health()
        return self._build_observation()

    def step(self, action: Action) -> tuple[Observation, float, bool, dict[str, Any]]:
        """Apply one action to the environment."""

        if self.done:
            observation = self._build_observation()
            reward = Reward(value=0.0, reason="Episode already finished. Call reset() to start a new incident.")
            info = self._build_info({}, reward)
            return observation, reward.value, True, info

        action = action if isinstance(action, Action) else Action.model_validate(action)
        self.step_count += 1

        if action.action_type == "query_logs":
            reward, action_info = self.query_logs(
                service=str(action.parameters.get("service", "")),
                time_window=action.parameters.get("time_window", "15m"),
            )
        elif action.action_type == "check_dependency":
            reward, action_info = self.check_dependency(
                service=str(action.parameters.get("service", "")),
            )
        elif action.action_type == "run_command":
            reward, action_info = self.run_command(
                command=str(action.parameters.get("command", "")),
            )
        elif action.action_type == "apply_fix":
            reward, action_info = self.apply_fix(
                fix_action=str(action.parameters.get("action", action.parameters.get("fix", ""))),
                service=action.parameters.get("service"),
            )
        elif action.action_type == "escalate":
            reward, action_info = self.escalate(
                team=str(action.parameters.get("team", "")),
            )
        else:
            reward = Reward(
                value=-0.1,
                reason=f"Unsupported action type '{action.action_type}'.",
            )
            action_info = {
                "unsupported_action": True,
            }

        self._advance_simulation()
        if self.resolved or self.step_count >= self.scenario.step_budget:
            self.done = True
            if not self.resolved and self.step_count >= self.scenario.step_budget:
                reward = Reward(
                    value=reward.value,
                    reason=f"{reward.reason} Step budget exhausted before full recovery.".strip(),
                )

        observation = self._build_observation()
        info = self._build_info(action_info, reward)
        self.trajectory.append(
            TrajectoryStep(
                step=self.step_count,
                action=action,
                reward=reward,
                observation=observation,
                done=self.done,
                info=info,
            )
        )
        return observation, reward.value, self.done, info

    def query_logs(self, service: str, time_window: str | int) -> tuple[Reward, dict[str, Any]]:
        """Surface service logs for the requested time window."""

        service_name = self._normalize_service(service)
        if service_name not in self.logs:
            return Reward(value=-0.1, reason=f"Unknown service '{service}' for log query."), {
                "relevant_query": False,
                "queried_service": service_name,
            }

        line_count = self._window_to_lines(time_window)
        self.queried_services.add(service_name)
        self.last_log_windows[service_name] = line_count
        self.visible_logs[service_name] = list(self.logs[service_name][-line_count:])

        relevant = service_name in self.scenario.relevant_log_services
        is_new_signal = relevant and service_name not in self.relevant_log_queries
        if relevant:
            self.relevant_log_queries.add(service_name)
            self.discovered_services.add(service_name)

        if is_new_signal:
            reason = f"Queried relevant logs for {service_name} and surfaced useful evidence."
            reward_value = 0.1
        elif relevant:
            reason = f"Re-queried {service_name}; the logs were still relevant but mostly confirmed known evidence."
            reward_value = 0.0
        else:
            reason = f"Queried logs for {service_name}, but the result was mostly a red herring."
            reward_value = -0.1

        return Reward(value=round(reward_value, 3), reason=reason), {
            "relevant_query": relevant,
            "queried_service": service_name,
            "log_window_lines": line_count,
        }

    def check_dependency(self, service: str) -> tuple[Reward, dict[str, Any]]:
        """Inspect one service's downstream dependency health."""

        service_name = self._normalize_service(service)
        if service_name not in self.dependencies:
            return Reward(value=-0.1, reason=f"Unknown service '{service}' for dependency inspection."), {
                "dependency_check": [],
                "relevant_dependency_check": False,
            }

        dependencies = self.dependencies.get(service_name, [])
        if not dependencies:
            line = f"Dependency check: {service_name} has no downstream services."
            self._append_log_line(service_name, line)
            return Reward(value=0.0, reason=f"{service_name} has no downstream dependencies to inspect."), {
                "dependency_check": [],
                "relevant_dependency_check": False,
            }

        status_pairs = [f"{dep}={self.services.get(dep, 'unknown')}" for dep in dependencies]
        line = f"Dependency check: {service_name} depends on {', '.join(status_pairs)}."
        self._append_log_line(service_name, line)

        new_lead = False
        hinted_dependencies: list[str] = []
        for dependency in dependencies:
            edge = f"{service_name}->{dependency}"
            if dependency in self.scenario.diagnostic_path and edge not in self.discovered_edges:
                self.discovered_edges.add(edge)
                self.discovered_services.add(dependency)
                new_lead = True
                hinted_dependencies.append(dependency)
                self._append_runbook_item(f"Inspect logs for {dependency} next.")

        reward_value = 0.15 if new_lead else 0.0
        if new_lead:
            reason = f"Dependency inspection of {service_name} revealed a more relevant failing dependency."
        else:
            reason = f"Dependency inspection of {service_name} did not surface a new lead."

        return Reward(value=round(reward_value, 3), reason=reason), {
            "dependency_check": status_pairs,
            "relevant_dependency_check": new_lead,
            "hinted_dependencies": hinted_dependencies,
        }

    def run_command(self, command: str) -> tuple[Reward, dict[str, Any]]:
        """Run a diagnostic or operational command."""

        normalized_command = " ".join(command.strip().split())
        lowered = normalized_command.lower()
        if not normalized_command:
            return Reward(value=-0.1, reason="Empty command provided."), {
                "command": lowered,
                "destructive_action": False,
            }

        if lowered in self.scenario.destructive_commands:
            self.destructive_action_count += 1
            self.cache_dropped = True
            cache_service = "session-cache" if "session-cache" in self.metrics else self.scenario.root_cause_service
            self._append_log_line(cache_service, "CRITICAL destructive cache drop triggered; cache hit rate collapsed.")
            reason = "Executed a destructive command and worsened the incident."
            return Reward(value=-1.0, reason=reason), {
                "command": lowered,
                "destructive_action": True,
            }

        if lowered.startswith("identify_root_cause"):
            claim = normalized_command[len("identify_root_cause") :].strip(" :")
            if self._matches_root_cause(claim):
                if not self.root_cause_identified:
                    self.root_cause_identified = True
                    self.discovered_services.add(self.scenario.root_cause_service)
                    self._append_runbook_item(
                        f"Root cause confirmed. Apply one of: {', '.join(self.scenario.valid_fix_actions)}."
                    )
                    return Reward(
                        value=0.5,
                        reason="Correctly identified the ground truth root cause.",
                    ), {
                        "command": lowered,
                        "identified_root_cause": True,
                        "destructive_action": False,
                    }
                return Reward(
                    value=0.0,
                    reason="Root cause was already identified earlier in the episode.",
                ), {
                    "command": lowered,
                    "identified_root_cause": True,
                    "destructive_action": False,
                }

            return Reward(
                value=-0.1,
                reason="Submitted an incorrect root cause diagnosis.",
            ), {
                "command": lowered,
                "identified_root_cause": False,
                "destructive_action": False,
            }

        if lowered.startswith("status "):
            service_name = self._normalize_service(normalized_command.split(" ", 1)[1])
            if service_name not in self.metrics:
                return Reward(value=-0.1, reason=f"Unknown service '{service_name}' in status command."), {
                    "command": lowered,
                    "destructive_action": False,
                }

            metric_summary = ", ".join(
                f"{key}={value}"
                for key, value in self.metrics[service_name].items()
            )
            self._append_log_line(service_name, f"STATUS {service_name}: {metric_summary}.")
            reward_value = 0.05 if service_name in self.scenario.diagnostic_path else 0.0
            reason = f"Collected runtime status for {service_name}."
            return Reward(value=round(reward_value, 3), reason=reason), {
                "command": lowered,
                "destructive_action": False,
                "status_service": service_name,
            }

        return Reward(
            value=-0.1,
            reason=f"Command '{normalized_command}' did not help the investigation.",
        ), {
            "command": lowered,
            "destructive_action": False,
        }

    def apply_fix(self, fix_action: str, service: str | None = None) -> tuple[Reward, dict[str, Any]]:
        """Apply a remediation attempt."""

        canonical = self._canonical_fix(fix_action, service)
        if canonical in self.scenario.valid_fix_actions:
            if not self.resolved:
                self.resolved = True
                reward_value = 1.0
                reasons = [f"Applied a valid remediation ({canonical}) and restored service health."]
                if self.step_count <= self.scenario.step_budget / 2:
                    reward_value += 0.3
                    reasons.append("Solved within half of the step budget.")
                self._recover_system()
                return Reward(value=round(reward_value, 3), reason=" ".join(reasons)), {
                    "correct_fix_applied": True,
                    "canonical_fix": canonical,
                }
            return Reward(value=0.0, reason="The incident is already resolved."), {
                "correct_fix_applied": True,
                "canonical_fix": canonical,
            }

        if canonical in self.scenario.invalid_actions:
            self._append_log_line(
                service or self.scenario.root_cause_service,
                f"ACTION {canonical} completed with no measurable improvement.",
            )
            return Reward(
                value=-0.1,
                reason=f"{canonical} was tempting but did not resolve the incident.",
            ), {
                "correct_fix_applied": False,
                "canonical_fix": canonical,
            }

        return Reward(
            value=-0.1,
            reason=f"{canonical or fix_action} is not a recognized remediation for this scenario.",
        ), {
            "correct_fix_applied": False,
            "canonical_fix": canonical,
        }

    def escalate(self, team: str) -> tuple[Reward, dict[str, Any]]:
        """Escalate the incident to another team."""

        normalized_team = " ".join(team.strip().lower().split())
        if not normalized_team:
            return Reward(value=-0.1, reason="Escalation requires a team name."), {
                "escalated_team": normalized_team,
            }

        hint = self.scenario.escalation_hints.get(normalized_team)
        if hint and normalized_team not in self.escalated_teams:
            self.escalated_teams.add(normalized_team)
            self.discovered_services.add(self.scenario.root_cause_service)
            self._append_runbook_item(f"{normalized_team} replied: {hint}")
            self._append_log_line(self.scenario.root_cause_service, f"ESCALATION {normalized_team}: {hint}")
            return Reward(
                value=0.05,
                reason=f"Escalation to {normalized_team} produced a useful hint.",
            ), {
                "escalated_team": normalized_team,
                "useful_escalation": True,
            }

        if hint:
            return Reward(
                value=0.0,
                reason=f"{normalized_team} already provided the available context.",
            ), {
                "escalated_team": normalized_team,
                "useful_escalation": True,
            }

        return Reward(
            value=0.0,
            reason=f"Escalation to {normalized_team} did not change the available evidence.",
        ), {
            "escalated_team": normalized_team,
            "useful_escalation": False,
        }

    def _advance_simulation(self) -> None:
        """Advance the world state after each action."""

        if self.resolved:
            self._sync_visible_logs()
            return

        for service, entries in self.scenario.evolution_logs.items():
            index = min(max(self.step_count - 1, 0), len(entries) - 1)
            if index >= 0 and entries:
                entry = entries[index]
                if entry not in self.logs[service][-2:]:
                    self.logs[service].append(entry)

        for service, weight in self.scenario.impact_weights.items():
            metrics = self.metrics[service]
            metrics["latency_ms"] = round(metrics.get("latency_ms", 0.0) + (35.0 * weight), 2)
            metrics["error_rate"] = round(min(1.0, metrics.get("error_rate", 0.0) + (0.025 * weight)), 3)
            metrics["availability"] = round(max(0.0, metrics.get("availability", 100.0) - (1.2 * weight)), 2)

            if service == self.scenario.root_cause_service:
                metrics["cpu"] = round(max(0.0, metrics.get("cpu", 0.0) - 0.02), 2)
            else:
                metrics["cpu"] = round(min(0.99, metrics.get("cpu", 0.0) + (0.02 * weight)), 2)

            if "cache_hit_rate" in metrics and self.cache_dropped:
                metrics["cache_hit_rate"] = round(max(0.0, metrics["cache_hit_rate"] - 15.0), 2)
                metrics["error_rate"] = round(min(1.0, metrics["error_rate"] + 0.08), 3)

        self._derive_service_health()
        self._sync_visible_logs()

    def _recover_system(self) -> None:
        """Restore services to a healthy state after a valid remediation."""

        for service, baseline in self.scenario.baseline_metrics.items():
            restored = deepcopy(baseline)
            if "latency_ms" in restored:
                restored["latency_ms"] = round(restored["latency_ms"] * 1.05, 2)
            self.metrics[service] = restored
            self.services[service] = "healthy"
            for line in self.scenario.recovery_logs.get(service, []):
                self.logs[service].append(line)

        self.cache_dropped = False
        self._derive_service_health()
        self._sync_visible_logs()

    def _build_observation(self) -> Observation:
        """Create an observation snapshot from current visible state."""

        return Observation(
            alert=self.scenario.alert,
            service_health=deepcopy(self.services),
            logs=deepcopy(self.visible_logs),
            metrics=deepcopy(self.metrics),
            runbook=list(self.runbook),
        )

    def _build_info(self, action_info: dict[str, Any], reward: Reward) -> dict[str, Any]:
        """Build the `info` payload returned by `step`."""

        return {
            **action_info,
            "reward": reward.model_dump(),
            "reward_reason": reward.reason,
            "steps_used": self.step_count,
            "step_budget": self.scenario.step_budget,
            "difficulty": self.scenario.difficulty,
            "resolved": self.resolved,
            "root_cause_identified": self.root_cause_identified,
            "diagnostic_progress": self._diagnostic_progress(),
            "destructive_action_count": self.destructive_action_count,
            "services": list(self.services),
            "dependencies": deepcopy(self.dependencies),
        }

    def _window_to_lines(self, time_window: str | int) -> int:
        """Convert a time window into a coarse number of lines."""

        if isinstance(time_window, int):
            minutes = max(time_window, 1)
        else:
            token = str(time_window).strip().lower()
            digits = "".join(character for character in token if character.isdigit())
            minutes = int(digits) if digits else 15
            if token.endswith("h"):
                minutes *= 60

        if minutes <= 15:
            return 3
        if minutes <= 60:
            return 5
        return 7

    def _canonical_fix(self, fix_action: str, service: str | None) -> str:
        """Normalize fix payloads so scenario comparisons stay simple."""

        normalized_action = " ".join(str(fix_action).strip().lower().split())
        normalized_service = self._normalize_service(service) if service else ""
        if normalized_action and normalized_service:
            return f"{normalized_action}:{normalized_service}"
        return normalized_action

    def _normalize_service(self, service: str | None) -> str:
        """Normalize service names used in action parameters."""

        return " ".join(str(service or "").strip().lower().split())

    def _append_log_line(self, service: str, line: str) -> None:
        """Append one log line and keep the surfaced window consistent."""

        service_name = self._normalize_service(service)
        if service_name not in self.logs:
            return
        self.logs[service_name].append(line)
        self.queried_services.add(service_name)
        self.last_log_windows.setdefault(service_name, 4)
        self._sync_visible_logs()

    def _append_runbook_item(self, item: str) -> None:
        """Append a runbook hint once."""

        if item not in self.runbook:
            self.runbook.append(item)

    def _sync_visible_logs(self) -> None:
        """Refresh surfaced logs for every visible service."""

        for service in self.queried_services:
            if service in self.logs:
                window = self.last_log_windows.get(service, 4)
                self.visible_logs[service] = list(self.logs[service][-window:])

    def _diagnostic_progress(self) -> float:
        """Return a 0..1 estimate of how far the investigation has progressed."""

        denominator = len(self.scenario.diagnostic_path) + 1
        numerator = len(self.discovered_services.intersection(self.scenario.diagnostic_path))
        if self.root_cause_identified:
            numerator += 1
        return round(min(1.0, numerator / denominator), 3)

    def _matches_root_cause(self, claim: str) -> bool:
        """Check whether the submitted diagnosis matches the scenario truth."""

        normalized_claim = self._normalize_text(claim)
        candidates = [self.scenario.root_cause, *self.scenario.root_cause_aliases]
        return any(
            normalized_claim
            and (
                normalized_claim in self._normalize_text(candidate)
                or self._normalize_text(candidate) in normalized_claim
            )
            for candidate in candidates
        )

    def _normalize_text(self, value: str) -> str:
        """Normalize free-form text for fuzzy comparison."""

        cleaned = "".join(character.lower() if character.isalnum() else " " for character in value)
        return " ".join(cleaned.split())

    def _derive_service_health(self) -> None:
        """Derive coarse health states from the current metrics."""

        for service, metrics in self.metrics.items():
            baseline_latency = self.scenario.baseline_metrics[service].get("latency_ms", 1.0)
            error_rate = metrics.get("error_rate", 0.0)
            availability = metrics.get("availability", 100.0)
            latency = metrics.get("latency_ms", 0.0)
            cache_hit_rate = metrics.get("cache_hit_rate", 100.0)

            if availability < 75.0 or error_rate >= 0.7 or cache_hit_rate < 10.0:
                self.services[service] = "down"
            elif availability < 97.0 or error_rate >= 0.08 or latency > (baseline_latency * 2.5):
                self.services[service] = "degraded"
            else:
                self.services[service] = "healthy"
