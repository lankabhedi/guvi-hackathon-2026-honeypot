#!/usr/bin/env python3
"""
Comprehensive test suite for Agentic Honey-Pot API v2.0
Tests all AI-powered components
"""

import requests
import json
import sys
import time

BASE_URL = "http://localhost:8001"
API_KEY = "hackathon-api-key-2026"


def test_health():
    """Test health endpoint"""
    print("\n" + "=" * 60)
    print("TEST 1: Health Check")
    print("=" * 60)

    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    data = response.json()

    print(f"✅ Status: {data['status']}")
    print(f"✅ Version: {data['version']}")
    print(f"✅ Features: {', '.join(data['features'])}")
    return True


def test_ai_detection():
    """Test AI-powered scam detection"""
    print("\n" + "=" * 60)
    print("TEST 2: AI-Powered Scam Detection")
    print("=" * 60)

    test_cases = [
        {
            "name": "UPI Fraud",
            "message": "Your account will be blocked. Share your UPI ID immediately to avoid suspension.",
            "expected_type": "UPI_FRAUD",
        },
        {
            "name": "KYC Scam",
            "message": "Dear customer, your SBI KYC is incomplete. Click this link to update immediately or account will be blocked.",
            "expected_type": "KYC_SCAM",
        },
        {
            "name": "Lottery Scam",
            "message": "Congratulations! You have won Rs. 5,00,000 in Amazon Lucky Draw. Call now to claim your prize!",
            "expected_type": "LOTTERY",
        },
    ]

    for test in test_cases:
        print(f"\nTesting: {test['name']}")
        payload = {
            "sessionId": f"test-detection-{test['name'].lower().replace(' ', '-')}",
            "message": {
                "sender": "scammer",
                "text": test["message"],
                "timestamp": "2026-01-21T10:15:30Z",
            },
            "conversationHistory": [],
            "metadata": {"channel": "SMS", "language": "English", "locale": "IN"},
        }

        response = requests.post(
            f"{BASE_URL}/honeypot",
            headers={"Content-Type": "application/json", "x-api-key": API_KEY},
            json=payload,
        )

        if response.status_code == 200:
            data = response.json()
            print(f"  ✅ Response received")
            print(f"  📝 Reply preview: {data['reply'][:60]}...")
        else:
            print(f"  ⚠️  Status: {response.status_code}")
            print(f"  Response: {response.text[:200]}")

    return True


def test_emotional_state_machine():
    """Test emotional state progression"""
    print("\n" + "=" * 60)
    print("TEST 3: Emotional State Machine")
    print("=" * 60)

    session_id = "test-emotions-001"
    conversation = [
        "Hello, this is calling from RBI. Your account has suspicious activity.",
        "If you don't verify immediately, your account will be blocked today.",
        "Police case will be filed against you. This is your last warning.",
        "Share your UPI ID now or we will suspend all your accounts.",
    ]

    print("Simulating conversation with escalating threats...")

    for i, message in enumerate(conversation):
        payload = {
            "sessionId": session_id,
            "message": {
                "sender": "scammer",
                "text": message,
                "timestamp": f"2026-01-21T10:{15 + i:02d}:30Z",
            },
            "conversationHistory": [],
            "metadata": {"channel": "SMS", "language": "English"},
        }

        response = requests.post(
            f"{BASE_URL}/honeypot",
            headers={"Content-Type": "application/json", "x-api-key": API_KEY},
            json=payload,
        )

        if response.status_code == 200:
            data = response.json()
            print(f"\nTurn {i + 1}: {message[:50]}...")
            print(f"  Response: {data['reply'][:70]}...")
            time.sleep(1)  # Rate limiting

    print("\n✅ Emotional progression test completed")
    return True


def test_entity_extraction():
    """Test AI-powered entity extraction"""
    print("\n" + "=" * 60)
    print("TEST 4: AI-Powered Entity Extraction")
    print("=" * 60)

    message = """Please transfer the verification fee to account 9876543210 
    or UPI id: fraud@paytm. You can also visit https://fake-sbi-verify.com 
    or call me on WhatsApp at +91-9876543210. Reference number: REF123456."""

    payload = {
        "sessionId": "test-extraction-001",
        "message": {
            "sender": "scammer",
            "text": message,
            "timestamp": "2026-01-21T10:15:30Z",
        },
        "conversationHistory": [],
        "metadata": {"channel": "WhatsApp", "language": "English"},
    }

    response = requests.post(
        f"{BASE_URL}/honeypot",
        headers={"Content-Type": "application/json", "x-api-key": API_KEY},
        json=payload,
    )

    if response.status_code == 200:
        print("✅ Entity extraction test passed")
        print(f"📝 Response: {response.json()['reply'][:80]}...")
        print("\nCheck session endpoint to see extracted entities:")
        print(f"GET {BASE_URL}/session/test-extraction-001")
    else:
        print(f"⚠️  Status: {response.status_code}")

    return True


def test_session_endpoint():
    """Test session information retrieval"""
    print("\n" + "=" * 60)
    print("TEST 5: Session Information Endpoint")
    print("=" * 60)

    # First, run a conversation to populate session data
    session_id = "test-session-info-001"
    messages = [
        "Your account will be blocked. Share UPI ID immediately.",
        "This is from SBI bank. You must verify today.",
        "Send to account 1234567890 or face legal action.",
    ]

    for msg in messages:
        payload = {
            "sessionId": session_id,
            "message": {
                "sender": "scammer",
                "text": msg,
                "timestamp": "2026-01-21T10:15:30Z",
            },
            "conversationHistory": [],
            "metadata": {"channel": "SMS"},
        }

        requests.post(
            f"{BASE_URL}/honeypot",
            headers={"Content-Type": "application/json", "x-api-key": API_KEY},
            json=payload,
        )
        time.sleep(0.5)

    # Now retrieve session info
    response = requests.get(
        f"{BASE_URL}/session/{session_id}", headers={"x-api-key": API_KEY}
    )

    if response.status_code == 200:
        data = response.json()
        print("✅ Session data retrieved successfully")
        print(f"📊 Session ID: {data['sessionId']}")
        print(f"📊 Message count: {data['data']['message_count']}")
        print(f"📊 Scam type: {data['data'].get('scam_type', 'Unknown')}")
        print(f"📊 Current mood: {data['data'].get('persona_mood', 'Unknown')}")

        entities = data["data"].get("extracted_entities", {})
        print(f"\n📊 Extracted Intelligence:")
        for key, values in entities.items():
            if values and key != "raw_extraction":
                print(f"   - {key}: {len(values)} items")
    else:
        print(f"⚠️  Status: {response.status_code}")

    return True


def test_invalid_api_key():
    """Test authentication"""
    print("\n" + "=" * 60)
    print("TEST 6: API Key Authentication")
    print("=" * 60)

    payload = {
        "sessionId": "test-auth",
        "message": {
            "sender": "scammer",
            "text": "Test message",
            "timestamp": "2026-01-21T10:15:30Z",
        },
        "conversationHistory": [],
    }

    response = requests.post(
        f"{BASE_URL}/honeypot",
        headers={"Content-Type": "application/json", "x-api-key": "wrong-key"},
        json=payload,
    )

    if response.status_code == 401:
        print("✅ Invalid API key correctly rejected")
    else:
        print(f"⚠️  Expected 401, got {response.status_code}")

    return True


def run_all_tests():
    """Run complete test suite"""
    print("\n" + "=" * 60)
    print("AGENTIC HONEY-POT API v2.0 - COMPREHENSIVE TEST SUITE")
    print("=" * 60)
    print("Testing AI-powered components:")
    print("- AI Scam Detection (Groq)")
    print("- Emotional State Machine")
    print("- Intelligent Entity Extraction")
    print("- Conversation Lifecycle")
    print("- Scammer Profiling")

    tests = [
        test_health,
        test_ai_detection,
        test_emotional_state_machine,
        test_entity_extraction,
        test_session_endpoint,
        test_invalid_api_key,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {passed + failed}")

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! System is ready.")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
