#!/usr/bin/env python3
"""
RotorQuant KV Cache Compression Benchmark
Tests Japanese summarization quality with different KV cache configurations
using llama.cpp server (OpenAI-compatible API).

Usage:
    python rotorquant_benchmark.py --model-path /path/to/model.gguf \
        --dataset /mnt/raid6/dataset_from_logs.jsonl \
        --samples 10 --gpu 3
"""

import json
import time
import requests
import subprocess
import signal
import sys
import os
import re
import argparse
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional
from pathlib import Path

LLAMA_SERVER = "/mnt/raid6/git/llama-cpp-turboquant/build/bin/llama-server"
LLAMA_BENCH = "/mnt/raid6/git/llama-cpp-turboquant/build/bin/llama-bench"

# KV cache configurations to test
KV_CONFIGS = [
    {"name": "f16/f16", "cache_type_k": "f16", "cache_type_v": "f16"},
    {"name": "planar3/planar3", "cache_type_k": "planar3", "cache_type_v": "planar3"},
    {"name": "iso3/iso3", "cache_type_k": "iso3", "cache_type_v": "iso3"},
    {"name": "planar3/f16", "cache_type_k": "planar3", "cache_type_v": "f16"},
]

@dataclass
class BenchmarkResult:
    config: str
    sample_id: int
    input_length: int
    output_length: int
    generation_time: float
    tokens_per_second: float
    generated_summary: str
    reference_summary: str
    rouge_1_f: float = 0.0
    rouge_2_f: float = 0.0
    rouge_l_f: float = 0.0


def calculate_rouge(generated: str, reference: str) -> Dict[str, float]:
    """Simple ROUGE calculation for Japanese text (character-level)"""
    def get_ngrams(text: str, n: int) -> set:
        text = re.sub(r'\s+', '', text)
        return set(text[i:i+n] for i in range(len(text)-n+1))

    def rouge_n(gen: str, ref: str, n: int) -> float:
        gen_ngrams = get_ngrams(gen, n)
        ref_ngrams = get_ngrams(ref, n)
        if not ref_ngrams or not gen_ngrams:
            return 0.0
        overlap = len(gen_ngrams & ref_ngrams)
        precision = overlap / len(gen_ngrams) if gen_ngrams else 0
        recall = overlap / len(ref_ngrams) if ref_ngrams else 0
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    def lcs_length(s1: str, s2: str) -> int:
        s1 = re.sub(r'\s+', '', s1)
        s2 = re.sub(r'\s+', '', s2)
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        return dp[m][n]

    lcs = lcs_length(generated, reference)
    gen_len = len(re.sub(r'\s+', '', generated))
    ref_len = len(re.sub(r'\s+', '', reference))

    if gen_len == 0 or ref_len == 0:
        rouge_l = 0.0
    else:
        p_lcs = lcs / gen_len
        r_lcs = lcs / ref_len
        rouge_l = 2 * p_lcs * r_lcs / (p_lcs + r_lcs) if (p_lcs + r_lcs) > 0 else 0.0

    return {
        'rouge_1_f': rouge_n(generated, reference, 1),
        'rouge_2_f': rouge_n(generated, reference, 2),
        'rouge_l_f': rouge_l
    }


def extract_japanese_summary(text: str) -> str:
    """Extract Japanese text from thinking model output"""
    if not text:
        return ""
    # Remove thinking blocks
    if '<think>' in text and '</think>' in text:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    if '</think>' in text:
        text = text.split('</think>')[-1]
    text = text.strip()

    japanese_char_count = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text))
    if japanese_char_count >= 20 and japanese_char_count > len(text) * 0.3:
        return text.strip()

    japanese_sentences = re.findall(r'[^\n\u3002]*[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff][^\n\u3002]*\u3002', text)
    if japanese_sentences:
        substantial = [s for s in japanese_sentences if len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', s)) >= 10]
        if substantial:
            return ''.join(substantial).strip()

    lines = text.split('\n')
    japanese_lines = [line for line in lines if re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', line)]
    if japanese_lines:
        combined = ''.join(japanese_lines).strip()
        if len(combined) >= 20:
            return combined

    return text.strip() if text else ""


def start_server(model_path: str, config: dict, gpu: int, port: int = 8090,
                 ctx_size: int = 32768) -> subprocess.Popen:
    """Start llama-server with given KV cache config"""
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)

    cmd = [
        LLAMA_SERVER,
        "-m", model_path,
        "--jinja",
        "-ngl", "99",
        "--cache-type-k", config["cache_type_k"],
        "--cache-type-v", config["cache_type_v"],
        "--host", "0.0.0.0",
        "--port", str(port),
        "-c", str(ctx_size),
    ]

    print(f"  Starting server: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return proc


def wait_for_server(port: int, timeout: int = 120) -> bool:
    """Wait for llama-server to be ready"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"http://localhost:{port}/health", timeout=2)
            if r.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False


def generate_summary(text: str, port: int = 8090) -> tuple:
    """Generate summary using llama.cpp server chat API"""
    max_text_len = 4000
    user_msg = f"以下の文章を200文字程度で要約してください。要約のみを出力し、説明は不要です。\n\n文章：\n{text[:max_text_len]}\n\n要約："

    start_time = time.time()
    try:
        response = requests.post(
            f"http://localhost:{port}/v1/chat/completions",
            json={
                "messages": [
                    {"role": "user", "content": user_msg}
                ],
                "max_tokens": 32768,
                "temperature": 0.3,
            },
            timeout=300
        )
        data = response.json()
        elapsed = time.time() - start_time

        msg = data["choices"][0]["message"]
        content = msg.get("content", "") or ""
        reasoning = msg.get("reasoning_content", "") or ""

        # If content is empty but reasoning has content, extract from reasoning
        if not content.strip() and reasoning:
            content = extract_japanese_summary(reasoning)
        else:
            content = extract_japanese_summary(content)

        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", len(content))
        tokens_per_sec = completion_tokens / elapsed if elapsed > 0 else 0

        return content.strip(), elapsed, tokens_per_sec, completion_tokens
    except Exception as e:
        elapsed = time.time() - start_time
        return f"Error: {str(e)}", elapsed, 0, 0


def run_llama_bench(model_path: str, config: dict, gpu: int) -> dict:
    """Run llama-bench for speed measurement"""
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(gpu)

    cmd = [
        LLAMA_BENCH,
        "-m", model_path,
        "-ngl", "99",
        "-ctk", config["cache_type_k"],
        "-ctv", config["cache_type_v"],
        "-p", "512",
        "-n", "128",
        "-r", "3",
    ]
    print(f"  Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
        return {"stdout": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"error": str(e)}


def run_benchmark(model_path: str, dataset_path: str, num_samples: int,
                  gpu: int, port: int, configs: list, output_path: str):
    """Run full benchmark across all KV cache configs"""
    # Load dataset
    samples = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= num_samples:
                break
            samples.append(json.loads(line))

    all_results = []
    bench_results = {}

    for config in configs:
        config_name = config["name"]
        print(f"\n{'='*60}")
        print(f"Config: {config_name}")
        print(f"{'='*60}")

        # Step 1: Run llama-bench for raw speed
        print(f"\n--- llama-bench ({config_name}) ---")
        bench = run_llama_bench(model_path, config, gpu)
        bench_results[config_name] = bench
        if "stdout" in bench:
            print(bench["stdout"][-500:] if len(bench.get("stdout","")) > 500 else bench.get("stdout",""))
        if "error" in bench:
            print(f"  Bench error: {bench['error']}")

        # Step 2: Run summarization benchmark via server
        print(f"\n--- Summarization Benchmark ({config_name}) ---")
        proc = start_server(model_path, config, gpu, port)
        try:
            print(f"  Waiting for server on port {port}...")
            if not wait_for_server(port, timeout=120):
                print(f"  ERROR: Server failed to start for {config_name}")
                # Read stderr for diagnostics
                proc.terminate()
                proc.wait(timeout=10)
                stderr = proc.stderr.read().decode() if proc.stderr else ""
                print(f"  Server stderr: {stderr[-500:]}")
                continue

            print(f"  Server ready. Running {len(samples)} samples...")

            for idx, sample in enumerate(samples):
                print(f"  Sample {idx+1}/{len(samples)}...", end=' ', flush=True)

                text = sample['text']
                reference = sample['summary']

                generated, elapsed, tps, tokens = generate_summary(text, port)
                rouge_scores = calculate_rouge(generated, reference)

                result = BenchmarkResult(
                    config=config_name,
                    sample_id=idx,
                    input_length=len(text),
                    output_length=len(generated),
                    generation_time=elapsed,
                    tokens_per_second=tps,
                    generated_summary=generated,
                    reference_summary=reference,
                    **rouge_scores
                )
                all_results.append(result)

                print(f'{elapsed:.2f}s, {tps:.1f} tok/s, ROUGE-L: {rouge_scores["rouge_l_f"]:.3f}')

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except:
                proc.kill()
            print(f"  Server stopped for {config_name}")

    # Save results
    output = {
        "model": model_path,
        "dataset": dataset_path,
        "num_samples": num_samples,
        "gpu": gpu,
        "results": [asdict(r) for r in all_results],
        "bench_raw": bench_results,
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print summary
    print_summary(all_results)
    return all_results


def print_summary(results: List[BenchmarkResult]):
    """Print benchmark comparison summary"""
    from collections import defaultdict

    config_stats = defaultdict(lambda: {
        'times': [], 'tps': [], 'rouge_1': [], 'rouge_2': [], 'rouge_l': []
    })

    for r in results:
        stats = config_stats[r.config]
        stats['times'].append(r.generation_time)
        stats['tps'].append(r.tokens_per_second)
        stats['rouge_1'].append(r.rouge_1_f)
        stats['rouge_2'].append(r.rouge_2_f)
        stats['rouge_l'].append(r.rouge_l_f)

    print('\n' + '='*90)
    print('ROTORQUANT BENCHMARK SUMMARY')
    print('='*90)
    print(f'{"Config":<20} {"Avg Time":>10} {"Tok/s":>10} {"ROUGE-1":>10} {"ROUGE-2":>10} {"ROUGE-L":>10}')
    print('-'*90)

    baseline = None
    for config_name, stats in config_stats.items():
        avg_time = sum(stats['times']) / len(stats['times'])
        avg_tps = sum(stats['tps']) / len(stats['tps'])
        avg_r1 = sum(stats['rouge_1']) / len(stats['rouge_1'])
        avg_r2 = sum(stats['rouge_2']) / len(stats['rouge_2'])
        avg_rl = sum(stats['rouge_l']) / len(stats['rouge_l'])

        if baseline is None:
            baseline = {'tps': avg_tps, 'r1': avg_r1, 'r2': avg_r2, 'rl': avg_rl}

        print(f'{config_name:<20} {avg_time:>9.2f}s {avg_tps:>10.1f} {avg_r1:>10.3f} {avg_r2:>10.3f} {avg_rl:>10.3f}')

    if baseline and len(config_stats) > 1:
        print('\n--- vs FP16 baseline ---')
        for config_name, stats in config_stats.items():
            if config_name == "f16/f16":
                continue
            avg_tps = sum(stats['tps']) / len(stats['tps'])
            avg_rl = sum(stats['rouge_l']) / len(stats['rouge_l'])
            tps_diff = (avg_tps / baseline['tps'] - 1) * 100 if baseline['tps'] > 0 else 0
            rl_diff = (avg_rl / baseline['rl'] - 1) * 100 if baseline['rl'] > 0 else 0
            print(f'  {config_name:<20} Speed: {tps_diff:+.1f}%  ROUGE-L: {rl_diff:+.1f}%')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RotorQuant KV Cache Benchmark')
    parser.add_argument('--model-path', required=True, help='Path to GGUF model')
    parser.add_argument('--dataset', default='/mnt/raid6/dataset_from_logs.jsonl')
    parser.add_argument('--samples', type=int, default=10)
    parser.add_argument('--gpu', type=int, default=3, help='GPU index to use')
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--output', default='rotorquant_benchmark_results.json')
    parser.add_argument('--configs', nargs='+', default=None,
                        help='KV configs to test (e.g. f16/f16 planar3/planar3)')

    args = parser.parse_args()

    if args.configs:
        configs = []
        for c in args.configs:
            k, v = c.split('/')
            configs.append({"name": c, "cache_type_k": k, "cache_type_v": v})
    else:
        configs = KV_CONFIGS

    run_benchmark(
        model_path=args.model_path,
        dataset_path=args.dataset,
        num_samples=args.samples,
        gpu=args.gpu,
        port=args.port,
        configs=configs,
        output_path=args.output,
    )
