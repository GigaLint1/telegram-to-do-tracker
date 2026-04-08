"""
LLM-powered motivational message generator using the Groq API (free tier).
Falls back silently to a random static message if the key is missing or the call fails.
"""

import logging
import os
import random

from config import MOTIVATIONAL_MESSAGES

logger = logging.getLogger(__name__)

_groq_client = None


def _get_client():
    global _groq_client
    if _groq_client is not None:
        return _groq_client
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from groq import AsyncGroq
        _groq_client = AsyncGroq(api_key=api_key)
        return _groq_client
    except ImportError:
        logger.warning("groq package not installed — falling back to static messages")
        return None


async def generate_motivational_message(
    slot: str,
    done: int,
    total: int,
    streak: int,
) -> str:
    """
    Generate a context-aware motivational message via Groq (llama-3.1-8b-instant).
    Falls back to a random static message on any failure.

    Args:
        slot:   'morning' | 'midday' | 'evening'
        done:   number of tasks completed today
        total:  total active tasks today
        streak: current streak in days
    """
    client = _get_client()
    if client is None:
        return random.choice(MOTIVATIONAL_MESSAGES)

    slot_label = {"morning": "morning", "midday": "midday", "evening": "evening"}.get(slot, slot)
    streak_line = f"a {streak}-day streak" if streak > 1 else "just starting their streak today"

    prompt = (
        f"You are a motivational coach for a productivity app. "
        f"Generate ONE short motivational message (1-2 sentences, max 30 words) for a user who:\n"
        f"- Is doing their {slot_label} check-in\n"
        f"- Has completed {done} out of {total} tasks today\n"
        f"- Has {streak_line}\n\n"
        f"Be specific to their situation. Be energetic and concise. "
        f"Do not use generic filler phrases like 'keep it up' or 'you got this'. "
        f"Reply with ONLY the message text, no quotes, no emojis."
    )

    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.9,
        )
        message = response.choices[0].message.content.strip()
        if message:
            return message
    except Exception as e:
        logger.warning(f"Groq API call failed: {e} — using static fallback")

    return random.choice(MOTIVATIONAL_MESSAGES)


def _fmt_secs(seconds: int) -> str:
    """Minimal duration formatter — avoids circular import from handlers.py."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0 and mins > 0:
        return f"{hours}h {mins}m"
    elif hours > 0:
        return f"{hours}h"
    return f"{mins}m"


async def generate_midtask_message(
    task_name: str,
    elapsed_seconds: int,
    custom_prompt: str,
) -> str:
    """
    Generate a mid-task motivational nudge using the user's custom prompt.
    Falls back to a random static message on any failure.
    """
    client = _get_client()
    if client is None:
        return random.choice(MOTIVATIONAL_MESSAGES)

    elapsed_str = _fmt_secs(elapsed_seconds)
    prompt = (
        f"{custom_prompt}\n\n"
        f"Context: The user has been working on '{task_name}' for {elapsed_str} in this session. "
        f"Reply with ONLY the message text, no quotes."
    )

    try:
        response = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.95,
        )
        message = response.choices[0].message.content.strip()
        if message:
            return message
    except Exception as e:
        logger.warning(f"Groq mid-task API call failed: {e} — using static fallback")

    return random.choice(MOTIVATIONAL_MESSAGES)
