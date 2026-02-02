#!/usr/bin/env python3
"""
Test script for Agentic Honey-Pot API
Tests all endpoints and functionality
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8001"
API_KEY = "hackathon-api-key-2026"


def test_health():
    """Test health endpoint"""
    print("Testing /health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("✅ Health check passed")


def test_honeypot_first_message():
    """Test first message in conversation"""
    print("\nTesting /honeypot with first message...")
    payload = {
        "sessionId": "test-session-001",
        "message": {
            "sender": "scammer",
            "text": "Your bank account will be blocked today. Verify immediately by clicking this link.",
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

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "reply" in data
    print(f"✅ First message test passed")
    print(f"   Reply: {data['reply'][:80]}...")


def test_honeypot_follow_up():
    """Test follow-up message with conversation history"""
    print("\nTesting /honeypot with follow-up message...")
    payload = {
        "sessionId": "test-session-001",
        "message": {
            "sender": "scammer",
            "text": "Share your UPI ID or bank account number to avoid suspension.",
            "timestamp": "2026-01-21T10:17:10Z",
        },
        "conversationHistory": [
            {
                "sender": "scammer",
                "text": "Your bank account will be blocked today. Verify immediately.",
                "timestamp": "2026-01-21T10:15:30Z",
            },
            {
                "sender": "user",
                "text": "Why will my account be blocked?",
                "timestamp": "2026-01-21T10:16:10Z",
            },
        ],
        "metadata": {"channel": "SMS", "language": "English", "locale": "IN"},
    }

    response = requests.post(
        f"{BASE_URL}/honeypot",
        headers={"Content-Type": "application/json", "x-api-key": API_KEY},
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    print(f"✅ Follow-up message test passed")
    print(f"   Reply: {data['reply'][:80]}...")


def test_entity_extraction():
    """Test entity extraction from message"""
    print("\nTesting entity extraction...")
    payload = {
        "sessionId": "test-session-002",
        "message": {
            "sender": "scammer",
            "text": "Transfer money to account 9876543210 or UPI id fraud@paytm. Visit http://fake-bank.com/verify",
            "timestamp": "2026-01-21T10:20:00Z",
        },
        "conversationHistory": [],
        "metadata": {"channel": "WhatsApp", "language": "English"},
    }

    response = requests.post(
        f"{BASE_URL}/honeypot",
        headers={"Content-Type": "application/json", "x-api-key": API_KEY},
        json=payload,
    )

    assert response.status_code == 200
    print("✅ Entity extraction test passed (check server logs for extracted data)")


def test_invalid_api_key():
    """Test authentication failure"""
    print("\nTesting invalid API key...")
    payload = {
        "sessionId": "test-session-003",
        "message": {
            "sender": "scammer",
            "text": "Test message",
            "timestamp": "2026-01-21T10:15:30Z",
        },
        "conversationHistory": [],
    }

    response = requests.post(
        f"{BASE_URL}/honeypot",
        headers={"Content-Type": "application/json", "x-api-key": "wrong-api-key"},
        json=payload,
    )

    assert response.status_code == 401
    print("✅ Invalid API key test passed (correctly rejected)")


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("AGENTIC HONEY-POT API TEST SUITE")
    print("=" * 60)

    try:
        test_health()
        test_honeypot_first_message()
        test_honeypot_follow_up()
        test_entity_extraction()
        test_invalid_api_key()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
