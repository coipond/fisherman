"""Client for a llama.cpp server (`llama-server`) through its native endpoints.

Prompts use the ChatML format (Qwen and most current open models). Models with `<think>` blocks
answer with an empty think block for fast answers, or reason first when asked to.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fisherman.contracts import Contract, is_int_at_least, is_string, is_url
from fisherman.errors import ModelError

# HTTP statuses that will not change on retry
_FINAL_STATUSES = (400, 401, 403, 404, 501)


class Llama:
    """A llama-server client."""

    #: Contract for the "model" configuration section
    CONTRACT = (
        Contract()
        .optional("url", is_url, "must be an http(s) URL")
        .optional("key_file", is_string, "must be a path")
        .optional("timeout", is_int_at_least(1), "must be an integer >= 1")
    )

    def __init__(
        self,
        url: str = "http://127.0.0.1:8088",
        key: str | None = None,
        timeout: int = 900,
        retries: int = 3,
    ) -> None:
        """Create a client.

        Args:
            url: Base URL of the server.
            key: API key, if the server was started with `--api-key` or `--api-key-file`.
            timeout: Seconds to wait for one request.
            retries: Attempts per request on network errors and server errors.

        """
        self.url = url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        if key:
            self._headers["Authorization"] = "Bearer " + key
        self._timeout = timeout
        self._retries = retries

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> Llama:
        """Build a client from the "model" configuration section.

        Args:
            cfg: The section: url, key_file, timeout.

        Returns:
            A configured client.

        """
        key = (
            Path(cfg["key_file"]).expanduser().read_text().strip() if cfg.get("key_file") else None
        )
        return cls(cfg.get("url", "http://127.0.0.1:8088"), key, int(cfg.get("timeout", 900)))

    def health(self) -> bool:
        """Check whether the server is up and has a model loaded.

        Returns:
            True when /health answers "ok".

        """
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=10) as response:  # noqa: S310 - configured URL
                return bool(json.load(response).get("status") == "ok")
        except (OSError, ValueError):
            return False

    def tokenize(self, text: str) -> list[int]:
        """Tokenize text with the server's model.

        Args:
            text: Text to tokenize.

        Returns:
            Token ids.

        """
        return list(self._post("/tokenize", {"content": text})["tokens"])

    def detokenize(self, tokens: list[int]) -> str:
        """Turn token ids back into text.

        Args:
            tokens: Token ids.

        Returns:
            The text.

        """
        return str(self._post("/detokenize", {"tokens": tokens})["content"])

    def truncate(self, text: str, max_tokens: int) -> str:
        """Cut text to at most `max_tokens` tokens.

        Args:
            text: Text to cut.
            max_tokens: Token budget.

        Returns:
            The text, or its beginning.

        """
        ids = self.tokenize(text)
        return text if len(ids) <= max_tokens else self.detokenize(ids[:max_tokens])

    def chat(
        self, system: str, user: str, n_predict: int, *, think: bool = False, **extra: Any
    ) -> str:
        """Ask the model and return its answer.

        Args:
            system: System prompt.
            user: User message.
            n_predict: Maximum tokens to generate, reasoning included.
            think: Let the model reason first. The reasoning is dropped from the answer.
            **extra: Additional /completion options, for example `json_schema`.

        Returns:
            The answer text.

        """
        text = str(
            self._complete(self.prompt(system, user, think=think), n_predict, **extra)["content"]
        )
        return text.rsplit("</think>", maxsplit=1)[-1].strip() if think else text.strip()

    def p_yes(self, system: str, user: str) -> float:
        """Probability that the model answers "yes" rather than "no".

        Args:
            system: System prompt that asks for a one-word yes/no answer.
            user: User message.

        Returns:
            P(yes) / (P(yes) + P(no)) for the first answer token, 0.5 when neither is likely.

        """
        response = self._complete(self.prompt(system, user), 1, n_probs=50)
        top = response["completion_probabilities"][0]["top_logprobs"]
        yes = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "yes")
        no = sum(math.exp(t["logprob"]) for t in top if t["token"].strip().lower() == "no")
        return yes / (yes + no) if yes + no else 0.5

    @staticmethod
    def prompt(system: str, user: str, *, think: bool = False) -> str:
        """Build a ChatML prompt.

        Args:
            system: System prompt.
            user: User message.
            think: Leave the think block open for the model to reason. When False, an empty
                think block is prefilled so the model answers directly.

        Returns:
            The prompt text.

        """
        head = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
        )
        return head if think else head + "<think>\n\n</think>\n\n"

    def _complete(self, prompt: str, n_predict: int, **extra: Any) -> dict[str, Any]:
        body = {
            "prompt": prompt,
            "n_predict": n_predict,
            "temperature": 0,
            "cache_prompt": True,
            "stop": ["<|im_end|>"],
            **extra,
        }
        return self._post("/completion", body)

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode()
        error: Exception | None = None
        for attempt in range(self._retries):
            try:
                request = urllib.request.Request(self.url + path, data, self._headers)  # noqa: S310 - configured URL
                with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                    result: dict[str, Any] = json.load(response)
                    return result
            except urllib.error.HTTPError as e:
                if e.code in _FINAL_STATUSES:
                    msg = f"{path}: HTTP {e.code}"
                    raise ModelError(msg) from e
                error = e
            except OSError as e:
                error = e
            time.sleep(5 * (attempt + 1))
        msg = f"{path}: {error}"
        raise ModelError(msg)
