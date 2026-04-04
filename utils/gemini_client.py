"""Google Gemini Generative Language API (used via utils.llm_client)."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()


def _endpoint(model: str) -> str:
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def gemini_key_configured() -> bool:
    return bool(GEMINI_API_KEY)


async def gemini_generate_content(
    prompt: str,
    *,
    system_instruction: str | None = None,
    temperature: float = 0.55,
    max_output_tokens: int = 2048,
    response_mime_type: str | None = None,
    response_json_schema: dict[str, Any] | None = None,
) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to your environment to use Gemini, or set GROQ_API_KEY for Groq."
        )

    parts: list[dict] = []
    if system_instruction:
        parts.append({"text": system_instruction})
    parts.append({"text": prompt})

    gen_cfg: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    if response_mime_type:
        gen_cfg["responseMimeType"] = response_mime_type
    if response_json_schema is not None:
        gen_cfg["responseJsonSchema"] = response_json_schema
        if "responseMimeType" not in gen_cfg:
            gen_cfg["responseMimeType"] = "application/json"

    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": gen_cfg,
    }

    url = f"{_endpoint(GEMINI_MODEL)}?key={GEMINI_API_KEY}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=body)
        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Gemini non-JSON response ({resp.status_code}): {resp.text[:500]}") from exc

        if resp.status_code != 200:
            err = data.get("error", {})
            msg = err.get("message", str(data)[:500])
            raise RuntimeError(f"Gemini API error ({resp.status_code}): {msg}")

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Gemini response: {json.dumps(data)[:800]}") from exc
