"""Repository boundaries and mock implementations."""

from services.api.app.repositories.base import CallRepository, JobRepository, QuoteRepository
from services.api.app.repositories.memory import InMemoryRepository
from services.api.app.repositories.supabase import SupabaseRepository
from services.api.app.repositories.supabase_client import (
    SupabasePostgrestClient,
    SupabaseTableClient,
)

__all__ = [
    "CallRepository",
    "InMemoryRepository",
    "JobRepository",
    "QuoteRepository",
    "SupabasePostgrestClient",
    "SupabaseRepository",
    "SupabaseTableClient",
]
