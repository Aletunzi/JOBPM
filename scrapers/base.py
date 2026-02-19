from abc import ABC, abstractmethod
from typing import AsyncIterator
from scrapers.normalizer import NormalizedJob


class BaseJobScraper(ABC):
    """Abstract base class for all job scrapers."""

    source_name: str = ""

    @abstractmethod
    async def fetch(self, **kwargs) -> AsyncIterator[NormalizedJob]:
        """Yield normalized PM job listings."""
        ...
