#!/usr/bin/env python3
"""
LLM Coding Benchmark - React Chat App Generation
Tests whether LLMs can build a working React chat application with
login, friend follow, and direct messaging features.

Usage:
    python coding_benchmark.py --models qwen3:8b qwen3.6:35b-a3b \
        --output coding_benchmark_results.json --host localhost
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, asdict, field
from typing import List, Dict
import argparse
import requests

from coding_benchmark_prompt import get_coding_prompt
from coding_benchmark_evaluate import evaluate_screenshots, visual_score_to_points

DOCKER_IMAGE = 'coding-bench-runner'
SCREENSHOT_BASE = os.path.join(os.path.dirname(__file__), 'coding_benchmark_screenshots')


@dataclass
class CodingBenchmarkResult:
    model: str
    generation_time: float = 0.0
    tokens_per_second: float = 0.0
    raw_output_length: int = 0
    files_generated: int = 0
    build_success: bool = False
    server_starts: bool = False
    test_login: bool = False
    test_friends: bool = False
    test_messaging: bool = False
    test_realtime: bool = False
    retry_count: int = 0
    max_retries: int = 10
    functional_score: float = 0.0
    visual_scores: Dict = field(default_factory=dict)
    visual_score: float = 0.0
    total_score: float = 0.0
    screenshots: Dict[str, str] = field(default_factory=dict)
    error_log: str = ''


def get_recovery_prompt(original_code: str, error_msg: str, retry_num: int) -> str:
    """Generate a recovery prompt to fix errors in the generated code."""
    return f"""前回生成したReactチャットアプリケーションのコードにエラーがありました。
エラーを修正して、完全なコードを再度出力してください。

## エラー内容 (リトライ {retry_num}/10)
{error_msg[:2000]}

## 修正指示
- エラーの原因を特定し、修正してください
- 全てのファイルを再度 === FILE: path === ... === END FILE === 形式で出力してください
- package.jsonにはvite, @vitejs/plugin-reactをdevDependenciesに含めてください
- better-sqlite3がインストールできない場合はsqlite3パッケージや代替手段を使ってください
- 全てのコードを省略せずに完全に出力してください

## 前回のコード（参考）
{original_code[:8000]}
"""


def is_thinking_model(model: str) -> bool:
    thinking_patterns = ['qwen3', 'qwen3.5', 'qwen3.6', 'deepseek-r1', 'gpt-oss', 'o1']
    return any(p in model.lower() for p in thinking_patterns)


def get_coding_model_options(model: str) -> dict:
    options = {
        'temperature': 0.3,
        'num_predict': 65536,
        'num_ctx': 131072,
    }
    if any(s in model.lower() for s in ['3b', '1b', '0.5b', '0.6b']):
        options['num_ctx'] = 32768
        options['num_predict'] = 16384
    if 'mistral-medium' in model.lower() or '128b' in model.lower():
        options['num_ctx'] = 32768
        options['num_predict'] = 16384
    return options


def _call_llama_cpp(api_url: str, prompt: str) -> tuple:
    """Call llama.cpp /completion with stream=true to bypass non-stream JSON UTF-8 bug.

    Wraps the user prompt with DeepSeek-V4 chat tokens so the same code path
    works against bare /completion endpoints serving deepseek_v4 GGUFs (e.g.
    PR#22378 fork). Streaming chunks let us capture partial output even when
    the server hits the broken-UTF-8 serialization bug.
    """
    wrapped = (
        '<｜begin▁of▁sentence｜><｜User｜>' + prompt + '<｜Assistant｜></think>'
    )
    start_time = time.time()
    output_chunks = []
    tokens = 0
    try:
        with requests.post(
            f'{api_url}/completion',
            json={
                'prompt': wrapped,
                'n_predict': 16384,
                'temperature': 0.3,
                'stop': ['<｜end▁of▁sentence｜>', '<｜User｜>'],
                'stream': True,
            },
            timeout=86400,
            stream=True,
        ) as response:
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith('data: '):
                    continue
                payload = line[6:].strip()
                if not payload or payload == '[DONE]':
                    continue
                try:
                    chunk = json.loads(payload)
                except Exception:
                    continue
                output_chunks.append(chunk.get('content', '') or '')
                tokens = chunk.get('tokens_predicted', tokens)
                if chunk.get('stop'):
                    break
        elapsed = time.time() - start_time
        output = ''.join(output_chunks)
        tps = tokens / elapsed if elapsed > 0 else 0
        return output.strip(), elapsed, tps
    except Exception as e:
        elapsed = time.time() - start_time
        partial = ''.join(output_chunks)
        if partial:
            return partial.strip(), elapsed, tokens / elapsed if elapsed > 0 else 0
        return f'Error: {str(e)}', elapsed, 0


def _call_mlx(api_url: str, prompt: str) -> tuple:
    """Call MLX /v1/chat/completions endpoint."""
    start_time = time.time()
    try:
        response = requests.post(
            f'{api_url}/v1/chat/completions',
            json={
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 65536,
                'temperature': 0.3
            },
            timeout=1800,
        )
        data = response.json()
        elapsed = time.time() - start_time
        output = data.get('choices', [{}])[0].get('message', {}).get('content', '') or ''
        usage = data.get('usage', {})
        tokens = usage.get('completion_tokens', len(output))
        tps = tokens / elapsed if elapsed > 0 else 0
        return output.strip(), elapsed, tps
    except Exception as e:
        return f'Error: {str(e)}', time.time() - start_time, 0


def _call_ollama(api_url: str, model: str, prompt: str) -> tuple:
    """Call Ollama /api/generate endpoint."""
    options = get_coding_model_options(model)
    start_time = time.time()
    try:
        response = requests.post(
            f'{api_url}/api/generate',
            json={'model': model, 'prompt': prompt, 'stream': False, 'options': options},
            timeout=14400,
        )
        data = response.json()
        elapsed = time.time() - start_time
        output = data.get('response', '') or ''
        eval_count = data.get('eval_count', len(output))
        eval_duration = data.get('eval_duration', elapsed * 1e9) / 1e9
        tps = eval_count / eval_duration if eval_duration > 0 else 0
        return output.strip(), elapsed, tps
    except Exception as e:
        return f'Error: {str(e)}', time.time() - start_time, 0


def _clean_thinking(output: str) -> str:
    """Remove thinking blocks from LLM output."""
    if '<think>' in output and '</think>' in output:
        output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL)
    if '</think>' in output:
        output = output.split('</think>')[-1]
    return output.strip()


def _detect_server_type(api_url: str) -> str:
    """Detect server type by checking available endpoints."""
    try:
        # Check if llama.cpp (has /completion endpoint)
        r = requests.post(
            f'{api_url}/completion',
            json={'prompt': 'test', 'n_predict': 1},
            timeout=10,
        )
        if r.ok:
            return 'llama_cpp'
    except:
        pass
    # Fall back to MLX (uses /v1/completions)
    return 'mlx'


def generate_code(model: str, ollama_host: str = 'localhost') -> tuple:
    """Call LLM to generate the chat app code."""
    prompt = get_coding_prompt()
    print(f'  Generating code with {model}...')

    # Determine API type from host
    if ':' in ollama_host and not ollama_host.endswith(':11434'):
        # Non-standard port = llama.cpp or MLX server
        api_url = f'http://{ollama_host}'
        server_type = _detect_server_type(api_url)
        if server_type == 'mlx':
            output, elapsed, tps = _call_mlx(api_url, prompt)
        else:
            output, elapsed, tps = _call_llama_cpp(api_url, prompt)
    else:
        host = ollama_host.split(':')[0] if ':' in ollama_host else ollama_host
        api_url = f'http://{host}:11434'
        output, elapsed, tps = _call_ollama(api_url, model, prompt)

    output = _clean_thinking(output)
    return output, elapsed, tps


def generate_code_with_prompt(model: str, prompt: str, ollama_host: str = 'localhost') -> tuple:
    """Call LLM with a custom prompt (for recovery)."""
    if ':' in ollama_host and not ollama_host.endswith(':11434'):
        api_url = f'http://{ollama_host}'
        server_type = _detect_server_type(api_url)
        if server_type == 'mlx':
            output, elapsed, tps = _call_mlx(api_url, prompt)
        else:
            output, elapsed, tps = _call_llama_cpp(api_url, prompt)
    else:
        host = ollama_host.split(':')[0] if ':' in ollama_host else ollama_host
        api_url = f'http://{host}:11434'
        output, elapsed, tps = _call_ollama(api_url, model, prompt)

    output = _clean_thinking(output)
    return output, elapsed, tps


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
        # Remove markdown code fences that LLMs sometimes add inside FILE blocks
        content = re.sub(r'^```\w*\n', '', content)
        content = re.sub(r'\n```\s*$', '', content)
        files[filepath] = content

    if files:
        return files

    # Pattern 2: ```filename or ```language\n// filename
    # Look for markdown code blocks with filenames
    pattern2 = re.compile(
        r'(?:^|\n)(?:#{1,3}\s+)?[`*]*(\S+\.\w+)[`*]*\s*\n```\w*\n(.*?)```',
        re.DOTALL
    )
    for match in pattern2.finditer(code_text):
        filepath = match.group(1).strip()
        content = match.group(2)
        files[filepath] = content

    if files:
        return files

    # Pattern 3: Look for individual code blocks with file indicators
    blocks = re.findall(r'```(?:\w+)?\n(.*?)```', code_text, re.DOTALL)
    for block in blocks:
        # Try to detect filename from first comment line
        first_line = block.strip().split('\n')[0] if block.strip() else ''
        if '// ' in first_line and '.' in first_line:
            name = first_line.replace('//', '').strip()
            files[name] = block
        elif first_line.startswith('{') and '"name"' in block:
            files['package.json'] = block
        elif 'express' in block and 'listen' in block:
            files['server.js'] = block
        elif 'createRoot' in block or 'ReactDOM' in block:
            files['src/main.jsx'] = block
        elif 'useState' in block and 'App' in block:
            files['src/App.jsx'] = block
        elif '<!DOCTYPE' in block or '<html' in block:
            files['index.html'] = block

    return files


def write_files_to_dir(files: Dict[str, str], target_dir: str):
    """Write parsed files to a directory."""
    for filepath, content in files.items():
        # Sanitize path
        filepath = filepath.lstrip('/')
        full_path = os.path.join(target_dir, filepath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)


def run_docker_test(code_dir: str, model_name: str, timeout: int = 300) -> dict:
    """Run the Docker container to build, test, and screenshot the app."""
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', model_name)
    screenshot_dir = os.path.join(SCREENSHOT_BASE, safe_name)
    os.makedirs(screenshot_dir, exist_ok=True)

    print(f'  Running Docker tests (timeout {timeout}s)...')

    try:
        result = subprocess.run(
            [
                'docker', 'run', '--rm',
                '-v', f'{code_dir}:/app:rw',
                '-v', f'{screenshot_dir}:/screenshots:rw',
                DOCKER_IMAGE,
            ],
            capture_output=True,
            text=True,
            timeout=timeout + 30,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr

        # Try to parse JSON from last line of stdout
        for line in reversed(stdout.split('\n')):
            line = line.strip()
            if line.startswith('{'):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass

        # Try to read results from screenshot dir
        results_file = os.path.join(screenshot_dir, 'results.json')
        if os.path.exists(results_file):
            with open(results_file) as f:
                return json.load(f)

        return {
            'build_success': False,
            'server_starts': False,
            'error': f'No JSON output. stderr: {stderr[-500:]}',
            'stderr': stderr[-2000:] if stderr else '',
        }

    except subprocess.TimeoutExpired:
        return {
            'build_success': False,
            'server_starts': False,
            'error': f'Docker container timed out after {timeout}s'
        }
    except Exception as e:
        return {
            'build_success': False,
            'server_starts': False,
            'error': str(e)
        }


def calculate_functional_score(docker_result: dict) -> float:
    """Calculate functional score (0-80) from Docker test results."""
    score = 0.0

    # Build success: 15 points
    if docker_result.get('build_success', False):
        score += 15

    # Server starts: 10 points
    if docker_result.get('server_starts', False):
        score += 10

    # Login test: 15 points
    login = docker_result.get('test_login', {})
    if isinstance(login, dict):
        if login.get('passed', False):
            score += 15
            if login.get('uiLogin', False):
                pass  # Full points already
            elif login.get('apiLogin', False):
                score -= 5  # API only, reduce by 5
    elif login:
        score += 15

    # Friends test: 15 points
    friends = docker_result.get('test_friends', {})
    if isinstance(friends, dict):
        if friends.get('passed', False):
            score += 15
            if not friends.get('uiFollow', False) and friends.get('apiFollow', False):
                score -= 5
    elif friends:
        score += 15

    # Messaging test: 15 points
    messaging = docker_result.get('test_messaging', {})
    if isinstance(messaging, dict):
        if messaging.get('passed', False):
            score += 15
            if not messaging.get('uiMsg', False) and messaging.get('apiMsg', False):
                score -= 5
    elif messaging:
        score += 15

    # Realtime test: 10 points
    realtime = docker_result.get('test_realtime', {})
    if isinstance(realtime, dict):
        if realtime.get('passed', False):
            score += 10
    elif realtime:
        score += 10

    return score


def run_benchmark(
    models: List[str],
    output_path: str = 'coding_benchmark_results.json',
    ollama_host: str = 'localhost',
    timeout: int = 300,
    skip_visual: bool = False,
    max_retries: int = 10,
) -> List[CodingBenchmarkResult]:
    """Run the full coding benchmark."""
    os.makedirs(SCREENSHOT_BASE, exist_ok=True)
    results = []

    for model in models:
        print(f'\n{"="*60}')
        print(f'Model: {model}')
        print(f'{"="*60}')

        result = CodingBenchmarkResult(model=model, max_retries=max_retries)
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', model)
        total_gen_time = 0.0

        # Step 1: Initial code generation
        code_text, elapsed, tps = generate_code(model, ollama_host)
        total_gen_time += elapsed
        result.tokens_per_second = tps
        result.raw_output_length = len(code_text)

        if code_text.startswith('Error:'):
            result.error_log = code_text
            result.generation_time = total_gen_time
            print(f'  Generation failed: {code_text[:200]}')
            results.append(result)
            continue

        print(f'  Generated {len(code_text)} chars in {elapsed:.1f}s ({tps:.1f} tok/s)')

        # Retry loop: up to max_retries attempts
        for attempt in range(max_retries + 1):
            if attempt > 0:
                print(f'\n  --- Retry {attempt}/{max_retries} ---')

            # Parse files
            files = parse_generated_files(code_text)
            result.files_generated = len(files)
            print(f'  Parsed {len(files)} files: {", ".join(list(files.keys())[:8])}')

            if not files or 'package.json' not in files:
                error_msg = 'No package.json found in generated code'
                print(f'  ERROR: {error_msg}')
                if attempt < max_retries:
                    recovery_prompt = get_recovery_prompt(code_text, error_msg, attempt + 1)
                    code_text, elapsed, _ = generate_code_with_prompt(model, recovery_prompt, ollama_host)
                    total_gen_time += elapsed
                    result.retry_count = attempt + 1
                    continue
                else:
                    result.error_log = error_msg
                    break

            # Write to temp dir and run Docker
            tmpdir = tempfile.mkdtemp(prefix='coding_bench_')
            try:
                write_files_to_dir(files, tmpdir)

                # Save generated code
                raw_output_path = os.path.join(SCREENSHOT_BASE, safe_name, 'generated_code.txt')
                os.makedirs(os.path.dirname(raw_output_path), exist_ok=True)
                with open(raw_output_path, 'w') as f:
                    f.write(code_text)

                docker_result = run_docker_test(tmpdir, model, timeout)

                result.build_success = docker_result.get('build_success', False)
                result.server_starts = docker_result.get('server_starts', False)

                # If build or server failed, try recovery
                if not result.build_success or not result.server_starts:
                    error_msg = docker_result.get('error', '')
                    stderr = docker_result.get('stderr', '')
                    full_error = f"{error_msg}\n{stderr}".strip()
                    print(f'  FAILED: {error_msg[:200]}')

                    if attempt < max_retries:
                        recovery_prompt = get_recovery_prompt(code_text, full_error, attempt + 1)
                        code_text, elapsed, _ = generate_code_with_prompt(model, recovery_prompt, ollama_host)
                        total_gen_time += elapsed
                        result.retry_count = attempt + 1
                        print(f'  Recovery generated {len(code_text)} chars in {elapsed:.1f}s')
                        continue
                    else:
                        result.error_log = full_error
                        break

                # Parse test results
                login = docker_result.get('test_login', {})
                result.test_login = login.get('passed', False) if isinstance(login, dict) else bool(login)
                friends = docker_result.get('test_friends', {})
                result.test_friends = friends.get('passed', False) if isinstance(friends, dict) else bool(friends)
                messaging = docker_result.get('test_messaging', {})
                result.test_messaging = messaging.get('passed', False) if isinstance(messaging, dict) else bool(messaging)
                realtime = docker_result.get('test_realtime', {})
                result.test_realtime = realtime.get('passed', False) if isinstance(realtime, dict) else bool(realtime)

                if docker_result.get('error'):
                    result.error_log = docker_result['error']

                # Calculate functional score
                result.functional_score = calculate_functional_score(docker_result)
                result.retry_count = attempt
                print(f'  Functional score: {result.functional_score}/80 (attempt {attempt + 1})')

                # If not all tests passed, retry with test failure feedback
                all_passed = result.test_login and result.test_friends and result.test_messaging and result.test_realtime
                if not all_passed and attempt < max_retries:
                    failed_tests = []
                    if not result.test_login: failed_tests.append('ログイン/サインアップ')
                    if not result.test_friends: failed_tests.append('フレンドフォロー/解除')
                    if not result.test_messaging: failed_tests.append('DM送受信')
                    if not result.test_realtime: failed_tests.append('リアルタイム更新(2秒ポーリング)')
                    test_error = f"以下の機能テストが失敗しました:\n- " + "\n- ".join(failed_tests)
                    test_error += f"\n\n現在のスコア: {result.functional_score}/80"
                    stderr = docker_result.get('stderr', '')
                    if stderr:
                        test_error += f"\n\nサーバーログ:\n{stderr[-1000:]}"
                    print(f'  Tests failed: {", ".join(failed_tests)}')
                    recovery_prompt = get_recovery_prompt(code_text, test_error, attempt + 1)
                    code_text, elapsed, _ = generate_code_with_prompt(model, recovery_prompt, ollama_host)
                    total_gen_time += elapsed
                    result.retry_count = attempt + 1
                    print(f'  Recovery generated {len(code_text)} chars in {elapsed:.1f}s')
                    continue

                # All tests passed or out of retries
                break

            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

        result.generation_time = total_gen_time

        # Visual evaluation (after retry loop)
        screenshot_dir = os.path.join(SCREENSHOT_BASE, safe_name)
        screenshots = {}
        for name in ['login', 'friends', 'dm', 'chat']:
            path = os.path.join(screenshot_dir, f'{name}.png')
            if os.path.exists(path):
                screenshots[name] = path
        result.screenshots = screenshots

        if screenshots and not skip_visual:
            print(f'  Evaluating {len(screenshots)} screenshots with Claude Vision...')
            visual = evaluate_screenshots(screenshot_dir, model)
            result.visual_scores = visual
            result.visual_score = visual_score_to_points(visual)
            print(f'  Visual score: {result.visual_score:.1f}/20 ({visual.get("comment", "")})')
        else:
            result.visual_score = 0.0
            if not screenshots:
                print(f'  No screenshots captured')

        result.total_score = result.functional_score + result.visual_score
        print(f'  TOTAL: {result.total_score:.1f}/100 (retries: {result.retry_count})')

        results.append(result)

    # Save results
    output_data = {
        'benchmark': 'coding',
        'description': 'React Chat App Generation Benchmark',
        'results': [asdict(r) for r in results],
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print_summary(results)
    return results


def print_summary(results: List[CodingBenchmarkResult]):
    """Print benchmark summary table."""
    print(f'\n{"="*90}')
    print('CODING BENCHMARK SUMMARY')
    print(f'{"="*90}')
    print(f'{"Model":<25} {"Gen(s)":>7} {"Retry":>5} {"Build":>6} {"Login":>6} '
          f'{"Friend":>7} {"DM":>6} {"RT":>6} {"Func":>6} {"Visual":>7} {"TOTAL":>7}')
    print('-' * 95)

    for r in results:
        check = lambda v: "OK" if v else "--"
        print(f'{r.model:<25} {r.generation_time:>6.0f}s {r.retry_count:>5} '
              f'{check(r.build_success):>6} {check(r.test_login):>6} '
              f'{check(r.test_friends):>7} {check(r.test_messaging):>6} '
              f'{check(r.test_realtime):>6} {r.functional_score:>5.0f}/80 '
              f'{r.visual_score:>5.0f}/20 {r.total_score:>5.0f}/100')


def ensure_docker_image():
    """Build the Docker image if it doesn't exist."""
    result = subprocess.run(
        ['docker', 'images', '-q', DOCKER_IMAGE],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        print(f'Building Docker image {DOCKER_IMAGE}...')
        docker_dir = os.path.join(os.path.dirname(__file__), 'coding_benchmark_docker')
        subprocess.run(
            ['docker', 'build', '-t', DOCKER_IMAGE, docker_dir],
            check=True,
            timeout=300,
        )
        print('Docker image built successfully.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LLM Coding Benchmark')
    parser.add_argument('--models', nargs='+', default=['qwen3:8b'])
    parser.add_argument('--output', default='coding_benchmark_results.json')
    parser.add_argument('--host', default='localhost', help='Ollama host')
    parser.add_argument('--timeout', type=int, default=300, help='Docker timeout (seconds)')
    parser.add_argument('--skip-visual', action='store_true', help='Skip Claude vision evaluation')
    parser.add_argument('--max-retries', type=int, default=10, help='Max retry attempts on failure')

    args = parser.parse_args()

    ensure_docker_image()

    run_benchmark(
        models=args.models,
        output_path=args.output,
        ollama_host=args.host,
        timeout=args.timeout,
        skip_visual=args.skip_visual,
        max_retries=args.max_retries,
    )
