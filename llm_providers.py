"""
LLM provider abstraction for Hari.
Supports Ollama (local) and AWS Bedrock (cloud).
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator, Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None  # type: ignore

try:
    import boto3
    BEDROCK_AVAILABLE = True
except ImportError:
    BEDROCK_AVAILABLE = False
    boto3 = None  # type: ignore


def _get_config_path() -> Path:
    """Config path: config.json in the app directory (same folder as this file)."""
    return Path(__file__).resolve().parent / "config.json"


def _load_config() -> dict:
    """Load config from config.json in the app directory."""
    config_path = _get_config_path()
    if not config_path.exists():
        return {}
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    def available(self) -> bool:
        """Check if the provider is ready to use."""
        pass

    @abstractmethod
    def generate(self, prompt: str, stream: bool = False) -> str | Iterator[str]:
        """Generate text from prompt. If stream=True, yields chunks."""
        pass

    def generate_json(self, prompt: str) -> Optional[dict[str, Any]]:
        """Generate and parse JSON response (for structured outputs like command parsing)."""
        text = self.generate(prompt, stream=False)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider."""

    def __init__(self, model: str = "qwen2:7b", endpoint: str = "http://localhost:11434/api/generate"):
        self.model = model
        self.endpoint = endpoint
        self.logger = logging.getLogger("llm.ollama")

    def available(self) -> bool:
        if not REQUESTS_AVAILABLE:
            return False
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=2)
            if r.status_code == 200:
                self.logger.info("Ollama is available")
                return True
        except Exception:
            pass
        self.logger.warning("Ollama not available")
        return False

    def generate(self, prompt: str, stream: bool = False) -> str | Iterator[str]:
        if not REQUESTS_AVAILABLE:
            return "" if not stream else (_ for _ in ())

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
        }
        try:
            resp = requests.post(self.endpoint, json=payload, stream=stream, timeout=60)
            if resp.status_code != 200:
                err = f"Ollama error {resp.status_code}: {resp.text}"
                return err if not stream else iter([err])

            if stream:
                return self._stream_response(resp)
            data = resp.json()
            return (data.get("response") or "").strip()
        except Exception as e:
            err = f"Ollama request failed: {e}"
            self.logger.error(err)
            return err if not stream else iter([err])

    def _stream_response(self, resp) -> Iterator[str]:
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                data = json.loads(line)
                chunk = data.get("response", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    break
            except json.JSONDecodeError:
                continue

    def generate_json(self, prompt: str) -> Optional[dict[str, Any]]:
        """Ollama supports format=json for better structured output."""
        if not REQUESTS_AVAILABLE:
            return None
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }
            resp = requests.post(self.endpoint, json=payload, timeout=30)
            if resp.status_code != 200:
                return None
            result = resp.json()
            text = result.get("response", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", text, re.DOTALL)
                if match:
                    return json.loads(match.group())
            return None
        except Exception as e:
            self.logger.error(f"Ollama JSON query failed: {e}")
            return None


class BedrockProvider(LLMProvider):
    """AWS Bedrock provider (Claude Messages API)."""

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
        region: str = "us-east-1",
    ):
        self.model_id = model_id
        self.region = region
        self.logger = logging.getLogger("llm.bedrock")
        self._client = None

    def _get_client(self):
        if self._client is None:
            if not BEDROCK_AVAILABLE:
                raise RuntimeError("boto3 not installed; pip install boto3")
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def available(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception as e:
            self.logger.warning(f"Bedrock not available: {e}")
            return False

    def _messages_body(self, prompt: str, max_tokens: int = 2048) -> str:
        return json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": 0.5,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
        })

    def generate(self, prompt: str, stream: bool = False) -> str | Iterator[str]:
        try:
            client = self._get_client()
            body = self._messages_body(prompt)

            if stream:
                return self._stream_generate(client, body)
            response = client.invoke_model(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
            )
            return self._parse_response(response["body"].read())
        except Exception as e:
            err = f"Bedrock request failed: {e}"
            self.logger.error(err)
            return err if not stream else iter([err])

    def _parse_response(self, body_bytes: bytes) -> str:
        data = json.loads(body_bytes)
        content = data.get("content", [])
        if not content:
            return ""
        for block in content:
            if block.get("type") == "text" and "text" in block:
                return block["text"].strip()
        return ""

    def _stream_generate(self, client, body: str) -> Iterator[str]:
        try:
            response = client.invoke_model_with_response_stream(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
            )
            for event in response["body"]:
                chunk_bytes = event.get("chunk", {}).get("bytes")
                if not chunk_bytes:
                    continue
                chunk_data = json.loads(chunk_bytes)
                if chunk_data.get("type") == "content_block_delta":
                    text = chunk_data.get("delta", {}).get("text", "")
                    if text:
                        yield text
        except Exception as e:
            self.logger.error(f"Bedrock stream failed: {e}")
            yield f"Bedrock stream error: {e}"


def create_llm_provider(config: Optional[dict] = None) -> LLMProvider:
    """
    Create LLM provider from config.
    Config keys: llm.provider ("ollama" | "bedrock"), llm.ollama.*, llm.bedrock.*
    """
    if config is None:
        config = _load_config()
    llm_cfg = config.get("llm") or {}

    provider_name = (llm_cfg.get("provider") or "ollama").lower()
    if provider_name == "bedrock":
        bedrock_cfg = llm_cfg.get("bedrock") or {}
        return BedrockProvider(
            model_id=bedrock_cfg.get("model_id", "anthropic.claude-3-haiku-20240307-v1:0"),
            region=bedrock_cfg.get("region", "us-east-1"),
        )
    # Default: ollama (support legacy top-level model/endpoint)
    ollama_cfg = llm_cfg.get("ollama") or {}
    return OllamaProvider(
        model=ollama_cfg.get("model") or llm_cfg.get("model", "qwen2:7b"),
        endpoint=ollama_cfg.get("endpoint") or llm_cfg.get("endpoint", "http://localhost:11434/api/generate"),
    )
