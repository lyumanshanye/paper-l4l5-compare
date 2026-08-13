#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import random
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from pypdf import PdfReader


DOI_PREFIX = "https://doi.org/"
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def normalize_doi(value):
    value = (value or "").strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    return value.rstrip(" .").lower()


def load_candidates(csv_path, seed):
    candidates = []
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        for row_number, row in enumerate(csv.DictReader(source), 2):
            doi = normalize_doi(row.get("doi"))
            if not DOI_RE.match(doi):
                continue
            language = (row.get("language") or "").strip().lower()
            if language not in {"", "en"}:
                continue
            try:
                size_mib = float(row.get("file_size") or 0)
            except ValueError:
                size_mib = 0
            if size_mib and not 0.05 <= size_mib <= 30:
                continue
            candidates.append({
                "csv_row": row_number,
                "paper_id": row.get("paper_id") or row.get("md5"),
                "doi": doi,
                "csv_title": row.get("title") or "",
                "csv_language": language,
                "publish_year": row.get("publish_year") or "",
                "journal_name": row.get("journal_name") or "",
                "author": row.get("author") or "",
                "s3_path": row.get("s3_path") or "",
                "bucket_name": row.get("bucket_name") or "",
            })
    random.Random(seed).shuffle(candidates)
    return candidates


def openalex_batch(session, candidates):
    values = "|".join(DOI_PREFIX + item["doi"] for item in candidates)
    response = session.get(
        "https://api.openalex.org/works",
        params={"filter": "doi:" + values, "per-page": len(candidates), "mailto": "noreply@example.com"},
        timeout=45,
    )
    response.raise_for_status()
    works = {}
    for work in response.json().get("results", []):
        doi = normalize_doi(work.get("doi"))
        if doi:
            works[doi] = work
    return works


def pdf_urls(work):
    locations = []
    for key in ("best_oa_location", "primary_location"):
        if work.get(key):
            locations.append(work[key])
    locations.extend(work.get("locations") or [])
    open_access = work.get("open_access") or {}
    urls = []
    for location in locations:
        if location.get("pdf_url"):
            urls.append(location["pdf_url"])
    if open_access.get("oa_url"):
        urls.append(open_access["oa_url"])
    seen = set()
    return [url for url in urls if url and not (url in seen or seen.add(url))]


def download_pdf(session, urls, destination):
    errors = []
    for url in urls:
        try:
            response = session.get(url, timeout=60, stream=True, allow_redirects=True)
            response.raise_for_status()
            body = bytearray()
            for block in response.iter_content(1024 * 256):
                body.extend(block)
                if len(body) > 40 * 1024 * 1024:
                    raise ValueError("PDF exceeds 40 MiB")
            if not bytes(body[:1024]).lstrip().startswith(b"%PDF"):
                raise ValueError("response is not a PDF")
            destination.write_bytes(body)
            return url, len(body), errors
        except Exception as error:
            errors.append(f"{url}: {type(error).__name__}: {error}")
    return None, 0, errors


def extract_text(pdf_path):
    reader = PdfReader(str(pdf_path), strict=False)
    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            pages.append(text)
    return "\n\n".join(pages).strip(), len(reader.pages)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--max-candidates", type=int, default=3000)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    pdf_dir = args.out / "pdfs"
    text_dir = args.out / "texts"
    pdf_dir.mkdir(exist_ok=True)
    text_dir.mkdir(exist_ok=True)
    manifest_path = args.out / "fetch_manifest.jsonl"
    failures_path = args.out / "fetch_failures.jsonl"

    candidates = load_candidates(args.csv, args.seed)[: args.max_candidates]
    session = requests.Session()
    session.headers.update({"User-Agent": "paper30-dsv4-compare/1.0 (research evaluation)"})
    selected = []

    with manifest_path.open("w", encoding="utf-8") as manifest, failures_path.open("w", encoding="utf-8") as failures:
        for offset in range(0, len(candidates), args.batch_size):
            batch = candidates[offset : offset + args.batch_size]
            try:
                works = openalex_batch(session, batch)
            except Exception as error:
                failures.write(json.dumps({"offset": offset, "stage": "openalex", "error": repr(error)}) + "\n")
                failures.flush()
                time.sleep(2)
                continue
            for candidate in batch:
                work = works.get(candidate["doi"])
                if not work:
                    continue
                urls = pdf_urls(work)
                if not urls:
                    continue
                paper_id = candidate["paper_id"] or hashlib.sha1(candidate["doi"].encode()).hexdigest()
                pdf_path = pdf_dir / f"{paper_id}.pdf"
                text_path = text_dir / f"{paper_id}.txt"
                used_url, byte_count, errors = download_pdf(session, urls, pdf_path)
                if not used_url:
                    failures.write(json.dumps({**candidate, "stage": "download", "errors": errors}, ensure_ascii=False) + "\n")
                    failures.flush()
                    continue
                try:
                    text, page_count = extract_text(pdf_path)
                except Exception as error:
                    pdf_path.unlink(missing_ok=True)
                    failures.write(json.dumps({**candidate, "stage": "extract", "error": repr(error)}, ensure_ascii=False) + "\n")
                    failures.flush()
                    continue
                alpha_count = len(re.findall(r"[A-Za-z]", text))
                if len(text) < 8000 or alpha_count / max(len(text), 1) < 0.35:
                    pdf_path.unlink(missing_ok=True)
                    failures.write(json.dumps({**candidate, "stage": "validate", "chars": len(text), "alpha": alpha_count}, ensure_ascii=False) + "\n")
                    failures.flush()
                    continue
                text_path.write_text(text, encoding="utf-8")
                record = {
                    **candidate,
                    "sample_index": len(selected) + 1,
                    "openalex_id": work.get("id"),
                    "title": work.get("display_name") or candidate["csv_title"],
                    "language": work.get("language") or candidate["csv_language"],
                    "type": work.get("type"),
                    "cited_by_count": work.get("cited_by_count"),
                    "pdf_url": used_url,
                    "pdf_bytes": byte_count,
                    "page_count": page_count,
                    "text_chars": len(text),
                    "pdf_path": str(pdf_path),
                    "text_path": str(text_path),
                }
                selected.append(record)
                manifest.write(json.dumps(record, ensure_ascii=False) + "\n")
                manifest.flush()
                print(f"[{len(selected):02d}/{args.count}] row={candidate['csv_row']} pages={page_count} chars={len(text)} {record['title']}", flush=True)
                if len(selected) >= args.count:
                    summary = {
                        "seed": args.seed,
                        "requested": args.count,
                        "selected": len(selected),
                        "candidates_examined_through": offset + len(batch),
                        "source_csv": str(args.csv),
                    }
                    (args.out / "fetch_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                    return
            time.sleep(0.2)
    raise SystemExit(f"only fetched {len(selected)} usable papers from {len(candidates)} candidates")


if __name__ == "__main__":
    main()
