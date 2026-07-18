"""Repository boundaries and mock implementations."""

from services.api.app.repositories.base import JobRepository
from services.api.app.repositories.memory import InMemoryJobRepository

__all__ = ["InMemoryJobRepository", "JobRepository"]
