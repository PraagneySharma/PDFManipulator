"""Optional user-funded natural-language translator.

Only prompt text and generated input aliases are transmitted; PDF bytes are
NEVER sent. The model outputs JSON, which goes through strict engine validation.
"""
from __future__ import annotations
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .engine import WorkflowError, validate_steps
from .parser import interpret

SYSTEM_PROMPT = """Translate the user's PDF instruction into a JSON object with a 'steps' array.
No code, no markdown, no comments. A step is an object with 'op' and parameters.
Allowed operations: load(source), load_each(sources), merge(sources),
duplex(fronts,backs,reverse_backs,rotate_backs,skip_first_back),
interleave(sources,reverse_second), split_every(n),
split_ranges(ranges,include_remaining), extract(pages), delete(pages),
reorder(order), reverse(), rotate(pages,degrees), duplicate(pages,times),
remove_blanks(threshold).
First step must load/merge/duplex/interleave/load_each. Use 1-based page
numbers and selections like '1,3,5-7' or 'even', 'odd', 'all'. If the user
asks to rotate all even pages, choose pages='even'. For multiple input files
use their exact aliases (input1, input2, etc). Do not invent source paths.
If ambiguous, use conservative simple steps. Never delete a source file,
execute code, or attempt to include paths or URLs. Return ONLY JSON."""

def _post(url: str, payload: dict, headers: dict[str, str]) -> dict:
    req = Request(url, data=json.dumps(payload).encode("utf-8"),
                  headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urlopen(req, timeout=35) as result:
            data = result.read(200_000)
        return json.loads(data)
    except HTTPError as exc:
        # Do not echo provider response bodies; they may contain sensitive data.
        raise WorkflowError(f"AI provider request failed (HTTP {exc.code}). Check your API key, billing, and model.") from exc
    except (URLError, TimeoutError) as exc:
        raise WorkflowError(f"AI provider could not be reached: {exc.reason if isinstance(exc, URLError) else 'timeout'}") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise WorkflowError("AI provider returned an invalid response.") from exc

def translate(prompt: str, aliases: list[str], provider: str = "offline", *, consent: bool = False, model: str | None = None) -> list[dict]:
    if provider == "offline":
        return interpret(prompt, aliases)
    if not consent:
        raise WorkflowError("Confirm permission before sending a prompt to an AI provider.")
    if len(prompt) > 2000 or not prompt.strip():
        raise WorkflowError("Prompt must be 1–2,000 characters.")
    if not aliases or len(aliases) > 30 or any(not a.startswith("input") or not a[5:].isdigit() for a in aliases):
        raise WorkflowError("Provide valid input aliases.")
    user = json.dumps({"request": prompt, "available_inputs": aliases})
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise WorkflowError("Set OPENAI_API_KEY in your environment. ChatGPT subscriptions do not supply API keys.")
        body = {"model": model or "gpt-4.1-mini", "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": user}]}
        result = _post("https://api.openai.com/v1/chat/completions", body, {"Authorization": "Bearer " + key})
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise WorkflowError("OpenAI response had no workflow.") from exc
    elif provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise WorkflowError("Set ANTHROPIC_API_KEY in your environment. Claude subscriptions are separate from API billing.")
        body = {"model": model or "claude-sonnet-4-5", "max_tokens": 1600,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user}]}
        result = _post("https://api.anthropic.com/v1/messages", body,
                       {"x-api-key": key, "anthropic-version": "2023-06-01"})
        try:
            content = "".join(x["text"] for x in result["content"] if x["type"] == "text")
        except (KeyError, IndexError, TypeError) as exc:
            raise WorkflowError("Anthropic response had no workflow.") from exc
    elif provider == "ollama":
        body = {"model": model or "llama3.2", "stream": False, "format": "json",
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": user}]}
        result = _post("http://127.0.0.1:11434/api/chat", body, {})
        try:
            content = result["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise WorkflowError("Local Ollama model returned no workflow.") from exc
    else:
        raise WorkflowError(f"Unsupported AI provider: {provider}")
    return parse_model_steps(content, aliases)


def parse_model_steps(content: str, aliases: list[str]) -> list[dict]:
    """Validate provider output before any local file operation is possible."""
    try:
        data = json.loads(content)
        steps = validate_steps(data["steps"])
        for step in steps:
            for key in ("source", "fronts", "backs"):
                if key in step and step[key] not in aliases:
                    raise WorkflowError(f"AI referred to an unknown input: {step[key]}")
            for alias in step.get("sources", []):
                if alias not in aliases:
                    raise WorkflowError(f"AI referred to an unknown input: {alias}")
        return steps
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        if isinstance(exc, WorkflowError):
            raise
        raise WorkflowError("AI produced an invalid workflow. Edit the prompt or use a manual preset.") from exc
