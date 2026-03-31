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

## Benchmark Results (RTX 5060 Ti 8GB)

### Combined Quantitative + Qualitative Evaluation

| Model | Size | Tok/s | ROUGE-L | Fluency | Accuracy | Overall | Recommendation |
|-------|------|-------|---------|---------|----------|---------|----------------|
| **gemma3:4b** | 3.3GB | 117 | 0.214 | 5.0 | 4.0 | **4.0** | **Best Overall** |
| llama3.2:3b | 2.0GB | **154** | 0.224 | 4.0 | 2.5 | 2.5 | Fastest |
| nemotron-3-nano:4b | 2.8GB | 6 | 0.210 | 3.5 | 2.5 | 2.5 | Quality but slow |
| phi4-mini | 2.5GB | 130 | 0.203 | 4.0 | 2.0 | 2.0 | Fast |
| mistral:7b-Q4 | 4.4GB | 1 | 0.185 | 2.5 | 1.0 | 1.0 | Not recommended |
| deepseek-r1:7b | 4.7GB | 1 | 0.163 | 1.5 | 1.0 | 1.0 | Not recommended |
| qwen3:4b | 2.5GB | 113 | 0.005 | 1.0 | 1.0 | 1.0 | Thinking-only |

*Qualitative scores (1-5) evaluated by Claude CLI*

## License

MIT
