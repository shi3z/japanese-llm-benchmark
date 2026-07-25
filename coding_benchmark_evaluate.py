#!/usr/bin/env python3
"""
Vision evaluation of chat app screenshots.
Evaluates design quality, usability, and completeness.

Backends (VISUAL_EVAL_API env var):
  - "anthropic" (default): Claude Vision via Anthropic API (needs ANTHROPIC_API_KEY)
  - "local": local VLM via an OpenAI-compatible endpoint (Ollama / llama-server --mmproj)
      VISUAL_EVAL_URL   (default http://localhost:11434/v1)
      VISUAL_EVAL_MODEL (default qwen2.5vl:32b)
"""

import base64
import json
import os
import re
from pathlib import Path


def _call_local_vlm(images_b64: list, prompt_text: str) -> str:
    """Query a local VLM through an OpenAI-compatible /chat/completions endpoint."""
    import requests
    base_url = os.environ.get('VISUAL_EVAL_URL', 'http://localhost:11434/v1').rstrip('/')
    model = os.environ.get('VISUAL_EVAL_MODEL', 'qwen2.5vl:32b')
    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        for b64 in images_b64
    ] + [{"type": "text", "text": prompt_text}]
    response = requests.post(
        f'{base_url}/chat/completions',
        json={
            'model': model,
            'messages': [{'role': 'user', 'content': content}],
            'max_tokens': 512,
            'temperature': 0.0,
        },
        timeout=1800,
    )
    response.raise_for_status()
    output = response.json()['choices'][0]['message']['content'] or ''
    if '</think>' in output:
        output = output.split('</think>')[-1]
    return output.strip()


def evaluate_screenshots(screenshot_dir: str, model_name: str) -> dict:
    """Evaluate screenshots using a vision model (Anthropic API or local VLM)."""
    screenshot_path = Path(screenshot_dir)

    # Collect existing screenshots
    images_b64 = []
    for name in ['login', 'friends', 'dm', 'chat']:
        path = screenshot_path / f'{name}.png'
        if path.exists() and path.stat().st_size > 0:
            with open(path, 'rb') as f:
                images_b64.append(base64.standard_b64encode(f.read()).decode('utf-8'))

    if not images_b64:
        return {
            'layout': 0, 'aesthetics': 0, 'usability': 0,
            'completeness': 0, 'uniqueness': 0, 'overall': 0,
            'comment': 'No screenshots available',
        }

    prompt_text = f"""以下は「{model_name}」というLLMが生成したReactチャットアプリケーションのスクリーンショットです。

デザイン品質を以下の観点で1-5点で評価してください：

1. **layout** (レイアウト): 要素の配置は適切で見やすいか。余白や整列は適切か
2. **aesthetics** (美しさ): 色使い、フォント、影、角丸などのビジュアル要素は美しいか
3. **usability** (使いやすさ): UIは直感的に操作できるか。ボタンや入力欄は分かりやすいか
4. **completeness** (完成度): チャットアプリとして必要な要素（ログイン、ユーザー一覧、メッセージ、送信フォーム）が揃っているか
5. **uniqueness** (独自性): デフォルトのBootstrapやMUIそのままではなく、独自の工夫があるか

**重要**: 画像に実際に写っているものだけを評価し、写っていない要素を想像で補わないでください。
スクリーンショットが白紙（真っ白）またはエラーメッセージのみの場合、その画面にUIは存在しません。
全画面が白紙・エラーのみの場合は全項目を1にしてください。一部の画面だけが白紙・エラーの場合は、その分completenessを下げてください。

JSON形式のみで回答してください（説明不要）：
{{"layout": X, "aesthetics": X, "usability": X, "completeness": X, "uniqueness": X, "overall": X, "comment": "一言コメント"}}"""

    try:
        if os.environ.get('VISUAL_EVAL_API', 'anthropic') in ('local', 'openai', 'ollama'):
            output = _call_local_vlm(images_b64, prompt_text)
        else:
            import anthropic
            client = anthropic.Anthropic()

            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": b64,
                    },
                }
                for b64 in images_b64
            ] + [{"type": "text", "text": prompt_text}]

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                messages=[{"role": "user", "content": content}],
            )

            output = response.content[0].text.strip()

        # Extract JSON from output
        json_match = re.search(r'\{[^{}]*\}', output, re.DOTALL)
        if json_match:
            scores = json.loads(json_match.group())
            for key in ['layout', 'aesthetics', 'usability', 'completeness', 'uniqueness', 'overall']:
                scores.setdefault(key, 0)
            scores.setdefault('comment', '')
            return scores

        return {
            'layout': 0, 'aesthetics': 0, 'usability': 0,
            'completeness': 0, 'uniqueness': 0, 'overall': 0,
            'comment': f'Failed to parse: {output[:200]}',
        }
    except Exception as e:
        return {
            'layout': 0, 'aesthetics': 0, 'usability': 0,
            'completeness': 0, 'uniqueness': 0, 'overall': 0,
            'comment': f'Error: {str(e)}',
        }


def visual_score_to_points(scores: dict, max_points: int = 20) -> float:
    """Convert 1-5 scale visual scores to benchmark points (0-max_points)."""
    overall = scores.get('overall', 0)
    return (overall / 5.0) * max_points
