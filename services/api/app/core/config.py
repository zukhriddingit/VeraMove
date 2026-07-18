"""Environment-backed settings with safe mock defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    app_mode: str = "mock"
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls(
            app_mode=os.getenv("APP_MODE", "mock").lower(),
            api_host=os.getenv("API_HOST", "127.0.0.1"),
            api_port=int(os.getenv("API_PORT", "8000")),
        )
        if settings.app_mode != "mock":
            raise RuntimeError("This starter only supports APP_MODE=mock")
        return settings
