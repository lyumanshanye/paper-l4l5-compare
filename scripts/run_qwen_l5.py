#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def load_prompt(path: Path):
    source = path.read_text(encoding="utf-8")
    match = re.search(
        r"def create_llm_refine_chunk_prompt.*?\n    return prompt\n",
        source,
        flags=re.DOTALL,
    )
    if not match:
        raise RuntimeError(f"cannot load L5 prompt from {path}")
    namespace = {}
    exec(match.group(0), namespace)
    return namespace["create_llm_refine_chunk_prompt"]


def clean_l5(text: str) -> str:
    text = re.sub(r"\*\*refined text:?\*\*", "", text, flags=re.IGNORECASE).strip()
    return re.sub(r"^refined text:?", "", text, flags=re.IGNORECASE).strip().rstrip("#").strip()


def post_json(url: str, body: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:30000/v1/chat/completions")
    parser.add_argument("--model", default="qwen3-235b-a22b")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument(
        "--prompt",
        default=Path(
            "/inspire/hdd2/project/special-project-1/public/yelv/"
            "pdf/merged_pipeline/refine/prompt/llm_refine_chunk.py"
        ),
        type=Path,
    )
    args = parser.parse_args()

    create_prompt = load_prompt(args.prompt)
    source = json.loads(args.samples.read_text(encoding="utf-8"))
    records = source["samples"][: args.limit] if args.limit else source["samples"]
    completed = 0
    lock = threading.Lock()

    def infer(record: dict) -> tuple[int, str, dict, float, str]:
        body = {
            "model": args.model,
            "messages": [{"role": "user", "content": create_prompt(record["seg"])}],
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": args.max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        started = time.monotonic()
        response = post_json(args.url, body, args.timeout)
        choice = response["choices"][0]
        text = clean_l5(choice["message"].get("content") or "")
        return (
            record["idx"],
            text,
            response.get("usage") or {},
            time.monotonic() - started,
            choice.get("finish_reason") or "",
        )

    results = {record["idx"]: dict(record) for record in records}
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {executor.submit(infer, record): record for record in records}
        for future in as_completed(futures):
            idx, text, usage, elapsed, finish_reason = future.result()
            if not text or finish_reason != "stop":
                raise RuntimeError(
                    f"paper={idx} invalid response: finish_reason={finish_reason} chars={len(text)}"
                )
            results[idx]["l5"] = text
            results[idx]["l5_usage"] = usage
            results[idx]["l5_seconds"] = elapsed
            with lock:
                completed += 1
                print(
                    f"[{completed:02d}/{len(records)}] paper={idx:02d} "
                    f"chars={len(text)} seconds={elapsed:.1f}",
                    flush=True,
                )

    output = {
        "model": args.model,
        "n_books": len(records),
        "books": [results[index] for index in sorted(results)],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
