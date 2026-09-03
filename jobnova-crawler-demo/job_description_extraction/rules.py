from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from job_description_extraction.models import ExtractionRule


class RuleRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.rules = self._load()

    def _load(self) -> dict[str, ExtractionRule]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return {key: ExtractionRule.from_dict(value) for key, value in payload.items()}

    def get(self, template_id: str) -> ExtractionRule | None:
        return self.rules.get(template_id)

    def put(self, template_id: str, xpath: str, source: str) -> ExtractionRule:
        rule = ExtractionRule(
            template_id=template_id,
            xpath=xpath,
            source=source,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.rules[template_id] = rule
        self.save()
        return rule

    def record(self, template_id: str, success: bool) -> None:
        rule = self.rules.get(template_id)
        if not rule:
            return
        if success:
            rule.success_count += 1
        else:
            rule.failure_count += 1
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: vars(value) for key, value in sorted(self.rules.items())}
        handle, temporary_path = tempfile.mkstemp(prefix=self.path.name, dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

