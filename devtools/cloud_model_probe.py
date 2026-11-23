"""Verify one synthetic function call through the actual harness client."""

import asyncio
import re

from skillkit.model import from_env


TOOLS = [{
    "name": "hello",
    "description": "Look up a greeting for a person",
    "parameters": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
}]


async def main():
    model = from_env()
    model.max_tokens = 512
    model.reasoning_effort = "low"
    try:
        async with asyncio.timeout(120):
            result = await model.chat(
                [{"role": "user", "content": "Call the hello tool with the name Ada."}],
                "Use exactly the requested function when it is available.",
                tools=TOOLS,
            )
    except TimeoutError:
        raise SystemExit(f"Model probe {model.model} timed out.") from None
    except Exception as exc:
        status = re.search(r"(?:HTTP\s+|retries:\s*)([45]\d{2})\b", str(exc))
        reason = f"HTTP {status.group(1)}" if status else type(exc).__name__
        raise SystemExit(f"Model probe {model.model} failed ({reason}).") from None

    if not any(call["name"] == "hello" and call["arguments"] == {"name": "Ada"}
               for call in result["tool_calls"]):
        raise SystemExit(f"Model probe {model.model} did not return the expected function call.")
    print(f"Model probe {model.model} passed.")


if __name__ == "__main__":
    asyncio.run(main())
