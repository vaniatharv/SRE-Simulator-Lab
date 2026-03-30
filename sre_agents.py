"""Demo agents for exercising the environment."""

from __future__ import annotations

import random
from typing import Sequence

from sre_models import Action, Observation


class RandomAgent:
    """A baseline agent that samples supported actions."""

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def reset(self) -> None:
        """Reset any agent-side state."""

    def act(self, observation: Observation, available_services: Sequence[str], difficulty: str) -> Action:
        """Pick a random supported action."""

        services = list(available_services)
        service = self._random.choice(services)
        teams = ["platform", "database", "ml-platform", "security", "frontend"]
        commands = [
            f"status {service}",
            "identify_root_cause cache issue",
            "identify_root_cause transient frontend error",
        ]
        if difficulty == "hard":
            commands.append("drop_cache")

        fixes = [
            {"action": "restart_service", "service": service},
            {"action": "scale_service", "service": service},
            {"action": "rollback_config", "service": service},
            {"action": "rotate_certificate", "service": service},
            {"action": "rollback_deploy", "service": service},
        ]
        action_type = self._random.choice(
            ["query_logs", "check_dependency", "run_command", "apply_fix", "escalate"]
        )
        if action_type == "query_logs":
            return Action(action_type=action_type, parameters={"service": service, "time_window": "30m"})
        if action_type == "check_dependency":
            return Action(action_type=action_type, parameters={"service": service})
        if action_type == "run_command":
            return Action(action_type=action_type, parameters={"command": self._random.choice(commands)})
        if action_type == "apply_fix":
            return Action(action_type=action_type, parameters=self._random.choice(fixes))
        return Action(action_type=action_type, parameters={"team": self._random.choice(teams)})


class RunbookAgent:
    """A simple hand-written policy that follows the evolving runbook."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Reset any local planning state."""

        self.queried_services: set[str] = set()
        self.checked_services: set[str] = set()
        self.diagnosis_submitted = False
        self.pending_fix: dict[str, str] | None = None
        self.escalated = False

    def act(self, observation: Observation, available_services: Sequence[str], difficulty: str) -> Action:
        """Choose a rule-based action from the observation."""

        services = list(available_services)
        clue = self._extract_clue(observation)
        if clue is not None:
            diagnosis, fix_payload = clue
            if not self.diagnosis_submitted:
                self.diagnosis_submitted = True
                self.pending_fix = fix_payload
                return Action(
                    action_type="run_command",
                    parameters={"command": f"identify_root_cause {diagnosis}"},
                )
            return Action(action_type="apply_fix", parameters=fix_payload)

        hinted_service = self._service_from_runbook(observation.runbook, services)
        if hinted_service and hinted_service not in self.queried_services:
            self.queried_services.add(hinted_service)
            return Action(
                action_type="query_logs",
                parameters={"service": hinted_service, "time_window": "30m"},
            )

        alert_service = self._service_from_text(observation.alert, services)
        if alert_service and alert_service not in self.queried_services:
            self.queried_services.add(alert_service)
            return Action(
                action_type="query_logs",
                parameters={"service": alert_service, "time_window": "30m"},
            )

        if alert_service and alert_service not in self.checked_services:
            self.checked_services.add(alert_service)
            return Action(
                action_type="check_dependency",
                parameters={"service": alert_service},
            )

        dependency_target = self._first_unchecked_service(observation.service_health, self.checked_services)
        if dependency_target:
            self.checked_services.add(dependency_target)
            return Action(action_type="check_dependency", parameters={"service": dependency_target})

        next_logs_target = self._first_unqueried_relevant_service(
            observation.service_health,
            self.queried_services,
        )
        if next_logs_target:
            self.queried_services.add(next_logs_target)
            return Action(
                action_type="query_logs",
                parameters={"service": next_logs_target, "time_window": "45m"},
            )

        if not self.escalated:
            self.escalated = True
            team = self._default_escalation_team(difficulty)
            return Action(action_type="escalate", parameters={"team": team})

        fallback = alert_service or services[0]
        return Action(action_type="run_command", parameters={"command": f"status {fallback}"})

    def _extract_clue(self, observation: Observation) -> tuple[str, dict[str, str]] | None:
        """Look for deterministic fix clues in visible logs."""

        haystack = " ".join(
            line.lower()
            for lines in observation.logs.values()
            for line in lines
        )
        if "db_password missing" in haystack:
            return (
                "checkout-api bad config rollout removed DB_PASSWORD",
                {"action": "rollback_config", "service": "checkout-api"},
            )
        if (
            ("certificate expired" in haystack or "certificate has expired" in haystack)
            and "inventory-db" in haystack
        ):
            return (
                "inventory-db certificate expired",
                {"action": "rotate_certificate", "service": "inventory-db"},
            )
        if "schema version 42" in haystack or "schema mismatch" in haystack:
            return (
                "feature-store schema mismatch after bad deploy",
                {"action": "rollback_deploy", "service": "feature-store"},
            )
        return None

    def _service_from_runbook(self, runbook: Sequence[str], services: Sequence[str]) -> str | None:
        """Extract the next service mentioned in runbook guidance."""

        for entry in reversed(runbook):
            service = self._service_from_text(entry, services)
            if service:
                return service
        return None

    def _service_from_text(self, text: str, services: Sequence[str]) -> str | None:
        """Find the first service name that appears in free-form text."""

        lowered = text.lower()
        for service in services:
            if service.lower() in lowered:
                return service
        return None

    def _first_unchecked_service(self, service_health: dict[str, str], checked: set[str]) -> str | None:
        """Return the next non-healthy service that has not been checked yet."""

        priority = {"down": 0, "degraded": 1, "healthy": 2}
        candidates = sorted(
            service_health.items(),
            key=lambda item: (priority.get(item[1], 3), item[0]),
        )
        for service, health in candidates:
            if health != "healthy" and service not in checked:
                return service
        return None

    def _first_unqueried_relevant_service(
        self,
        service_health: dict[str, str],
        queried: set[str],
    ) -> str | None:
        """Return the next non-healthy service that has not had logs queried."""

        for service, health in service_health.items():
            if health != "healthy" and service not in queried:
                return service
        return None

    def _default_escalation_team(self, difficulty: str) -> str:
        """Choose a conservative escalation target for the demo."""

        mapping = {
            "easy": "platform",
            "medium": "database",
            "hard": "ml-platform",
        }
        return mapping.get(difficulty, "platform")
