from groq import AsyncGroq
import os
import json
from typing import List, Dict, Any


class EntityExtractor:
    """AI-powered entity extraction using Groq LLM - extracts ONLY scammer-provided information"""

    def __init__(self):
        self._client = None
        self.model = "llama-3.1-8b-instant"

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
- phoneNumber: +91-XXXXXXXXXX
- phishing link: http://example.com
- suspicious keyword: urgent, verify, blocked

Extract the VALUES, not the field names.

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
                temperature=0.6,  # Qwen 3 Thinking Mode
                max_tokens=2048,  # Needs space to think
                # reasoning_format="parsed" # REMOVED due to library incompatibility
            )

            content = (response.choices[0].message.content or "").strip()

            # Clean <think> tags for extractor too
            import re

            result_text = re.sub(
                r"<think>.*?</think>", "", content, flags=re.DOTALL
            ).strip()

            try:
                extracted = json.loads(result_text)
            except json.JSONDecodeError:
                extracted = self._fallback_extraction(current_message)

            # Flatten for GUVI format
            flattened = self._flatten_for_guvi(extracted)
            return flattened

        except Exception as e:
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
            if acc.get("confidence", 0) > 0.6:
                flattened["bankAccounts"].append(acc["value"])

        for upi in financial.get("upi_ids", []):
            if upi.get("confidence", 0) > 0.6:
                flattened["upiIds"].append(upi["value"])

        # Contact
        contact = extracted.get("contact", {})
        for phone in contact.get("phone_numbers", []):
            if phone.get("confidence", 0) > 0.6:
                flattened["phoneNumbers"].append(phone["value"])

        # Infrastructure
        infra = extracted.get("infrastructure", {})
        for link in infra.get("phishing_links", []):
            if link.get("confidence", 0) > 0.6:
                flattened["phishingLinks"].append(link["value"])

        # Operational
        operational = extracted.get("operational", {})
        for amt in operational.get("amounts", []):
            if amt.get("confidence", 0) > 0.6:
                flattened["amounts"].append(amt["value"])

        for ref in operational.get("reference_numbers", []):
            if ref.get("confidence", 0) > 0.6:
                flattened["referenceNumbers"].append(ref["value"])

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
        bank_matches = re.findall(r"\b\d{11,18}\b", message)
        result["bankAccounts"] = bank_matches

        # UPI IDs
        upi_matches = re.findall(r"\b[\w.-]+@[\w]+\b", message)
        result["upiIds"] = upi_matches

        # URLs
        url_matches = re.findall(r'https?://[^\s<>"{}|^`[\]]+', message)
        result["phishingLinks"] = url_matches

        # Phone numbers
        phone_matches = re.findall(r"(?:\+91)?\s*[6-9]\d{9}", message)
        result["phoneNumbers"] = phone_matches

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
