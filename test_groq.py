#!/usr/bin/env python3
"""Test Groq LLM integration"""

import os

os.chdir("/home/samnitmehandiratta/honey-pot-api")

from dotenv import load_dotenv

load_dotenv()

from app.persona import PersonaEngine

print("Testing Groq LLM Integration...")
persona = PersonaEngine()

# Test generating a response
test_message = "Hello, this is calling from your bank. We have detected suspicious activity on your account."
history = []

print(f"\nScammer: {test_message}")
response, persona_id = persona.generate_response(test_message, history, "elderly")
print(f"Victim ({persona_id}): {response}")

print("\n✅ Groq LLM working!" if response else "\n❌ Groq failed")
