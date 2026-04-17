#!/usr/bin/env python3
"""
Claude Vision evaluation of chat app screenshots.
Evaluates design quality, usability, and completeness via Anthropic API.
"""

import base64
import json
import os
import re
from pathlib import Path


def evaluate_screenshots(screenshot_dir: str, model_name: str) -> dict:
    """Evaluate screenshots using Anthropic Vision API."""
    screenshot_path = Path(screenshot_dir)

    # Collect existing screenshots
    image_contents = []
    for name in ['login', 'friends', 'dm', 'chat']:
        path = screenshot_path / f'{name}.png'
        if path.exists():
            with open(path, 'rb') as f:
                b64 = base64.standard_b64encode(f.read()).decode('utf-8')
            image_contents.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            })

    if not image_contents:
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

JSON形式のみで回答してください（説明不要）：
{{"layout": X, "aesthetics": X, "usability": X, "completeness": X, "uniqueness": X, "overall": X, "comment": "一言コメント"}}"""

    try:
        import anthropic
        client = anthropic.Anthropic()

        content = image_contents + [{"type": "text", "text": prompt_text}]

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
