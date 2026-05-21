from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    anthropic_api_key: str
    clerk_secret_key: str
    internal_hmac_secret: str
    staging_repo_url: str
    staging_repo_token: str
    agent_id: str
    agent_version: str
    env_id: str


def load() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        clerk_secret_key=os.environ.get("CLERK_SECRET_KEY", ""),
        internal_hmac_secret=os.environ.get("INTERNAL_HMAC_SECRET", ""),
        staging_repo_url=os.environ.get("STAGING_REPO_URL", ""),
        staging_repo_token=os.environ.get("STAGING_REPO_TOKEN", ""),
        agent_id=os.environ.get("AGENT_ID", ""),
        agent_version=os.environ.get("AGENT_VERSION", ""),
        env_id=os.environ.get("ENV_ID", ""),
    )


settings = load()
