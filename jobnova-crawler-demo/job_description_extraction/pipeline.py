from __future__ import annotations

import json
import time
from pathlib import Path

from job_description_extraction.html_utils import (
    extract_jobposting_jsonld,
    extract_xpath,
    html_to_text,
    score_description,
)
from job_description_extraction.llm import OpenAIJobExtractor, merge_usage
from job_description_extraction.models import ExtractionResult, ModelUsage
from job_description_extraction.rules import RuleRegistry
from job_description_extraction.templates import BUILT_IN_XPATHS, detect_template


class HybridExtractor:
    MODES = {"llm_only", "template_aware", "hybrid"}

    def __init__(
        self,
        registry: RuleRegistry,
        low_cost_llm: OpenAIJobExtractor | None = None,
        strong_llm: OpenAIJobExtractor | None = None,
        confidence_threshold: float = 0.65,
        event_log: str | Path | None = None,
    ):
        self.registry = registry
        self.low_cost_llm = low_cost_llm
        self.strong_llm = strong_llm
        self.confidence_threshold = confidence_threshold
        self.event_log = Path(event_log) if event_log else None

    def extract(self, url: str, raw_html: str, mode: str = "hybrid") -> ExtractionResult:
        if mode not in self.MODES:
            raise ValueError(f"mode must be one of {sorted(self.MODES)}")
        started = time.perf_counter()
        template_id = detect_template(url, raw_html)
        warnings: list[str] = []
        usages: list[ModelUsage] = []

        if mode == "llm_only":
            result = self._llm_extract(url, template_id, raw_html, started)
            self._record(result)
            return result

        jsonld = extract_jobposting_jsonld(raw_html)
        result = self._build_result(url, template_id, "structured_data", jsonld, started)
        if result.successful:
            self._record(result)
            return result
        warnings.extend(result.warnings or ["structured_data_missing_or_low_confidence"])

        rule = self.registry.get(template_id)
        xpath = rule.xpath if rule else BUILT_IN_XPATHS.get(template_id, "")
        if xpath:
            description = extract_xpath(raw_html, xpath)
            rule_source = rule.source if rule else "built_in"
            result = self._build_result(
                url, template_id, f"template_rule:{rule_source}", description, started
            )
            self.registry.record(template_id, result.successful)
            if result.successful:
                result.warnings = warnings + result.warnings
                self._record(result)
                return result
            warnings.extend(result.warnings or ["template_rule_failed"])

        if self.strong_llm:
            try:
                learned_xpath, usage, _ = self.strong_llm.generate_xpath(raw_html)
                usages.append(usage)
                description = extract_xpath(raw_html, learned_xpath)
                candidate = self._build_result(
                    url, template_id, "template_rule:llm_learned", description, started
                )
                candidate.usage = merge_usage(*usages)
                if candidate.successful:
                    self.registry.put(template_id, learned_xpath, "llm_learned")
                    candidate.warnings = warnings + candidate.warnings
                    self._record(candidate)
                    return candidate
                warnings.extend(candidate.warnings or ["learned_rule_low_confidence"])
            except Exception as exc:
                warnings.append(f"rule_learning_failed:{type(exc).__name__}")
        else:
            warnings.append("strong_llm_not_configured")

        if mode == "hybrid" and self.low_cost_llm:
            fallback = self._llm_extract(url, template_id, raw_html, started)
            fallback.strategy = "llm_fallback"
            fallback.usage = merge_usage(*usages, fallback.usage)
            fallback.warnings = warnings + fallback.warnings
            self._record(fallback)
            return fallback

        failed = ExtractionResult(
            url=url,
            template_id=template_id,
            strategy="failed",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            warnings=warnings,
            usage=merge_usage(*usages),
        )
        self._record(failed)
        return failed

    def _llm_extract(
        self, url: str, template_id: str, raw_html: str, started: float
    ) -> ExtractionResult:
        if not self.low_cost_llm:
            return ExtractionResult(
                url=url,
                template_id=template_id,
                strategy="llm_only",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                warnings=["low_cost_llm_not_configured"],
            )
        try:
            description, usage, _ = self.low_cost_llm.extract_description(raw_html)
            result = self._build_result(url, template_id, "llm_only", description, started)
            result.usage = usage
            return result
        except Exception as exc:
            return ExtractionResult(
                url=url,
                template_id=template_id,
                strategy="llm_only",
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                warnings=[f"llm_extraction_failed:{type(exc).__name__}"],
            )

    def _build_result(
        self,
        url: str,
        template_id: str,
        strategy: str,
        description_html: str,
        started: float,
    ) -> ExtractionResult:
        confidence, warnings = score_description(description_html)
        text = html_to_text(description_html)
        return ExtractionResult(
            url=url,
            template_id=template_id,
            strategy=strategy,
            description_html=description_html,
            description_text=text,
            confidence=confidence,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            successful=bool(text) and confidence >= self.confidence_threshold,
            warnings=warnings,
        )

    def _record(self, result: ExtractionResult) -> None:
        if not self.event_log:
            return
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        with self.event_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")

