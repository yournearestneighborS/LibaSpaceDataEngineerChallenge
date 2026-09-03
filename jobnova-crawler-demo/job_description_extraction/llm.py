from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from job_description_extraction.html_utils import clean_fragment, compact_html
from job_description_extraction.models import ModelUsage


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


DEFAULT_PRICES = {
    "gpt-5.6-luna": ModelPrice(input_per_million=0.20, output_per_million=1.20),
    "gpt-5.6-sol": ModelPrice(input_per_million=4.00, output_per_million=20.00),
}


class OpenAIJobExtractor:
    """Small adapter around Chat Completions with explicit usage accounting."""

    def __init__(self, model: str, price: ModelPrice | None = None):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install project dependencies before enabling LLM extraction") from exc
        self.client = OpenAI()
        self.model = model
        self.price = price or DEFAULT_PRICES.get(model, ModelPrice(0.0, 0.0))

    def extract_description(self, raw_html: str) -> tuple[str, ModelUsage, float]:
        prompt = (
            "Extract the complete job description from this career-page HTML. Preserve headings, "
            "paragraphs, and bullet lists. Remove navigation, cookie notices, application forms, "
            "headers, footers, recommended jobs, and sharing controls. Return JSON with exactly one "
            "field named description_html. Do not summarize or invent content.\n\nHTML:\n"
            + compact_html(raw_html)
        )
        return self._json_request(prompt, expected_key="description_html")

    def generate_xpath(self, raw_html: str) -> tuple[str, ModelUsage, float]:
        prompt = (
            "Study this job-detail page template and produce one reusable XPath that selects only "
            "the complete job-description container on other pages using the same template. Avoid "
            "job titles, location metadata, application forms, cookie UI, navigation, related jobs, "
            "and footers. Prefer stable ids, data attributes, or semantic attributes over positional "
            "indexes. Return JSON with exactly one field named xpath.\n\nHTML:\n"
            + compact_html(raw_html)
        )
        xpath, usage, latency_ms = self._json_request(prompt, expected_key="xpath", clean=False)
        if not xpath.startswith(("/", ".")) or any(token in xpath.lower() for token in ("document(", "collection(")):
            raise ValueError(f"Model returned an unsafe or invalid XPath: {xpath!r}")
        return xpath, usage, latency_ms

    def _json_request(
        self, prompt: str, expected_key: str, clean: bool = True
    ) -> tuple[str, ModelUsage, float]:
        started = time.perf_counter()
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a deterministic web-data extraction component. Return valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        latency_ms = (time.perf_counter() - started) * 1000
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
        value = str(payload.get(expected_key) or "").strip()
        if not value:
            raise ValueError(f"Model response did not contain {expected_key!r}")

        input_tokens = int(getattr(response.usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(response.usage, "completion_tokens", 0) or 0)
        cost = (
            input_tokens * self.price.input_per_million
            + output_tokens * self.price.output_per_million
        ) / 1_000_000
        call = {
            "model": self.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 8),
        }
        usage = ModelUsage(
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 8),
            calls=[call],
        )
        return (clean_fragment(value) if clean else value), usage, latency_ms


def merge_usage(*usage_values: ModelUsage) -> ModelUsage:
    calls: list[dict[str, Any]] = []
    models: list[str] = []
    for usage in usage_values:
        calls.extend(usage.calls)
        if usage.model and usage.model not in models:
            models.append(usage.model)
    return ModelUsage(
        model=",".join(models),
        input_tokens=sum(value.input_tokens for value in usage_values),
        output_tokens=sum(value.output_tokens for value in usage_values),
        cost_usd=round(sum(value.cost_usd for value in usage_values), 8),
        calls=calls,
    )

