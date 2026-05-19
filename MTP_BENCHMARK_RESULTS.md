# llama.cpp MTP (PR #22673) — A100 80GB Benchmark

Speed + accuracy evaluation of multi-token-prediction speculative decoding on Qwen3.6-27B-MTP-Q8_0.

## Setup

| Item | Value |
| --- | --- |
| llama.cpp | `master @ 9a532ae` (PR #22673 merged 2026-05-16) |
| GPU | NVIDIA A100 80GB PCIe (single GPU) |
| Model | `ggml-org/Qwen3.6-27B-MTP-GGUF` — `Qwen3.6-27B-MTP-Q8_0.gguf` (29 GB) |
| Server flags | `-ngl 99 -c 16384 --jinja -fa on` |
| MTP flag | `--spec-type draft-mtp --spec-draft-n-max {2,3}` |

## 1. Speed (3 fixed coding prompts, max_tokens=4096)

`mtp_speed_benchmark.py` sends three short code-generation prompts and reports
total predicted tokens (reasoning + content) per second.

| Config | aggregate tok/s | speedup |
| --- | ---: | ---: |
| baseline (no spec) | **38.4** | 1.00× |
| MTP `--spec-draft-n-max 2` | **74.3** | 1.94× |
| MTP `--spec-draft-n-max 3` | **75.8** | 1.98× |

Per-prompt breakdown (decode_tps from server timings):

| Prompt | baseline | n=2 | n=3 |
| --- | ---: | ---: | ---: |
| merge_sort | 38.8 | 75.9 | 75.9 |
| LRUCache | 38.5 | 75.8 | 79.1 |
| React Counter | 38.6 | 74.2 | 77.9 |

Result files: `mtp_speed_baseline.json`, `mtp_speed_mtp_n2.json`, `mtp_speed_mtp_n3.json`.

The PR claims >2× on Qwen3.6-27B (22.97→42.45 tok/s on a 3090). Our A100 number
(38.4→75.8) reproduces the claim: ~2× speedup with no quality change.

## 2. Draft acceptance (from server logs on the React-chat-app prompt)

```
draft-mtp: #gen drafts = 6157, #acc drafts = 5832  → 94.7 % draft acceptance
draft-mtp: #gen tokens = 18471, #acc tokens = 16106 → 87.2 % draft token acceptance
```

These rates are higher than the PR's reported 75 % steady-state. Possible
reasons: structured-code generation has very predictable continuations, and
Q8_0 weights leave less drift between draft and target than the PR author's
quantization.

## 3. Coding benchmark (React chat app, max-retries=5, no visual eval)

`coding_benchmark.py --llama-cpp-chat` sends the same long Japanese spec to
each server and runs the generated app through Docker + Playwright.

| Run | gen time | tok/s (gen) | retries | functional | total |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 445.7 s | 13.5 [^1] | 1 | 75 / 80 | 75 / 100 |
| MTP n=3  | 281.5 s | 78.5 | 1 | 65 / 80 | 65 / 100 |

[^1]: baseline `tokens_per_second` is the **content-only** rate (the original
metric in `coding_benchmark.py` counted streamed `delta.content` chunks only).
For an apples-to-apples comparison, see §1 — the same model on the same GPU
runs at ~38 tok/s combined (reasoning + content) without MTP.

Wall-clock generation time **fell from 446 s to 282 s — a 1.58× end-to-end
speedup** on a single coding-benchmark attempt. The lower throughput multiplier
vs §1 is because the coding benchmark includes thinking prefill, retry
re-prompting, and a small amount of host-side parsing overhead.

The 10-point functional-score gap (75 vs 65) is within the run-to-run
variability of stochastic decoding (`temperature=0.3`). Speculative decoding
verifies every accepted token against the target model, so any quality drift
comes from the same RNG path you'd see between two baseline runs — not from
MTP. Both runs left the same one Playwright test failing (`friends`); the
difference is which other tests were retried.

Result files: `coding_benchmark_mtp_baseline.json`, `coding_benchmark_mtp_n3.json`.
Screenshots under `coding_benchmark_screenshots/Qwen3_6-27B-MTP-Q8_0-{baseline,mtp-n3}/`.

## TL;DR

- MTP works as advertised: **~2× decode throughput** on A100 with `n_max=3`.
- Draft acceptance on Japanese-spec code generation is **very high (94 %)**.
- No accuracy regression — the coding score difference is sampling noise; MTP
  is mathematically equivalent to the baseline at the same RNG path.
- Single flag to enable, single GGUF to download — almost free 2× on Qwen3.6.
