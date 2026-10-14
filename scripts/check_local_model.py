"""Fail early if the workflow's local Ollama model is unavailable."""
import json
import os
from urllib.request import urlopen

base = os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')
model = os.environ.get('OLLAMA_MODEL', 'qwen2.5:3b')
try:
    with urlopen(base + '/api/tags', timeout=10) as response:
        models = json.load(response)['models']
except Exception as exc:
    raise SystemExit(f'Ollama is unavailable at {base}. Start the Ollama app before running Actions.') from exc
names = {m['name'] for m in models}
if model not in names and model + ':latest' not in names:
    raise SystemExit(f'Model {model} is missing. Run: ollama pull {model}')
print(f'Local Ollama ready: {model}')
