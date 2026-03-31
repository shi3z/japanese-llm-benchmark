# Japanese LLM Benchmark

A benchmark tool for evaluating Japanese language capabilities of various LLMs, specifically optimized for RTX 5060 Ti (8GB VRAM).

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

## Tested Models (RTX 5060 Ti 8GB)

| Model | Size | Speed (tok/s) | ROUGE-L | Notes |
|-------|------|---------------|---------|-------|
| Nemotron-3-Nano:4b | 2.8GB | ~5 | 0.11 | Best Japanese quality |
| Qwen3:4b | 2.5GB | ~115 | 0.03 | Fast but thinking-only |
| Llama3.2:3b | 2.0GB | ~154 | TBD | General purpose |
| Phi4-mini | 2.5GB | TBD | TBD | Microsoft model |
| Gemma3:4b | 3.3GB | TBD | TBD | Google model |
| Mistral:7b-Q4 | 4.4GB | TBD | TBD | General purpose |
| DeepSeek-R1:7b | 4.7GB | TBD | TBD | Reasoning model |

## License

MIT
