"""
Career Trend Agent package.

Public surface area — only import what the outside world needs:

    from job_search_ai.agents.career_trend import CareerTrendAgent
    from job_search_ai.agents.career_trend.schemas import (
        StudentProfile,
        CareerTrendResponse,
    )

Everything else (QueryBuilder, TavilyService, ResultFilter,
PromptBuilder, LLMService) is an implementation detail and should
not be imported directly by callers outside this package.
"""

from job_search_ai.agents.career_trend.agent import CareerTrendAgent

__all__ = ["CareerTrendAgent"]
