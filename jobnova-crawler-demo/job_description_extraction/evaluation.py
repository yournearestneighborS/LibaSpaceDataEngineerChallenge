from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Iterable

from job_description_extraction.models import ExtractionResult


TOKEN_PATTERN = re.compile(r"\w+(?:[+#.-]\w+)*", re.UNICODE)


@dataclass
class PageMetrics:
    completeness_recall: float
    content_precision: float
    accuracy_f1: float
    contamination_rate: float
    structure_recall: float
    full_extraction: bool


def evaluate_text(candidate: str, ground_truth: str) -> PageMetrics:
    candidate_tokens = Counter(_tokens(candidate))
    truth_tokens = Counter(_tokens(ground_truth))
    overlap = sum((candidate_tokens & truth_tokens).values())
    candidate_total = sum(candidate_tokens.values())
    truth_total = sum(truth_tokens.values())
    precision = overlap / candidate_total if candidate_total else 0.0
    recall = overlap / truth_total if truth_total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    structure_recall = _structure_recall(candidate, ground_truth)
    return PageMetrics(
        completeness_recall=round(recall, 4),
        content_precision=round(precision, 4),
        accuracy_f1=round(f1, 4),
        # No extracted content is a completeness failure, not contamination.
        # Contamination measures the share of *returned* content that is extra.
        contamination_rate=round(1 - precision, 4) if candidate_total else 0.0,
        structure_recall=round(structure_recall, 4),
        full_extraction=recall >= 0.98 and precision >= 0.98 and structure_recall >= 0.95,
    )


def result_row(mode: str, result: ExtractionResult, ground_truth: str) -> dict:
    metrics = evaluate_text(result.description_text, ground_truth)
    return {
        "url": result.url,
        "mode": mode,
        "template_id": result.template_id,
        "strategy": result.strategy,
        **asdict(metrics),
        "successful": result.successful,
        "confidence": result.confidence,
        "latency_ms": result.latency_ms,
        "model": result.usage.model,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "cost_usd": result.usage.cost_usd,
    }


def aggregate_rows(rows: Iterable[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["mode"], []).append(row)
    aggregates: list[dict] = []
    for mode, values in sorted(grouped.items()):
        count = len(values)
        total_cost = sum(value["cost_usd"] for value in values)
        aggregates.append(
            {
                "mode": mode,
                "pages": count,
                "avg_completeness_recall": round(mean(v["completeness_recall"] for v in values), 4),
                "avg_content_precision": round(mean(v["content_precision"] for v in values), 4),
                "avg_accuracy_f1": round(mean(v["accuracy_f1"] for v in values), 4),
                "avg_contamination_rate": round(mean(v["contamination_rate"] for v in values), 4),
                "avg_structure_recall": round(mean(v["structure_recall"] for v in values), 4),
                "full_extraction_rate": round(sum(v["full_extraction"] for v in values) / count, 4),
                "avg_latency_ms": round(mean(v["latency_ms"] for v in values), 3),
                "total_cost_usd": round(total_cost, 6),
                "cost_per_page_usd": round(total_cost / count, 8),
                "estimated_cost_100k_usd": round(total_cost / count * 100_000, 2),
            }
        )
    return aggregates


def _tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _structure_recall(candidate: str, ground_truth: str) -> float:
    truth_bullets = sum(line.lstrip().startswith(("- ", "* ", "• ")) for line in ground_truth.splitlines())
    candidate_bullets = sum(line.lstrip().startswith(("- ", "* ", "• ")) for line in candidate.splitlines())
    bullet_recall = min(1.0, candidate_bullets / truth_bullets) if truth_bullets else 1.0

    truth_headings = _heading_blocks(ground_truth)
    candidate_headings = _heading_blocks(candidate)
    heading_recall = (
        len(truth_headings & candidate_headings) / len(truth_headings) if truth_headings else 1.0
    )
    return (bullet_recall + heading_recall) / 2


def _heading_blocks(text: str) -> set[str]:
    headings: set[str] = set()
    for block in re.split(r"\n\s*\n", text):
        value = " ".join(block.split()).strip()
        if (
            value
            and "\n" not in block.strip()
            and len(value) <= 100
            and not value.startswith(("- ", "* ", "• "))
            and not value.endswith((".", ",", ";"))
            and any(character.isalpha() for character in value)
        ):
            headings.add(value.casefold())
    return headings
