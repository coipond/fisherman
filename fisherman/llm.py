"""A small client for a llama.cpp server (llama-server), using its native endpoints.

Prompts use the ChatML format (Qwen and most current open models). Reasoning models that
use <think> blocks run with an empty think block for fast answers, or with reasoning on.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


class LLMError(Exception):
    pass


class Llama:
    def __init__(self, url: str, key: Optional[str] = None, timeout: int = 900, retries: int = 3):
        self.url = url.rstrip("/")
        self.headers = {"Content-Type": "application/json"}
        if key:
            self.headers["Authorization"] = "Bearer " + key
        self.timeout = timeout
        self.retries = retries

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "Llama":
        key = cfg.get("key")
        if cfg.get("key_file"):
            key = Path(cfg["key_file"]).expanduser().read_text().strip()
        return cls(cfg.get("url", "http://127.0.0.1:8088"), key, int(cfg.get("timeout", 900)))

    def post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(body).encode()
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(self.url + path, data, self.headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code in (400, 401, 403, 404, 501):
                    raise LLMError(f"{path}: HTTP {e.code}") from e
                err: Exception = e
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                err = e
            time.sleep(5 * (attempt + 1))
        raise LLMError(f"{path}: {err}")

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=10) as r:
                return json.load(r).get("status") == "ok"
        except Exception:
            return False

    def tokenize(self, text: str) -> List[int]:
        return self.post("/tokenize", {"content": text})["tokens"]

    def detokenize(self, tokens: List[int]) -> str:
        return self.post("/detokenize", {"tokens": tokens})["content"]

    def truncate(self, text: str, max_tokens: int) -> str:
        ids = self.tokenize(text)
        return text if len(ids) <= max_tokens else self.detokenize(ids[:max_tokens])

    @staticmethod
    def chat_prompt(system: str, user: str, think: bool = False) -> str:
        prompt = f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
        return prompt if think else prompt + "<think>\n\n</think>\n\n"

    def complete(self, prompt: str, n_predict: int, **extra: Any) -> Dict[str, Any]:
        body = {"prompt": prompt, "n_predict": n_predict, "temperature": 0, "cache_prompt": True, "stop": ["<|im_end|>"]}
        body.update(extra)
        return self.post("/completion", body)

    def chat(self, system: str, user: str, n_predict: int, think: bool = False, **extra: Any) -> str:
        """The answer text; with think=True the reasoning is dropped."""
        text = self.complete(self.chat_prompt(system, user, think), n_predict, **extra)["content"]
        return text.split("</think>")[-1].strip() if think else text.strip()

    def p_yes(self, system: str, user: str) -> float:
        """Probability of "yes" over "no" for the first answer token."""
        r = self.complete(self.chat_prompt(system, user), 1, n_probs=50)
        top = r["completion_probabilities"][0]["top_logprobs"]
        yes = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "yes")
        no = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "no")
        return yes / (yes + no) if yes + no else 0.5
