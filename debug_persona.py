import os
import asyncio
from groq import AsyncGroq
from dotenv import load_dotenv
import re

load_dotenv()


async def test_qwen_persona_generation():
    client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    print(
        "🧠 Testing Qwen 3 32B Persona Generation (Simulating app/persona.py logic)..."
    )

    prompt = """You are Rajesh Kumar, age 68. Retired government employee.
    
    CURRENT EMOTIONAL STATE: WORRIED
    Instruction: STRATEGY: Say 'Server Down'. The app is just spinning. Ask for another account. Keep it short.
    
    CONVERSATION HISTORY:
    Them: URGENT: Your SBI account has been compromised.
    
    SCAMMER JUST SAID: "Please share your account number and OTP."
    
    Respond as Rajesh Kumar.
    CRITICAL GUIDELINES:
    1. Use natural Hinglish. Be slightly irritated. Vary your starters.
    2. KEEP IT SHORT. Max 1-2 sentences. 
    3. Be natural. Do NOT repeat the scammer's bank numbers.
    4. If in FAKE_ERROR mode, just say "It failed, giving error."
    
    Your response:"""

    try:
        response = await client.chat.completions.create(
            model="qwen/qwen3-32b",
            messages=[
                {
                    "role": "system",
                    "content": "You are Rajesh Kumar, 68 years old. Speak naturally with typos. Short messages only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            # max_tokens removed as per current code
            reasoning_format="parsed",  # FORCE reasoning to be parsed separately
        )

        # 1. Inspect Raw Response Object
        print("\n--- RAW RESPONSE OBJECT ---")
        print(f"ID: {response.id}")

        # 2. Inspect Content
        content = response.choices[0].message.content
        print(f"\n--- RAW CONTENT field (Type: {type(content)}) ---")
        print(f"'{content}'")

        # 3. Inspect Reasoning (if parsed)
        if hasattr(response.choices[0].message, "reasoning"):
            print(f"\n--- PARSED REASONING field ---")
            print(
                response.choices[0].message.reasoning[:100] + "..."
            )  # Print first 100 chars
        else:
            print("\n--- NO PARSED REASONING FIELD FOUND ---")

        # 4. Simulate Regex Logic
        if content:
            cleaned_content = re.sub(
                r"<think>.*?</think>", "", content, flags=re.DOTALL
            )
            print(f"\n--- CLEANED CONTENT (After Regex) ---")
            print(f"'{cleaned_content.strip()}'")
        else:
            print("\n❌ CONTENT IS NONE OR EMPTY!")

    except Exception as e:
        print(f"\n❌ EXCEPTION CAUGHT: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_qwen_persona_generation())
