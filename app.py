#!/usr/bin/env python3
"""
Japanese LLM Benchmark WebUI
FastAPI + HTML/JS interface for benchmark visualization
"""

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
import json
import time
import requests
from pathlib import Path
from typing import List, Dict
import re

app = FastAPI(title='Japanese LLM Benchmark')

benchmark_status = {
    'running': False,
    'current_model': '',
    'current_sample': 0,
    'total_samples': 0,
    'progress': 0,
    'results': []
}

def calculate_rouge(generated: str, reference: str) -> Dict[str, float]:
    def get_ngrams(text: str, n: int) -> set:
        text = re.sub(r'\s+', '', text)
        return set(text[i:i+n] for i in range(len(text)-n+1))

    def rouge_n(gen: str, ref: str, n: int) -> float:
        gen_ngrams = get_ngrams(gen, n)
        ref_ngrams = get_ngrams(ref, n)
        if not ref_ngrams or not gen_ngrams:
            return 0.0
        overlap = len(gen_ngrams & ref_ngrams)
        precision = overlap / len(gen_ngrams) if gen_ngrams else 0
        recall = overlap / len(ref_ngrams) if ref_ngrams else 0
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    def lcs_length(s1: str, s2: str) -> int:
        s1 = re.sub(r'\s+', '', s1)
        s2 = re.sub(r'\s+', '', s2)
        m, n = len(s1), len(s2)
        if m == 0 or n == 0:
            return 0
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        return dp[m][n]

    lcs = lcs_length(generated, reference)
    gen_len = len(re.sub(r'\s+', '', generated))
    ref_len = len(re.sub(r'\s+', '', reference))

    if gen_len == 0 or ref_len == 0:
        rouge_l = 0.0
    else:
        p_lcs = lcs / gen_len
        r_lcs = lcs / ref_len
        rouge_l = 2 * p_lcs * r_lcs / (p_lcs + r_lcs) if (p_lcs + r_lcs) > 0 else 0.0

    return {
        'rouge_1': rouge_n(generated, reference, 1),
        'rouge_2': rouge_n(generated, reference, 2),
        'rouge_l': rouge_l
    }

def generate_summary(model: str, text: str, max_tokens: int = 300) -> dict:
    prompt = f"""以下の文章を200文字程度で要約してください。要約のみを出力し、説明は不要です。

文章：
{text[:4000]}

要約："""

    start_time = time.time()
    try:
        response = requests.post(
            'http://localhost:11434/api/generate',
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'options': {'num_predict': max_tokens, 'temperature': 0.3}
            },
            timeout=300
        )
        data = response.json()
        elapsed = time.time() - start_time

        output = data.get('response', '') or ''
        thinking = data.get('thinking', '')

        if '</think>' in output:
            output = output.split('</think>')[-1].strip()
        elif not output and thinking:
            output = thinking

        eval_count = data.get('eval_count', len(output))
        eval_duration = data.get('eval_duration', elapsed * 1e9) / 1e9
        tokens_per_sec = eval_count / eval_duration if eval_duration > 0 else 0

        return {
            'output': output.strip(),
            'elapsed': elapsed,
            'tokens_per_sec': tokens_per_sec,
            'eval_count': eval_count
        }
    except Exception as e:
        return {
            'output': f'Error: {str(e)}',
            'elapsed': time.time() - start_time,
            'tokens_per_sec': 0,
            'eval_count': 0
        }

def run_benchmark_task(models: List[str], num_samples: int, dataset_path: str):
    global benchmark_status

    benchmark_status['running'] = True
    benchmark_status['results'] = []
    benchmark_status['total_samples'] = num_samples * len(models)

    samples = []
    with open(Path(dataset_path).expanduser(), 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= num_samples:
                break
            samples.append(json.loads(line))

    sample_idx = 0
    for model in models:
        benchmark_status['current_model'] = model

        for idx, sample in enumerate(samples):
            sample_idx += 1
            benchmark_status['current_sample'] = sample_idx
            benchmark_status['progress'] = int(100 * sample_idx / benchmark_status['total_samples'])

            text = sample['text']
            reference = sample['summary']

            result = generate_summary(model, text)
            rouge = calculate_rouge(result['output'], reference)

            benchmark_status['results'].append({
                'model': model,
                'sample_id': idx,
                'input_length': len(text),
                'output_length': len(result['output']),
                'generation_time': result['elapsed'],
                'tokens_per_second': result['tokens_per_sec'],
                'generated_summary': result['output'][:500],
                'reference_summary': reference[:500],
                **rouge
            })

    with open('benchmark_results.json', 'w', encoding='utf-8') as f:
        json.dump(benchmark_status['results'], f, ensure_ascii=False, indent=2)

    benchmark_status['running'] = False
    benchmark_status['progress'] = 100

HTML_CONTENT = '''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Japanese LLM Benchmark</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1400px; margin: 0 auto; padding: 20px;
            background: #f5f5f5;
        }
        h1 { color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }
        .card {
            background: white; border-radius: 8px; padding: 20px;
            margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        label { display: block; margin: 10px 0 5px; font-weight: bold; }
        input, select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        button {
            background: #4CAF50; color: white; border: none; padding: 12px 24px;
            border-radius: 4px; cursor: pointer; font-size: 16px; margin: 5px;
        }
        button:hover { background: #45a049; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        .progress-bar {
            width: 100%; height: 30px; background: #e0e0e0; border-radius: 15px;
            overflow: hidden; margin: 10px 0;
        }
        .progress-fill {
            height: 100%; background: linear-gradient(90deg, #4CAF50, #8BC34A);
            transition: width 0.3s;
        }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f8f8f8; font-weight: bold; }
        tr:hover { background: #f5f5f5; }
        .chart-container { height: 300px; margin: 20px 0; }
        .status { padding: 10px; border-radius: 4px; margin: 10px 0; }
        .status.running { background: #fff3e0; border-left: 4px solid #ff9800; }
        .status.done { background: #e8f5e9; border-left: 4px solid #4CAF50; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 10px; }
        .checkbox-group label { display: flex; align-items: center; gap: 5px; font-weight: normal; }
    </style>
</head>
<body>
    <h1>Japanese LLM Benchmark - RTX 5060 Ti</h1>

    <div class="card">
        <h2>Benchmark Settings</h2>
        <div class="grid">
            <div>
                <label>Models:</label>
                <div class="checkbox-group" id="modelCheckboxes"></div>
            </div>
            <div>
                <label>Number of Samples:</label>
                <input type="number" id="numSamples" value="5" min="1" max="100">
            </div>
        </div>
        <div style="margin-top: 20px;">
            <button onclick="startBenchmark()" id="startBtn">Start Benchmark</button>
            <button onclick="loadResults()" style="background: #2196F3;">Load Results</button>
        </div>
    </div>

    <div class="card" id="statusCard" style="display: none;">
        <h2>Progress</h2>
        <div class="status running" id="statusText">Preparing...</div>
        <div class="progress-bar">
            <div class="progress-fill" id="progressBar" style="width: 0%;"></div>
        </div>
        <p id="progressText">0%</p>
    </div>

    <div class="card" id="resultsCard" style="display: none;">
        <h2>Benchmark Results</h2>
        <div class="grid">
            <div class="chart-container"><canvas id="speedChart"></canvas></div>
            <div class="chart-container"><canvas id="rougeChart"></canvas></div>
        </div>
        <h3>Detailed Results</h3>
        <table id="resultsTable">
            <thead>
                <tr>
                    <th>Model</th>
                    <th>Avg Time(s)</th>
                    <th>Tok/s</th>
                    <th>ROUGE-1</th>
                    <th>ROUGE-2</th>
                    <th>ROUGE-L</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
    </div>

    <div class="card" id="samplesCard" style="display: none;">
        <h2>Sample Outputs</h2>
        <div id="sampleOutputs"></div>
    </div>

    <script>
        let speedChart, rougeChart;
        let statusInterval;

        async function loadModels() {
            try {
                const resp = await fetch('/api/models');
                const models = await resp.json();
                const container = document.getElementById('modelCheckboxes');
                container.innerHTML = models.map(m =>
                    `<label><input type="checkbox" value="${m}" ${['nemotron-3-nano:4b', 'qwen3:4b'].includes(m) ? 'checked' : ''}> ${m}</label>`
                ).join('');
            } catch (e) {
                console.error('Failed to load models:', e);
            }
        }

        async function startBenchmark() {
            const checkboxes = document.querySelectorAll('#modelCheckboxes input:checked');
            const models = Array.from(checkboxes).map(cb => cb.value);
            const numSamples = parseInt(document.getElementById('numSamples').value);

            if (models.length === 0) {
                alert('Please select at least one model');
                return;
            }

            document.getElementById('startBtn').disabled = true;
            document.getElementById('statusCard').style.display = 'block';
            document.getElementById('resultsCard').style.display = 'none';

            await fetch('/api/benchmark/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({models, num_samples: numSamples})
            });

            statusInterval = setInterval(checkStatus, 1000);
        }

        async function checkStatus() {
            const resp = await fetch('/api/benchmark/status');
            const status = await resp.json();

            document.getElementById('progressBar').style.width = status.progress + '%';
            document.getElementById('progressText').textContent = status.progress + '%';
            document.getElementById('statusText').textContent =
                status.running ? `${status.current_model} - Sample ${status.current_sample}/${status.total_samples}` : 'Done!';

            if (!status.running && status.progress === 100) {
                clearInterval(statusInterval);
                document.getElementById('startBtn').disabled = false;
                document.getElementById('statusText').className = 'status done';
                displayResults(status.results);
            }
        }

        async function loadResults() {
            try {
                const resp = await fetch('/api/benchmark/results');
                const results = await resp.json();
                if (results.length > 0) {
                    document.getElementById('resultsCard').style.display = 'block';
                    displayResults(results);
                } else {
                    alert('No results available');
                }
            } catch (e) {
                alert('Failed to load results');
            }
        }

        function displayResults(results) {
            document.getElementById('resultsCard').style.display = 'block';
            document.getElementById('samplesCard').style.display = 'block';

            const modelStats = {};
            results.forEach(r => {
                if (!modelStats[r.model]) {
                    modelStats[r.model] = {times: [], tps: [], r1: [], r2: [], rl: [], samples: []};
                }
                modelStats[r.model].times.push(r.generation_time);
                modelStats[r.model].tps.push(r.tokens_per_second);
                modelStats[r.model].r1.push(r.rouge_1);
                modelStats[r.model].r2.push(r.rouge_2);
                modelStats[r.model].rl.push(r.rouge_l);
                modelStats[r.model].samples.push(r);
            });

            const models = Object.keys(modelStats);
            const avg = arr => arr.reduce((a,b) => a+b, 0) / arr.length;

            const tbody = document.querySelector('#resultsTable tbody');
            tbody.innerHTML = models.map(m => {
                const s = modelStats[m];
                return `<tr>
                    <td><strong>${m}</strong></td>
                    <td>${avg(s.times).toFixed(2)}</td>
                    <td>${avg(s.tps).toFixed(1)}</td>
                    <td>${avg(s.r1).toFixed(3)}</td>
                    <td>${avg(s.r2).toFixed(3)}</td>
                    <td>${avg(s.rl).toFixed(3)}</td>
                </tr>`;
            }).join('');

            if (speedChart) speedChart.destroy();
            speedChart = new Chart(document.getElementById('speedChart'), {
                type: 'bar',
                data: {
                    labels: models,
                    datasets: [{
                        label: 'Tokens/sec',
                        data: models.map(m => avg(modelStats[m].tps)),
                        backgroundColor: '#4CAF50'
                    }]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: true, text: 'Generation Speed (tokens/sec)' }}}
            });

            if (rougeChart) rougeChart.destroy();
            rougeChart = new Chart(document.getElementById('rougeChart'), {
                type: 'bar',
                data: {
                    labels: models,
                    datasets: [
                        { label: 'ROUGE-1', data: models.map(m => avg(modelStats[m].r1)), backgroundColor: '#2196F3' },
                        { label: 'ROUGE-2', data: models.map(m => avg(modelStats[m].r2)), backgroundColor: '#FF9800' },
                        { label: 'ROUGE-L', data: models.map(m => avg(modelStats[m].rl)), backgroundColor: '#9C27B0' }
                    ]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { title: { display: true, text: 'ROUGE Scores' }}}
            });

            const samplesDiv = document.getElementById('sampleOutputs');
            samplesDiv.innerHTML = models.map(m => {
                const sample = modelStats[m].samples[0];
                return `<div class="card">
                    <h4>${m}</h4>
                    <p><strong>Generated:</strong> ${sample.generated_summary}</p>
                    <p><strong>Reference:</strong> ${sample.reference_summary}</p>
                    <p><small>Time: ${sample.generation_time.toFixed(2)}s, ${sample.tokens_per_second.toFixed(1)} tok/s</small></p>
                </div>`;
            }).join('');
        }

        loadModels();
    </script>
</body>
</html>'''

@app.get('/', response_class=HTMLResponse)
async def index():
    return HTML_CONTENT

@app.get('/api/models')
async def get_models():
    try:
        resp = requests.get('http://localhost:11434/api/tags', timeout=10)
        models = [m['name'] for m in resp.json().get('models', [])]
        return JSONResponse(models)
    except:
        return JSONResponse(['nemotron-3-nano:4b', 'qwen3:4b'])

@app.post('/api/benchmark/start')
async def start_benchmark(data: dict, background_tasks: BackgroundTasks):
    if benchmark_status['running']:
        return {'error': 'Benchmark already running'}

    models = data.get('models', ['nemotron-3-nano:4b'])
    num_samples = data.get('num_samples', 5)

    background_tasks.add_task(
        run_benchmark_task,
        models,
        num_samples,
        '~/dataset_from_logs.jsonl'
    )

    return {'status': 'started'}

@app.get('/api/benchmark/status')
async def get_status():
    return JSONResponse(benchmark_status)

@app.get('/api/benchmark/results')
async def get_results():
    try:
        with open('benchmark_results.json', 'r', encoding='utf-8') as f:
            return JSONResponse(json.load(f))
    except:
        return JSONResponse([])

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8080)
