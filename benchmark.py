#!/usr/bin/env python3
"""
Japanese LLM Benchmark System
Evaluates summarization quality and speed for various LLMs
"""

import json
import time
import requests
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import re
from pathlib import Path

@dataclass
class BenchmarkResult:
    model: str
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
    """Simple ROUGE calculation for Japanese text"""
    # Character-level n-grams for Japanese
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
    
    # ROUGE-L (LCS-based)
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

def generate_summary(model: str, text: str, max_tokens: int = 300) -> tuple:
    """Generate summary using Ollama API"""
    prompt = f"""以下の文章を200文字程度で要約してください。要約のみを出力し、説明は不要です。

文章：
{text[:4000]}

要約："""
    
    start_time = time.time()
    try:
        response = requests.post(
            'http://localhost:11434/api/generate',
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'num_predict': max_tokens,
                    'temperature': 0.3
                }
            },
            timeout=300
        )
        data = response.json()
        elapsed = time.time() - start_time
        
        # Handle thinking models
        output = data.get('response', '') or ''
        thinking = data.get('thinking', '')
        
        # Extract actual response after </think> tag if present
        if '</think>' in output:
            output = output.split('</think>')[-1].strip()
        elif not output and thinking:
            # For models that only output thinking
            output = thinking.split('\n')[-1] if thinking else ''
        
        eval_count = data.get('eval_count', len(output))
        eval_duration = data.get('eval_duration', elapsed * 1e9) / 1e9
        
        tokens_per_sec = eval_count / eval_duration if eval_duration > 0 else 0
        
        return output.strip(), elapsed, tokens_per_sec, eval_count
    except Exception as e:
        elapsed = time.time() - start_time
        return f'Error: {str(e)}', elapsed, 0, 0

def run_benchmark(
    dataset_path: str,
    models: List[str],
    num_samples: int = 10,
    output_path: str = 'benchmark_results.json'
) -> List[BenchmarkResult]:
    """Run benchmark on specified models"""
    
    # Load dataset
    samples = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= num_samples:
                break
            samples.append(json.loads(line))
    
    results = []
    
    for model in models:
        print(f'\n=== Benchmarking {model} ===')
        
        for idx, sample in enumerate(samples):
            print(f'  Sample {idx+1}/{len(samples)}...', end=' ', flush=True)
            
            text = sample['text']
            reference = sample['summary']
            
            generated, elapsed, tps, tokens = generate_summary(model, text)
            
            # Calculate ROUGE scores
            rouge_scores = calculate_rouge(generated, reference)
            
            result = BenchmarkResult(
                model=model,
                sample_id=idx,
                input_length=len(text),
                output_length=len(generated),
                generation_time=elapsed,
                tokens_per_second=tps,
                generated_summary=generated,
                reference_summary=reference,
                **rouge_scores
            )
            results.append(result)
            
            print(f'{elapsed:.2f}s, {tps:.1f} tok/s, ROUGE-L: {rouge_scores["rouge_l_f"]:.3f}')
    
    # Save results
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
    
    return results

def print_summary(results: List[BenchmarkResult]):
    """Print benchmark summary"""
    from collections import defaultdict
    
    model_stats = defaultdict(lambda: {
        'times': [], 'tps': [], 'rouge_1': [], 'rouge_2': [], 'rouge_l': []
    })
    
    for r in results:
        stats = model_stats[r.model]
        stats['times'].append(r.generation_time)
        stats['tps'].append(r.tokens_per_second)
        stats['rouge_1'].append(r.rouge_1_f)
        stats['rouge_2'].append(r.rouge_2_f)
        stats['rouge_l'].append(r.rouge_l_f)
    
    print('\n' + '='*80)
    print('BENCHMARK SUMMARY')
    print('='*80)
    print(f'{"Model":<35} {"Avg Time":>10} {"Tok/s":>10} {"ROUGE-1":>10} {"ROUGE-2":>10} {"ROUGE-L":>10}')
    print('-'*80)
    
    for model, stats in model_stats.items():
        avg_time = sum(stats['times']) / len(stats['times'])
        avg_tps = sum(stats['tps']) / len(stats['tps'])
        avg_r1 = sum(stats['rouge_1']) / len(stats['rouge_1'])
        avg_r2 = sum(stats['rouge_2']) / len(stats['rouge_2'])
        avg_rl = sum(stats['rouge_l']) / len(stats['rouge_l'])
        
        print(f'{model:<35} {avg_time:>9.2f}s {avg_tps:>10.1f} {avg_r1:>10.3f} {avg_r2:>10.3f} {avg_rl:>10.3f}')

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Japanese LLM Benchmark')
    parser.add_argument('--dataset', default='~/dataset_from_logs.jsonl')
    parser.add_argument('--models', nargs='+', default=['nemotron-3-nano:4b', 'qwen3:4b'])
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--output', default='benchmark_results.json')
    
    args = parser.parse_args()
    
    results = run_benchmark(
        dataset_path=Path(args.dataset).expanduser(),
        models=args.models,
        num_samples=args.samples,
        output_path=args.output
    )
    
    print_summary(results)
