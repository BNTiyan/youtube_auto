"""Provider contract tests; no running model or API credentials needed."""
import importlib
import json
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

# Permit running this contract test before project dependencies are installed.
try:
    import requests
except ImportError:
    requests = types.ModuleType("requests")
    requests.RequestException = type("RequestException", (Exception,), {})
    requests.post = Mock()
    sys.modules["requests"] = requests

import llm_client


class LocalLLMTests(unittest.TestCase):
    def test_local_default_and_request_contract(self):
        response = Mock()
        response.json.return_value = {"response": json.dumps({"title": "Example"})}
        with patch.dict(os.environ, {}, clear=True), patch.object(requests, "post", return_value=response) as post:
            self.assertEqual(llm_client.generate_json("Return JSON"), {"title": "Example"})
            self.assertEqual(post.call_args.args[0], "http://localhost:11434/api/generate")
            self.assertEqual(post.call_args.kwargs["json"]["stream"], False)
            response.raise_for_status.assert_called_once()

    def test_explicit_local_never_calls_gemini(self):
        response = Mock()
        response.json.return_value = {"response": '```json\n{"ok": true}\n```'}
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "GEMINI_API_KEY": "unused", "OLLAMA_MODEL": "custom"}), patch.object(requests, "post", return_value=response) as post:
            self.assertEqual(llm_client.generate_json("JSON"), {"ok": True})
            self.assertEqual(post.call_args.kwargs["json"]["model"], "custom")

    def test_connection_failure_is_actionable(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}), patch.object(requests, "post", side_effect=requests.RequestException):
            with self.assertRaisesRegex(RuntimeError, "Start Ollama"):
                llm_client.generate_json("JSON")

    def test_reject_non_object(self):
        response = Mock()
        response.json.return_value = {"response": '[]'}
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}), patch.object(requests, "post", return_value=response):
            with self.assertRaisesRegex(ValueError, "JSON object"):
                llm_client.generate_json("JSON")

    def test_invalid_provider(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "typo"}):
            with self.assertRaises(ValueError):
                llm_client.provider_name()


if __name__ == "__main__":
    unittest.main()
