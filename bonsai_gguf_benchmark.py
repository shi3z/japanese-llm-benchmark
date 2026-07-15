#!/usr/bin/env python3
"""
Ternary-Bonsai-27B GGUF Benchmark (llama.cpp server)
Japanese summarization benchmark via llama-server /v1/chat/completions.
Based on bonsai_mlx_benchmark.py (same ROUGE / dataset / prompt).

Usage:
    python bonsai_gguf_benchmark.py --host localhost:8081 --samples 10 \
        --dataset ~/dataset_from_logs.jsonl --output bonsai27b_gguf_dgx_results.json
"""

import argparse
import json
import time
import re
from pathlib import Path

import requests


def calculate_rouge(generated: str, reference: str) -> dict:
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


def strip_thinking(text: str) -> str:
    if '<think>' in text and '</think>' in text:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    if '</think>' in text:
        text = text.split('</think>')[-1]
    return text.strip()


def run_benchmark(host: str, dataset_path: str, num_samples: int,
                  output_path: str, max_tokens: int, label: str):
    api_url = f'http://{host}/v1/chat/completions'

    samples = []
    with open(Path(dataset_path).expanduser(), 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= num_samples:
                break
            samples.append(json.loads(line))

    results = []
    for idx, sample in enumerate(samples):
        text = sample['text'][:4000]
        reference = sample['summary']

        prompt = f"以下の文章を200文字程度で要約してください。要約のみを出力し、説明は不要です。\n\n文章：\n{text}\n\n要約："

        print(f"  Sample {idx+1}/{len(samples)}...", end=' ', flush=True)

        start_time = time.time()
        try:
            resp = requests.post(api_url, json={
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': max_tokens,
                'temperature': 0.7,
                'top_p': 0.95,
                'top_k': 20,
            }, timeout=3600)
            data = resp.json()
        except Exception as e:
            print(f'ERROR: {e}')
            data = {}
        elapsed = time.time() - start_time

        msg = (data.get('choices') or [{}])[0].get('message', {})
        content = msg.get('content') or ''
        reasoning = msg.get('reasoning_content') or ''
        generated = strip_thinking(content)

        usage = data.get('usage', {})
        completion_tokens = usage.get('completion_tokens', 0)
        tps = completion_tokens / elapsed if elapsed > 0 else 0

        rouge_scores = calculate_rouge(generated, reference)

        results.append({
            "model": label,
            "sample_id": idx,
            "input_length": len(text),
            "output_length": len(generated),
            "generation_time": elapsed,
            "completion_tokens": completion_tokens,
            "tokens_per_second": tps,
            "reasoning_length": len(reasoning),
            "generated_summary": generated,
            "reference_summary": reference,
            **rouge_scores
        })

        print(f'{elapsed:.2f}s, {tps:.1f} tok/s, outlen={len(generated)}, '
              f'thinklen={len(reasoning)}, ROUGE-L: {rouge_scores["rouge_l_f"]:.3f}')

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "model": label,
                "platform": "llama.cpp (PrismML fork, CUDA) / DGX Spark GB10",
                "dataset": str(dataset_path),
                "num_samples": num_samples,
                "results": results,
            }, f, ensure_ascii=False, indent=2)

    valid = [r for r in results if r['output_length'] > 0]
    if valid:
        avg_time = sum(r['generation_time'] for r in valid) / len(valid)
        avg_tps = sum(r['tokens_per_second'] for r in valid) / len(valid)
        avg_r1 = sum(r['rouge_1_f'] for r in valid) / len(valid)
        avg_r2 = sum(r['rouge_2_f'] for r in valid) / len(valid)
        avg_rl = sum(r['rouge_l_f'] for r in valid) / len(valid)

        print(f'\n{"="*70}')
        print(f'{label} BENCHMARK SUMMARY')
        print(f'{"="*70}')
        print(f'Samples:   {len(valid)}/{len(results)}')
        print(f'Avg Time:  {avg_time:.2f}s')
        print(f'Avg Tok/s: {avg_tps:.1f}')
        print(f'ROUGE-1:   {avg_r1:.3f}')
        print(f'ROUGE-2:   {avg_r2:.3f}')
        print(f'ROUGE-L:   {avg_rl:.3f}')
    else:
        print('\nNo valid outputs.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost:8081')
    parser.add_argument('--dataset', default='~/dataset_from_logs.jsonl')
    parser.add_argument('--samples', type=int, default=10)
    parser.add_argument('--max-tokens', type=int, default=3072)
    parser.add_argument('--label', default='Ternary-Bonsai-27B-Q2_0 (llama.cpp CUDA)')
    parser.add_argument('--output', default='bonsai27b_gguf_dgx_results.json')
    args = parser.parse_args()
    run_benchmark(args.host, args.dataset, args.samples,
                  args.output, args.max_tokens, args.label)
