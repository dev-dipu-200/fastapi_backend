from openai import OpenAI
from src.configure.settings import settings

# Initialize OpenAI client with Hugging Face API
client = OpenAI(
    # base_url="https://router.huggingface.co/fireworks-ai/inference/v1",
    base_url="https://router.huggingface.co/v1",
    api_key=settings.HF_API_KEY,
)

async def open_ai_question(question: str) -> str:
    try:
        prompt = f"Q: {question}\nA:"
        completion = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-R1:fastest",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return completion.choices[0].message.content.strip()

    except Exception as e:
        raise RuntimeError(f"LLM Error: {e}")
