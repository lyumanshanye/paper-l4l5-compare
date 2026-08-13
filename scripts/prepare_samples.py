#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

from transformers import AutoTokenizer


REFERENCE_RE = re.compile(
    r"^\s*(references|bibliography|acknowledg(?:e)?ments?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
ABSTRACT_LABEL_RE = re.compile(r"^\s*([SP])(\d+)\s*$", re.MULTILINE)


def paragraph_offsets(text):
    offsets = []
    for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, flags=re.DOTALL):
        paragraph = match.group(0).strip()
        if len(paragraph) >= 80:
            offsets.append((match.start(), paragraph))
    return offsets


def normalized_with_offsets(text):
    normalized = []
    offsets = []
    for offset, character in enumerate(text.lower()):
        if character.isalnum():
            normalized.append(character)
            offsets.append(offset)
    return "".join(normalized), offsets


def locate_article(text, title):
    normalized_text, offsets = normalized_with_offsets(text)
    normalized_title = "".join(character for character in title.lower() if character.isalnum())
    normalized_start = normalized_text.find(normalized_title)
    article_start = offsets[normalized_start] if normalized_start >= 0 else 0

    end_candidates = []
    reference = REFERENCE_RE.search(text, article_start + 500)
    if reference:
        end_candidates.append(reference.start())

    labels = [match for match in ABSTRACT_LABEL_RE.finditer(text, max(0, article_start - 200), article_start + 100)]
    if labels:
        prefix, number = labels[-1].group(1), int(labels[-1].group(2))
        next_label = re.search(rf"^\s*{prefix}{number + 1}\s*$", text[article_start + 500 :], re.MULTILINE)
        if next_label:
            end_candidates.append(article_start + 500 + next_label.start())

    article_end = min(end_candidates) if end_candidates else len(text)
    return article_start, article_end, normalized_start >= 0


def choose_region(text, title, tokenizer, sample_index, token_count):
    article_start, article_end, title_found = locate_article(text, title)
    article = text[article_start:article_end]
    paragraphs = paragraph_offsets(article)
    if not paragraphs:
        paragraphs = [(0, article.strip())] if article.strip() else []
    if not paragraphs:
        raise ValueError("empty article")
    stop_offset = len(article)
    usable = [(offset, paragraph) for offset, paragraph in paragraphs if offset < stop_offset]
    fractions = (0.32, 0.40, 0.48, 0.56, 0.64)
    target = stop_offset * fractions[(sample_index - 1) % len(fractions)]
    start_position = min(range(len(usable)), key=lambda index: abs(usable[index][0] - target))
    suffix_token_count = sum(
        len(tokenizer.encode(paragraph, add_special_tokens=False))
        for _, paragraph in usable[start_position:]
    )
    while start_position > 0 and suffix_token_count < token_count:
        start_position -= 1
        suffix_token_count += len(tokenizer.encode(usable[start_position][1], add_special_tokens=False))
    region = "\n\n".join(paragraph for _, paragraph in usable[start_position:])
    ids = tokenizer.encode(region, add_special_tokens=False)[:token_count]
    if len(ids) < token_count * 0.75:
        ids = tokenizer.encode(article, add_special_tokens=False)[:token_count]
        start_position = 0
    if len(ids) < 128:
        raise ValueError(f"article too short: {len(ids)} tokens")
    return (
        tokenizer.decode(ids, skip_special_tokens=True),
        len(ids),
        start_position,
        article_start,
        article_end,
        title_found,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--tokenizer", required=True, type=Path)
    parser.add_argument("--tokens", type=int, default=1024)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer), trust_remote_code=True)
    samples = []
    for line in args.manifest.open(encoding="utf-8"):
        record = json.loads(line)
        text = Path(record["text_path"]).read_text(encoding="utf-8")
        segment, segment_tokens, paragraph_index, article_start, article_end, title_found = choose_region(
            text, record["title"], tokenizer, record["sample_index"], args.tokens
        )
        samples.append({
            "idx": record["sample_index"],
            "paper_id": record["paper_id"],
            "csv_row": record["csv_row"],
            "doi": record["doi"],
            "title": record["title"],
            "journal_name": record["journal_name"],
            "publish_year": record["publish_year"],
            "openalex_id": record["openalex_id"],
            "pdf_url": record["pdf_url"],
            "page_count": record["page_count"],
            "text_chars": record["text_chars"],
            "segment_tokens": segment_tokens,
            "segment_paragraph_index": paragraph_index,
            "article_start_char": article_start,
            "article_end_char": article_end,
            "article_chars": article_end - article_start,
            "title_found": title_found,
            "seg": segment,
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"seed": 20260813, "samples": samples}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(samples)} samples -> {args.out}")


if __name__ == "__main__":
    main()
