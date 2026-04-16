#!/usr/bin/env python3
"""
Ternary-Bonsai-8B MLX 2-bit Benchmark
Japanese summarization benchmark using MLX on Apple Silicon.
"""

import json
import time
import re
from pathlib import Path

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


def run_benchmark(model_path: str, dataset_path: str, num_samples: int = 10,
                  output_path: str = "bonsai_mlx_results.json"):
    from mlx_lm import load, generate

    print(f"Loading model: {model_path}")
    model, tokenizer = load(model_path)
    print("Model loaded.")

    # Load dataset
    samples = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= num_samples:
                break
            samples.append(json.loads(line))

    results = []

    for idx, sample in enumerate(samples):
        text = sample['text'][:4000]
        reference = sample['summary']

        prompt = f"以下の文章を200文字程度で要約してください。要約のみを出力し、説明は不要です。\n\n文章：\n{text}\n\n要約："

        # Apply chat template if available
        if hasattr(tokenizer, 'apply_chat_template'):
            messages = [{"role": "user", "content": prompt}]
            formatted = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            formatted = prompt

        print(f"  Sample {idx+1}/{len(samples)}...", end=' ', flush=True)

        start_time = time.time()
        output = generate(
            model, tokenizer, prompt=formatted,
            max_tokens=1024, verbose=False
        )
        elapsed = time.time() - start_time

        # Clean output
        generated = output.strip()
        # Remove thinking blocks if present
        if '<think>' in generated and '</think>' in generated:
            generated = re.sub(r'<think>.*?</think>', '', generated, flags=re.DOTALL)
        if '</think>' in generated:
            generated = generated.split('</think>')[-1]
        generated = generated.strip()

        # Estimate tokens per second
        token_count = len(tokenizer.encode(output))
        tps = token_count / elapsed if elapsed > 0 else 0

        rouge_scores = calculate_rouge(generated, reference)

        result = {
            "model": model_path,
            "sample_id": idx,
            "input_length": len(text),
            "output_length": len(generated),
            "generation_time": elapsed,
            "tokens_per_second": tps,
            "generated_summary": generated,
            "reference_summary": reference,
            **rouge_scores
        }
        results.append(result)

        print(f'{elapsed:.2f}s, {tps:.1f} tok/s, outlen={len(generated)}, ROUGE-L: {rouge_scores["rouge_l_f"]:.3f}')

    # Save results
    output_data = {
        "model": model_path,
        "platform": "MLX / Apple M3 Ultra 512GB",
        "dataset": dataset_path,
        "num_samples": num_samples,
        "results": results,
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Print summary
    valid = [r for r in results if r['output_length'] > 0]
    if valid:
        avg_time = sum(r['generation_time'] for r in valid) / len(valid)
        avg_tps = sum(r['tokens_per_second'] for r in valid) / len(valid)
        avg_r1 = sum(r['rouge_1_f'] for r in valid) / len(valid)
        avg_r2 = sum(r['rouge_2_f'] for r in valid) / len(valid)
        avg_rl = sum(r['rouge_l_f'] for r in valid) / len(valid)

        print(f'\n{"="*70}')
        print(f'Ternary-Bonsai-8B MLX 2-bit BENCHMARK SUMMARY')
        print(f'{"="*70}')
        print(f'Platform:  Apple M3 Ultra 512GB (MLX)')
        print(f'Model:     {model_path}')
        print(f'Samples:   {len(valid)}')
        print(f'Avg Time:  {avg_time:.2f}s')
        print(f'Avg Tok/s: {avg_tps:.1f}')
        print(f'ROUGE-1:   {avg_r1:.3f}')
        print(f'ROUGE-2:   {avg_r2:.3f}')
        print(f'ROUGE-L:   {avg_rl:.3f}')
        print(f'{"="*70}')

    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='prism-ml/Ternary-Bonsai-8B-mlx-2bit')
    parser.add_argument('--dataset', default='dataset_from_logs.jsonl')
    parser.add_argument('--samples', type=int, default=10)
    parser.add_argument('--output', default='bonsai_mlx_results.json')
    args = parser.parse_args()

    run_benchmark(args.model, args.dataset, args.samples, args.output)
