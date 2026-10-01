from dataclasses import dataclass, field
from typing import Any

@dataclass
class LLMRequest:
    input_text: str
    model: str
    prompt_version: str
    schema_version: str
    event_id: str = ""
    temperature: float | None = None

@dataclass
class LLMResponse:
    text: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

class LLMProvider:
    name = "base"
    def health_check(self) -> dict: raise NotImplementedError
    def generate(self, request: LLMRequest) -> LLMResponse: raise NotImplementedError

