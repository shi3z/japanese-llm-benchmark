#!/usr/bin/env python3
"""
Simple coding benchmark - just generates code without Docker tests
"""

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from typing import Dict
import argparse

import torch
from transformers import AutoModelForCausalLM, AutoProcessor

from coding_benchmark_prompt import get_coding_prompt

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'coding_benchmark_outputs')


def load_model(model_id: str):
    """Load model and processor."""
    print(f"Loading model: {model_id}")
    print(f"Available GPUs: {torch.cuda.device_count()}")

    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    tokenizer = processor.tokenizer

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    print("Model loaded successfully!")
    print(f"Device map: {model.hf_device_map}")
    return model, tokenizer


def generate_code(model, tokenizer, prompt: str, max_tokens: int = 32768) -> tuple:
    """Generate code using transformers."""
    messages = [{"role": "user", "content": prompt}]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True
    )

    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    input_len = inputs.input_ids.shape[1]

    print(f"  Input tokens: {input_len}")

    start_time = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=0.3,
            top_p=0.95,
            top_k=20,
            do_sample=True,
        )
    elapsed = time.time() - start_time

    output_tokens = outputs.shape[1] - input_len
    tps = output_tokens / elapsed if elapsed > 0 else 0

    response = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True)

    print(f"  Output tokens: {output_tokens}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Speed: {tps:.1f} tok/s")

    return response, elapsed, tps, output_tokens


def clean_thinking(output: str) -> str:
    """Remove thinking blocks from LLM output."""
    thinking_content = ""
    code_content = output

    # Extract thinking content
    think_match = re.search(r'<think>(.*?)</think>', output, flags=re.DOTALL)
    if think_match:
        thinking_content = think_match.group(1).strip()

    # Remove thinking blocks
    if '<think>' in output and '</think>' in output:
        code_content = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL)
    if '</think>' in output:
        code_content = output.split('</think>')[-1]

    return thinking_content, code_content.strip()


def parse_generated_files(code_text: str) -> Dict[str, str]:
    """Parse LLM output into file path -> content mapping."""
    files = {}

    # Pattern 1: === FILE: path ===\n...\n=== END FILE ===
    pattern1 = re.compile(
        r'===\s*FILE:\s*(.+?)\s*===\s*\n(.*?)===\s*END\s*FILE\s*===',
        re.DOTALL
    )
    for match in pattern1.finditer(code_text):
        filepath = match.group(1).strip()
        content = match.group(2)
        content = re.sub(r'^```\w*\n', '', content)
        content = re.sub(r'\n```\s*$', '', content)
        files[filepath] = content

    if files:
        return files

    # Pattern 2: markdown code blocks with filenames
    pattern2 = re.compile(
        r'(?:^|\n)(?:#{1,3}\s+)?[`*]*(\S+\.\w+)[`*]*\s*\n```\w*\n(.*?)```',
        re.DOTALL
    )
    for match in pattern2.finditer(code_text):
        filepath = match.group(1).strip()
        content = match.group(2)
        files[filepath] = content

    return files


def write_files_to_dir(files: Dict[str, str], target_dir: str):
    """Write parsed files to a directory."""
    for filepath, content in files.items():
        filepath = filepath.lstrip('/')
        full_path = os.path.join(target_dir, filepath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"    Wrote: {filepath} ({len(content)} bytes)")


def run_benchmark(model_id: str, output_dir: str = OUTPUT_DIR, max_tokens: int = 32768):
    """Run the coding benchmark."""
    os.makedirs(output_dir, exist_ok=True)

    # Load model
    model, tokenizer = load_model(model_id)

    model_name = model_id.split('/')[-1]
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', model_name)

    print(f'\n{"="*60}')
    print(f'CODING BENCHMARK: {model_name}')
    print(f'{"="*60}')

    # Get prompt
    prompt = get_coding_prompt()
    print(f'\nPrompt length: {len(prompt)} chars')

    # Generate code
    print('\nGenerating code...')
    raw_output, elapsed, tps, output_tokens = generate_code(model, tokenizer, prompt, max_tokens)

    # Clean thinking
    thinking, code_output = clean_thinking(raw_output)

    print(f'\nRaw output: {len(raw_output)} chars')
    print(f'Thinking: {len(thinking)} chars')
    print(f'Code output: {len(code_output)} chars')

    # Parse files
    print('\nParsing generated files...')
    files = parse_generated_files(code_output)
    print(f'Found {len(files)} files:')
    for fname in sorted(files.keys()):
        print(f'  - {fname}')

    # Save outputs
    model_output_dir = os.path.join(output_dir, safe_name)
    os.makedirs(model_output_dir, exist_ok=True)

    # Save raw output
    with open(os.path.join(model_output_dir, 'raw_output.txt'), 'w') as f:
        f.write(raw_output)

    # Save thinking
    if thinking:
        with open(os.path.join(model_output_dir, 'thinking.txt'), 'w') as f:
            f.write(thinking)

    # Save code output
    with open(os.path.join(model_output_dir, 'code_output.txt'), 'w') as f:
        f.write(code_output)

    # Write individual files
    if files:
        files_dir = os.path.join(model_output_dir, 'generated_app')
        os.makedirs(files_dir, exist_ok=True)
        print(f'\nWriting files to {files_dir}:')
        write_files_to_dir(files, files_dir)

    # Save results
    results = {
        'model': model_name,
        'model_id': model_id,
        'generation_time': elapsed,
        'tokens_per_second': tps,
        'output_tokens': output_tokens,
        'raw_output_length': len(raw_output),
        'thinking_length': len(thinking),
        'code_output_length': len(code_output),
        'files_generated': len(files),
        'files': list(files.keys()),
        'has_package_json': 'package.json' in files,
        'has_server_js': 'server.js' in files,
        'has_app_jsx': any('App.jsx' in f or 'App.js' in f for f in files),
        'has_index_html': 'index.html' in files,
    }

    with open(os.path.join(model_output_dir, 'results.json'), 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f'\n{"="*60}')
    print('BENCHMARK RESULTS')
    print(f'{"="*60}')
    print(f'Model: {model_name}')
    print(f'Generation time: {elapsed:.1f}s')
    print(f'Speed: {tps:.1f} tokens/sec')
    print(f'Output tokens: {output_tokens}')
    print(f'Files generated: {len(files)}')
    print(f'Has package.json: {results["has_package_json"]}')
    print(f'Has server.js: {results["has_server_js"]}')
    print(f'Has App.jsx: {results["has_app_jsx"]}')
    print(f'Has index.html: {results["has_index_html"]}')
    print(f'\nOutput saved to: {model_output_dir}')

    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Simple LLM Coding Benchmark')
    parser.add_argument('--model', default='Qwen/Qwen3.6-27B', help='HuggingFace model ID')
    parser.add_argument('--output-dir', default=OUTPUT_DIR, help='Output directory')
    parser.add_argument('--max-tokens', type=int, default=32768, help='Max output tokens')

    args = parser.parse_args()

    run_benchmark(
        model_id=args.model,
        output_dir=args.output_dir,
        max_tokens=args.max_tokens,
    )
