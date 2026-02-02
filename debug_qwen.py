import os
import asyncio
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()


async def test_qwen_reasoning():
    client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    print("🧠 Testing Qwen 3 32B Output Structure...")

    try:
        response = await client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Answer briefly.",
                },
                {"role": "user", "content": "What is 2+2?"},
            ],
            temperature=0.8,
            max_tokens=150,
        )

        raw_content = response.choices[0].message.content
        print("\n--- RAW CONTENT START ---")
        print(raw_content)
        print("--- RAW CONTENT END ---\n")

        if "<think>" in raw_content:
            print("✅ <think> tags DETECTED.")
        else:
            print("⚠️ NO <think> tags found. It might be unstructured text.")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_qwen_reasoning())
