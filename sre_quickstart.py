"""Quick workspace entry point for importing and sampling the simulator."""

from sre_agents import RandomAgent, RunbookAgent
from sre_environment import SREEnvironment
from sre_grading import grade_easy, grade_hard, grade_medium
from sre_models import Action, Observation, Reward, TrajectoryStep

__all__ = [
    "Action",
    "Observation",
    "RandomAgent",
    "Reward",
    "RunbookAgent",
    "SREEnvironment",
    "TrajectoryStep",
    "grade_easy",
    "grade_medium",
    "grade_hard",
]


if __name__ == "__main__":
    environment = SREEnvironment(difficulty="easy")
    initial_observation = environment.reset()
    print(initial_observation.model_dump_json(indent=2))
