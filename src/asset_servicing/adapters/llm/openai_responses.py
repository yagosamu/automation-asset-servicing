"""OpenAI Responses API adapter for multimodal structured agent calls."""

from __future__ import annotations

import base64
import json
import logging
import os
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, Self, TypeVar, cast

import openai
from pydantic import BaseModel, SecretStr, ValidationError

from asset_servicing.ports.llm import (
    ExtractionRequest,
    ExtractionResponse,
    LocateRequest,
    LocateResponse,
    ValidationRequest,
    ValidationResponse,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
logger = logging.getLogger(__name__)


class _ResponsesResource(Protocol):
    def parse(self, **kwargs: object) -> object:
        """Create one parsed Responses API call."""


class _UsageData(Protocol):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class _ParsedResponse(Protocol):
    id: str
    status: str
    output_parsed: object | None
    output: list[object]
    incomplete_details: object | None
    usage: _UsageData | None


@dataclass(frozen=True, slots=True)
class OpenAIConfig:
    """Runtime configuration with one independently selected model per agent."""

    api_key: SecretStr
    locator_model: str
    extractor_model: str
    validator_model: str
    timeout_seconds: float = 60.0
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.api_key.get_secret_value():
            raise ValueError("OPENAI_API_KEY must not be empty")
        if not self.locator_model or not self.extractor_model or not self.validator_model:
            raise ValueError("all three agent models must be configured")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= self.max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Load credentials and independent model choices from the environment."""

        values = os.environ if environ is None else environ
        required_names = (
            "OPENAI_API_KEY",
            "LOCATOR_MODEL",
            "EXTRACTOR_MODEL",
            "VALIDATOR_MODEL",
        )
        missing = [name for name in required_names if not values.get(name)]
        if missing:
            raise ValueError(f"missing OpenAI configuration: {', '.join(missing)}")
        return cls(
            api_key=SecretStr(values["OPENAI_API_KEY"]),
            locator_model=values["LOCATOR_MODEL"],
            extractor_model=values["EXTRACTOR_MODEL"],
            validator_model=values["VALIDATOR_MODEL"],
            timeout_seconds=float(values.get("OPENAI_TIMEOUT_SECONDS", "60")),
            max_attempts=int(values.get("OPENAI_MAX_ATTEMPTS", "3")),
        )


class LLMProviderError(RuntimeError):
    """Sanitized provider failure suitable for persistence and user display."""

    def __init__(self, *, code: str, message: str, retryable: bool, attempts: int) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.attempts = attempts


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Provider-reported token usage for one completed agent call."""

    agent: str
    model: str
    prompt_version: str
    response_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    attempts: int


def _default_backoff(attempt: int) -> float:
    """Return bounded exponential delay with a small jitter component."""

    return min(8.0, float(2 ** (attempt - 1))) + random.uniform(0.0, 0.25)


class OpenAIResponsesProvider:
    """Provider-neutral agent operations backed by the OpenAI Responses API."""

    def __init__(
        self,
        *,
        responses: _ResponsesResource,
        config: OpenAIConfig,
        usage_sink: Callable[[LLMUsage], None] | None = None,
        backoff: Callable[[int], float] = _default_backoff,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._responses = responses
        self._config = config
        self._usage_sink = usage_sink
        self._backoff = backoff
        self._sleep = sleep

    @classmethod
    def from_config(
        cls,
        config: OpenAIConfig,
        *,
        usage_sink: Callable[[LLMUsage], None] | None = None,
        backoff: Callable[[int], float] = _default_backoff,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Self:
        """Build the official SDK client with retries owned only by this adapter."""

        client = openai.OpenAI(
            api_key=config.api_key.get_secret_value(),
            max_retries=0,
            timeout=config.timeout_seconds,
        )
        return cls(
            responses=cast(_ResponsesResource, client.responses),
            config=config,
            usage_sink=usage_sink,
            backoff=backoff,
            sleep=sleep,
        )

    def locate(self, request: LocateRequest) -> LocateResponse:
        """Locate a section using the complete PDF at economical visual detail."""

        return self._call(
            agent="locator",
            model=self._config.locator_model,
            request=request,
            context={"chapter_hint": request.chapter_hint},
            response_type=LocateResponse,
            detail="low",
        )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        """Extract atomic facts from confirmed pages at high visual detail."""

        return self._call(
            agent="extractor",
            model=self._config.extractor_model,
            request=request,
            context={
                "page_start": request.page_start,
                "page_end": request.page_end,
                "preferred_vocabulary": request.preferred_vocabulary,
            },
            response_type=ExtractionResponse,
            detail="high",
        )

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        """Validate facts independently against the source at high detail."""

        return self._call(
            agent="validator",
            model=self._config.validator_model,
            request=request,
            context={
                "page_start": request.page_start,
                "page_end": request.page_end,
                "variables": [variable.model_dump(mode="json") for variable in request.variables],
            },
            response_type=ValidationResponse,
            detail="high",
        )

    def _call(
        self,
        *,
        agent: str,
        model: str,
        request: LocateRequest | ExtractionRequest | ValidationRequest,
        context: dict[str, object],
        response_type: type[ResponseModel],
        detail: str,
    ) -> ResponseModel:
        encoded_pdf = base64.b64encode(request.document.content).decode("ascii")
        attempts = 0
        while attempts < self._config.max_attempts:
            attempts += 1
            try:
                raw_response = self._responses.parse(
                    model=model,
                    instructions=request.instructions,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_file",
                                    "filename": request.document.filename,
                                    "file_data": f"data:application/pdf;base64,{encoded_pdf}",
                                    "detail": detail,
                                },
                                {
                                    "type": "input_text",
                                    "text": json.dumps(context, ensure_ascii=False, sort_keys=True),
                                },
                            ],
                        }
                    ],
                    text_format=response_type,
                    metadata={"agent": agent, "prompt_version": request.prompt_version},
                    store=False,
                    timeout=self._config.timeout_seconds,
                )
                break
            except (
                openai.APITimeoutError,
                openai.APIConnectionError,
                openai.RateLimitError,
            ) as error:
                logger.warning(
                    "transient LLM request failure agent=%s attempt=%d error_type=%s",
                    agent,
                    attempts,
                    type(error).__name__,
                )
                if attempts >= self._config.max_attempts:
                    raise LLMProviderError(
                        code="transient_failure",
                        message="The LLM provider is temporarily unavailable",
                        retryable=True,
                        attempts=attempts,
                    ) from None
                self._sleep(self._backoff(attempts))
            except (ValidationError, ValueError):
                raise LLMProviderError(
                    code="invalid_schema",
                    message="The LLM response did not match the required schema",
                    retryable=True,
                    attempts=attempts,
                ) from None
            except openai.APIError as error:
                logger.warning(
                    "non-transient LLM request failure agent=%s error_type=%s",
                    agent,
                    type(error).__name__,
                )
                raise LLMProviderError(
                    code="request_failed",
                    message="The LLM provider rejected the request",
                    retryable=False,
                    attempts=attempts,
                ) from None
        else:
            raise AssertionError("retry loop exited without a response")

        response = cast(_ParsedResponse, raw_response)
        parsed = response.output_parsed
        if self._contains_refusal(response.output):
            raise LLMProviderError(
                code="refusal",
                message="The LLM provider refused the request",
                retryable=False,
                attempts=attempts,
            )
        if response.status == "incomplete":
            raise LLMProviderError(
                code="incomplete",
                message="The LLM response was incomplete",
                retryable=True,
                attempts=attempts,
            )
        if response.status != "completed":
            raise LLMProviderError(
                code="response_failed",
                message="The LLM provider did not complete the request",
                retryable=True,
                attempts=attempts,
            )
        if not isinstance(parsed, response_type):
            raise LLMProviderError(
                code="invalid_schema",
                message="The LLM response did not match the required schema",
                retryable=True,
                attempts=attempts,
            )
        if response.usage is not None and self._usage_sink is not None:
            self._usage_sink(
                LLMUsage(
                    agent=agent,
                    model=model,
                    prompt_version=request.prompt_version,
                    response_id=response.id,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    total_tokens=response.usage.total_tokens,
                    attempts=attempts,
                )
            )
        return parsed

    @staticmethod
    def _contains_refusal(output: list[object]) -> bool:
        for item in output:
            content = getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for part in content:
                if getattr(part, "type", None) == "refusal":
                    return True
        return False


__all__ = ["LLMProviderError", "LLMUsage", "OpenAIConfig", "OpenAIResponsesProvider"]
