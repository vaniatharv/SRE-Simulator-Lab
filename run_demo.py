"""Run one or more sample SRE environment episodes."""

from __future__ import annotations

import argparse
from typing import Callable

from sre_agents import RandomAgent, RunbookAgent
from sre_environment import SREEnvironment
from sre_grading import grade_easy, grade_hard, grade_medium


def main() -> None:
    """Parse CLI arguments and run the requested demos."""

    parser = argparse.ArgumentParser(description="Run the SRE incident response simulator demo.")
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard", "all"],
        default="all",
        help="Scenario difficulty to run.",
    )
    parser.add_argument(
        "--agent",
        choices=["runbook", "random"],
        default="runbook",
        help="Which demo agent to use.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Seed used by the random agent.",
    )
    args = parser.parse_args()

    difficulties = ["easy", "medium", "hard"] if args.difficulty == "all" else [args.difficulty]
    grade_map: dict[str, Callable] = {
        "easy": grade_easy,
        "medium": grade_medium,
        "hard": grade_hard,
    }

    for difficulty in difficulties:
        print("=" * 88)
        print(f"Scenario: {difficulty.upper()}")
        environment = SREEnvironment(difficulty=difficulty, seed=args.seed)
        agent = RunbookAgent() if args.agent == "runbook" else RandomAgent(seed=args.seed)
        agent.reset()

        observation = environment.reset()
        print(f"Alert: {observation.alert}")
        print("Initial service health:", observation.service_health)
        print("Initial runbook:")
        for item in observation.runbook:
            print(f"  - {item}")

        done = False
        while not done:
            action = agent.act(observation, list(environment.services), difficulty)
            print("-" * 88)
            print(f"Step {environment.step_count + 1} action: {action.model_dump()}")
            observation, reward, done, info = environment.step(action)
            print(f"Reward: {reward:.2f}")
            print(f"Reason: {info['reward_reason']}")
            print("Service health:", observation.service_health)
            print("Surfaced logs:")
            for service, lines in observation.logs.items():
                print(f"  {service}:")
                for line in lines[-3:]:
                    print(f"    - {line}")
            print("Key metrics:")
            for service, metrics in observation.metrics.items():
                summary = ", ".join(f"{key}={value}" for key, value in metrics.items())
                print(f"  {service}: {summary}")
            print(f"Diagnostic progress: {info['diagnostic_progress']}")
            print(f"Resolved: {info['resolved']}")

        score = grade_map[difficulty](environment.trajectory)
        print("-" * 88)
        print(f"Episode finished after {environment.step_count} steps.")
        print(f"Resolved: {environment.resolved}")
        print(f"Root cause identified: {environment.root_cause_identified}")
        print(f"Grader score: {score:.3f}")
        print()


if __name__ == "__main__":
    main()
