#!/usr/bin/env python3
import argparse
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen


def load_function(path, function_name):
    source = path.read_text(encoding="utf-8")
    match = re.search(rf"def {function_name}.*?\n    return prompt\n", source, flags=re.DOTALL)
    if not match:
        raise RuntimeError(f"cannot load {function_name} from {path}")
    namespace = {}
    exec(match.group(0), namespace)
    return namespace[function_name]


def clean_l4(text):
    match = re.search(r"<CLEANED_TEXT>(.*?)</CLEANED_TEXT>", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"<CLEANED_TEXT>(.*)", text, flags=re.DOTALL | re.IGNORECASE)
    return (match.group(1) if match else text).strip()


def clean_l5(text):
    text = re.sub(r"\*\*refined text:?\*\*", "", text, flags=re.IGNORECASE).strip()
    return re.sub(r"^refined text:?", "", text, flags=re.IGNORECASE).strip().rstrip("#").strip()


def post_json(url, body, timeout):
    request = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:20000/v1/chat/completions")
    parser.add_argument("--model", default="dsv4-flash")
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--root", default="/inspire/hdd2/project/special-project-1/public/yelv", type=Path)
    args = parser.parse_args()

    create_l4 = load_function(args.root / "pdf/bench_l5_stage/l4_clean_prompt.py", "create_llm_clean_chunk_prompt")
    create_l5 = load_function(args.root / "pdf/bench_l5_stage/bench_l5_rewrite.py", "create_llm_refine_chunk_prompt")
    source = json.loads(args.samples.read_text(encoding="utf-8"))
    records = source["samples"]
    lock = threading.Lock()
    completed = 0

    def infer(record, stage):
        prompt = create_l4(record["seg"]) if stage == "l4" else create_l5(record["seg"])
        body = {
            "model": args.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": args.max_tokens,
        }
        started = time.time()
        response = post_json(args.url, body, 900)
        text = response["choices"][0]["message"]["content"] or ""
        return record["idx"], stage, clean_l4(text) if stage == "l4" else clean_l5(text), response.get("usage", {}), time.time() - started

    results = {record["idx"]: {**record, "model": args.model} for record in records}
    jobs = [(record, stage) for record in records for stage in ("l4", "l5")]
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(infer, record, stage) for record, stage in jobs]
        for future in as_completed(futures):
            idx, stage, text, usage, elapsed = future.result()
            results[idx][stage] = text
            results[idx][stage + "_usage"] = usage
            results[idx][stage + "_seconds"] = elapsed
            with lock:
                completed += 1
                print(f"[{completed:02d}/{len(jobs)}] paper={idx:02d} stage={stage} chars={len(text)} seconds={elapsed:.1f}", flush=True)
    output = {
        "model_order": [args.model],
        "n_books": len(records),
        "books": [
            {
                "idx": item["idx"],
                "domain": item["journal_name"] or "Academic paper",
                "source": f"CSV row {item['csv_row']} · {item['publish_year']} · {item['doi']}",
                "title": item["title"],
                "seg": item["seg"],
                "models": {args.model: {"l4": item["l4"], "l5": item["l5"]}},
                "metadata": {key: item[key] for key in (
                    "paper_id", "csv_row", "doi", "openalex_id", "pdf_url", "page_count",
                    "text_chars", "segment_tokens", "l4_usage", "l5_usage", "l4_seconds", "l5_seconds"
                )},
            }
            for item in (results[index] for index in sorted(results))
        ],
    }
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
