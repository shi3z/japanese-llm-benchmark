#!/usr/bin/env python3
"""Batch visual evaluation of all coding-benchmark screenshots with a local VLM.

Usage:
    VISUAL_EVAL_API=local VISUAL_EVAL_MODEL=qwen2.5vl-32b-16k \
        python3 run_visual_eval.py --output visual_eval_results.json
"""

import argparse
import json
import os
import time
from pathlib import Path

from coding_benchmark_evaluate import evaluate_screenshots, visual_score_to_points

SCREENSHOT_BASE = Path(__file__).parent / 'coding_benchmark_screenshots'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='visual_eval_results.json')
    parser.add_argument('--dirs', nargs='*', help='Specific screenshot dirs (default: all)')
    args = parser.parse_args()

    evaluator = os.environ.get('VISUAL_EVAL_MODEL', 'qwen2.5vl:32b') \
        if os.environ.get('VISUAL_EVAL_API', 'anthropic') in ('local', 'openai', 'ollama') \
        else 'claude (anthropic API)'

    dirs = args.dirs or sorted(d.name for d in SCREENSHOT_BASE.iterdir() if d.is_dir())
    results = {}
    for name in dirs:
        path = SCREENSHOT_BASE / name
        t = time.time()
        scores = evaluate_screenshots(str(path), name)
        elapsed = time.time() - t
        if scores.get('comment') == 'No screenshots available':
            print(f'{name}: no screenshots, skipped')
            continue
        points = visual_score_to_points(scores)
        results[name] = {'scores': scores, 'visual_points': points}
        print(f'{name}: overall {scores.get("overall")}/5 -> {points:.0f}/20 ({elapsed:.0f}s) {scores.get("comment","")}')

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump({'evaluator': evaluator, 'results': results}, f, ensure_ascii=False, indent=1)
    print(f'\nSaved {len(results)} results to {args.output} (evaluator: {evaluator})')


if __name__ == '__main__':
    main()
