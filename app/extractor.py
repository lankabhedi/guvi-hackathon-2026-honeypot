from groq import AsyncGroq
import os
import json
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ============================================================
# KNOWN UPI PSP HANDLES (Payment Service Provider)
# UPI IDs look like: name@handle (NO dots in handle)
# Emails look like: name@domain.tld (MUST have dot in domain)
# ============================================================
KNOWN_UPI_HANDLES = {
    # Major banks
    'upi', 'sbi', 'okaxis', 'okhdfcbank', 'okicici', 'oksbi', 'okpnb',
    'ybl', 'ibl', 'axl', 'icici', 'hdfcbank', 'pnb', 'kotak', 'indus',
    'bob', 'rbl', 'unionbank', 'canarabank', 'barodampay', 'idbi',
    'centralbank', 'indianbank', 'iob', 'mahb', 'syndicate', 'united',
    'vijb', 'denabank', 'corporation', 'obc', 'allbank', 'andhra',
    # Wallets / Payment apps
    'paytm', 'apl', 'freecharge', 'mobikwik', 'airtel', 'jio',
    'postbank', 'phonepe', 'gpay', 'amazonpay', 'slice', 'niyobank',
    # Generic / test handles
    'fakebank', 'fakeupi', 'bank', 'pay', 'axis', 'hdfc',
}

# Compiled regex patterns
PHONE_PATTERN = re.compile(
    r'(?<!\d)(?:\+91[\s\-]*)?[6-9]\d{9}(?!\d)'
)
BANK_ACCOUNT_PATTERN = re.compile(r'(?<!\d)\d{9,18}(?!\d)')
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|^`\[\]]+|www\.[^\s<>"{}|^`\[\]]+', re.IGNORECASE)
AT_PATTERN = re.compile(r'\b[\w.\-]+@[\w.\-]+\b')  # Catches both UPI and email
# Case ID requires 'case' keyword AND value must be at least 6 chars to avoid matching employee IDs
CASE_ID_PATTERN = re.compile(r'(?i)(?:case[-\s]?(?:id|number|no\.?)[/:\s]+)([A-Z0-9/\-]{6,})')
# Policy requires 'policy' keyword + value must be at least 3 chars
POLICY_PATTERN = re.compile(r'(?i)(?:policy[-\s#]?(?:no|number)?)[/:\s]+([A-Z0-9/\-]{3,})')
# Order requires 'order' keyword + value must be at least 3 chars (prevent matching 'ord' in normal words)
ORDER_PATTERN = re.compile(r'(?i)(?:order[-\s#]?(?:no|number|id)?)[/:\s]+([A-Z0-9/\-]{3,})')
AMOUNT_PATTERN = re.compile(r'(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d{2})?)', re.IGNORECASE)


# Real TLDs — if domain ends with one of these, it's always an email
REAL_TLDS = {
    'com', 'in', 'org', 'net', 'co', 'io', 'edu', 'gov', 'info', 'biz',
    'me', 'us', 'uk', 'ca', 'au', 'de', 'fr', 'jp', 'cn', 'ru', 'br',
    'xyz', 'online', 'site', 'tech', 'app', 'dev', 'cloud',
}


def classify_at_sign_match(match: str) -> str:
    """
    Classify an @-containing string as either 'upi' or 'email'.
    
    Rules (in order):
    1. If domain has a dot AND ends with a real TLD → ALWAYS email
       (e.g., security@sbi.com → email, even though 'sbi' is a UPI handle)
    2. If domain has a dot but NOT a real TLD → check UPI handles
    3. If domain has NO dot → UPI ID
    """
    if '@' not in match:
        return 'unknown'
    
    _, domain = match.rsplit('@', 1)
    domain_lower = domain.lower()
    
    # If domain has a dot
    if '.' in domain:
        # Get the TLD (last part after dot)
        tld = domain_lower.rsplit('.', 1)[-1]
        
        # If it ends with a real TLD, it's ALWAYS an email
        # This catches security@sbi.com, admin@icici.in, etc.
        if tld in REAL_TLDS:
            return 'email'
        
        # Non-standard TLD with dot — still likely email
        return 'email'
    
    # No dot in domain — it's a UPI ID (e.g., scammer@fakebank)
    return 'upi'


def regex_extract(text: str) -> Dict[str, Any]:
    """
    Instant regex-based entity extraction.
    Runs BEFORE the LLM call for speed and reliability.
    Properly classifies UPI IDs vs email addresses.
    """
    result = {
        "bankAccounts": [],
        "upiIds": [],
        "phishingLinks": [],
        "phoneNumbers": [],
        "emailAddresses": [],
        "caseIds": [],
        "policyNumbers": [],
        "orderNumbers": [],
        "amounts": [],
        "suspiciousKeywords": [],
    }
    
    # 1. URLs (extract first so we can exclude them from other patterns)
    url_matches = URL_PATTERN.findall(text)
    result["phishingLinks"] = list(set(url_matches))
    
    # 2. @ matches — classify as UPI or email
    at_matches = AT_PATTERN.findall(text)
    for match in at_matches:
        # Skip if it's part of a URL
        if any(match in url for url in url_matches):
            continue
        
        classification = classify_at_sign_match(match)
        if classification == 'upi':
            if match not in result["upiIds"]:
                result["upiIds"].append(match)
        elif classification == 'email':
            if match not in result["emailAddresses"]:
                result["emailAddresses"].append(match)
    
    # 3. Phone numbers (Indian format)
    phone_matches = PHONE_PATTERN.findall(text)
    # Also look for +91-XXXXX-XXXXX format with hyphens
    phone_hyphen = re.findall(r'\+91[\-\s]?\d{4,5}[\-\s]?\d{5,6}', text)
    all_phones = list(set(phone_matches + phone_hyphen))
    result["phoneNumbers"] = [p.strip() for p in all_phones if p.strip()]
    
    # 4. Bank accounts (9-18 digits, but not phone numbers)
    bank_matches = BANK_ACCOUNT_PATTERN.findall(text)
    # Filter out numbers that are phone numbers
    phone_digits = set(re.sub(r'[^\d]', '', p) for p in result["phoneNumbers"])
    result["bankAccounts"] = [
        b for b in bank_matches 
        if b not in phone_digits 
        and len(b) >= 9
        # Exclude 10-digit numbers starting with 6-9 (these are phone numbers)
        and not (len(b) == 10 and b[0] in '6789')
    ]
    
    # 5. Case IDs
    case_matches = CASE_ID_PATTERN.findall(text)
    result["caseIds"] = list(set(case_matches))
    
    # 6. Policy numbers
    policy_matches = POLICY_PATTERN.findall(text)
    result["policyNumbers"] = list(set(policy_matches))
    
    # 7. Order numbers
    order_matches = ORDER_PATTERN.findall(text)
    result["orderNumbers"] = list(set(order_matches))
    
    # 8. Amounts
    amount_matches = AMOUNT_PATTERN.findall(text)
    result["amounts"] = list(set(amount_matches))
    
    # 9. Suspicious keywords
    scam_keywords = [
        "urgent", "immediately", "blocked", "suspended", "verify", "click",
        "upi", "account", "otp", "kyc", "update", "bank",
        "police", "legal action", "arrest", "it department",
        "won", "lottery", "prize", "cashback", "reward",
        "job offer", "work from home", "part time",
        "anydesk", "teamviewer", "remote access",
    ]
    text_lower = text.lower()
    for kw in scam_keywords:
        if kw in text_lower and kw not in result["suspiciousKeywords"]:
            result["suspiciousKeywords"].append(kw)
    
    logger.info(
        f"🔧 [REGEX] Extraction - Banks: {result['bankAccounts']}, "
        f"UPIs: {result['upiIds']}, Phones: {result['phoneNumbers']}, "
        f"Emails: {result['emailAddresses']}, Links: {result['phishingLinks']}, "
        f"CaseIds: {result['caseIds']}, PolicyNums: {result['policyNumbers']}, "
        f"OrderNums: {result['orderNumbers']}"
    )
    
    return result


def merge_extraction_results(regex_result: Dict, llm_result: Dict) -> Dict[str, Any]:
    """Merge regex and LLM extraction results with deduplication."""
    merged = {}
    list_keys = [
        "bankAccounts", "upiIds", "phishingLinks", "phoneNumbers",
        "emailAddresses", "caseIds", "policyNumbers", "orderNumbers",
        "amounts", "suspiciousKeywords",
    ]
    
    for key in list_keys:
        regex_vals = regex_result.get(key, [])
        llm_vals = llm_result.get(key, [])
        # Union with deduplication (case-insensitive for some)
        seen = set()
        merged_list = []
        for val in regex_vals + llm_vals:
            if val and val.lower() not in seen:
                seen.add(val.lower())
                merged_list.append(val)
        merged[key] = merged_list
    
    # Post-merge: re-classify any emails that are actually UPI IDs
    reclassified_upis = []
    remaining_emails = []
    for email in merged.get("emailAddresses", []):
        if classify_at_sign_match(email) == 'upi':
            reclassified_upis.append(email)
        else:
            remaining_emails.append(email)
    
    if reclassified_upis:
        logger.info(f"🔄 [MERGE] Reclassified {reclassified_upis} from emails to UPI IDs")
        for upi in reclassified_upis:
            if upi.lower() not in {u.lower() for u in merged["upiIds"]}:
                merged["upiIds"].append(upi)
    merged["emailAddresses"] = remaining_emails
    
    # Similarly, reclassify any UPI IDs that are actually emails
    reclassified_emails = []
    remaining_upis = []
    for upi in merged.get("upiIds", []):
        if classify_at_sign_match(upi) == 'email':
            reclassified_emails.append(upi)
        else:
            remaining_upis.append(upi)
    
    if reclassified_emails:
        logger.info(f"🔄 [MERGE] Reclassified {reclassified_emails} from UPI IDs to emails")
        for email in reclassified_emails:
            if email.lower() not in {e.lower() for e in merged["emailAddresses"]}:
                merged["emailAddresses"].append(email)
    merged["upiIds"] = remaining_upis
    
    # Copy non-list fields
    merged["referenceNumbers"] = llm_result.get("referenceNumbers", []) or regex_result.get("referenceNumbers", [])
    merged["organizationClaimed"] = llm_result.get("organizationClaimed", "") or regex_result.get("organizationClaimed", "")
    merged["infoRequested"] = llm_result.get("infoRequested", []) or regex_result.get("infoRequested", [])
    merged["raw_extraction"] = llm_result.get("raw_extraction", {})
    
    return merged


class EntityExtractor:
    """AI-powered entity extraction using Groq LLM + regex-first layer"""

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
        Extract actionable intelligence using REGEX-FIRST + AI approach.
        1. Run instant regex extraction
        2. Run LLM extraction in parallel  
        3. Merge both results with deduplication
        """
        # STEP 1: Instant regex extraction
        conversation_text = self._build_conversation_text(current_message, history)
        regex_result = regex_extract(conversation_text)
        
        # STEP 2: LLM extraction
        llm_result = await self._llm_extract(current_message, history, conversation_text)
        
        # STEP 3: Merge results
        merged = merge_extraction_results(regex_result, llm_result)
        
        logger.info(
            f"🧠 [EXTRACTOR] 📦 FINAL MERGED OUTPUT:\n{json.dumps(merged, indent=2)}"
        )
        return merged

    async def _llm_extract(
        self, current_message: str, history: List[Dict], conversation_text: str
    ) -> Dict[str, Any]:
        """LLM-based entity extraction with improved UPI vs email prompt."""

        prompt = f"""You are extracting scammer details from a conversation.

CONVERSATION:
{conversation_text}

CRITICAL CLASSIFICATION RULES:
- UPI IDs look like: name@bankhandle (NO DOT after @) → put in upi_ids
- Emails look like: name@domain.com (HAS DOT after @) → put in emails  
- Example: "scammer.fraud@fakebank" → UPI ID (no dot after @)
- Example: "fraud@gmail.com" → Email (has dot after @)
- Example: "cashback.scam@fakeupi" → UPI ID (no dot after @)
- Example: "offers@fake-amazon-deals.com" → Email (has dot after @)

INSTRUCTIONS:
Extract ALL entities from the conversation text above.
For phone numbers, PRESERVE the full format including country code and hyphens.

Return this exact JSON structure:
{{
    "financial": {{
        "bank_accounts": [],
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
        "case_ids": [],
        "policy_numbers": [],
        "order_numbers": [],
        "organization_claimed": ""
    }},
    "extraction_summary": ""
}}

If no entities found, return empty arrays.
Return ONLY the JSON, no markdown."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an entity extraction AI. Return only valid JSON. Be precise. IMPORTANT: UPI IDs have NO dot after @ (e.g. user@bankname). Emails ALWAYS have a dot after @ (e.g. user@gmail.com).",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2048,
                top_p=1,
            )

            content = (response.choices[0].message.content or "").strip()

            logger.info(
                f"🧠 [EXTRACTOR] 🔍 RAW LLM OUTPUT:\n{'=' * 60}\n{content}\n{'=' * 60}"
            )

            # Clean thinking tags
            result_text = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", content, flags=re.DOTALL).strip()

            # Clean markdown code blocks
            result_text = re.sub(r"```json\s*", "", result_text, flags=re.IGNORECASE)
            result_text = re.sub(r"```\s*$", "", result_text, flags=re.MULTILINE)
            result_text = result_text.strip()

            try:
                extracted = json.loads(result_text)
                logger.info(
                    f"✅ [EXTRACTOR] ✨ LLM JSON PARSED:\n{json.dumps(extracted, indent=2)}"
                )
            except json.JSONDecodeError as e:
                logger.error(f"❌ [EXTRACTOR] JSON DECODE FAILED: {e}")
                return self._empty_result()

            # Flatten for GUVI format
            return self._flatten_for_guvi(extracted)

        except Exception as e:
            logger.error(f"❌ [EXTRACTOR] LLM extraction failed: {str(e)}")
            return self._empty_result()

    def _empty_result(self) -> Dict[str, Any]:
        """Return empty extraction result."""
        return {
            "bankAccounts": [],
            "upiIds": [],
            "phishingLinks": [],
            "phoneNumbers": [],
            "emailAddresses": [],
            "caseIds": [],
            "policyNumbers": [],
            "orderNumbers": [],
            "suspiciousKeywords": [],
            "amounts": [],
            "referenceNumbers": [],
            "organizationClaimed": "",
            "infoRequested": [],
            "raw_extraction": {},
        }

    def _build_conversation_text(
        self, current_message: str, history: List[Dict]
    ) -> str:
        """Build full conversation text for context"""
        conversation = []

        if history:
            for msg in history[-5:]:  # Last 5 turns
                scammer_msg = msg.get("scammer_message", "") or msg.get("text", "")
                response = msg.get("response", "")
                sender = msg.get("sender", "")
                if scammer_msg:
                    label = "Scammer" if sender != "user" else "Victim"
                    conversation.append(f"{label}: {scammer_msg}")
                if response:
                    conversation.append(f"Victim: {response}")

        conversation.append(f"Scammer (current): {current_message}")

        return "\n".join(conversation)

    def _flatten_for_guvi(self, extracted: Dict) -> Dict[str, Any]:
        """Flatten extracted entities for GUVI callback format with UPI/email reclassification"""
        flattened = self._empty_result()
        flattened["raw_extraction"] = extracted

        # Financial
        financial = extracted.get("financial", {})
        for acc in financial.get("bank_accounts", []):
            val = acc["value"] if isinstance(acc, dict) else acc
            if val and val not in flattened["bankAccounts"]:
                flattened["bankAccounts"].append(val)

        for upi in financial.get("upi_ids", []):
            val = upi["value"] if isinstance(upi, dict) else upi
            if val and val not in flattened["upiIds"]:
                flattened["upiIds"].append(val)

        # Contact
        contact = extracted.get("contact", {})
        for phone in contact.get("phone_numbers", []):
            val = phone["value"] if isinstance(phone, dict) else phone
            if val and val not in flattened["phoneNumbers"]:
                flattened["phoneNumbers"].append(val)

        for email in contact.get("emails", []):
            val = email["value"] if isinstance(email, dict) else email
            if val:
                # Re-classify: if no dot after @, it's a UPI ID
                if classify_at_sign_match(val) == 'upi':
                    if val not in flattened["upiIds"]:
                        flattened["upiIds"].append(val)
                else:
                    if val not in flattened["emailAddresses"]:
                        flattened["emailAddresses"].append(val)

        # Infrastructure
        infra = extracted.get("infrastructure", {})
        for link in infra.get("phishing_links", []):
            val = link["value"] if isinstance(link, dict) else link
            if val and val not in flattened["phishingLinks"]:
                flattened["phishingLinks"].append(val)

        # Operational
        operational = extracted.get("operational", {})
        for amt in operational.get("amounts", []):
            val = amt["value"] if isinstance(amt, dict) else amt
            if val:
                flattened["amounts"].append(val)

        for ref in operational.get("reference_numbers", []):
            val = ref["value"] if isinstance(ref, dict) else ref
            if val:
                flattened["referenceNumbers"].append(val)

        flattened["organizationClaimed"] = operational.get("organization_claimed", "")

        for case_id in operational.get("case_ids", []):
            val = case_id["value"] if isinstance(case_id, dict) else case_id
            if val and val not in flattened["caseIds"]:
                flattened["caseIds"].append(val)

        for pol_num in operational.get("policy_numbers", []):
            val = pol_num["value"] if isinstance(pol_num, dict) else pol_num
            if val and val not in flattened["policyNumbers"]:
                flattened["policyNumbers"].append(val)

        for ord_num in operational.get("order_numbers", []):
            val = ord_num["value"] if isinstance(ord_num, dict) else ord_num
            if val and val not in flattened["orderNumbers"]:
                flattened["orderNumbers"].append(val)

        # What they asked for
        victim = extracted.get("victim_targeted", {})
        flattened["infoRequested"] = victim.get("info_requested", [])

        # Suspicious keywords
        summary = extracted.get("extraction_summary", "")
        if summary:
            keywords = ["urgent", "immediately", "blocked", "verify", "upi", "account", "otp", "kyc", "suspended"]
            for kw in keywords:
                if kw in summary.lower() and kw not in flattened["suspiciousKeywords"]:
                    flattened["suspiciousKeywords"].append(kw)

        return flattened

    async def analyze_conversation_for_termination(
        self, history: List[Dict], extracted_entities: Dict
    ) -> tuple:
        """
        Analyze if conversation should end
        Returns: (should_end: bool, reason: str, intel_completeness: float)
        """
        if not history:
            return False, "CONTINUE", 0.0

        has_bank = len(extracted_entities.get("bankAccounts", [])) > 0
        has_upi = len(extracted_entities.get("upiIds", [])) > 0
        has_phone = len(extracted_entities.get("phoneNumbers", [])) > 0
        has_links = len(extracted_entities.get("phishingLinks", [])) > 0

        intel_score = sum([has_bank, has_upi, has_phone, has_links]) / 4.0

        # Simple logic - no LLM needed for termination decisions
        if intel_score >= 0.75 and len(history) >= 5:
            return True, "INTEL_COMPLETE", intel_score
        elif len(history) >= 20:
            return True, "MAX_TURNS", intel_score
        else:
            return False, "CONTINUE", intel_score
