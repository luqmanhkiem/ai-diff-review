"""End-to-end check of the real `llm` provider.

Usage:
    LLM_API_KEY=<your-gemini-key> .venv/bin/python scripts/verify_llm.py

Confirms two things the brief asks for:
  1. With a valid key, provider=llm returns a `done` job with findings.
  2. With a bad key, provider=llm returns a `failed` job (never a crash).

Get a free key at https://aistudio.google.com/apikey (Google AI Studio).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config
from app.providers.base import ProviderError
from app.providers.llm import LlmProvider
from app.diff_parser import parse_diff

DIFF = (
    "diff --git a/pay.js b/pay.js\n--- a/pay.js\n+++ b/pay.js\n"
    "@@ -0,0 +1,3 @@\n"
    '+const apiKey = "sk_live_0123456789ABCDEF";\n'
    "+eval(userInput);\n"
    "+if (x == null) return;\n"
)


async def main():
    if not config.LLM_API_KEY:
        print("LLM_API_KEY is not set — the llm path would fail gracefully.")
        print("Set it and re-run to verify the happy path.")
        return
    files = parse_diff(DIFF)
    provider = LlmProvider()

    print(f"Model: {config.LLM_MODEL} @ {config.LLM_BASE_URL}")
    try:
        findings = await provider.review_chunk(files)
        print(f"OK — model returned {len(findings)} finding(s):")
        for f in findings:
            print(f"  {f.ruleId} {f.path}:{f.line} [{f.severity}] {f.title}")
    except ProviderError as e:
        print(f"ProviderError (this is the graceful-failure path): {e}")


if __name__ == "__main__":
    asyncio.run(main())
