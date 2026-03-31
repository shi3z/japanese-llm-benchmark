#!/usr/bin/env python3
"""
Qualitative evaluation of LLM summaries using Claude CLI
Evaluates fluency, accuracy, and coherence of generated summaries
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List
import re

# Rate limiting settings
DELAY_BETWEEN_CALLS = 10  # seconds between Claude API calls
DELAY_AFTER_ERROR = 30    # seconds to wait after an error

def evaluate_with_claude(
    original_text: str,
    reference_summary: str,
    generated_summary: str,
    model_name: str
) -> Dict:
    """
    Use Claude CLI to qualitatively evaluate a generated summary
    Returns scores for fluency, accuracy, coherence, and overall quality
    """

    prompt = f"""以下の要約の品質を評価してください。

## 原文（一部）:
{original_text[:2000]}...

## 正解要約:
{reference_summary}

## 評価対象の要約 ({model_name}が生成):
{generated_summary}

以下の観点で1-5点で評価し、JSONで回答してください:

1. **fluency** (流暢さ): 日本語として自然か、文法的に正しいか
2. **accuracy** (正確さ): 原文の内容を正確に反映しているか
3. **coherence** (一貫性): 論理的に一貫しているか
4. **conciseness** (簡潔さ): 適切な長さで要点をまとめているか
5. **overall** (総合評価): 要約として全体的な品質

回答形式（JSONのみ、説明不要）:
{{"fluency": X, "accuracy": X, "coherence": X, "conciseness": X, "overall": X, "comment": "一言コメント"}}
"""

    try:
        result = subprocess.run(
            ['claude', '-p', prompt, '--output-format', 'text'],
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout.strip()

        # Extract JSON from response
        json_match = re.search(r'\{[^}]+\}', output, re.DOTALL)
        if json_match:
            scores = json.loads(json_match.group())
            return scores
        else:
            return {"error": "Failed to parse JSON", "raw": output}

    except subprocess.TimeoutExpired:
        return {"error": "Claude CLI timeout"}
    except Exception as e:
        return {"error": str(e)}


def run_qualitative_evaluation(
    results_file: str = "benchmark_results.json",
    output_file: str = "qualitative_results.json",
    max_samples_per_model: int = 3
) -> List[Dict]:
    """
    Run qualitative evaluation on benchmark results using Claude
    """

    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    # Group by model
    model_samples = {}
    for r in results:
        model = r['model']
        if model not in model_samples:
            model_samples[model] = []
        if len(model_samples[model]) < max_samples_per_model:
            model_samples[model].append(r)

    evaluations = []
    total = sum(len(samples) for samples in model_samples.values())
    current = 0

    for model, samples in model_samples.items():
        print(f"\n=== Evaluating {model} ===")

        for sample in samples:
            current += 1
            print(f"  [{current}/{total}] Sample {sample['sample_id']}...", end=' ', flush=True)

            # Skip if generated summary is too short or contains errors
            if len(sample.get('generated_summary', '')) < 10:
                print("skipped (too short)")
                continue

            scores = evaluate_with_claude(
                original_text=f"(Text length: {sample['input_length']} chars)",
                reference_summary=sample['reference_summary'],
                generated_summary=sample['generated_summary'],
                model_name=model
            )

            evaluation = {
                'model': model,
                'sample_id': sample['sample_id'],
                'generated_summary': sample['generated_summary'][:200],
                'reference_summary': sample['reference_summary'][:200],
                'rouge_l': sample.get('rouge_l', 0),
                'tokens_per_second': sample.get('tokens_per_second', 0),
                **scores
            }
            evaluations.append(evaluation)

            if 'error' in scores:
                print(f"error: {scores['error']}")
                print(f"    Waiting {DELAY_AFTER_ERROR}s before next call...")
                time.sleep(DELAY_AFTER_ERROR)
            else:
                print(f"overall: {scores.get('overall', 'N/A')}/5")
                # Rate limiting: wait between successful calls
                print(f"    Waiting {DELAY_BETWEEN_CALLS}s (rate limit)...")
                time.sleep(DELAY_BETWEEN_CALLS)

    # Save results
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(evaluations, f, ensure_ascii=False, indent=2)

    # Print summary
    print_evaluation_summary(evaluations)

    return evaluations


def print_evaluation_summary(evaluations: List[Dict]):
    """Print summary of qualitative evaluations"""

    from collections import defaultdict

    model_scores = defaultdict(lambda: {
        'fluency': [], 'accuracy': [], 'coherence': [],
        'conciseness': [], 'overall': [], 'rouge_l': [], 'tps': []
    })

    for e in evaluations:
        if 'error' not in e:
            model = e['model']
            for key in ['fluency', 'accuracy', 'coherence', 'conciseness', 'overall']:
                if key in e:
                    model_scores[model][key].append(e[key])
            model_scores[model]['rouge_l'].append(e.get('rouge_l', 0))
            model_scores[model]['tps'].append(e.get('tokens_per_second', 0))

    avg = lambda x: sum(x)/len(x) if x else 0

    print("\n" + "="*100)
    print("QUALITATIVE EVALUATION SUMMARY (Claude評価)")
    print("="*100)
    print(f"{'Model':<30} {'Fluency':>8} {'Accuracy':>8} {'Coherence':>8} {'Concise':>8} {'Overall':>8} {'ROUGE-L':>8} {'Tok/s':>8}")
    print("-"*100)

    # Sort by overall score
    sorted_models = sorted(model_scores.keys(),
                          key=lambda m: avg(model_scores[m]['overall']),
                          reverse=True)

    for model in sorted_models:
        s = model_scores[model]
        print(f"{model:<30} "
              f"{avg(s['fluency']):>8.2f} "
              f"{avg(s['accuracy']):>8.2f} "
              f"{avg(s['coherence']):>8.2f} "
              f"{avg(s['conciseness']):>8.2f} "
              f"{avg(s['overall']):>8.2f} "
              f"{avg(s['rouge_l']):>8.3f} "
              f"{avg(s['tps']):>8.1f}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Qualitative evaluation with Claude')
    parser.add_argument('--results', default='benchmark_results.json',
                       help='Benchmark results file')
    parser.add_argument('--output', default='qualitative_results.json',
                       help='Output file for qualitative scores')
    parser.add_argument('--samples', type=int, default=3,
                       help='Max samples per model to evaluate')

    args = parser.parse_args()

    run_qualitative_evaluation(
        results_file=args.results,
        output_file=args.output,
        max_samples_per_model=args.samples
    )
