"""One way to call an LLM for structured JSON, shared by the report writer and draft-traits.

An `Ask` takes (system prompt, user prompt) and returns (JSON text, (input tokens, output
tokens)). Two providers: the Anthropic API (structured output) and a local Ollama model (JSON
schema output). No temperature is sent (docs/REPORT_AGENT.md, Model notes). Tests pass fakes.
"""

from collections.abc import Callable
from typing import Any

Ask = Callable[[str, str], tuple[str, tuple[int, int]]]


class LlmError(Exception):
    """The call failed; the message says why in plain words."""


def anthropic_ask(
    model: str, api_key: str, schema: dict[str, Any], max_tokens: int, timeout_s: float = 30.0
) -> Ask:
    import anthropic  # imported here so the rest of the app never needs it

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=1)

    def ask(system: str, prompt: str) -> tuple[str, tuple[int, int]]:
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.AuthenticationError:
            raise LlmError("Anthropic rejected the API key in .env (ANTHROPIC_API_KEY).") from None
        except anthropic.PermissionDeniedError:
            raise LlmError("Anthropic refused the request (check the key's permissions).") from None
        except anthropic.RateLimitError:
            raise LlmError("Anthropic rate limit hit; wait a minute.") from None
        except anthropic.APITimeoutError:
            raise LlmError("Anthropic took too long to answer.") from None
        except anthropic.APIStatusError as exc:
            if exc.status_code == 400 and "credit" in str(exc.message).lower():
                raise LlmError("The Anthropic account is out of credit.") from None
            raise LlmError(f"Anthropic API error {exc.status_code}: {exc.message}") from None
        except anthropic.APIConnectionError:
            raise LlmError("Couldn't reach the Anthropic API (network).") from None
        if response.stop_reason in ("refusal", "max_tokens"):
            raise LlmError(f"the model stopped early ({response.stop_reason})")
        text = next((block.text for block in response.content if block.type == "text"), "")
        return text, (response.usage.input_tokens, response.usage.output_tokens)

    return ask


def ollama_ask(
    model: str, schema: dict[str, Any], base_url: str = "http://localhost:11434",
    timeout_s: float = 60.0, transport: Any = None,
) -> Ask:  # fmt: skip
    """A local model through Ollama's chat API, with the JSON schema as the output format."""
    import httpx

    client = httpx.Client(base_url=base_url, timeout=timeout_s, transport=transport,
                          trust_env=False)  # fmt: skip

    def ask(system: str, prompt: str) -> tuple[str, tuple[int, int]]:
        body = {
            "model": model, "stream": False, "format": schema,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
        }  # fmt: skip
        try:
            response = client.post("/api/chat", json=body)  # Ollama runs locally; not the LCU
        except httpx.HTTPError as exc:
            raise LlmError(f"Couldn't reach Ollama at {base_url}: {exc}") from None
        if response.is_error:
            raise LlmError(f"Ollama error {response.status_code}: {response.text[:200]}")
        data = response.json()
        text = (data.get("message") or {}).get("content", "")
        return text, (int(data.get("prompt_eval_count") or 0), int(data.get("eval_count") or 0))

    return ask
