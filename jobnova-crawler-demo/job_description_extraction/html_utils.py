from __future__ import annotations

import html as html_stdlib
import json
import re
from collections.abc import Iterable
from typing import Any

from lxml import etree, html


REMOVABLE_TAGS = {"script", "style", "noscript", "nav", "footer", "form", "svg", "canvas"}
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "div", "dl", "dt", "dd",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "ol",
    "p", "pre", "section", "table", "tr", "ul",
}
CONTAMINATION_TERMS = {
    "accept cookies", "cookie preferences", "recommended jobs", "related jobs",
    "sign in", "log in", "privacy policy", "share this job", "apply for this job",
    "upload resume", "first name", "last name", "voluntary self-identification",
}


def parse_document(raw_html: str) -> html.HtmlElement:
    parser = html.HTMLParser(encoding="utf-8", recover=True)
    return html.fromstring(raw_html.encode("utf-8", errors="replace"), parser=parser)


def extract_jobposting_jsonld(raw_html: str) -> str:
    """Return the description from the first JobPosting JSON-LD object."""
    root = parse_document(raw_html)
    for node in root.xpath("//script[contains(translate(@type,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ld+json')]"):
        raw = node.text or ""
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        for candidate in _walk_json(payload):
            candidate_type = candidate.get("@type")
            types = candidate_type if isinstance(candidate_type, list) else [candidate_type]
            if "JobPosting" in types and candidate.get("description"):
                return clean_fragment(str(candidate["description"]))
    return ""


def _walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def extract_xpath(raw_html: str, xpath: str) -> str:
    root = parse_document(raw_html)
    try:
        matches = root.xpath(xpath)
    except etree.XPathError:
        return ""
    fragments: list[str] = []
    for match in matches:
        if isinstance(match, etree._Element):
            fragments.append(etree.tostring(match, encoding="unicode", method="html"))
        elif match is not None:
            fragments.append(f"<p>{html_stdlib.escape(str(match))}</p>")
    return clean_fragment("\n".join(fragments))


def clean_fragment(fragment: str) -> str:
    if not fragment.strip():
        return ""
    wrapper = html.fragment_fromstring(fragment, create_parent="div")
    for node in list(wrapper.iterdescendants()):
        tag = str(node.tag).lower() if isinstance(node.tag, str) else ""
        if tag in REMOVABLE_TAGS:
            node.drop_tree()
            continue
        for attribute in list(node.attrib):
            if attribute not in {"href"}:
                del node.attrib[attribute]
        if "href" in node.attrib and not node.attrib["href"].startswith(("http://", "https://", "mailto:")):
            del node.attrib["href"]
    serialized = "".join(
        etree.tostring(child, encoding="unicode", method="html") for child in wrapper
    )
    if wrapper.text and wrapper.text.strip():
        serialized = f"<p>{html_stdlib.escape(wrapper.text.strip())}</p>" + serialized
    return re.sub(r"\n{3,}", "\n\n", serialized).strip()


def html_to_text(fragment: str) -> str:
    if not fragment.strip():
        return ""
    root = html.fragment_fromstring(fragment, create_parent="div")
    chunks: list[str] = []

    def visit(node: etree._Element):
        tag = str(node.tag).lower() if isinstance(node.tag, str) else ""
        if tag == "li":
            chunks.append("\n- ")
        elif tag in BLOCK_TAGS:
            chunks.append("\n")
        if node.text:
            chunks.append(node.text)
        for child in node:
            visit(child)
            if child.tail:
                chunks.append(child.tail)
        if tag in BLOCK_TAGS:
            chunks.append("\n")

    visit(root)
    text = "".join(chunks).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def score_description(fragment: str) -> tuple[float, list[str]]:
    text = html_to_text(fragment)
    lowered = text.lower()
    warnings: list[str] = []
    if len(text) < 200:
        warnings.append("description_too_short")
    contamination_hits = [term for term in CONTAMINATION_TERMS if term in lowered]
    if contamination_hits:
        warnings.append("possible_boilerplate:" + ",".join(sorted(contamination_hits)))

    length_score = min(1.0, len(text) / 1200)
    structure_score = min(1.0, (fragment.count("<li") + fragment.count("<h") + 1) / 6)
    contamination_penalty = min(0.5, 0.08 * len(contamination_hits))
    confidence = max(0.0, min(1.0, 0.65 * length_score + 0.35 * structure_score - contamination_penalty))
    return round(confidence, 4), warnings


def compact_html(raw_html: str, max_chars: int = 120_000) -> str:
    """Remove obviously irrelevant nodes before sending HTML to a model."""
    root = parse_document(raw_html)
    for node in list(root.iterdescendants()):
        tag = str(node.tag).lower() if isinstance(node.tag, str) else ""
        if tag in REMOVABLE_TAGS - {"script"}:
            node.drop_tree()
        elif tag == "script" and "ld+json" not in str(node.get("type", "")).lower():
            node.drop_tree()
    compacted = etree.tostring(root, encoding="unicode", method="html")
    compacted = re.sub(r"\s+", " ", compacted)
    return compacted[:max_chars]

