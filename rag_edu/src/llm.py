import os
import json
from litellm import completion
from dotenv import load_dotenv

load_dotenv()

# We can use "gemini/gemini-1.5-flash", "openai/gpt-4o-mini", etc.
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

def generate_json(prompt: str, timeout: float = 6.0) -> dict:
    """Generate structured JSON using LLM. Bounded by timeout to keep pipeline fast."""
    try:
        response = completion(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            timeout=timeout,
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"LLM JSON generation failed: {e}")
        return {}

def generate_text(system_prompt: str, user_prompt: str, max_tokens: int = 512, timeout: float = 25.0) -> str:
    """Generate freeform text. Capped at max_tokens for latency control."""
    try:
        response = completion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            timeout=timeout,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM text generation failed: {e}")
        return "Xin lỗi, hiện tại em đang gặp chút trục trặc. Anh chị vui lòng đợi lát thư lại nha."
