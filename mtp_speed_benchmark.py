#!/usr/bin/env python3
"""Quick MTP speed/accuracy probe against llama.cpp /v1/chat/completions.

Sends N coding prompts to a llama-server, measures total tokens (reasoning +
content) per second, and saves the responses + per-prompt stats. Run twice —
once against a baseline server, once against a server started with MTP — and
the JSON outputs can be diff'd to quantify the MTP speedup.
"""
import argparse
import json
import time
import requests


PROMPTS = [
    # 1) Algorithmic / pure code
    "Write a self-contained Python function `merge_sort(arr)` that sorts a list "
    "of integers using merge sort. Include a 3-line docstring. Output only the "
    "code block, no explanation.",
    # 2) Slightly larger — a tiny module
    "Write a self-contained Python module with: (1) a class `LRUCache(capacity)` "
    "with `get(key)` and `put(key, value)`, both O(1) average, using `OrderedDict`. "
    "(2) a `main()` that exercises it with 8 ops and prints results. Output only "
    "code, single ```python block.",
    # 3) JS / web — relevant for the coding benchmark
    "Write a single React functional component `Counter` in JSX that shows a "
    "count and two buttons (+1, -1). Use useState. Output only one ```jsx code "
    "block, no setup, no surrounding text.",
]


def measure(api_url: str, prompt: str, max_tokens: int) -> dict:
    start = time.time()
    chunks = []
    reasoning_chars = 0
    content_tokens = 0
    reasoning_tokens = 0
    timings = {}
    try:
        with requests.post(
            f"{api_url}/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "stream": True,
            },
            timeout=86400,
            stream=True,
        ) as response:
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    chunk = json.loads(payload)
                except Exception:
                    continue
                ch = (chunk.get("choices") or [{}])[0]
                delta = ch.get("delta", {}) or {}
                if delta.get("content"):
                    chunks.append(delta["content"])
                    content_tokens += 1
                if delta.get("reasoning_content"):
                    reasoning_chars += len(delta["reasoning_content"])
                    reasoning_tokens += 1
                if chunk.get("timings"):
                    timings = chunk["timings"]
                if ch.get("finish_reason"):
                    break
    except Exception as e:
        chunks.append(f"\n[ERROR: {e}]")
    elapsed = time.time() - start
    content = "".join(chunks)
    # Prefer server-reported counts if present (more accurate)
    predicted_n = timings.get("predicted_n", content_tokens + reasoning_tokens)
    predicted_ms = timings.get("predicted_ms", elapsed * 1000)
    decode_tps = (predicted_n / (predicted_ms / 1000)) if predicted_ms else 0
    wall_tps = predicted_n / elapsed if elapsed > 0 else 0
    return {
        "elapsed_s": round(elapsed, 3),
        "predicted_n": predicted_n,
        "content_tokens_streamed": content_tokens,
        "reasoning_tokens_streamed": reasoning_tokens,
        "reasoning_chars": reasoning_chars,
        "decode_tps": round(decode_tps, 2),
        "wall_tps": round(wall_tps, 2),
        "prompt_ms": timings.get("prompt_ms"),
        "prompt_n": timings.get("prompt_n"),
        "content_head": content[:400],
        "content_tail": content[-400:] if len(content) > 400 else "",
        "content_len": len(content),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", required=True, help="e.g. http://localhost:11438")
    ap.add_argument("--label", required=True, help="baseline | mtp-n2 | mtp-n3 ...")
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--warmup", action="store_true", help="Run one warm-up before measurements")
    args = ap.parse_args()

    if args.warmup:
        print("Warm-up ...", flush=True)
        measure(args.api_url, "Say hi.", 32)

    results = []
    for i, p in enumerate(PROMPTS):
        print(f"[{args.label}] Prompt {i+1}/{len(PROMPTS)} ...", flush=True)
        r = measure(args.api_url, p, args.max_tokens)
        r["prompt_idx"] = i
        r["prompt_head"] = p[:80]
        results.append(r)
        print(
            f"  predicted_n={r['predicted_n']} decode_tps={r['decode_tps']} "
            f"wall_tps={r['wall_tps']} elapsed={r['elapsed_s']}s",
            flush=True,
        )

    summary = {
        "label": args.label,
        "api_url": args.api_url,
        "max_tokens": args.max_tokens,
        "n_prompts": len(PROMPTS),
        "results": results,
        "avg_decode_tps": round(sum(r["decode_tps"] for r in results) / len(results), 2),
        "avg_wall_tps": round(sum(r["wall_tps"] for r in results) / len(results), 2),
        "total_predicted_n": sum(r["predicted_n"] for r in results),
        "total_elapsed_s": round(sum(r["elapsed_s"] for r in results), 2),
    }
    summary["aggregate_tps"] = round(
        summary["total_predicted_n"] / summary["total_elapsed_s"], 2
    ) if summary["total_elapsed_s"] else 0
    with open(args.output, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {args.output}")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
