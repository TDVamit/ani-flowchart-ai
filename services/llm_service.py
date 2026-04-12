"""
LLM Service — provider-agnostic adapter.

Supported providers:
  - "anthropic"  → uses anthropic SDK, model e.g. "claude-opus-4-6"
  - "openai"     → uses openai SDK, model e.g. "gpt-4o"
  - "gemini"     → uses google-genai SDK (from google import genai), model e.g. "gemini-2.5-flash"
                   NOTE: google-generativeai is deprecated as of Nov 2025. Use google-genai instead.

All methods return a dict: {"content": str, "prompt_tokens": int, "completion_tokens": int}
"""

import anthropic
import openai
from google import genai
from google.genai import types as genai_types
from config import settings


class LLMService:

    def __init__(self, provider: str = None, model: str = None):
        self.provider = provider or settings.default_llm_provider
        self.model = model or settings.default_llm_model

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 8000,
        temperature: float = 0.3,
    ) -> dict:
        """Route to the correct provider and return normalized response."""
        if self.provider == "anthropic":
            return await self._call_anthropic(system_prompt, user_message, max_tokens, temperature)
        elif self.provider == "openai":
            return await self._call_openai(system_prompt, user_message, max_tokens, temperature)
        elif self.provider == "gemini":
            return await self._call_gemini(system_prompt, user_message, max_tokens, temperature)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def _call_anthropic(self, system_prompt, user_message, max_tokens, temperature):
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return {
            "content": response.content[0].text,
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }

    async def _call_openai(self, system_prompt, user_message, max_tokens, temperature):
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return {
            "content": response.choices[0].message.content,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }

    async def _call_gemini(self, system_prompt, user_message, max_tokens, temperature):
        # New google-genai SDK: pip install google-genai
        # Import: from google import genai
        # The old google-generativeai package is fully deprecated — do NOT use it.
        client = genai.Client(api_key=settings.google_api_key)

        response = await client.aio.models.generate_content(
            model=self.model,
            contents=user_message,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        usage = response.usage_metadata
        return {
            "content": response.text,
            "prompt_tokens": usage.prompt_token_count if usage else 0,
            "completion_tokens": usage.candidates_token_count if usage else 0,
        }


# Available models per provider (for the frontend settings UI)
AVAILABLE_MODELS = {
    "anthropic": [
        {"id": "claude-opus-4-6", "name": "Claude Opus 4.6 (most capable)"},
        {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6 (fast + smart)"},
        {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5 (fastest)"},
    ],
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
    ],
    "gemini": [
        {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash (recommended)"},
        {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro (most capable)"},
        {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash"},
    ],
}
