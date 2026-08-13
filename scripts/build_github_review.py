#!/usr/bin/env python3
import argparse
import html
import json
from pathlib import Path


def html_text(value):
    return html.escape(value).replace("\n", "<br>\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsv4", required=True, type=Path)
    parser.add_argument("--qwen", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    args = parser.parse_args()

    dsv4 = json.loads(args.dsv4.read_text(encoding="utf-8"))
    qwen = json.loads(args.qwen.read_text(encoding="utf-8"))
    qwen_by_id = {book["idx"]: book for book in qwen["books"]}
    args.out_dir.mkdir(parents=True, exist_ok=True)

    index_rows = []
    for book in dsv4["books"]:
        idx = book["idx"]
        qwen_book = qwen_by_id[idx]
        metadata = book.get("metadata", {})
        filename = f"{idx:02d}.md"
        pdf_url = html.escape(metadata.get("pdf_url", ""), quote=True)
        title = html.escape(book["title"])
        source = html.escape(book["source"])
        index_rows.append(f"| {idx:02d} | [{title}](reviews/{filename}) | {source} |")

        page = f"""# {idx:02d}. {title}

[{source}]({pdf_url})

<details>
<summary><strong>Same L5 input</strong></summary>
<br>
<div>{html_text(book["seg"])}</div>
</details>

## Model comparison

<table>
<thead><tr><th width="50%">DeepSeek-V4-Flash</th><th width="50%">Qwen3-235B-A22B</th></tr></thead>
<tbody><tr>
<td valign="top"><div>{html_text(book["models"]["dsv4-flash"]["l5"])}</div></td>
<td valign="top"><div>{html_text(qwen_book["l5"])}</div></td>
</tr></tbody>
</table>

[Back to all 30 papers](../review.md)
"""
        (args.out_dir / filename).write_text(page, encoding="utf-8")

    index = """# Paper L5: DeepSeek-V4-Flash vs Qwen3-235B-A22B

GitHub-native fallback for networks that cannot open GitHub Pages. All 30
papers use the same source segment and the same L5 prompt for both models.

| # | Paper | Source |
|---:|---|---|
""" + "\n".join(index_rows) + "\n"
    args.index.write_text(index, encoding="utf-8")
    print(f"saved {len(index_rows)} reviews -> {args.out_dir}")


if __name__ == "__main__":
    main()
