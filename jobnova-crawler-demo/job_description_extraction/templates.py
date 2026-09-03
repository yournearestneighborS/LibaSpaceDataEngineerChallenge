from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse


ATS_MARKERS = {
    "smartrecruiters": ("smartrecruiters.com", "smartrecruiters"),
    "greenhouse": ("greenhouse.io", "greenhouse"),
    "lever": ("lever.co", "lever-jobs"),
    "ashby": ("ashbyhq.com", "ashby"),
    "workday": ("myworkdayjobs.com", "workday"),
    "icims": ("icims.com", "icims"),
    "teamtailor": ("teamtailor.com", "teamtailor"),
    "breezy": ("breezy.hr", "breezy"),
    "jobvite": ("jobs.jobvite.com", "jobvite"),
    "successfactors": ("successfactors", "career_site"),
}


BUILT_IN_XPATHS = {
    "smartrecruiters": "//*[@itemprop='description' or contains(@class,'job-description')]",
    "greenhouse": "//*[@id='content']//div[contains(@class,'job__description') or contains(@class,'job-post')] | //*[@id='content']/*[not(self::form)]",
    "lever": "//div[contains(concat(' ',normalize-space(@class),' '),' content ')]",
    "icims": "//div[contains(@class,'iCIMS_JobContent') or contains(@class,'job-description')]",
    "teamtailor": "//*[contains(@class,'job-posting') and contains(@class,'description')] | //*[@data-controller='job-description']",
    "breezy": "//*[contains(@class,'description') and not(contains(@class,'meta'))]",
    "jobvite": "//*[@id='jv-job-detail' or contains(@class,'jv-job-detail-description')]",
}


def detect_template(url: str, raw_html: str) -> str:
    haystack = f"{url}\n{raw_html[:80_000]}".lower()
    for template_id, markers in ATS_MARKERS.items():
        if any(marker in haystack for marker in markers):
            return template_id

    hostname = urlparse(url).hostname or "unknown"
    tag_signature = "|".join(re.findall(r"<([a-z0-9]+)(?:\s|>)", raw_html[:40_000].lower())[:120])
    digest = hashlib.sha256(tag_signature.encode("utf-8")).hexdigest()[:12]
    return f"custom:{hostname}:{digest}"

