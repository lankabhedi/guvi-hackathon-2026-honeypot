from groq import AsyncGroq
import os
import json
from typing import List, Dict, Any


class EntityExtractor:
    """AI-powered entity extraction using Groq LLM - extracts ONLY scammer-provided information"""

    def __init__(self):
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "openai/gpt-oss-20b"

    async def extract_entities(
        self, current_message: str, history: List[Dict]
    ) -> Dict[str, Any]:
        """
        Extract actionable intelligence from conversation using AI
        Only extracts information the SCAMMER provided, not victim details
        """
        conversation_text = self._build_conversation_text(current_message, history)

        prompt = f"""You are a fraud investigation AI. Extract actionable intelligence from this scam conversation.

CONVERSATION:
{conversation_text}

INSTRUCTIONS:
1. Extract ONLY information the SCAMMER provided (not what they asked from victim)
2. Focus on financial details, contact info, and infrastructure
3. Be precise - only extract confirmed scammer data
4. If something is unclear or could be legitimate, mark confidence lower

EXTRACT THESE ENTITIES:

Financial Details (scammer's receiving accounts):
- bank_accounts: Account numbers provided by scammer for receiving money
- upi_ids: UPI IDs provided by scammer (format: username@provider)
- ifsc_codes: IFSC codes provided
- wallet_ids: Paytm/PhonePe/GooglePay wallet IDs

Contact Information (how to reach scammer):
- phone_numbers: Phone numbers scammer provided or called from
- whatsapp_numbers: WhatsApp numbers shared
- emails: Email addresses provided by scammer
- telegram_handles: Telegram usernames

Infrastructure (scammer's tools):
- phishing_links: URLs scammer asked victim to click
- malicious_apps: App names or APK links
- fake_websites: Domain names of fake sites

Operational Details:
- amounts: Money amounts requested (e.g., "5000 rupees", "processing fee of 200")
- reference_numbers: Transaction IDs, reference codes, ticket numbers
- organization_claimed: Who they claim to be ("SBI Bank", "Amazon", etc.)

Victims' Information (what they asked for - for context only):
- info_requested: List what they asked victim to provide

CONFIDENCE SCORES:
- 0.9-1.0: Definitely scammer data (explicitly stated)
- 0.7-0.8: Likely scammer data (strong context)
- 0.5-0.6: Possible scammer data (unclear)
- 0.0-0.4: Uncertain or likely legitimate

Return this exact JSON structure:
{{
    "financial": {{
        "bank_accounts": [{{"value": "FULL_ACCOUNT_NUMBER_HERE", "confidence": 0.95, "context": "send money to this account"}}],
        "upi_ids": [],
        "ifsc_codes": [],
        "wallet_ids": []
    }},
    "contact": {{
        "phone_numbers": [],
        "whatsapp_numbers": [],
        "emails": [],
        "telegram_handles": []
    }},
    "infrastructure": {{
        "phishing_links": [],
        "malicious_apps": [],
        "fake_websites": []
    }},
    "operational": {{
        "amounts": [],
        "reference_numbers": [],
        "organization_claimed": ""
    }},
    "victim_targeted": {{
        "info_requested": ["UPI ID", "OTP", "Account number"]
    }},
    "extraction_summary": "Brief summary of what was extracted"
}}

CRITICAL RULES:
1. ONLY extract what the SCAMMER provided (their accounts, their numbers)
2. DO NOT extract what they asked the victim to provide
3. Include confidence scores for every extraction
4. If no entities found, return empty arrays
5. Be conservative - only high confidence extractions
6. EXTRACT EXACTLY AS WRITTEN. Do not alter, truncate, or normalize numbers. Preserve full 16-digit account numbers.
7. THINKING PROCESS: Be concise. Don't over-analyze.

Return ONLY the JSON, no other text."""

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

        # Bank accounts (9-18 digits)
        bank_matches = re.findall(r"\b\d{9,18}\b", message)
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
            # Fallback logic
            if intel_score >= 0.75:
                return True, "INTEL_COMPLETE", intel_score
            elif len(history) >= 20:
                return True, "MAX_TURNS", intel_score
            else:
                return False, "CONTINUE", intel_score
