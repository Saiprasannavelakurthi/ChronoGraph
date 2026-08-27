"""
config/settings.py
──────────────────
Centralised configuration for ChronoGraph Week 1.

All values are read from environment variables (or a `.env` file).
No secrets are hard-coded here – copy `.env.example` → `.env` and fill in
your values before running the project.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ─── Project root (two levels up from this file) ──────────────────────────────
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application-wide settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM Provider ─────────────────────────────────────────────────────────
    llm_provider: Literal["groq", "ollama", "openai", "mock", "fallback"] = Field(
        default="groq",
        description="Which LLM backend to use for triple extraction.",
    )
    llm_model: str = Field(
        default="",
        description="Optional model override for the active provider.",
    )

    # ── Groq ──────────────────────────────────────────────────────────────────
    groq_api_key: str = Field(
        default="",
        description="Groq Cloud API key. Required when llm_provider=groq.",
    )
    groq_model: str = Field(
        default="llama-3.1-8b-instant",
        description="Groq model to use (e.g. llama-3.1-8b-instant, llama-3.3-70b-versatile).",
    )

    # ── Ollama ────────────────────────────────────────────────────────────────
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL of the running Ollama server.",
    )
    ollama_model: str = Field(
        default="llama3",
        description="Ollama model tag to use (must already be pulled).",
    )

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key. Required only when llm_provider=openai.",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model to use.",
    )

    # ── Data Paths ────────────────────────────────────────────────────────────
    raw_data_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "raw",
        description="Directory containing the raw mock dataset JSON files.",
    )
    processed_data_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "processed",
        description="Directory where pipeline outputs are written.",
    )

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=True)

    # ── Extraction ────────────────────────────────────────────────────────────
    extraction_max_events: int = Field(
        default=0,
        description="Max events to process. 0 = unlimited.",
    )
    extraction_min_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Discard triples with confidence below this threshold.",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO")

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def slack_raw_path(self) -> Path:
        return self.raw_data_dir / "slack_history.json"

    @property
    def github_raw_path(self) -> Path:
        return self.raw_data_dir / "github_prs.json"

    @property
    def jira_raw_path(self) -> Path:
        return self.raw_data_dir / "jira_tickets.json"

    @property
    def normalized_events_path(self) -> Path:
        return self.processed_data_dir / "normalized_events.json"

    @property
    def extracted_triples_path(self) -> Path:
        return self.processed_data_dir / "extracted_triples.json"

    @property
    def graph_ready_triples_path(self) -> Path:
        """Week 2 graph-ready output (consumed by Saiprasanna's Neo4j module)."""
        return self.processed_data_dir / "graph_ready_triples.json"

    @property
    def graph_prep_summary_path(self) -> Path:
        """Week 2 graph preparation summary report."""
        return self.processed_data_dir / "graph_prep_summary.json"

    @property
    def retrieval_ready_records_path(self) -> Path:
        """Week 3 retrieval-ready records output (data contract file)."""
        return self.processed_data_dir / "retrieval_ready_records.json"

    @property
    def retrieval_prep_summary_path(self) -> Path:
        """Week 3 pipeline execution metadata summary."""
        return self.processed_data_dir / "retrieval_prep_summary.json"

    @property
    def retrieval_quality_stats_path(self) -> Path:
        """Week 3 retrieval data quality and coverage statistics."""
        return self.processed_data_dir / "retrieval_quality_stats.json"


    @model_validator(mode="after")
    def apply_llm_model_override(self) -> Settings:
        if self.llm_model:
            if self.llm_provider == "groq":
                self.groq_model = self.llm_model
            elif self.llm_provider == "openai":
                self.openai_model = self.llm_model
            elif self.llm_provider == "ollama":
                self.ollama_model = self.llm_model
        return self


def configure_logging(level: str = "INFO") -> None:
    """Set up root logger with a consistent format."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ── Singleton ─────────────────────────────────────────────────────────────────
settings = Settings()
configure_logging(settings.log_level)
