#!/usr/bin/env python3
"""
Test script to verify callback timer and show how to check LLM extraction logs

This script demonstrates:
1. Current INACTIVITY_TIMEOUT setting
2. How to check LLM extraction logs
3. Expected callback timing behavior
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import INACTIVITY_TIMEOUT
import subprocess


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def test_callback_timing():
    """Test and display callback timing configuration"""
    print_section("📊 CALLBACK TIMER CONFIGURATION")

    BUFFER = 2  # Built-in buffer to avoid race conditions
    effective_wait = INACTIVITY_TIMEOUT - BUFFER

    print(f"⏱️  INACTIVITY_TIMEOUT (configured): {INACTIVITY_TIMEOUT} seconds")
    print(f"🛡️  Buffer (race condition prevention): {BUFFER} seconds")
    print(f"⚡ Effective wait before callback: {effective_wait} seconds")
    print()
    print("📅 How it works:")
    print(f"   1. Honeypot sends response to GUVI")
    print(f"   2. Inactivity monitor starts")
    print(f"   3. Wait {INACTIVITY_TIMEOUT} seconds (checking for new messages)")
    print(f"   4. If inactive >= {effective_wait}s: Send callback")
    print()
    print("⏱️  Timeline Example:")
    print(f"   T=0s:     Honeypot sends message")
    print(f"   T=1s:     Waiting...")
    print(f"   T={effective_wait}s:  ⚡ CALLBACK FIRED to GUVI")
    print(f"   T={INACTIVITY_TIMEOUT}s: Monitor check complete")


def show_llm_logs_instructions():
    """Show how to check LLM extraction logs"""
    print_section("🔍 HOW TO CHECK LLM EXTRACTION LOGS")

    print("To verify your GPT OSS 120B model changes are working:")
    print()
    print("1️⃣  Start the server:")
    print("     $ uvicorn app.main:app --reload")
    print()
    print("2️⃣  Send test message to honeypot")
    print()
    print("3️⃣  Check the logs for these markers:")
    print()
    print("   🧠 [EXTRACTOR] Raw LLM Output:")
    print("   → Shows raw response from openai/gpt-oss-120b model")
    print()
    print("   🧠 [EXTRACTOR] 🧹 CLEANED OUTPUT:")
    print("   → Shows output after removing markdown tags")
    print()
    print("   ✅ [EXTRACTOR] ✨ PARSED JSON SUCCESSFULLY:")
    print("   → Shows the parsed JSON structure")
    print()
    print("   🧠 [EXTRACTOR] 📦 FINAL FLATTENED OUTPUT:")
    print("   → Shows final entities in GUVI format")
    print()
    print("4️⃣  Verify extraction quality:")
    print("     ✓ Phone numbers with +91 prefix preserved")
    print("     ✓ Bank accounts, UPI IDs extracted")
    print("     ✓ No empty raw_extraction (means LLM worked, not fallback)")


def show_live_log_monitoring():
    """Show how to monitor logs in real-time"""
    print_section("📺 LIVE LOG MONITORING")

    print("To watch logs in real-time:")
    print()
    print("   $ tail -f honeypot.log | grep -E '\[EXTRACTOR\]|Callback|MONITOR'")
    print()
    print("This will show:")
    print("   • Raw LLM output")
    print("   • Entity extraction results")
    print("   • Callback firing")
    print("   • Monitor status")


def verify_configuration():
    """Verify all configuration is correct"""
    print_section("✅ CONFIGURATION VERIFICATION")

    # Check model configuration
    from app.extractor import EntityExtractor
    from app.detector import ScamDetector
    from app.persona import PersonaAgent
    from app.session import SessionManager

    extractor = EntityExtractor()
    detector = ScamDetector()
    persona = PersonaAgent()
    session_mgr = SessionManager()

    checks = [
        ("Extractor Model", extractor.model, "openai/gpt-oss-120b"),
        ("Detector Model", detector.model, "openai/gpt-oss-120b"),
        ("Persona Model", persona.model, "openai/gpt-oss-120b"),
        ("Session Model", session_mgr.summary_model, "openai/gpt-oss-120b"),
        ("Callback Timer", f"{INACTIVITY_TIMEOUT}s", "6s (4s effective)"),
    ]

    print("Checking configuration...")
    print()
    all_good = True
    for name, actual, expected in checks:
        status = "✅" if str(expected) in str(actual) else "❌"
        print(f"{status} {name}: {actual}")
        if "❌" in status:
            print(f"   Expected: {expected}")
            all_good = False
    print()

    if all_good:
        print("🎉 All configurations are correct!")
    else:
        print("⚠️  Some configurations need attention")


def show_expected_logs_example():
    """Show example of what good logs should look like"""
    print_section("📝 EXPECTED LLM EXTRACTION LOGS")

    print("When your changes are working, logs should look like this:")
    print()
    print("─" * 70)
    print("🧠 [EXTRACTOR] 🔍 RAW LLM OUTPUT:")
    print("=" * 60)
    print("{")
    print('    "financial": {')
    print('        "bank_accounts": ["1234567890123456"],')
    print('        "upi_ids": ["scammer@paytm"],')
    print('        "ifsc_codes": [],')
    print('        "wallet_ids": []')
    print("    },")
    print('    "contact": {')
    print('        "phone_numbers": ["+91-9876543210"],  ← +91 preserved!')
    print('        "whatsapp_numbers": [],')
    print('        "emails": [],')
    print('        "telegram_handles": []')
    print("    },")
    print("    ...")
    print("}")
    print("=" * 60)
    print()
    print("✅ [EXTRACTOR] ✨ PARSED JSON SUCCESSFULLY:")
    print("  (valid JSON structure)")
    print()
    print("🧠 [EXTRACTOR] 📦 FINAL FLATTENED OUTPUT:")
    print("{")
    print('    "bankAccounts": ["1234567890123456"],')
    print('    "upiIds": ["scammer@paytm"],')
    print('    "phoneNumbers": ["+91-9876543210"],  ← +91 in final output!')
    print("    ...")
    print("}")
    print("─" * 70)


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  🧪 HONEY-POT API - VERIFICATION & TESTING")
    print("=" * 70)

    test_callback_timing()
    show_llm_logs_instructions()
    show_live_log_monitoring()
    verify_configuration()
    show_expected_logs_example()

    print("\n" + "=" * 70)
    print("  ✅ VERIFICATION COMPLETE")
    print("=" * 70)
    print()
    print("📝 Next Steps:")
    print("   1. Start server: uvicorn app.main:app --reload")
    print("   2. Monitor logs: tail -f honeypot.log | grep -E '\[EXTRACTOR\]'")
    print("   3. Test with GUVI or local test")
    print("   4. Verify extraction quality in logs")
    print()
