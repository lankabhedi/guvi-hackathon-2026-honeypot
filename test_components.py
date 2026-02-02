#!/usr/bin/env python3
"""Quick test of honeypot API components"""

import os

os.chdir("/home/samnitmehandiratta/honey-pot-api")

from app.detector import ScamDetector
from app.extractor import EntityExtractor
from app.database import init_db, save_conversation, get_conversation_history

print("Testing Scam Detector...")
detector = ScamDetector()
is_scam, confidence, indicators = detector.analyze(
    "URGENT: Your account will be blocked. Click this link immediately to verify your details"
)
print(f"  Scam detected: {is_scam} (confidence: {confidence:.2f})")
print(f"  Indicators: {indicators}")

print("\nTesting Entity Extractor...")
extractor = EntityExtractor()
test_message = "Please transfer money to account 1234567890 or UPI id test@paytm"
entities = extractor.extract_entities(test_message, [])
print(f"  Found entities: {entities}")

print("\nTesting Database...")
init_db()
save_conversation(
    "test-conv-1", "Hello this is a test", "I'm not sure, who is this?", {}
)
history = get_conversation_history("test-conv-1")
print(f"  Saved conversation, history length: {len(history)}")

print("\n✅ All components working!")
