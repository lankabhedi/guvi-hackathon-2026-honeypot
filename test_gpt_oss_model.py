#!/usr/bin/env python3
"""Test script to verify openai/gpt-oss-120b model configuration"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.extractor import EntityExtractor
from app.detector import ScamDetector
from app.persona import PersonaAgent
from app.session import SessionManager


def test_model_configuration():
    """Test that all components are configured with the correct model"""
    print("\n" + "=" * 60)
    print("🧪 Testing Model Configuration")
    print("=" * 60 + "\n")

    # Test Extractor
    extractor = EntityExtractor()
    print(f"✅ EntityExtractor Model: {extractor.model}")
    assert extractor.model == "openai/gpt-oss-120b", "Extractor model mismatch!"
    print(f"   Model initialized correctly")

    # Test Detector
    detector = ScamDetector()
    print(f"\n✅ ScamDetector Model: {detector.model}")
    assert detector.model == "openai/gpt-oss-120b", "Detector model mismatch!"
    print(f"   Model initialized correctly")

    # Test Persona
    persona = PersonaAgent()
    print(f"\n✅ PersonaAgent Model: {persona.model}")
    assert persona.model == "openai/gpt-oss-120b", "Persona model mismatch!"
    print(f"   Model initialized correctly")

    # Test SessionManager
    session_mgr = SessionManager()
    print(f"\n✅ SessionManager Summary Model: {session_mgr.summary_model}")
    assert session_mgr.summary_model == "openai/gpt-oss-120b", "Session model mismatch!"
    print(f"   Model initialized correctly")

    print("\n" + "=" * 60)
    print("✅ All models configured correctly with openai/gpt-oss-120b!")
    print("=" * 60 + "\n")

    return True


async def test_extraction_with_new_model():
    """Test extraction with the new GPT OSS 120B model"""
    print("\n" + "=" * 60)
    print("🧪 Testing Extraction with openai/gpt-oss-120b")
    print("=" * 60 + "\n")

    extractor = EntityExtractor()

    test_message = "Please transfer money to account 1234567890123456 or UPI scammer@paytm immediately. Call +91-9876543210 for verification."

    print(f"Test message: {test_message}")
    print(f"\nUsing model: {extractor.model}")
    print(f"Max completion tokens: 8192")
    print(f"Temperature: 1.0")
    print(f"Top p: 1.0")

    print(f"\n⏳ Extracting entities (this may take a moment due to 120B model)...")
    print(f"   Note: First call will be slower (model loading)...\n")

    try:
        result = await extractor.extract_entities(test_message, [])

        print(f"\n✅ Extraction successful!")
        print(f"\nExtracted entities:")
        print(f"  Bank accounts: {result.get('bankAccounts', [])}")
        print(f"  UPI IDs: {result.get('upiIds', [])}")
        print(f"  Phone numbers: {result.get('phoneNumbers', [])}")
        print(f"  Phishing links: {result.get('phishingLinks', [])}")
        print(f"  Amounts: {result.get('amounts', [])}")
        print(f"  Reference numbers: {result.get('referenceNumbers', [])}")
        print(f"  Organization: {result.get('organizationClaimed', '')}")

        # Verify extraction quality
        assert "1234567890123456" in result.get("bankAccounts", []), (
            "Bank account not extracted!"
        )
        assert "scammer@paytm" in result.get("upiIds", []), "UPI ID not extracted!"
        assert any("+91" in phone for phone in result.get("phoneNumbers", [])), (
            "Phone number with country code not preserved!"
        )

        print(f"\n✅ All entities extracted correctly!")
        print(f"\n" + "=" * 60)
        print(f"✅ openai/gpt-oss-120b extraction test passed!")
        print("=" * 60 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ Extraction failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_detection_with_new_model():
    """Test scam detection with the new GPT OSS 120B model"""
    print("\n" + "=" * 60)
    print("🧪 Testing Scam Detection with openai/gpt-oss-120b")
    print("=" * 60 + "\n")

    detector = ScamDetector()

    test_message = (
        "Your account will be blocked in 24 hours. Send your OTP to verify immediately."
    )

    print(f"Test message: {test_message}")
    print(f"\nUsing model: {detector.model}")
    print(f"Max completion tokens: 8192")
    print(f"Temperature: 1.0")
    print(f"Top p: 1.0")

    print(f"\n⏳ Detecting scam...")
    print(f"   This uses the powerful 120B model for accurate classification\n")

    try:
        is_scam, confidence, analysis = await detector.analyze(test_message)

        print(f"\n✅ Detection successful!")
        print(f"\nDetection results:")
        print(f"  Is scam: {is_scam}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Scam type: {analysis.get('scam_type', 'UNKNOWN')}")
        print(f"  Risk level: {analysis.get('risk_level', 'UNKNOWN')}")
        print(f"  Tactics: {', '.join(analysis.get('tactics', []))}")
        print(f"  Reasoning: {analysis.get('reasoning', 'N/A')}")

        assert is_scam == True, "Should detect this as a scam!"
        assert confidence > 0.5, "Confidence should be high!"

        print(f"\n✅ Detection working correctly!")
        print(f"\n" + "=" * 60)
        print(f"✅ openai/gpt-oss-120b detection test passed!")
        print("=" * 60 + "\n")

        return True

    except Exception as e:
        print(f"\n❌ Detection failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🧪 Testing OpenAI GPT OSS 120B Integration")
    print("=" * 60)

    # Test model configuration
    test_model_configuration()

    # Test extraction
    import asyncio

    extraction_ok = asyncio.run(test_extraction_with_new_model())

    # Test detection
    detection_ok = asyncio.run(test_detection_with_new_model())

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"✅ Model configuration: PASSED")
    print(
        f"{'✅' if extraction_ok else '❌'} Entity extraction: {'PASSED' if extraction_ok else 'FAILED'}"
    )
    print(
        f"{'✅' if detection_ok else '❌'} Scam detection: {'PASSED' if detection_ok else 'FAILED'}"
    )

    if extraction_ok and detection_ok:
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED - Ready for deployment!")
        print("=" * 60 + "\n")
    else:
        print("\n" + "=" * 60)
        print("⚠️  Some tests failed - please review errors above")
        print("=" * 60 + "\n")
        sys.exit(1)
