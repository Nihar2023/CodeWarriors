"""Unified LLM client: Groq (default when configured) or Google Gemini."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

import httpx

from utils.gemini_client import gemini_generate_content, gemini_key_configured

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


def strip_markdown_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _extract_balanced_json_object(s: str) -> str | None:
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(s)):
        c = s[i]
        if escape:
            escape = False
            continue
        if in_string:
            if c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def parse_json_from_llm(raw: str) -> Any:
    """Parse JSON from model output; handles fences and leading/trailing prose."""
    text = strip_markdown_json_fences(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        extracted = _extract_balanced_json_object(text)
        if extracted:
            return json.loads(extracted)
        raise


def _resolve_provider() -> Literal["groq", "gemini"] | None:
    explicit = os.getenv("AI_PROVIDER", "").strip().lower()
    has_groq = bool(GROQ_API_KEY)
    has_gemini = gemini_key_configured()

    if explicit == "groq":
        return "groq" if has_groq else None
    if explicit == "gemini":
        return "gemini" if has_gemini else None
    if has_groq:
        return "groq"
    if has_gemini:
        return "gemini"
    return None


def llm_configured() -> bool:
    return _resolve_provider() is not None


def active_llm_provider() -> Literal["groq", "gemini"] | None:
    """Which provider will handle the next request (same logic as generate_text)."""
    return _resolve_provider()


async def _groq_generate_content(
    prompt: str,
    *,
    system_instruction: str | None = None,
    temperature: float = 0.55,
    max_output_tokens: int = 2048,
    response_mime_type: str | None = None,
    response_json_schema: dict[str, Any] | None = None,
) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set.")

    messages: list[dict[str, str]] = []
    sys_parts: list[str] = []
    if system_instruction:
        sys_parts.append(system_instruction)
    want_json = response_mime_type == "application/json" or response_json_schema is not None
    if want_json:
        sys_parts.append(
            "You must output a single valid JSON value (object or array) only, with no markdown "
            "fences or other text."
        )
    if response_json_schema is not None:
        sys_parts.append("The JSON must conform to this schema:\n" + json.dumps(response_json_schema))
    if sys_parts:
        messages.append({"role": "system", "content": "\n\n".join(sys_parts)})
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
    }
    if want_json:
        body["response_format"] = {"type": "json_object"}

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(GROQ_CHAT_URL, json=body, headers=headers)
        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Groq non-JSON response ({resp.status_code}): {resp.text[:500]}") from exc

        if resp.status_code != 200:
            err = data.get("error", {})
            msg = err.get("message", str(data)[:500])
            raise RuntimeError(f"Groq API error ({resp.status_code}): {msg}")

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected Groq response: {json.dumps(data)[:800]}") from exc


async def generate_text(
    prompt: str,
    *,
    system_instruction: str | None = None,
    temperature: float = 0.55,
    max_output_tokens: int = 2048,
    response_mime_type: str | None = None,
    response_json_schema: dict[str, Any] | None = None,
) -> str:
    provider = _resolve_provider()
    if provider is None:
        raise RuntimeError(
            "No LLM configured. Set GROQ_API_KEY (recommended free tier) and/or GEMINI_API_KEY in `.env`. "
            "Optional: AI_PROVIDER=groq or AI_PROVIDER=gemini to force one provider."
        )

    if provider == "groq":
        return await _groq_generate_content(
            prompt,
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type=response_mime_type,
            response_json_schema=response_json_schema,
        )

    return await gemini_generate_content(
        prompt,
        system_instruction=system_instruction,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type=response_mime_type,
        response_json_schema=response_json_schema,
    )


async def generate_json_array_or_object(prompt: str, *, system_instruction: str | None = None) -> Any:
    raw = await generate_text(
        prompt + "\n\nRespond with valid JSON only (no markdown fences).",
        system_instruction=system_instruction,
        temperature=0.35,
        response_mime_type="application/json",
    )
    return parse_json_from_llm(raw)
