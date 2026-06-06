"""Crawl JD Help Center FAQ pages into JSONL.

The JD Help Center pages currently use GBK/GB2312 encoded HTML and a stable
URL shape:

    category/list page: https://help.jd.com/user/issue/list-112.html
    detail page:        https://help.jd.com/user/issue/325-915.html

The crawler intentionally stays conservative:
    - one request at a time
    - configurable delay
    - per-category limit
    - dedupe by canonical URL

Examples:
    python scripts/crawl_jd_faq.py --dry-run
    python scripts/crawl_jd_faq.py --per-category-limit 100 --output data/jd_faq.jsonl
    python scripts/crawl_jd_faq.py --categories 售后政策 物流配送
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional

BASE_URL = "https://help.jd.com"
INDEX_URL = f"{BASE_URL}/user/issue.html"
DEFAULT_OUTPUT = Path("data/jd_faq.jsonl")

USER_AGENT = (
    "Mozilla/5.0 (compatible; ecommerce-cs-jd-faq-crawler/1.0; "
    "+https://github.com/yyyz0211/ecommerce-cs)"
)

# The target buckets requested by step 4.5.1. The IDs are visible in
# help.jd.com/user/issue.html as li.list-item[data-id=...].
TARGET_CATEGORIES: dict[str, list[int]] = {
    "售后政策": [112, 117, 113, 114, 115, 116, 429, 488],
    "物流配送": [80, 81, 86, 310, 85, 82, 83, 84],
    "支付发票": [171, 172, 173, 175, 176, 177, 178, 179, 181, 959, 499, 501, 505],
    "账户管理": [149, 150, 151, 892],
}

BLOCK_TAGS = {
    "address",
    "article",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
    "ol",
}


@dataclass
class CategoryLink:
    category: str
    category_id: int
    url: str
    title: str


@dataclass
class FAQRecord:
    source: str
    category: str
    category_id: int
    question: str
    answer: str
    url: str
    fetched_at: str


class TextExtractor(HTMLParser):
    """Turn a fragment of HTML into readable text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in BLOCK_TAGS:
            self._chunks.append("\n")
        if tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self._chunks.append(f"[图片：{alt}]")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if not self._skip_depth and tag in BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data:
            self._chunks.append(data)

    def text(self) -> str:
        raw = html.unescape("".join(self._chunks))
        raw = raw.replace("\xa0", " ")
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


class CategoryParser(HTMLParser):
    """Parse the left-side category tree from help.jd.com/user/issue.html."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.categories: dict[int, dict[str, str | int]] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "li":
            return
        attr = dict(attrs)
        class_name = attr.get("class", "")
        if "list-item" not in class_name or "data-id" not in attr:
            return
        try:
            category_id = int(attr["data-id"])
        except ValueError:
            return
        self.categories[category_id] = {
            "id": category_id,
            "name": attr.get("data-name", "").strip(),
            "parent_id": int(attr["data-parent-id"]) if attr.get("data-parent-id", "").isdigit() else 0,
            "parent_name": attr.get("data-parent-name", "").strip(),
            "url": absolute_url(f"/user/issue/list-{category_id}.html"),
        }


class FAQListParser(HTMLParser):
    """Parse FAQ links from the first ul.help_list on a list page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.next_url: Optional[str] = None
        self._in_help_list = False
        self._help_list_done = False
        self._current_href: Optional[str] = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attr = dict(attrs)
        if tag == "ul" and not self._help_list_done and "help_list" in attr.get("class", ""):
            self._in_help_list = True
            return
        if tag == "a":
            href = attr.get("href")
            text_class = attr.get("class", "")
            if self._in_help_list and href:
                self._current_href = href
                self._current_text = []
            if href and "next" in text_class:
                self.next_url = absolute_url(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_help_list and self._current_href:
            title = clean_text("".join(self._current_text)).lstrip("·").strip()
            if title and "/user/issue/" in self._current_href:
                self.links.append((absolute_url(self._current_href), title))
            self._current_href = None
            self._current_text = []
        elif tag == "ul" and self._in_help_list:
            self._in_help_list = False
            self._help_list_done = True

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)


def clean_text(value: str) -> str:
    value = html.unescape(value or "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def absolute_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return urllib.parse.urljoin(BASE_URL, url)


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlparse(absolute_url(url))
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def detect_encoding(raw: bytes, headers) -> str:
    content_type = headers.get("Content-Type", "") if headers else ""
    match = re.search(r"charset=([\w-]+)", content_type, flags=re.I)
    if match:
        return normalize_encoding(match.group(1))
    head = raw[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset=['\"]?([\w-]+)", head, flags=re.I)
    if match:
        return normalize_encoding(match.group(1))
    return "gbk"


def normalize_encoding(value: str) -> str:
    value = value.strip().lower()
    if value in {"gb2312", "gb18030"}:
        return "gbk"
    return value or "gbk"


def fetch_html(url: str, *, timeout: float, retries: int, delay: float) -> str:
    request = urllib.request.Request(absolute_url(url), headers={"User-Agent": USER_AGENT})
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                encoding = detect_encoding(raw, response.headers)
                return raw.decode(encoding, errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            sleep_for = delay * (attempt + 1)
            logging.warning("Fetch failed, retrying in %.1fs: %s", sleep_for, url)
            time.sleep(sleep_for)
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def parse_categories(index_html: str) -> dict[int, dict[str, str | int]]:
    parser = CategoryParser()
    parser.feed(index_html)
    return parser.categories


def parse_faq_list(list_html: str) -> tuple[list[tuple[str, str]], Optional[str]]:
    parser = FAQListParser()
    parser.feed(list_html)
    return parser.links, parser.next_url


def extract_tag_block(source: str, *, tag: str, attr_name: str, attr_value: str) -> str:
    pattern = re.compile(
        rf"<{tag}\b(?=[^>]*\b{re.escape(attr_name)}=[\"'][^\"']*{re.escape(attr_value)}[^\"']*[\"'])[^>]*>",
        flags=re.I,
    )
    match = pattern.search(source)
    if not match:
        return ""

    start = match.start()
    cursor = match.end()
    depth = 1
    token_pattern = re.compile(rf"</?{tag}\b[^>]*>", flags=re.I)
    for token in token_pattern.finditer(source, cursor):
        token_text = token.group(0)
        if token_text.startswith("</"):
            depth -= 1
        elif not token_text.endswith("/>"):
            depth += 1
        if depth == 0:
            return source[start : token.end()]
    return source[start:]


def extract_detail(detail_html: str, fallback_title: str) -> tuple[str, str]:
    container = extract_tag_block(detail_html, tag="div", attr_name="id", attr_value="pdfContainer")
    if not container:
        container = extract_tag_block(detail_html, tag="div", attr_name="class", attr_value="contxt")
    if not container:
        container = detail_html

    title = fallback_title
    title_match = re.search(r'<div\b[^>]*class=["\'][^"\']*help-tit1[^"\']*["\'][^>]*>(.*?)</div>', container, re.I | re.S)
    if title_match:
        title = strip_html(title_match.group(1)) or fallback_title

    # Remove the visible title from answer to avoid duplicating question text.
    if title_match:
        container = container[: title_match.start()] + container[title_match.end() :]
    answer = strip_html(container)
    return clean_text(title), answer


def strip_html(fragment: str) -> str:
    extractor = TextExtractor()
    extractor.feed(fragment)
    return extractor.text()


def iter_target_category_links(
    discovered: dict[int, dict[str, str | int]],
    selected_categories: Iterable[str],
) -> list[CategoryLink]:
    links: list[CategoryLink] = []
    for bucket_name in selected_categories:
        for category_id in TARGET_CATEGORIES[bucket_name]:
            info = discovered.get(category_id)
            if info:
                title = str(info.get("name") or category_id)
                url = str(info.get("url") or absolute_url(f"/user/issue/list-{category_id}.html"))
            else:
                title = str(category_id)
                url = absolute_url(f"/user/issue/list-{category_id}.html")
            links.append(CategoryLink(category=bucket_name, category_id=category_id, title=title, url=url))
    return links


def collect_faq_links(
    category_link: CategoryLink,
    *,
    per_category_remaining: int,
    timeout: float,
    retries: int,
    delay: float,
    max_pages_per_list: int,
) -> list[tuple[str, str]]:
    collected: list[tuple[str, str]] = []
    seen: set[str] = set()
    page_url: Optional[str] = category_link.url
    pages = 0

    while page_url and len(collected) < per_category_remaining and pages < max_pages_per_list:
        logging.info("List page: %s", page_url)
        list_html = fetch_html(page_url, timeout=timeout, retries=retries, delay=delay)
        links, next_url = parse_faq_list(list_html)
        for url, title in links:
            key = canonical_url(url)
            if key not in seen:
                seen.add(key)
                collected.append((key, title))
                if len(collected) >= per_category_remaining:
                    break
        pages += 1
        page_url = next_url
        if page_url and len(collected) < per_category_remaining:
            time.sleep(delay)

    return collected


def crawl(
    *,
    categories: list[str],
    per_category_limit: int,
    output: Path,
    csv_output: Optional[Path],
    timeout: float,
    retries: int,
    delay: float,
    max_pages_per_list: int,
    dry_run: bool,
) -> list[FAQRecord]:
    index_html = fetch_html(INDEX_URL, timeout=timeout, retries=retries, delay=delay)
    discovered = parse_categories(index_html)
    logging.info("Discovered %d JD help categories", len(discovered))

    category_links = iter_target_category_links(discovered, categories)
    records: list[FAQRecord] = []
    seen_detail_urls: set[str] = set()
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    for bucket_name in categories:
        bucket_links = [link for link in category_links if link.category == bucket_name]
        bucket_seen: set[str] = set()
        bucket_candidates: list[tuple[CategoryLink, str, str]] = []

        for category_link in bucket_links:
            remaining = per_category_limit - len(bucket_seen)
            if remaining <= 0:
                break
            faq_links = collect_faq_links(
                category_link,
                per_category_remaining=remaining,
                timeout=timeout,
                retries=retries,
                delay=delay,
                max_pages_per_list=max_pages_per_list,
            )
            for url, title in faq_links:
                if url in bucket_seen:
                    continue
                bucket_seen.add(url)
                bucket_candidates.append((category_link, url, title))
                if len(bucket_seen) >= per_category_limit:
                    break
            time.sleep(delay)

        logging.info("%s candidate FAQ links: %d", bucket_name, len(bucket_candidates))
        if dry_run:
            for category_link, url, title in bucket_candidates[:10]:
                logging.info("DRY %s/%s: %s -> %s", bucket_name, category_link.title, title, url)
            continue

        for category_link, url, fallback_title in bucket_candidates:
            if url in seen_detail_urls:
                continue
            seen_detail_urls.add(url)
            logging.info("Detail page: %s", url)
            detail_html = fetch_html(url, timeout=timeout, retries=retries, delay=delay)
            question, answer = extract_detail(detail_html, fallback_title)
            if not question or not answer:
                logging.warning("Skip empty FAQ: %s", url)
                continue
            records.append(
                FAQRecord(
                    source="京东帮助中心",
                    category=bucket_name,
                    category_id=category_link.category_id,
                    question=question,
                    answer=answer,
                    url=url,
                    fetched_at=fetched_at,
                )
            )
            time.sleep(delay)

    if not dry_run:
        write_jsonl(output, records)
        if csv_output:
            write_csv(csv_output, records)
    return records


def write_jsonl(path: Path, records: list[FAQRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for record in records:
            fp.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    logging.info("Wrote %d records to %s", len(records), path)


def write_csv(path: Path, records: list[FAQRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(asdict(records[0]).keys()) if records else list(FAQRecord.__dataclass_fields__))
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    logging.info("Wrote %d records to %s", len(records), path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl JD Help Center FAQ pages.")
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=sorted(TARGET_CATEGORIES),
        default=sorted(TARGET_CATEGORIES),
        help="Target high-level categories to crawl.",
    )
    parser.add_argument("--per-category-limit", type=int, default=100, help="Maximum FAQ records per high-level category.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSONL output path.")
    parser.add_argument("--csv-output", type=Path, default=None, help="Optional CSV output path.")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retry count for failed requests.")
    parser.add_argument("--delay", type=float, default=0.8, help="Delay seconds between requests.")
    parser.add_argument("--max-pages-per-list", type=int, default=10, help="Safety cap for pagination per list page.")
    parser.add_argument("--dry-run", action="store_true", help="Only collect/list candidate links; do not fetch detail pages or write files.")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")
    records = crawl(
        categories=args.categories,
        per_category_limit=args.per_category_limit,
        output=args.output,
        csv_output=args.csv_output,
        timeout=args.timeout,
        retries=args.retries,
        delay=args.delay,
        max_pages_per_list=args.max_pages_per_list,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        logging.info("Dry run finished. No files written.")
    else:
        counts: dict[str, int] = {}
        for record in records:
            counts[record.category] = counts.get(record.category, 0) + 1
        logging.info("Category counts: %s", counts)


if __name__ == "__main__":
    main()
