import os
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Configuration settings for LLM Graph Extraction."""

    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq").lower()
    LLM_MODEL: str = os.getenv("GROQ_MODEL") or os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    LLM_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY", None)
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY", None)
    EXTRACTION_MAX_RETRIES: int = int(os.getenv("EXTRACTION_MAX_RETRIES", "2"))

    @classmethod
    def get_llm(cls):
        """
        Instantiate and return a LlamaIndex LLM instance based on configuration.
        Supports Groq, Ollama, and OpenAI-compatible providers.
        Raises ValueError or RuntimeError if provider configuration or API key is missing.
        """
        provider = cls.LLM_PROVIDER.lower()
        api_key = cls.GROQ_API_KEY or cls.LLM_API_KEY

        # 1. Groq Provider
        if provider == "groq":
            if not api_key or api_key.startswith("gsk_your_groq_api_key"):
                raise ValueError(
                    "Groq API key missing. Please set GROQ_API_KEY in your environment or .env file."
                )

            model_name = cls.LLM_MODEL
            if model_name in ("llama-3.1-8b-instant", "llama-3.3-70b-versatile", "llama-3.3-70b", "llama3-70b-8192", "llama3-8b-8192"):
                model_name = "openai/gpt-oss-120b"

            try:
                from llama_index.llms.groq import Groq
                return Groq(
                    model=model_name,
                    api_key=api_key,
                    temperature=cls.LLM_TEMPERATURE
                )
            except ImportError:
                pass

            try:
                from llama_index.llms.openai import OpenAI
                return OpenAI(
                    model=model_name,
                    api_base="https://api.groq.com/openai/v1",
                    api_key=api_key,
                    temperature=cls.LLM_TEMPERATURE
                )
            except ImportError as err:
                raise RuntimeError(
                    f"Required LlamaIndex provider package not installed: {err}. "
                    "Please install `llama-index-llms-groq` or `llama-index-llms-openai`."
                )

        # 2. Ollama Provider (Local)
        if provider == "ollama":
            try:
                from llama_index.llms.ollama import Ollama
                return Ollama(
                    model=cls.LLM_MODEL,
                    base_url=cls.LLM_BASE_URL or "http://localhost:11434",
                    temperature=cls.LLM_TEMPERATURE,
                    request_timeout=120.0
                )
            except ImportError as err:
                raise RuntimeError(
                    f"Ollama LlamaIndex package not installed: {err}. Please install `llama-index-llms-ollama`."
                )

        # 3. OpenAI / Generic OpenAI-compatible Provider
        if provider in ("openai", "openai-compatible", "local-openai"):
            if not api_key:
                raise ValueError("LLM_API_KEY missing for OpenAI provider.")
            try:
                from llama_index.llms.openai import OpenAI
                return OpenAI(
                    model=cls.LLM_MODEL,
                    api_base=cls.LLM_BASE_URL,
                    api_key=api_key,
                    temperature=cls.LLM_TEMPERATURE
                )
            except ImportError as err:
                raise RuntimeError(
                    f"OpenAI LlamaIndex package not installed: {err}. Please install `llama-index-llms-openai`."
                )

        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. Supported providers: 'groq', 'ollama', 'openai'."
        )
