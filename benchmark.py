#!/usr/bin/env python3
"""
Japanese LLM Benchmark System
Evaluates summarization quality and speed for various LLMs
"""

import json
import os
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

def is_thinking_model(model: str) -> bool:
    """Check if model is a thinking/reasoning model"""
    thinking_patterns = ['qwen3', 'qwen3.5', 'gpt-oss', 'deepseek-r1', 'o1', 'thinking', 'reasoning']
    return any(p in model.lower() for p in thinking_patterns)

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

    # Check if text is already predominantly Japanese (contains Japanese chars and not mostly English)
    japanese_char_count = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text))
    if japanese_char_count >= 20 and japanese_char_count > len(text) * 0.3:
        # Text is already Japanese - return as is (preserving LLM, AI, etc.)
        return text.strip()

    # First, try to find quoted Japanese text (often the summary is quoted)
    # Pattern: Japanese text between quotes - now includes alphanumeric for terms like LLM, AI
    quoted_japanese = re.findall(r'[「"\']([\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\w、。\s]+)[」"\']', text)
    if quoted_japanese:
        # Return the longest quoted Japanese text
        best = max(quoted_japanese, key=len)
        if len(best) >= 50:
            return best.strip()

    # Try to find Japanese sentences (continuous text with Japanese chars, allowing alphanumeric)
    # Match sentences ending with Japanese punctuation
    japanese_sentences = re.findall(r'[^\n。]*[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff][^\n。]*。', text)
    if japanese_sentences:
        # Filter sentences that contain substantial Japanese
        substantial = [s for s in japanese_sentences if len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', s)) >= 10]
        if substantial:
            return ''.join(substantial).strip()

    # Fallback: Extract all text containing Japanese characters (including surrounding context)
    lines = text.split('\n')
    japanese_lines = [line for line in lines if re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', line)]
    if japanese_lines:
        combined = ''.join(japanese_lines).strip()
        if len(combined) >= 20:
            return combined

    return text.strip() if text else ""

def get_model_options(model: str) -> dict:
    """Get appropriate options for each model"""
    options = {
        'temperature': 0.3
    }

    # Thinking models need more tokens and larger context (128K)
    if 'gpt-oss' in model.lower():
        options['num_predict'] = 32768  # 32K output tokens
        options['num_ctx'] = 131072  # 128K context for gpt-oss
    elif 'qwen3' in model.lower() or 'qwen3.5' in model.lower():
        options['num_predict'] = 32768  # 32K output tokens
        options['num_ctx'] = 131072  # 128K context for qwen3/qwen3.5
    elif 'deepseek' in model.lower():
        options['num_predict'] = 1000
        options['num_ctx'] = 8192
    elif 'nemotron' in model.lower():
        options['num_predict'] = 800
        options['num_ctx'] = 8192
    else:
        options['num_predict'] = 500
        options['num_ctx'] = 4096

    return options

def generate_summary(model: str, text: str, max_tokens: int = None, ollama_host: str = 'localhost') -> tuple:
    """Generate summary using Ollama API"""

    # For thinking models, use full text with large context
    if is_thinking_model(model):
        max_text_len = 20000  # Full text for 128K context thinking models
        prompt = f"""以下の文章を200文字程度の日本語で要約してください。

文章：
{text[:max_text_len]}

要約："""
    else:
        max_text_len = 4000
        prompt = f"""以下の文章を200文字程度で要約してください。要約のみを出力し、説明は不要です。

文章：
{text[:max_text_len]}

要約："""

    start_time = time.time()
    try:
        # Get model-specific options (includes num_ctx, num_predict, temperature)
        options = get_model_options(model)
        if max_tokens is not None:
            options['num_predict'] = max_tokens

        # Set BENCH_API=openai to use /v1/chat/completions (llama-server --jinja applies
        # the model's own chat template; needed for non-DeepSeek GGUFs like Laguna)
        if os.environ.get('BENCH_API') == 'openai' and ':' in ollama_host:
            api_url = f'http://{ollama_host}/v1/chat/completions'
            openai_max_tokens = int(os.environ.get('BENCH_MAX_TOKENS', options.get('num_predict', 512)))
            data = None
            for attempt in range(3):
                try:
                    response = requests.post(
                        api_url,
                        json={
                            'messages': [{'role': 'user', 'content': prompt}],
                            'max_tokens': openai_max_tokens,
                            'temperature': options.get('temperature', 0.3),
                        },
                        timeout=3600,
                    )
                    data = response.json()
                    if response.status_code == 200 and data.get('choices'):
                        break
                except Exception as e:
                    data = {'error': str(e)}
                time.sleep(2)
            elapsed = time.time() - start_time
            message = ((data or {}).get('choices') or [{}])[0].get('message', {})
            output = message.get('content', '') or ''
            if '<think>' in output:
                output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL)
            if '</think>' in output:
                output = output.split('</think>')[-1]
            usage = (data or {}).get('usage', {}) or {}
            eval_count = usage.get('completion_tokens', len(output))
            tokens_per_sec = eval_count / elapsed if elapsed > 0 else 0
            return output.strip(), elapsed, tokens_per_sec, eval_count

        # Handle host with or without port; route non-11434 ports to llama.cpp /v1/chat/completions
        is_llama_cpp = ':' in ollama_host and not ollama_host.endswith(':11434')
        if is_llama_cpp:
            # Use /completion (raw prompt) to avoid jinja template parser bugs in PR#22378
            api_url = f'http://{ollama_host}/completion'
            wrapped = (
                '<｜begin▁of▁sentence｜><｜User｜>'
                + prompt
                + '<｜Assistant｜></think>'
            )
            data = None
            for attempt in range(3):
                try:
                    response = requests.post(
                        api_url,
                        json={
                            'prompt': wrapped,
                            'n_predict': options.get('num_predict', 512),
                            'temperature': options.get('temperature', 0.3),
                            'stop': ['<｜end▁of▁sentence｜>', '<｜User｜>'],
                        },
                        timeout=3600,
                    )
                    data = response.json()
                    if response.status_code == 200 and data.get('content'):
                        break
                except Exception as e:
                    data = {'error': str(e)}
                time.sleep(2)
            elapsed = time.time() - start_time
            output = (data or {}).get('content', '') or ''
            eval_count = (data or {}).get('tokens_predicted', len(output))
            tokens_per_sec = eval_count / elapsed if elapsed > 0 else 0
            if '</think>' in output:
                output = output.split('</think>')[-1].strip()
            return output.strip(), elapsed, tokens_per_sec, eval_count

        if ':' in ollama_host:
            api_url = f'http://{ollama_host}/api/generate'
        else:
            api_url = f'http://{ollama_host}:11434/api/generate'

        response = requests.post(
            api_url,
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'options': options
            },
            timeout=300
        )
        data = response.json()
        elapsed = time.time() - start_time

        # Handle thinking models - check both response and thinking fields
        output = data.get('response', '') or ''
        thinking = data.get('thinking', '') or ''

        # For thinking models, extract actual Japanese summary
        if is_thinking_model(model):
            # If response is empty but thinking has content, extract from thinking
            if not output.strip() and thinking:
                output = extract_japanese_summary(thinking)
            else:
                output = extract_japanese_summary(output)
        elif '</think>' in output:
            output = output.split('</think>')[-1].strip()

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
    output_path: str = 'benchmark_results.json',
    ollama_host: str = 'localhost'
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

            generated, elapsed, tps, tokens = generate_summary(model, text, ollama_host=ollama_host)
            
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
    parser.add_argument('--host', default='localhost', help='Ollama host')

    args = parser.parse_args()

    results = run_benchmark(
        dataset_path=Path(args.dataset).expanduser(),
        models=args.models,
        num_samples=args.samples,
        output_path=args.output,
        ollama_host=args.host
    )

    print_summary(results)
