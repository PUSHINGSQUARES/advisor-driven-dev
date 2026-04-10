#!/usr/bin/env python3
"""
ask.py — Multi-provider LLM CLI for Claude Code advisor-driven development.

Usage:
    python3 ask.py --model haiku "prompt here"
    python3 ask.py --model kimi "prompt here"
    python3 ask.py --model gemini "prompt here"
    python3 ask.py --model minimax "prompt here"
    python3 ask.py --model sonnet --system "You are a test writer." "prompt here"
    echo "prompt" | python3 ask.py --model haiku --stdin
    python3 ask.py --model gemini --video clip.mp4 "Describe what happens in this video"
    python3 ask.py --model kimi-think "complex reasoning task"
    python3 ask.py --model kimi-agent "research task requiring tool use"
    python3 ask.py --model kimi-swarm "complex multi-step task needing parallel agents"
    python3 ask.py --model gemma "prompt here"              # local, free, no API key

Reads API keys from macOS Keychain (or env vars — see get_key()).
Prints the response to stdout. Errors go to stderr.
No external dependencies — stdlib only.

Designed to be called from Claude Code sessions as a cheap executor:
  Opus (orchestrator) plans -> dispatches work via ask.py -> reads response.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# --- Key Storage ---
#
# Default: macOS Keychain. Change KEYCHAIN_SERVICE to your own service name,
# or replace get_key() entirely with env var reads (see README).

KEYCHAIN_SERVICE = "com.your-project.keys"  # <-- change this
KEYCHAIN_ACCOUNTS = {
    "anthropic": "apiKey_anthropic",
    "moonshot":  "apiKey_moonshot",
    "google":    "apiKey_gemini",
    "minimax":   "apiKey_minimax",
}

def get_key(provider: str) -> str:
    """Read API key from macOS Keychain. Replace with env vars if not on macOS."""
    # --- Option A: macOS Keychain (default) ---
    account = KEYCHAIN_ACCOUNTS.get(provider)
    if not account:
        print(f"Unknown provider: {provider}", file=sys.stderr)
        sys.exit(1)
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"Keychain lookup failed for {account}: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f"Keychain lookup timed out for {account}", file=sys.stderr)
        sys.exit(1)

    # --- Option B: Environment variables (uncomment to use instead) ---
    # env_map = {
    #     "anthropic": "ANTHROPIC_API_KEY",
    #     "moonshot": "MOONSHOT_API_KEY",
    #     "google": "GEMINI_API_KEY",
    #     "minimax": "MINIMAX_API_KEY",
    # }
    # key = os.environ.get(env_map.get(provider, ""))
    # if not key:
    #     print(f"Missing env var for {provider}", file=sys.stderr)
    #     sys.exit(1)
    # return key


# --- Model Registry ---

MODELS = {
    # Anthropic
    "haiku":   {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001",  "thinking": False},
    "sonnet":  {"provider": "anthropic", "model_id": "claude-sonnet-4-6",          "thinking": True, "budget": 10000},
    "opus":    {"provider": "anthropic", "model_id": "claude-opus-4-6",            "thinking": True, "budget": 16000},
    # Moonshot (Kimi) — four modes
    "kimi":       {"provider": "moonshot",  "model_id": "kimi-k2.5"},
    "kimi-think": {"provider": "moonshot",  "model_id": "kimi-k2.5",  "kimi_mode": "thinking"},
    "kimi-agent": {"provider": "moonshot",  "model_id": "kimi-k2.5",  "kimi_mode": "agent"},
    "kimi-swarm": {"provider": "moonshot",  "model_id": "kimi-k2.5",  "kimi_mode": "agent_swarm"},
    # Google (Gemini)
    "gemini":  {"provider": "google",    "model_id": "gemini-3.1-pro-preview"},
    # MiniMax
    "minimax": {"provider": "minimax",   "model_id": "MiniMax-M2.5"},
    # Local (Ollama) — free, no API key
    "gemma":       {"provider": "ollama", "model_id": "gemma4"},
    "gemma-small": {"provider": "ollama", "model_id": "gemma3:4b"},
}


# --- API Callers ---

def call_anthropic(api_key: str, model_id: str, messages: list, system: str | None,
                   thinking: bool = False, budget: int = 10000) -> str:
    body: dict = {
        "model": model_id,
        "messages": messages,
    }
    if system:
        body["system"] = system
    if thinking:
        body["max_tokens"] = budget + 8192
        body["thinking"] = {"type": "enabled", "budget_tokens": budget}
    else:
        body["max_tokens"] = 8192

    data = json.dumps(body).encode()
    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())

    parts = []
    for block in result.get("content", []):
        if block.get("type") == "text":
            parts.append(block["text"])
    return "\n".join(parts) or "(empty response)"


def call_openai_compat(api_key: str, model_id: str, messages: list, system: str | None,
                       base_url: str, kimi_mode: str | None = None) -> str:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)

    body: dict = {
        "model": model_id,
        "messages": msgs,
        "max_tokens": 8192,
    }

    # Kimi mode selection (thinking, agent, agent_swarm)
    if kimi_mode:
        body["mode"] = kimi_mode
        if kimi_mode == "agent_swarm":
            body["max_tokens"] = 16384

    data = json.dumps(body).encode()
    timeout = 600 if kimi_mode in ("agent", "agent_swarm") else 300

    req = Request(
        f"{base_url}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read())

    return result["choices"][0]["message"]["content"]


def call_google(api_key: str, model_id: str, messages: list, system: str | None) -> str:
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    body: dict = {"contents": contents}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    data = json.dumps(body).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    req = Request(url, data=data, headers={"Content-Type": "application/json"})

    with urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())

    candidates = result.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts) or "(empty response)"
    return "(no candidates returned)"


def call_ollama(model_id: str, messages: list, system: str | None) -> str:
    """Call local Ollama instance. Free, no API key needed."""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)

    body = {
        "model": model_id,
        "messages": msgs,
        "stream": False,
    }

    data = json.dumps(body).encode()
    req = Request(
        "http://localhost:11434/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=600) as resp:
        result = json.loads(resp.read())

    return result.get("message", {}).get("content", "(empty response)")


OPENAI_ENDPOINTS = {
    "moonshot": "https://api.moonshot.cn/v1",
    "minimax":  "https://api.minimax.io/v1",
}


def call_google_video(api_key: str, model_id: str, video_path: str, prompt: str,
                      system: str | None) -> str:
    """Upload video to Gemini Files API, then analyze it."""
    import mimetypes
    import time

    path = os.path.expanduser(video_path)
    if not os.path.isfile(path):
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    mime_type = mimetypes.guess_type(path)[0] or "video/mp4"
    file_size = os.path.getsize(path)

    # Step 1: Start resumable upload
    metadata = json.dumps({"file": {"display_name": os.path.basename(path)}}).encode()
    start_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
    start_req = Request(start_url, data=metadata, method="POST", headers={
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json",
    })
    with urlopen(start_req, timeout=60) as resp:
        upload_url = resp.headers["X-Goog-Upload-URL"]

    # Step 2: Upload the file bytes
    with open(path, "rb") as f:
        file_data = f.read()

    upload_req = Request(upload_url, data=file_data, method="PUT", headers={
        "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize",
        "Content-Length": str(file_size),
    })
    with urlopen(upload_req, timeout=600) as resp:
        upload_result = json.loads(resp.read())

    file_uri = upload_result["file"]["uri"]
    file_name = upload_result["file"]["name"]

    # Step 3: Poll until processing is complete
    for _ in range(120):  # up to 10 minutes
        status_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
        status_req = Request(status_url)
        with urlopen(status_req, timeout=30) as resp:
            status = json.loads(resp.read())
        state = status.get("state", "")
        if state == "ACTIVE":
            break
        elif state == "FAILED":
            print(f"Video processing failed: {status}", file=sys.stderr)
            sys.exit(1)
        time.sleep(5)
    else:
        print("Video processing timed out", file=sys.stderr)
        sys.exit(1)

    # Step 4: Generate content with the video
    body: dict = {
        "contents": [{
            "parts": [
                {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                {"text": prompt},
            ]
        }]
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
    gen_req = Request(gen_url, data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"})
    with urlopen(gen_req, timeout=300) as resp:
        result = json.loads(resp.read())

    # Step 5: Clean up uploaded file
    try:
        del_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
        del_req = Request(del_url, method="DELETE")
        urlopen(del_req, timeout=10)
    except Exception:
        pass  # best effort cleanup

    candidates = result.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts) or "(empty response)"
    return "(no candidates returned)"


def call_model(model_name: str, prompt: str, system: str | None,
               video: str | None = None) -> str:
    config = MODELS[model_name]
    provider = config["provider"]
    model_id = config["model_id"]
    api_key = get_key(provider) if provider != "ollama" else None
    messages = [{"role": "user", "content": prompt}]

    # Video analysis — route to Gemini
    if video:
        if provider != "google":
            print(f"Video analysis only supported with Gemini models, not {model_name}", file=sys.stderr)
            sys.exit(1)
        return call_google_video(api_key, model_id, video, prompt, system)

    if provider == "ollama":
        return call_ollama(model_id, messages, system)
    elif provider == "anthropic":
        return call_anthropic(
            api_key, model_id, messages, system,
            thinking=config.get("thinking", False),
            budget=config.get("budget", 10000),
        )
    elif provider == "google":
        return call_google(api_key, model_id, messages, system)
    elif provider in OPENAI_ENDPOINTS:
        return call_openai_compat(api_key, model_id, messages, system, OPENAI_ENDPOINTS[provider],
                                  kimi_mode=config.get("kimi_mode"))
    else:
        print(f"No caller for provider: {provider}", file=sys.stderr)
        sys.exit(1)


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Ask any LLM a question. Keys from macOS Keychain or env vars.",
        epilog="Models: " + ", ".join(MODELS.keys()),
    )
    parser.add_argument("--model", "-m", required=True, choices=list(MODELS.keys()),
                        help="Model to use")
    parser.add_argument("--system", "-s", default=None,
                        help="System prompt (optional)")
    parser.add_argument("--video", "-v", default=None,
                        help="Path to video file (Gemini only -- uploads and analyzes)")
    parser.add_argument("--stdin", action="store_true",
                        help="Read prompt from stdin instead of positional arg")
    parser.add_argument("prompt", nargs="?", default=None,
                        help="The prompt to send")

    args = parser.parse_args()

    if args.stdin:
        prompt = sys.stdin.read().strip()
    elif args.prompt:
        prompt = args.prompt
    else:
        parser.error("Provide a prompt as argument or use --stdin")

    if not prompt:
        parser.error("Empty prompt")

    try:
        response = call_model(args.model, prompt, args.system, video=args.video)
        print(response)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
