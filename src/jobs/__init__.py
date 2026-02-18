"""Config-driven jobs."""

from .runner import JobRunner

# Import modules for job registration side effects.
from .kimi_blog import KimiBlogJob  # noqa: F401
from .minimax_news import MiniMaxNewsJob  # noqa: F401
from .minimax_releases import MiniMaxReleasesJob  # noqa: F401
from .openai_research import OpenAIResearchFilterJob  # noqa: F401
from .selector_scrape import SelectorScrapeJob  # noqa: F401
from .waymo_blog import WaymoBlogTechnologyJob  # noqa: F401

__all__ = ["JobRunner"]
