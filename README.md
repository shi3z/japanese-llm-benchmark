# Japanese LLM Benchmark

A benchmark tool for evaluating Japanese language capabilities of various LLMs.

## Features

- **ROUGE Score Evaluation**: Measures summarization quality using ROUGE-1, ROUGE-2, and ROUGE-L
- **Speed Benchmarking**: Measures tokens per second for each model
- **WebUI**: Interactive web interface for running benchmarks and visualizing results
- **Multiple Model Support**: Works with any Ollama-compatible model

## Requirements

- Python 3.10+
- Ollama running locally
- 8GB+ VRAM (for full GPU inference)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### WebUI Mode

```bash
python app.py
```

Access the WebUI at `http://localhost:8080`

### CLI Mode

```bash
python benchmark.py --dataset dataset.jsonl --models nemotron-3-nano:4b qwen3:4b --samples 10
```

## Dataset Format

JSONL file with the following structure:

```json
{"text": "Long Japanese text to summarize...", "summary": "Reference summary"}
```

---

# Benchmark Results

RTX 5090 (32GB) / RTX 5060 (8GB) - 7000文字長文テキスト - 定性的評価

## 総合ランキング

| Rank | Model | ROUGE-L | Speed | Size | Tier |
|------|-------|---------|-------|------|------|
| 1 | qwen3:30b-a3b | **0.347** | 200 tok/s | 18.6GB | S |
| 2 | qwen3:8b | **0.333** | 204 tok/s | 5.2GB | S |
| 3 | gemma3:12b | 0.303 | 141 tok/s | 8.1GB | A |
| 4 | qwen3-128k | 0.302 | 203 tok/s | 5.2GB | A |
| 5 | qwen3:14b | 0.292 | 128 tok/s | 9.3GB | A |
| 6 | gpt-oss-128k | 0.288 | 259 tok/s | 13.8GB | A |
| 7 | mistral-small | 0.285 | 96 tok/s | 14.3GB | A |
| 8 | ELYZA 8B | 0.258 | 241 tok/s | 4.9GB | B |
| 9 | llama3.2:3b | 0.246 | 427 tok/s | 2.0GB | B |
| 10 | gemma3:4b | 0.243 | 286 tok/s | 3.3GB | B |
| 11 | mistral:7b | 0.196 | 244 tok/s | 4.4GB | C |
| 12 | LLM-JP 1.8b | 0.150 | 609 tok/s | 1.2GB | D |
| 13 | phi4-mini | 0.107 | 378 tok/s | 2.5GB | D |
| 14 | nemotron-mini | 0.048 | 366 tok/s | 2.7GB | D |

---

## 定性的評価

### S Tier - 卓越した品質（実用レベルで推奨）

#### qwen3:30b-a3b (MoE)
- **ROUGE-L**: 0.347 | **Speed**: 200 tok/s | **Size**: 18.6GB

**生成例 (Sample 1)**:
> 大規模言語モデルは目的別・ユーザー別にカスタマイズされ、多様性を持つべきという考え方が広がっている。AgenticAIがユーザーの好みを学習し、デジタルツインとしてメール返信や意思決定を担う未来が描かれる。技術主導型の未来戦略において、人間性や倫理、市民参加が不可欠と認識が拡大。欧州はプライバシー保護を最優先に、北米は市場主導型のアプローチを取るなど、地域ごとのAI倫理のアプローチが異なる。

**評価**:
- ✅ 主要論点を網羅（LLM、デジタルツイン、倫理、国際協調）
- ✅ 「欧州 vs 北米」の具体的対比を保持
- ✅ 日本語として自然で読みやすい

---

#### qwen3:8b
- **ROUGE-L**: 0.333 | **Speed**: 204 tok/s | **Size**: 5.2GB

**生成例 (Sample 1)**:
> 大規模言語モデルの応用が注目され、ユーザー別カスタマイズやデジタルツインとしてのAgenticAIの可能性が示される。AI倫理や市民参加の重要性が強調され、欧米アジアの地域差も。技術と人間性の融合が未来の情報エコシステムの基盤となる。

**評価**:
- ✅ 117文字で非常に簡潔
- ✅ 核心的キーワードを的確に抽出
- ✅ 8GB VRAMで動作可能
- ⚠️ 一部文末が唐突

---

### A Tier - 高品質（多くの用途で推奨）

#### gemma3:12b
- **ROUGE-L**: 0.303 | **Speed**: 141 tok/s | **Size**: 8.1GB

> 大規模言語モデルの進化は、個々のニーズに合わせたカスタマイズや「デジタルツイン」としての活用を可能にし...技術と倫理の融合による、市民参加型の情報倫理構築が鍵となる。

- ✅ 主要概念を正確に抽出
- ✅ 225文字で適切な長さ
- ⚠️ 国際比較の視点がやや弱い

#### qwen3-128k
- **ROUGE-L**: 0.302 | **Speed**: 203 tok/s | **Size**: 5.2GB

> 大規模言語モデルの応用が注目され、カスタマイズされたAgenticAIがユーザーのデジタルツインとして活用される。情報エコシステムの多様性と倫理的課題が強調され...

- ✅ 115文字と非常に簡潔
- ✅ 128Kコンテキスト対応
- ⚠️ 簡潔すぎて詳細が欠落

#### gpt-oss-128k
- **ROUGE-L**: 0.288 | **Speed**: 259 tok/s | **Size**: 13.8GB

- ✅ 具体的な応用例を挙げている
- ✅ 128Kコンテキスト対応
- ⚠️ 一部文章が不自然

#### mistral-small
- **ROUGE-L**: 0.285 | **Speed**: 96 tok/s | **Size**: 14.3GB

- ✅ 内容の網羅性が高い
- ✅ EU vs 米国のアプローチの違いを明記
- ⚠️ 324文字とやや長め

---

### B Tier - 標準的品質（用途によっては使用可能）

#### ELYZA 8B
- **ROUGE-L**: 0.258 | **Speed**: 241 tok/s | **Size**: 4.9GB

- ✅ 日本語特化モデルらしく文法が自然
- ✅ 160文字で適切な長さ
- ⚠️ 「国際協調」の視点が弱い

#### llama3.2:3b
- **ROUGE-L**: 0.246 | **Speed**: 427 tok/s | **Size**: 2.0GB

- ✅ 3Bパラメータながら主要概念を捉えている
- ⚠️ 「この文脈において」という不要な前置き
- ⚠️ やや冗長な表現

#### gemma3:4b
- **ROUGE-L**: 0.243 | **Speed**: 286 tok/s | **Size**: 3.3GB

- ✅ 内容は正確
- ❌ 503文字と非常に長い（要約として不適切）
- ⚠️ 簡潔さに欠ける

---

### C Tier - 品質に課題あり（限定的な用途のみ）

#### mistral:7b
- **ROUGE-L**: 0.196 | **Speed**: 244 tok/s | **Size**: 4.4GB

> 1. ローカルAIのセキュリティに関する主な注意点は、シリコングラフィックス社の創業と...2. プレイヤーに休みの時間を忘れるな。3. さらに弾幕系の敵を追加して...

- ❌ 番号リスト形式で要約として不適切
- ❌ 無関係な内容が混入（ゲーム関連）
- ❌ ハルシネーション発生

---

### D Tier - 非推奨（日本語要約タスクに不適合）

#### LLM-JP 1.8b
- **ROUGE-L**: 0.150 | **Speed**: 609 tok/s

- ❌ 原文の要約ではなく一般的な説明を生成
- ❌ 原文にない例（Siri, Alexa）を挙げている
- ❌ 要約タスクを理解していない

#### phi4-mini
- **ROUGE-L**: 0.107

- ❌ 2/3のサンプルでタイムアウトエラー
- ❌ 成功した1件も内容が断片的
- ❌ 安定性に重大な問題

#### nemotron-mini
- **ROUGE-L**: 0.048

- ❌ 3サンプル中2件が空出力
- ❌ 1件の出力も原文と無関係
- ❌ 日本語要約タスクに完全に不適合

---

## RTX 5060 (8GB VRAM) ベンチマーク結果

### 8GB VRAM向けランキング

| Rank | Model | ROUGE-L | Speed | Size | 評価 |
|------|-------|---------|-------|------|------|
| 1 | **qwen3:8b** | **0.333** | 204 tok/s | 5.2GB | 最高性能！ |
| 2 | qwen3-128k | 0.302 | 203 tok/s | 5.2GB | 128K対応 |
| 3 | ELYZA 8B | 0.258 | 241 tok/s | 4.9GB | 日本語特化 |
| 4 | llama3.2:3b | 0.246 | 427 tok/s | 2.0GB | 軽量・高速 |
| 5 | gemma3:4b | 0.243 | 286 tok/s | 3.3GB | バランス型 |
| 6 | mistral:7b | 0.196 | 244 tok/s | 4.4GB | 注意 |

### qwen3:8b サンプル出力

#### Sample 1: LLM・デジタルツイン・AI倫理
- **ROUGE-L**: 0.384 | **出力長**: 117文字 | **速度**: 204 tok/s

> 大規模言語モデルの応用が注目され、ユーザー別カスタマイズやデジタルツインとしてのAgenticAIの可能性が示される。AI倫理や市民参加の重要性が強調され、欧米アジアの地域差も。技術と人間性の融合が未来の情報エコシステムの基盤となる。

#### Sample 2: メディアと市民参加
- **ROUGE-L**: 0.325 | **出力長**: 153文字 | **速度**: 204 tok/s

> 技術の進歩により、自然言語処理やAIが社会に大きな影響を与えている。ラジオや映画などのメディアは市民参加を促し、デジタル革命では情報の双方向性が強化されている。ブロックチェーンを活用したデジタルアイデンティティ管理や、VR・ARによる新たな情報体験が進む一方、情報の信頼性や市民責任の重要性が問われている。

#### Sample 3: 印刷革命と知識の民主化
- **ROUGE-L**: 0.289 | **出力長**: 130文字 | **速度**: 203 tok/s

> グーテンベルクの活版印刷は知識の民主化を実現し、現代のデジタル技術（ブロックチェーン、オープンソース）がその精神を継承。情報の信頼性とオープンアクセスを確保するため、技術・倫理・国際協力が融合した多面的アプローチが求められ、教育では想像力の育成が重要とされる。

### qwen3:8b 定性的評価

| 評価軸 | スコア | コメント |
|--------|--------|----------|
| 正確性 | 4.5/5 | 主要論点をほぼ完全に抽出 |
| 簡潔さ | 5/5 | 120-150文字で最適な長さ |
| 日本語の自然さ | 4/5 | 一部文末の切れが気になる |
| キーワード抽出 | 5/5 | 重要用語を的確に選択 |
| **総合** | **4.5/5** | 8GBモデルとしては卓越 |

**結論**: RTX 5060 8GBでは **qwen3:8b** が最適。ROUGE-L 0.333は30Bクラスのqwen3:30b-a3b (0.347)に迫る性能を5.2GBで実現。

---

## 評価軸別 最優秀モデル

| 評価軸 | 最優秀 | コメント |
|--------|--------|----------|
| 内容の正確性 | qwen3:30b-a3b | 主要論点を漏れなく抽出 |
| 簡潔さ | qwen3:8b / qwen3:14b | 100文字以下で要点を凝縮 |
| 日本語の自然さ | gemma3:12b | 文法的に最も自然 |
| 速度と品質のバランス | mistral-small | 96 tok/sかつROUGE-L 0.285 |
| コストパフォーマンス | qwen3:8b | 5.2GBで高品質 |
| 8GB VRAM最適 | qwen3:8b | 30Bに迫る性能を軽量で実現 |

---

## 注意が必要なモデル

- **mistral:7b**: 長文でハルシネーション発生
- **LLM-JP 1.8b**: 要約タスクを理解せず
- **phi4-mini**: 接続エラーが頻発
- **nemotron-mini**: 日本語出力がほぼ空

---

## 評価環境

- **Hardware**: RTX 5090 (32GB) / RTX 5060 (8GB)
- **Sample Size**: ~7000 chars/sample (3 samples)
- **Thinking Models**: 128K context, 32K output
- **Date**: April 2026

---

## License

MIT
