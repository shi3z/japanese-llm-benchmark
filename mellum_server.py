#!/usr/bin/env python3
"""Minimal OpenAI-compatible /v1/chat/completions server for Mellum2.

Runs via transformers (vLLM does not yet recognize MellumForCausalLM as of
0.22). Supports the streaming subset needed by coding_benchmark.py.
"""
import argparse
import asyncio
import json
import time
import uuid

import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
from threading import Thread


app = FastAPI()
state = {"model": None, "tok": None, "device": None, "name": None}


@app.get("/health")
def health():
    return {"status": "ok"} if state["model"] is not None else JSONResponse(
        {"status": "loading"}, status_code=503
    )


@app.get("/v1/models")
def models():
    return {"data": [{"id": state["name"], "object": "model"}], "object": "list"}


def make_chunk(text, name, finish=None):
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": name,
        "choices": [{
            "index": 0,
            "delta": ({"content": text} if text else {}),
            "finish_reason": finish,
        }],
    }


@app.post("/v1/chat/completions")
async def chat(req: dict):
    messages = req.get("messages", [])
    max_new = int(req.get("max_tokens", 2048))
    temperature = float(req.get("temperature", 0.3))
    stream = bool(req.get("stream", False))

    tok = state["tok"]
    model = state["model"]
    device = state["device"]
    name = state["name"]

    prompt = tok.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tok(prompt, return_tensors="pt").to(device)
    prompt_len = inputs.input_ids.shape[1]

    gen_kwargs = dict(
        **inputs,
        max_new_tokens=max_new,
        do_sample=(temperature > 0),
        temperature=max(temperature, 1e-5),
        pad_token_id=tok.eos_token_id,
    )

    if stream:
        streamer = TextIteratorStreamer(
            tok, skip_prompt=True, skip_special_tokens=True
        )
        gen_kwargs["streamer"] = streamer
        thread = Thread(target=model.generate, kwargs=gen_kwargs)
        thread.start()

        async def gen():
            t0 = time.time()
            n_tokens = 0
            for piece in streamer:
                if not piece:
                    continue
                n_tokens += 1
                chunk = make_chunk(piece, name)
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
            final = make_chunk("", name, finish="stop")
            final["timings"] = {
                "predicted_n": n_tokens,
                "predicted_ms": (time.time() - t0) * 1000.0,
            }
            yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            thread.join()

        return StreamingResponse(gen(), media_type="text/event-stream")

    # non-stream
    t0 = time.time()
    with torch.inference_mode():
        out = model.generate(**gen_kwargs)
    new_tokens = out[0, prompt_len:]
    text = tok.decode(new_tokens, skip_special_tokens=True)
    elapsed_ms = (time.time() - t0) * 1000.0
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": name,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": int(prompt_len),
            "completion_tokens": int(new_tokens.shape[0]),
            "total_tokens": int(prompt_len + new_tokens.shape[0]),
        },
        "timings": {
            "predicted_n": int(new_tokens.shape[0]),
            "predicted_ms": elapsed_ms,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--served-model-name", required=True)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=11441)
    args = ap.parse_args()

    print(f"Loading {args.model_path} in bfloat16 ...", flush=True)
    tok = AutoTokenizer.from_pretrained(args.model_path)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        dtype=torch.bfloat16,
        device_map="cuda:0",
    )
    model.eval()
    state["model"] = model
    state["tok"] = tok
    state["device"] = "cuda:0"
    state["name"] = args.served_model_name
    print("Loaded. Starting server.", flush=True)

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
