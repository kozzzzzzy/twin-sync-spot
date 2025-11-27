"""Gemini API client for TwinSync Spot.

Uses Google's Gemini 2.0 Flash model to compare photos
against the user's definition of their spot's Ready State.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import aiohttp

from .const import GEMINI_MODEL, GEMINI_API_BASE

_LOGGER = logging.getLogger(__name__)


class GeminiClientError(Exception):
    """Raised when Gemini API fails."""


class GeminiClient:
    """Client for Gemini API with vision capabilities."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def analyze_spot(
        self,
        session: aiohttp.ClientSession,
        image_bytes: bytes,
        spot_name: str,
        definition: str,
        voice_prompt: str,
        memory_context: str,
    ) -> dict[str, Any]:
        """
        Analyze spot image against user's definition.

        Returns dict with:
        - status: "sorted" or "needs_attention"
        - to_sort: list of items not matching definition
        - looking_good: list of items matching definition
        - notes: dict with main/pattern/encouragement
        """
        start_time = time.time()

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        prompt = self._build_prompt(spot_name, definition, voice_prompt, memory_context)

        url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent"

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_b64,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.4,
                "topK": 32,
                "topP": 1,
                "maxOutputTokens": 2048,
            },
        }

        try:
            async with session.post(url, headers=headers, json=payload, timeout=90) as resp:
                if resp.status == 429:
                    text = await resp.text()
                    _LOGGER.warning("Gemini quota exceeded: %s", text[:500])
                    raise GeminiClientError(
                        "Gemini API quota exceeded. Try again later."
                    )
                if resp.status != 200:
                    text = await resp.text()
                    raise GeminiClientError(f"Gemini API HTTP {resp.status}: {text}")

                data = await resp.json()
        except aiohttp.ClientError as err:
            raise GeminiClientError(f"Network error: {err}") from err
        except GeminiClientError:
            raise
        except Exception as err:
            raise GeminiClientError(f"Unexpected error: {err}") from err

        response_time = time.time() - start_time

        # Parse response
        try:
            parsed = self._parse_response(data)
        except Exception as err:
            _LOGGER.error("Failed to parse Gemini response: %s", data)
            raise GeminiClientError(f"Invalid response format: {err}") from err

        parsed["api_response_time"] = response_time
        parsed["image_size"] = len(image_bytes)

        return parsed

    def _build_prompt(
        self,
        spot_name: str,
        definition: str,
        voice_prompt: str,
        memory_context: str,
    ) -> str:
        """Build the analysis prompt."""
        return f'''You are checking if "{spot_name}" matches its Ready State.

THE USER'S DEFINITION OF READY STATE:
{definition}

HISTORY (from previous checks):
{memory_context}

YOUR VOICE (how to communicate):
{voice_prompt}

TASK:
Look at the photo and compare it to the user's definition above.

1. List what's "To sort" - things that DON'T match the definition
2. List what's "Looking good" - things that DO match the definition
3. Write brief notes in your voice
4. If the history mentions patterns, you can reference them

RULES:
- Be SPECIFIC about what you see. "Coffee mug on left side of desk" not "items present"
- Reference the user's OWN WORDS from their definition
- If they said "no dishes" and you see dishes, call that out specifically
- Keep notes to 2-3 sentences MAX
- NEVER say "AI" or mention being an AI
- NEVER use generic phrases like "Let's get organized!"
- NEVER use the word "deviation" or "violation" or "spec"

RETURN THIS EXACT JSON FORMAT:
{{
    "status": "sorted" or "needs_attention",
    "to_sort": [
        {{"item": "specific item name", "location": "where it is"}}
    ],
    "looking_good": ["item 1", "item 2"],
    "notes": {{
        "main": "Your main observation in 1-2 sentences",
        "pattern": "Any pattern from history worth mentioning, or null",
        "encouragement": "Something encouraging if appropriate, or null"
    }}
}}

IMPORTANT:
- If EVERYTHING matches the definition, return status "sorted" with empty to_sort
- If ANYTHING doesn't match, return status "needs_attention"
- Do NOT include a "recurring" field - that's calculated separately
- Return ONLY valid JSON, no markdown, no extra text'''

    def _parse_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse Gemini response into structured result."""
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates in response")

        first = candidates[0]
        parts = first.get("content", {}).get("parts", [])

        text_block = None
        for part in parts:
            if "text" in part:
                text_block = part["text"]
                break

        if not text_block:
            raise ValueError("No text in response")

        # Clean up markdown formatting
        text_block = text_block.strip()
        if text_block.startswith("```json"):
            text_block = text_block[7:]
        if text_block.startswith("```"):
            text_block = text_block[3:]
        if text_block.endswith("```"):
            text_block = text_block[:-3]

        parsed = json.loads(text_block.strip())

        # Validate and normalize
        return self._validate_response(parsed)

    def _validate_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize the parsed response."""
        if not isinstance(data, dict):
            raise ValueError("Response must be a JSON object")

        # Status
        status = data.get("status", "needs_attention")
        if status not in ("sorted", "needs_attention"):
            status = "needs_attention"

        # To sort items
        to_sort_raw = data.get("to_sort", [])
        if not isinstance(to_sort_raw, list):
            to_sort_raw = []

        to_sort = []
        for item in to_sort_raw:
            if isinstance(item, dict):
                # Remove "recurring" if AI included it (we calculate this ourselves)
                item.pop("recurring", None)
                if item.get("item"):
                    to_sort.append({
                        "item": str(item.get("item", "")).strip(),
                        "location": str(item.get("location", "")) if item.get("location") else None,
                    })
            elif isinstance(item, str) and item.strip():
                to_sort.append({
                    "item": item.strip(),
                    "location": None,
                })

        # Looking good items
        looking_good_raw = data.get("looking_good", [])
        if not isinstance(looking_good_raw, list):
            looking_good_raw = []

        looking_good = []
        for item in looking_good_raw:
            if isinstance(item, str) and item.strip():
                looking_good.append(item.strip())
            elif isinstance(item, dict) and item.get("item"):
                looking_good.append(str(item["item"]).strip())

        # Notes
        notes_raw = data.get("notes", {})
        if not isinstance(notes_raw, dict):
            notes_raw = {}

        notes = {
            "main": str(notes_raw.get("main", "")) if notes_raw.get("main") else None,
            "pattern": str(notes_raw.get("pattern", "")) if notes_raw.get("pattern") else None,
            "encouragement": str(notes_raw.get("encouragement", "")) if notes_raw.get("encouragement") else None,
        }

        return {
            "status": status,
            "to_sort": to_sort,
            "looking_good": looking_good,
            "notes": notes,
        }

    async def validate_api_key(self, session: aiohttp.ClientSession) -> bool:
        """Validate that the API key works."""
        url = f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}"
        headers = {"x-goog-api-key": self._api_key}

        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status == 200
        except Exception:
            return False
