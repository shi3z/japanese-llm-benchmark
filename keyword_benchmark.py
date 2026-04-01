#!/usr/bin/env python3
"""
Japanese LLM Keyword Extraction Benchmark
Evaluates keyword extraction quality from question-like prompts
"""

import json
import time
import subprocess
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Set
from pathlib import Path

@dataclass
class KeywordResult:
    model: str
    sample_id: int
    question: str
    expected_keywords: List[str]
    extracted_keywords: List[str]
    generation_time: float
    tokens_per_second: float
    precision: float
    recall: float
    f1_score: float
    raw_output: str

def normalize_keyword(keyword: str) -> str:
    """Normalize keyword for comparison"""
    # Lowercase, remove spaces, normalize
    return keyword.lower().strip()

def calculate_keyword_metrics(extracted: List[str], expected: List[str]) -> Dict[str, float]:
    """Calculate precision, recall, F1 for keyword extraction"""
    if not extracted or not expected:
        return {'precision': 0.0, 'recall': 0.0, 'f1_score': 0.0}

    # Normalize for comparison
    extracted_normalized = set(normalize_keyword(k) for k in extracted)
    expected_normalized = set(normalize_keyword(k) for k in expected)

    # Also check partial matches (for cases like "機械学習" matching "機械学習")
    matches = 0
    for ext in extracted_normalized:
        for exp in expected_normalized:
            if ext in exp or exp in ext:
                matches += 1
                break

    precision = matches / len(extracted) if extracted else 0.0
    recall = matches / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        'precision': precision,
        'recall': recall,
        'f1_score': f1
    }

def extract_json_keywords(text: str) -> List[str]:
    """Extract keywords from JSON response"""
    if not text:
        return []

    # Remove thinking blocks
    if '<think>' in text and '</think>' in text:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    if '</think>' in text:
        text = text.split('</think>')[-1]

    text = text.strip()

    # Try to find JSON in the response
    # Pattern 1: Look for {"keywords": [...]}
    json_match = re.search(r'\{[^{}]*"keywords"\s*:\s*\[[^\]]*\][^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            keywords = data.get('keywords', [])
            if isinstance(keywords, list):
                return [str(k) for k in keywords]
        except json.JSONDecodeError:
            pass

    # Pattern 2: Just look for the array after "keywords"
    array_match = re.search(r'"keywords"\s*:\s*\[([^\]]*)\]', text, re.DOTALL)
    if array_match:
        try:
            array_str = '[' + array_match.group(1) + ']'
            keywords = json.loads(array_str)
            if isinstance(keywords, list):
                return [str(k) for k in keywords]
        except json.JSONDecodeError:
            pass

    # Pattern 3: Look for any JSON array
    array_match = re.search(r'\[([^\[\]]+)\]', text)
    if array_match:
        try:
            keywords = json.loads('[' + array_match.group(1) + ']')
            if isinstance(keywords, list):
                return [str(k) for k in keywords]
        except json.JSONDecodeError:
            pass

    return []

def is_thinking_model(model: str) -> bool:
    """Check if model is a thinking/reasoning model"""
    thinking_patterns = ['qwen3', 'qwen3.5', 'gpt-oss', 'deepseek-r1', 'o1', 'thinking', 'reasoning']
    return any(p in model.lower() for p in thinking_patterns)

def get_model_options(model: str) -> dict:
    """Get appropriate options for each model"""
    options = {
        'temperature': 0.1  # Low temperature for consistent extraction
    }

    # Thinking models need more tokens for chain-of-thought + output
    if 'gpt-oss' in model.lower():
        options['num_predict'] = 4096
        options['num_ctx'] = 8192
    elif 'qwen3' in model.lower() or 'qwen3.5' in model.lower():
        options['num_predict'] = 4096  # More tokens for thinking + output
        options['num_ctx'] = 8192
    else:
        options['num_predict'] = 512
        options['num_ctx'] = 4096

    return options

def extract_keywords(model: str, question: str, ollama_host: str = 'localhost') -> tuple:
    """Extract keywords from question using LLM"""

    prompt = f"""以下の質問文から、検索に使用するキーワードを抽出してください。
結果はJSON形式で、"keywords"というプロパティに文字列のリストとして返してください。

質問: {question}

JSON形式で回答:"""

    start_time = time.time()
    try:
        options = get_model_options(model)

        if ':' in ollama_host and not ollama_host.replace('.', '').replace(':', '').isdigit():
            api_url = f'http://{ollama_host}/api/generate'
        else:
            api_url = f'http://{ollama_host}:11434/api/generate'

        # Use curl via subprocess for better network compatibility
        request_data = json.dumps({
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': options
        })

        result = subprocess.run(
            ['curl', '-s', '--connect-timeout', '10', '-X', 'POST', api_url,
             '-H', 'Content-Type: application/json',
             '-d', request_data],
            capture_output=True,
            text=True,
            timeout=180
        )

        data = json.loads(result.stdout)
        elapsed = time.time() - start_time

        output = data.get('response', '') or ''
        thinking = data.get('thinking', '') or ''

        eval_count = data.get('eval_count', len(output) + len(thinking))
        eval_duration = data.get('eval_duration', elapsed * 1e9) / 1e9
        tokens_per_sec = eval_count / eval_duration if eval_duration > 0 else 0

        # Try to extract keywords from response first
        keywords = extract_json_keywords(output)

        # If no keywords found in response, try thinking content
        if not keywords and thinking:
            keywords = extract_json_keywords(thinking)

        # Combine output for logging
        full_output = output if output.strip() else thinking

        return keywords, elapsed, tokens_per_sec, full_output.strip()
    except Exception as e:
        elapsed = time.time() - start_time
        return [], elapsed, 0, f'Error: {str(e)}'

def run_keyword_benchmark(
    dataset_path: str,
    models: List[str],
    num_samples: int = None,
    output_path: str = 'keyword_benchmark_results.json',
    ollama_host: str = 'localhost'
) -> List[KeywordResult]:
    """Run keyword extraction benchmark"""

    # Load dataset
    samples = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if num_samples and i >= num_samples:
                break
            samples.append(json.loads(line))

    results = []

    for model in models:
        print(f'\n=== Benchmarking {model} ===')

        for idx, sample in enumerate(samples):
            print(f'  Sample {idx+1}/{len(samples)}...', end=' ', flush=True)

            question = sample['question']
            expected = sample['keywords']

            extracted, elapsed, tps, raw_output = extract_keywords(
                model, question, ollama_host=ollama_host
            )

            metrics = calculate_keyword_metrics(extracted, expected)

            result = KeywordResult(
                model=model,
                sample_id=idx,
                question=question,
                expected_keywords=expected,
                extracted_keywords=extracted,
                generation_time=elapsed,
                tokens_per_second=tps,
                raw_output=raw_output,
                **metrics
            )
            results.append(result)

            status = "✓" if metrics['f1_score'] > 0.5 else "△" if extracted else "✗"
            print(f'{status} {elapsed:.2f}s, F1: {metrics["f1_score"]:.3f}, extracted: {extracted}')

    # Save results
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)

    return results

def print_summary(results: List[KeywordResult]):
    """Print benchmark summary"""
    from collections import defaultdict

    model_stats = defaultdict(lambda: {
        'precision': [], 'recall': [], 'f1': [], 'times': [], 'tps': []
    })

    for r in results:
        stats = model_stats[r.model]
        stats['precision'].append(r.precision)
        stats['recall'].append(r.recall)
        stats['f1'].append(r.f1_score)
        stats['times'].append(r.generation_time)
        stats['tps'].append(r.tokens_per_second)

    print('\n' + '='*90)
    print('KEYWORD EXTRACTION BENCHMARK SUMMARY')
    print('='*90)
    print(f'{"Model":<30} {"Precision":>10} {"Recall":>10} {"F1":>10} {"Avg Time":>10} {"Tok/s":>10}')
    print('-'*90)

    for model, stats in sorted(model_stats.items(), key=lambda x: -sum(x[1]['f1'])/len(x[1]['f1'])):
        avg_p = sum(stats['precision']) / len(stats['precision'])
        avg_r = sum(stats['recall']) / len(stats['recall'])
        avg_f1 = sum(stats['f1']) / len(stats['f1'])
        avg_time = sum(stats['times']) / len(stats['times'])
        avg_tps = sum(stats['tps']) / len(stats['tps'])

        print(f'{model:<30} {avg_p:>10.3f} {avg_r:>10.3f} {avg_f1:>10.3f} {avg_time:>9.2f}s {avg_tps:>10.1f}')

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Japanese LLM Keyword Extraction Benchmark')
    parser.add_argument('--dataset', default='keyword_dataset.jsonl')
    parser.add_argument('--models', nargs='+', default=['qwen3:8b'])
    parser.add_argument('--samples', type=int, default=None)
    parser.add_argument('--output', default='keyword_benchmark_results.json')
    parser.add_argument('--host', default='localhost', help='Ollama host')

    args = parser.parse_args()

    results = run_keyword_benchmark(
        dataset_path=Path(args.dataset).expanduser(),
        models=args.models,
        num_samples=args.samples,
        output_path=args.output,
        ollama_host=args.host
    )

    print_summary(results)
