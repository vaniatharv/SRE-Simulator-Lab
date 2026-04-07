A small Python project that simulates an SRE incident response environment for training AI agents.

The simulator exposes a reinforcement learning-style interface:

```python
observation = env.reset()
observation, reward, done, info = env.step(action)
```

Agents investigate production-style incidents by querying logs, checking dependencies, running commands, applying fixes, and escalating to other teams. The environment tracks evolving logs, service health, metrics, rewards, and trajectory history for grading.

## Features

- `SREEnvironment` with `reset()` and `step()` methods
- Pydantic models for observations, actions, rewards, and trajectory steps
- Three difficulty levels: easy, medium, and hard
- Root-cause tracking with valid fixes and tempting invalid actions
- Reward shaping for investigation quality, correct diagnosis, safe behavior, and fast recovery
- Built-in grader functions for easy, medium, and hard trajectories
- Demo agents:
  - `RunbookAgent` for a simple rule-based workflow
  - `RandomAgent` for baseline exploration

## Project Structure

```text
.
|-- README.md
|-- requirements.txt
|-- demo_model.py
|-- run_demo.py
|-- sre_models.py
|-- sre_scenarios.py
|-- sre_environment.py
|-- sre_grading.py
`-- sre_agents.py
```

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Data Validation | [Pydantic](https://docs.pydantic.dev/) v2 |
| RL Interface | Custom `gym`-style `reset()` / `step()` loop |
| Scenario Engine | `sre_scenarios.py` — hand-crafted incident definitions |
| Environment | `sre_environment.py` — stateful simulation with evolving logs & metrics |
| Grading | `sre_grading.py` — trajectory-based scoring functions |
| Demo Agents | Rule-based `RunbookAgent` and random-baseline `RandomAgent` |

## Requirements

- Python 3.10+
- `pydantic>=2.0,<3.0`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start

Run all scenarios with the rule-based demo agent:

```bash
python run_demo.py --difficulty all --agent runbook
```

Run a single scenario:

```bash
python run_demo.py --difficulty hard --agent runbook
```

Run the random baseline:

```bash
python run_demo.py --difficulty medium --agent random --seed 7
```

Preview the initial observation model:

```bash
python demo_model.py
```

## Core API

### Data Models

`sre_models.py` defines:

- `Observation`
  - `alert: str`
  - `service_health: dict[str, str]`
  - `logs: dict[str, list[str]]`
  - `metrics: dict[str, dict[str, float]]`
  - `runbook: list[str]`
- `Action`
  - `action_type: str`
  - `parameters: dict[str, Any]`
- `Reward`
  - `value: float`
  - `reason: str`

### Environment

`sre_environment.py` exposes:

```python
from sre_environment import SREEnvironment
from sre_models import Action

env = SREEnvironment(difficulty="easy")
obs = env.reset()

action = Action(
    action_type="query_logs",
    parameters={"service": "checkout-api", "time_window": "30m"},
)

next_obs, reward, done, info = env.step(action)
```

### Supported Action Types

- `query_logs`
  - Example: `{"service": "api-gateway", "time_window": "30m"}`
- `check_dependency`
  - Example: `{"service": "orders-service"}`
- `run_command`
  - Example: `{"command": "identify_root_cause inventory-db certificate expired"}`
- `apply_fix`
  - Example: `{"action": "rotate_certificate", "service": "inventory-db"}`
- `escalate`
  - Example: `{"team": "database"}`

## Scenario Overview

### Easy

- Single service failure
- One misleading log line
- Clear root cause
- Short step budget

### Medium

- Cascading failure across three services
- Dependency chain: `api-gateway -> orders-service -> inventory-db`
- Partial rewards for partial diagnosis

### Hard

- Five services with noisy signals
- Multiple red herrings
- SLA-style step budget pressure
- Destructive command trap such as `drop_cache`

## Reward Model

The environment returns both a numeric reward and a human-readable explanation.

Default reward shaping includes:

- `+0.1` for querying relevant logs
- `-0.1` for irrelevant investigation actions
- `-1.0` for destructive actions
- `+0.5` for correctly identifying the root cause
- `+1.0` for successful resolution
- `+0.3` bonus for solving within half of the step budget

The `info` dictionary also includes investigation progress, whether the root cause has been identified, whether the incident is resolved, and how many destructive actions were taken.

## Grading

`sre_grading.py` provides:

- `grade_easy(trajectory) -> float`
- `grade_medium(trajectory) -> float`
- `grade_hard(trajectory) -> float`

Grading considers:

- correctness of root-cause identification
- correctness of remediation
- efficiency relative to the step budget
- avoidance of destructive behavior

## Built-in Demo Agents

### RunbookAgent

A deterministic, rule-based agent that:

- starts from the alert source
- follows dependency hints
- reads visible logs for root-cause clues
- submits a diagnosis
- applies a matching fix

### RandomAgent

A simple baseline that samples valid action types and parameters without deep reasoning.

## Extending the Simulator

You can extend the project by:

- adding new scenarios in `sre_scenarios.py`
- introducing new action types in `sre_environment.py`
- adjusting reward shaping for your training setup
- replacing the demo agents with learned agents or external policy loops
- exporting `env.trajectory` for offline evaluation

## Notes

- The root-level `sre_*.py` files are the active implementation files.
- The environment keeps a `trajectory` list of `TrajectoryStep` records for grading or replay.
- Logs and metrics evolve after each action, even before resolution, to simulate incident pressure.
