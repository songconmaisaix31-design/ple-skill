"""Recognize a llama.cpp prompt overflow and restart from the original task."""

import json


def is_context_rejection(error):
    """Match the structured HTTP error surfaced by ModelClient for llama.cpp b12651."""
    if not isinstance(error, RuntimeError):
        return False
    prefix = "HTTP 400: "
    text = str(error)
    if not text.startswith(prefix):
        return False
    try:
        body = json.loads(text[len(prefix):])
    except ValueError:
        return False
    detail = body.get("error") if isinstance(body, dict) else None
    if not isinstance(detail, dict) or detail.get("type") != "exceed_context_size_error":
        return False
    prompt = detail.get("n_prompt_tokens")
    window = detail.get("n_ctx")
    return (detail.get("code") == 400 and type(prompt) is int and type(window) is int
            and prompt >= window > 0)


def fresh_messages(instruction):
    """Start a valid new conversation with a fixed-size addition to the full task."""
    return [{"role": "user", "content": (
        "Task instruction:\n\n" + instruction
        + "\n\nThe previous conversation reached its context limit. Inspect the current "
          "workspace for saved work and read the inputs you still need. Check the current "
          "state before repeating any actions. Use tools to complete and verify the requested "
          "deliverable, then call finish. Keep tool output short."
    )}]
