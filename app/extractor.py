from groq import AsyncGroq
import os
import json
from typing import List, Dict, Any


class EntityExtractor:
    """AI-powered entity extraction using Groq LLM - extracts ONLY scammer-provided information"""

    def __init__(self):
        self._client = None
        self.model = "openai/gpt-oss-120b"  # Using OpenAI GPT OSS 120B model

    @property
    def client(self):
        """Lazy initialization of Groq client"""
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable not set")
            self._client = AsyncGroq(api_key=api_key)
        return self._client

    async def extract_entities(
        self, current_message: str, history: List[Dict]
    ) -> Dict[str, Any]:
        """
        Extract actionable intelligence from conversation using AI
        Only extracts information the SCAMMER provided, not victim details
        """
        conversation_text = self._build_conversation_text(current_message, history)

        prompt = f"""You are extracting scammer details from a conversation.

CONVERSATION:
{conversation_text}

INSTRUCTIONS:
Extract ALL bank accounts, UPI IDs, phone numbers, links, and suspicious keywords you see in the text.

Look for patterns like:
- bankAccount: 1234567890123456
- upiId: scammer@upi
- phoneNumber: +XX-XXXXXXXXXX (EXTRACT EXACTLY AS WRITTEN, KEEP COUNTRY CODE)
- phishing link: http://example.com
- suspicious keyword: urgent, verify, blocked

Extract the VALUES, not the field names.
IMPORTANT: For phone numbers, PRESERVE the full format including ANY country code and hyphens (e.g. "+91-...", "+1-...", "+44-..."). Do not strip the prefix.

Return this exact JSON structure:
{{
    "financial": {{
        "bank_accounts": ["1234567890123456"],
        "upi_ids": ["scammer@upi"],
        "ifsc_codes": [],
        "wallet_ids": []
    }},
    "contact": {{
        "phone_numbers": ["+91-9876543210"],
        "whatsapp_numbers": [],
        "emails": [],
        "telegram_handles": []
    }},
    "infrastructure": {{
        "phishing_links": ["http://example.com"],
        "malicious_apps": [],
        "fake_websites": []
    }},
    "operational": {{
        "amounts": [],
        "reference_numbers": [],
        "organization_claimed": "SBI Bank"
    }},
    "extraction_summary": "Extracted 1 bank account, 1 UPI ID, 1 phone number"
}}

If no entities found, return empty arrays.
Return ONLY the JSON, no markdown."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an entity extraction AI. Return only valid JSON. Be precise and conservative.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=1,  # Using GPT OSS 120B recommended temperature
                max_completion_tokens=8192,
                top_p=1,
            )

            content = (response.choices[0].message.content or "").strip()

            # COMPREHENSIVE LOGGING: Log raw LLM output
            import logging

            logger = logging.getLogger(__name__)
            logger.info(
                f"🧠 [EXTRACTOR] 🔍 RAW LLM OUTPUT:\n{'=' * 60}\n{content}\n{'=' * 60}"
            )

            # Clean thinking tags
            import re

            result_text = re.sub(r"<thinking>.*?", "", content, flags=re.DOTALL).strip()

            # Clean markdown code blocks (NEW)
            result_text = re.sub(r"```json\s*", "", result_text, flags=re.IGNORECASE)
            result_text = re.sub(r"```\s*$", "", result_text, flags=re.MULTILINE)
            result_text = result_text.strip()

            # Log cleaned output
            logger.info(
                f"🧠 [EXTRACTOR] 🧹 CLEANED OUTPUT:\n{'=' * 60}\n{result_text}\n{'=' * 60}"
            )

            try:
                extracted = json.loads(result_text)
                logger.info(
                    f"✅ [EXTRACTOR] ✨ PARSED JSON SUCCESSFULLY:\n{json.dumps(extracted, indent=2)}"
                )
            except json.JSONDecodeError as e:
                logger.error(f"❌ [EXTRACTOR] JSON DECODE FAILED! Error: {e}")
                logger.error(
                    f"❌ [EXTRACTOR] Attempting fallback extraction using regex..."
                )
                extracted = self._fallback_extraction(current_message)

            # Flatten for GUVI format
            flattened = self._flatten_for_guvi(extracted)
            logger.info(
                f"🧠 [EXTRACTOR] 📦 FINAL FLATTENED OUTPUT:\n{json.dumps(flattened, indent=2)}"
            )
            return flattened

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"❌ [EXTRACTOR] ❌ EXCEPTION IN EXTRACTION: {str(e)}", exc_info=True
            )
            logger.error(f"❌ [EXTRACTOR] Using fallback extraction due to exception")
            return self._fallback_extraction(current_message)

    def _build_conversation_text(
        self, current_message: str, history: List[Dict]
    ) -> str:
        """Build full conversation text for context"""
        conversation = []

        if history:
            for msg in history[-5:]:  # Last 5 turns
                scammer_msg = msg.get("scammer_message", "")
                response = msg.get("response", "")
                if scammer_msg:
                    conversation.append(f"Scammer: {scammer_msg}")
                if response:
                    conversation.append(f"Victim: {response}")

        conversation.append(f"Scammer (current): {current_message}")

        return "\n".join(conversation)

    def _flatten_for_guvi(self, extracted: Dict) -> Dict[str, Any]:
        """Flatten extracted entities for GUVI callback format"""
        flattened = {
            "bankAccounts": [],
            "upiIds": [],
            "phishingLinks": [],
            "phoneNumbers": [],
            "suspiciousKeywords": [],
            "amounts": [],
            "referenceNumbers": [],
            "organizationClaimed": "",
            "infoRequested": [],
            "raw_extraction": extracted,
        }

        # Financial
        financial = extracted.get("financial", {})
        for acc in financial.get("bank_accounts", []):
            # Handle both dict (with confidence) and string formats
            if isinstance(acc, dict):
                if acc.get("confidence", 0) > 0.6:
                    flattened["bankAccounts"].append(acc["value"])
            elif isinstance(acc, str):
                flattened["bankAccounts"].append(acc)

        for upi in financial.get("upi_ids", []):
            if isinstance(upi, dict):
                if upi.get("confidence", 0) > 0.6:
                    flattened["upiIds"].append(upi["value"])
            elif isinstance(upi, str):
                flattened["upiIds"].append(upi)

        # Contact
        contact = extracted.get("contact", {})
        for phone in contact.get("phone_numbers", []):
            if isinstance(phone, dict):
                if phone.get("confidence", 0) > 0.6:
                    flattened["phoneNumbers"].append(phone["value"])
            elif isinstance(phone, str):
                flattened["phoneNumbers"].append(phone)

        # Infrastructure
        infra = extracted.get("infrastructure", {})
        for link in infra.get("phishing_links", []):
            if isinstance(link, dict):
                if link.get("confidence", 0) > 0.6:
                    flattened["phishingLinks"].append(link["value"])
            elif isinstance(link, str):
                flattened["phishingLinks"].append(link)

        # Operational
        operational = extracted.get("operational", {})
        for amt in operational.get("amounts", []):
            if isinstance(amt, dict):
                if amt.get("confidence", 0) > 0.6:
                    flattened["amounts"].append(amt["value"])
            elif isinstance(amt, str):
                flattened["amounts"].append(amt)

        for ref in operational.get("reference_numbers", []):
            if isinstance(ref, dict):
                if ref.get("confidence", 0) > 0.6:
                    flattened["referenceNumbers"].append(ref["value"])
            elif isinstance(ref, str):
                flattened["referenceNumbers"].append(ref)

        flattened["organizationClaimed"] = operational.get("organization_claimed", "")

        # What they asked for
        victim = extracted.get("victim_targeted", {})
        flattened["infoRequested"] = victim.get("info_requested", [])

        # Suspicious keywords from summary
        summary = extracted.get("extraction_summary", "")
        if summary:
            keywords = ["urgent", "immediately", "blocked", "verify", "upi", "account"]
            for kw in keywords:
                if kw in summary.lower():
                    flattened["suspiciousKeywords"].append(kw)

        return flattened

    def _fallback_extraction(self, message: str) -> Dict[str, Any]:
        """Basic regex fallback when Groq fails"""
        import re

        result = {
            "bankAccounts": [],
            "upiIds": [],
            "phishingLinks": [],
            "phoneNumbers": [],
            "suspiciousKeywords": [],
            "amounts": [],
            "referenceNumbers": [],
            "organizationClaimed": "",
            "infoRequested": [],
            "raw_extraction": {},
        }

        # Bank accounts (11-18 digits, excluding 10-digit phone numbers)
        # Using negative lookbehind to avoid matching within longer numbers
        bank_matches = re.findall(r"(?<!\d)\d{11,18}(?!\d)", message)
        result["bankAccounts"] = bank_matches

        # UPI IDs
        upi_matches = re.findall(r"\b[\w.-]+@[\w]+\b", message)
        result["upiIds"] = upi_matches

        # URLs
        url_matches = re.findall(r'https?://[^\s<>"{}|^`[\]]+', message)
        result["phishingLinks"] = url_matches

        # Phone numbers - UPDATED to preserve +91- format and avoid false positives
        # Match: +91-XXXXXXXXXX, +91 XXXXX XXXXX, or plain 10-digit numbers starting with 6-9
        # Using lookaround for boundaries to handle + sign correctly
        phone_matches = re.findall(
            r"(?<!\d)\+91[\s-]*[6-9]\d{9}(?!\d)|(?<!\d)[6-9]\d{9}(?!\d)", message
        )
        result["phoneNumbers"] = phone_matches

        # Log what regex found
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"🔧 [FALLBACK] Regex extraction - Banks: {len(result['bankAccounts'])}, "
            f"UPIs: {len(result['upiIds'])}, Phones: {result['phoneNumbers']}, "
            f"Links: {len(result['phishingLinks'])}"
        )

        return result

    async def analyze_conversation_for_termination(
        self, history: List[Dict], extracted_entities: Dict
    ) -> tuple:
        """
        Analyze if conversation should end
        Returns: (should_end: bool, reason: str, intel_completeness: float)
        """
        if not history:
            return False, "CONTINUE", 0.0

        conversation_text = "\n".join(
            [
                f"Turn {i + 1}: Scammer: {h.get('scammer_message', '')}, Victim: {h.get('response', '')}"
                for i, h in enumerate(history[-5:])
            ]
        )

        has_bank = len(extracted_entities.get("bankAccounts", [])) > 0
        has_upi = len(extracted_entities.get("upiIds", [])) > 0
        has_phone = len(extracted_entities.get("phoneNumbers", [])) > 0
        has_links = len(extracted_entities.get("phishingLinks", [])) > 0

        intel_score = sum([has_bank, has_upi, has_phone, has_links]) / 4.0

        prompt = f"""Analyze this scam conversation and determine if it should end:

CONVERSATION:
{conversation_text}

EXTRACTED INTELLIGENCE:
- Bank accounts: {len(extracted_entities.get("bankAccounts", []))}
- UPI IDs: {len(extracted_entities.get("upiIds", []))}
- Phone numbers: {len(extracted_entities.get("phoneNumbers", []))}
- Phishing links: {len(extracted_entities.get("phishingLinks", []))}

DECISION CRITERIA:
1. END if we have MAXIMIZED intelligence (>2 accounts/UPIs) OR >15 turns.
2. END if scammer is leaving/saying goodbye/frustrated.
3. END if scammer detected honeypot.
4. CONTINUE if we have < 2 accounts and scammer is still engaged (try to get more).
5. CONTINUE if the last message from US was a question or error claim (wait for their reply).

Respond in JSON:
{{
    "should_end": true/false,
    "reason": "INTEL_COMPLETE/SCAMMER_EXITED/SCAMMER_SUSPICIOUS/MAX_TURNS/CONTINUE",
    "intel_completeness": 0.0-1.0,
    "scammer_state": "cooperative/frustrated/suspicious/leaving",
    "recommended_action": "end_gracefully/continue_engaging/stall_for_time"
}}

Respond with ONLY the JSON."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a conversation analysis AI.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=200,
            )

            result_text = (response.choices[0].message.content or "").strip()
            result = json.loads(result_text)

            should_end = result.get("should_end", False)
            reason = result.get("reason", "CONTINUE")
            completeness = result.get("intel_completeness", intel_score)

            return should_end, reason, completeness

        except Exception as e:
            # Fallback logic - only end if we have substantial intel AND enough turns
            if intel_score >= 0.75 and len(history) >= 5:
                return True, "INTEL_COMPLETE", intel_score
            elif len(history) >= 20:
                return True, "MAX_TURNS", intel_score
            else:
                return False, "CONTINUE", intel_score
