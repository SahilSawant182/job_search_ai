"""
Agents package for job_search_ai.

This package contains specialized AI agents that perform autonomous,
multi-step reasoning and tool use to generate career insights.

Each agent follows the same pattern:
  - A public-facing agent class with a single `run()` entry point.
  - Internal services responsible for a single task each.
  - Dataclass schemas shared across all services within the agent.
"""
