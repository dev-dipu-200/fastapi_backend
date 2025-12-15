# from openai import OpenAI
# from src.configure.settings import settings

# # Initialize OpenAI client with Hugging Face API
# client = OpenAI(
#     # base_url="https://router.huggingface.co/fireworks-ai/inference/v1",
#     base_url="https://router.huggingface.co/v1",
#     api_key=settings.HF_API_KEY,
# )

# async def open_ai_question(question: str) -> str:
#     try:
#         prompt = f"Q: {question}\nA:"
#         completion = client.chat.completions.create(
#             model="deepseek-ai/DeepSeek-R1:fastest",
#             messages=[
#                 {"role": "user", "content": prompt}
#             ]
#         )

#         return completion.choices[0].message.content.strip()

#     except Exception as e:
#         raise RuntimeError(f"LLM Error: {e}")


from groq import Groq
from src.configure.settings import settings
import logging

# Initialize Groq client
client = Groq(
    api_key=settings.GROQ_API_KEY,
)

async def open_ai_question(question: str) -> str:
    try:
        stream = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "user", "content": question}
            ],
            temperature=1,
            max_tokens=8192,
            top_p=1,
            reasoning_effort="medium",
            stream=True, 
            stop=None,
        )

        full_response = ""
        for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            full_response += content
            print(content, end="", flush=True)  # Live output to console/logs

        return full_response.strip()

    except Exception as e:
        logging.error(f"Groq LLM call failed: {repr(e)}")
        raise RuntimeError("LLM service unavailable – please try again later.")
