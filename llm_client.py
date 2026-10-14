"""Shared JSON generation for local Ollama and optional Gemini."""
import json
import os
import requests


def provider_name():
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if not provider:
        provider = "gemini" if os.getenv("GEMINI_API_KEY") else "ollama"
    if provider not in {"ollama", "gemini"}:
        raise ValueError("LLM_PROVIDER must be ollama or gemini")
    return provider


def generate_json(prompt):
    provider = provider_name()
    if provider == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        try:
            response = requests.post(
                f"{base}/api/generate",
                json={"model": model, "prompt": prompt, "format": "json", "stream": False},
                timeout=(10, float(os.getenv("LLM_TIMEOUT", "300"))),
            )
            response.raise_for_status()
            raw = response.json()["response"]
        except (requests.RequestException, KeyError, ValueError) as exc:
            raise RuntimeError(
                f"Ollama generation failed at {base} using {model}. "
                "Start Ollama and pull the configured model."
            ) from exc
    else:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is required for LLM_PROVIDER=gemini")
        from google import genai
        response = genai.Client(api_key=key).models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), contents=prompt,
        )
        raw = response.text or ""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM must return a JSON object")
    return data
