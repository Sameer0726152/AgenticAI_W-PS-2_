"""Turns a job posting URL into plain text via the Greenhouse / Lever public APIs."""
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from app import config


class JobFetchError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class FetchedJob:
    source_type: str  # greenhouse | lever | manual
    source_url: str
    text: str
    company: str | None = None
    title: str | None = None
    location: str | None = None


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK_TAGS or tag == "li":
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _get_json(url: str) -> dict:
    try:
        resp = httpx.get(
            url, headers={"User-Agent": config.HTTP_USER_AGENT}, timeout=20,
            follow_redirects=True, verify=config.SSL_CONTEXT,
        )
    except httpx.HTTPError as e:
        raise JobFetchError(502, f"Could not reach job board: {e}") from e
    if resp.status_code == 404:
        raise JobFetchError(404, "Posting not found - it may be closed. Paste the posting text instead.")
    if resp.status_code != 200:
        raise JobFetchError(502, f"Job board returned HTTP {resp.status_code}")
    return resp.json()


def _fetch_greenhouse(url: str, board: str, job_id: str) -> FetchedJob:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
    # Greenhouse returns HTML that is itself HTML-escaped.
    text = html_to_text(html.unescape(data.get("content", "")))
    return FetchedJob(
        source_type="greenhouse",
        source_url=url,
        text=text,
        company=data.get("company_name") or board.replace("-", " ").title(),
        title=data.get("title"),
        location=(data.get("location") or {}).get("name"),
    )


def _fetch_lever(url: str, host: str, company: str, posting_id: str) -> FetchedJob:
    api_host = "api.eu.lever.co" if ".eu." in host else "api.lever.co"
    data = _get_json(f"https://{api_host}/v0/postings/{company}/{posting_id}")
    sections = [data.get("descriptionPlain", "")]
    for block in data.get("lists", []):
        sections.append(f"{block.get('text', '')}\n{html_to_text(block.get('content', ''))}")
    sections.append(data.get("additionalPlain", ""))
    return FetchedJob(
        source_type="lever",
        source_url=url,
        text="\n\n".join(s.strip() for s in sections if s and s.strip()),
        company=company.replace("-", " ").title(),
        title=data.get("text"),
        location=(data.get("categories") or {}).get("location"),
    )


def fetch_job(url: str, pasted_text: str | None = None) -> FetchedJob:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise JobFetchError(400, "Enter a full job posting URL (https://...)")
    if pasted_text and pasted_text.strip():
        return FetchedJob(source_type="manual", source_url=url, text=pasted_text.strip())

    host = parsed.netloc.lower()
    parts = [p for p in parsed.path.split("/") if p]
    if host.endswith("greenhouse.io") and len(parts) >= 3 and parts[1] == "jobs":
        return _fetch_greenhouse(url, parts[0], parts[2])
    if host.endswith("lever.co") and len(parts) >= 2:
        return _fetch_lever(url, host, parts[0], parts[1])
    raise JobFetchError(400, "Only Greenhouse and Lever URLs are fetched automatically. Paste the posting text too.")
