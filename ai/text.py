"""
Text generation using Cloudflare Workers AI.
"""
import json
import logging
from typing import Optional, Dict, Any
from openai import OpenAI
from .config import get_config

logger = logging.getLogger(__name__)


def generate_text(
    prompt: str,
    model: str = "workers-ai/@cf/openai/gpt-oss-120b",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    system_prompt: Optional[str] = None
) -> Optional[str]:
    """
    Generate text using Cloudflare Workers AI.

    Args:
        prompt: The user prompt for text generation
        model: AI model identifier
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum tokens to generate
        system_prompt: Optional system prompt to guide behavior

    Returns:
        Generated text string or None on failure
    """
    try:
        config = get_config()
        base_url = f"https://gateway.ai.cloudflare.com/v1/{config['account_id']}/{config['gateway_name']}/compat"

        client = OpenAI(
            base_url=base_url,
            api_key=config['api_token'],
            default_headers={"cf-aig-authorization": f"Bearer {config['api_token']}"}
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info(f"Generating text with model {model} (temp={temperature}, max_tokens={max_tokens})")

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        result = response.choices[0].message.content
        logger.info(f"Generated {len(result)} characters")
        return result

    except Exception as e:
        logger.error(f"Text generation failed: {e}", exc_info=True)
        return None


def generate_structured_response(
    prompt: str,
    json_schema: Optional[Dict[str, Any]] = None,
    model: str = "workers-ai/@cf/openai/gpt-oss-120b",
    temperature: float = 0.2,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Generate a structured JSON response using Cloudflare Workers AI.

    Args:
        prompt: The user prompt for generation
        json_schema: Optional JSON schema to validate against
        model: AI model identifier
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum tokens to generate
        system_prompt: Optional system prompt

    Returns:
        Parsed JSON dictionary or None on failure
    """
    try:
        config = get_config()
        base_url = f"https://gateway.ai.cloudflare.com/v1/{config['account_id']}/{config['gateway_name']}/compat"

        client = OpenAI(
            base_url=base_url,
            api_key=config['api_token'],
            default_headers={"cf-aig-authorization": f"Bearer {config['api_token']}"}
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            schema_desc = f" The response must conform to this schema: {json.dumps(json_schema)}" if json_schema else ""
            messages.append({
                "role": "system",
                "content": f"You must respond with valid JSON only, no additional text.{schema_desc}"
            })

        messages.append({"role": "user", "content": prompt})

        logger.info(f"Generating structured response with model {model}")

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens
        )

        content = response.choices[0].message.content
        if not content:
            logger.error("AI returned empty content")
            return None

        result = json.loads(content)
        logger.info(f"Parsed structured response with {len(result)} keys")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        return None
    except Exception as e:
        logger.error(f"Structured response generation failed: {e}", exc_info=True)
        return None
