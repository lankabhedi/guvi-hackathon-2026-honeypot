from groq import AsyncGroq
import os
import json
from typing import Dict, Any, Tuple


class ScamDetector:
    """AI-powered scam detection using Groq LLM"""

    def __init__(self):
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "openai/gpt-oss-20b"

    async def analyze(
        self, message: str, conversation_history: list | None = None
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Analyze message for scam intent using AI
        Returns: (is_scam, confidence, analysis_dict)
        """
        history_context = (
            self._format_history(conversation_history) if conversation_history else ""
        )

        prompt = f"""You are a fraud detection expert specializing in Indian financial scams.

Analyze this message for scam intent:
Message: "{message}"
{history_context}

SCAM TYPES TO CLASSIFY:
- UPI_FRAUD: Payment requests, UPI ID demands, "send money to receive money"
- PHISHING: Suspicious links, verification requests, fake login pages
- KYC_SCAM: Account suspension threats, update KYC/PAN/Aadhar
- LOTTERY: Prize notifications, "you won", lottery scams
- JOB_SCAM: Work from home offers, part-time jobs, upfront fees
- SEXTORTION: Video call threats, blackmail, "your video is recorded"
- FAMILY_EMERGENCY: Relative in hospital, accident, urgent money needed
- INVESTMENT: Crypto schemes, double money schemes, trading tips
- LEGITIMATE: Genuine bank communication, authentic offers

TACTICS TO IDENTIFY:
- Urgency: "immediately", "today", "urgent", "hurry"
- Authority: "bank manager", "police", "IT department", "RBI"
- Fear: "account blocked", "legal action", "arrest warrant"
- Reward: "you won", "cash prize", "bonus", "lucky winner"
- Trust: "beta", "sir/ma'am", respectful language to build trust
- Technical: "verify", "update", "link", "download app"

Respond in this exact JSON format:
{{
    "is_scam": true/false,
    "scam_type": "UPI_FRAUD/PHISHING/KYC_SCAM/LOTTERY/JOB_SCAM/SEXTORTION/FAMILY_EMERGENCY/INVESTMENT/LEGITIMATE",
    "confidence": 0.0-1.0,
    "tactics": ["urgency", "authority", "fear", "reward", "trust", "technical"],
    "risk_level": "LOW/MEDIUM/HIGH/CRITICAL",
    "indian_context": true/false,
    "reasoning": "Brief explanation of why this is/isn't a scam",
    "suggested_persona_mood": "NEUTRAL/WORRIED/EXCITED/CONFUSED/COOPERATIVE"
}}

Respond with ONLY the JSON, no other text."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a fraud detection AI. Return only valid JSON. Be precise and conservative in scam detection.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,  # Recommended for Qwen 3 Thinking Mode
                max_tokens=2048,  # Thinking needs more tokens
                # reasoning_format="parsed",  # REMOVED due to library incompatibility
            )

            # Log reasoning for debugging if available
            # if hasattr(response.choices[0].message, "reasoning"):
            #     print(f"🧠 Detector Reasoning: {response.choices[0].message.reasoning}")

            content = (response.choices[0].message.content or "").strip()

            # Clean <think> tags for detector too
            import re

            result_text = re.sub(
                r"<think>.*?</think>", "", content, flags=re.DOTALL
            ).strip()

            # Extract JSON from response
            try:
                analysis = json.loads(result_text)
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                analysis = self._parse_fallback(result_text, message)

            is_scam = analysis.get("is_scam", False)
            confidence = analysis.get("confidence", 0.0)

            return is_scam, confidence, analysis

        except Exception as e:
            # Fallback to basic analysis if API fails
            return self._fallback_analysis(message)

    def _format_history(self, history: list) -> str:
        """Format conversation history for context"""
        if not history:
            return ""

        context = "\nPrevious messages:\n"
        for msg in history[-3:]:  # Last 3 messages
            sender = msg.get("sender", "unknown")
            text = msg.get("text", "")
            context += f"- {sender}: {text}\n"
        return context

    def _parse_fallback(self, text: str, message: str) -> Dict[str, Any]:
        """Parse response if JSON extraction fails"""
        text_lower = message.lower()

        # Basic detection logic as fallback
        scam_indicators = [
            "urgent",
            "immediately",
            "blocked",
            "suspended",
            "verify",
            "click",
            "upi",
            "account number",
            "won",
            "lottery",
            "prize",
            "kyc",
            "update",
            "bank",
            "sbi",
            "hdfc",
            "icici",
            "police",
            "it department",
        ]

        indicator_count = sum(
            1 for indicator in scam_indicators if indicator in text_lower
        )
        is_scam = indicator_count >= 2

        return {
            "is_scam": is_scam,
            "scam_type": "UNKNOWN",
            "confidence": min(indicator_count * 0.2, 0.8),
            "tactics": [],
            "risk_level": "MEDIUM" if is_scam else "LOW",
            "indian_context": True,
            "reasoning": "Fallback analysis based on keyword matching",
            "suggested_persona_mood": "NEUTRAL",
        }

    def _fallback_analysis(self, message: str) -> Tuple[bool, float, Dict[str, Any]]:
        """Basic fallback when Groq API fails"""
        text_lower = message.lower()

        scam_keywords = [
            "urgent",
            "blocked",
            "verify",
            "upi",
            "account",
            "won",
            "prize",
        ]
        matches = sum(1 for kw in scam_keywords if kw in text_lower)

        is_scam = matches >= 2
        confidence = min(matches * 0.2, 0.7)

        analysis = {
            "is_scam": is_scam,
            "scam_type": "UNKNOWN",
            "confidence": confidence,
            "tactics": [],
            "risk_level": "MEDIUM" if is_scam else "LOW",
            "indian_context": True,
            "reasoning": "API failure - fallback to keyword matching",
            "suggested_persona_mood": "NEUTRAL",
        }

        return is_scam, confidence, analysis
