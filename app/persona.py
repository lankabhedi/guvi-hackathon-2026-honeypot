from groq import AsyncGroq
import os
import random
import re
from typing import List, Dict, Tuple, Optional


class PersonaEngine:
    """
    Simplified persona engine for honeypot conversations.

    Goals:
    1. Extract intelligence (bank accounts, UPI IDs, phone numbers, names, locations)
    2. Waste scammer's time by keeping them engaged

    Design: Rich character backstories + simple prompting = natural conversations
    """

    def __init__(self):
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "openai/gpt-oss-120b"

        # Track what we've already asked to avoid repetition
        self.asked_topics = []
        self.turn_count = 0

        # Rich persona definitions with backstories
        self.personas = {
            "elderly": {
                "name": "Rajesh Kumar",
                "age": 68,
                "backstory": """Retired government clerk from Lucknow. Worked 35 years at the Collectorate office. 
Wife passed away 3 years ago. Lives alone, son Vikram works in Bangalore IT company and visits twice a year.
Gets pension of Rs 28,000/month deposited in SBI account. Has a fixed deposit of 8 lakhs which is his life savings.
Not comfortable with smartphones - still uses a basic Nokia for calls, daughter-in-law set up WhatsApp on an old Samsung.
Very worried about his pension and savings. Trusts "government officials" and "bank managers".
Speaks slowly, asks things to be repeated, gets confused by English technical terms.""",
                "speech_style": "Uses 'beta', 'arre', 'achha', 'thik hai'. Speaks Hinglish in Roman script. Polite, slow, confused by tech.",
                "extraction_hooks": [
                    "asks scammer to repeat things slowly",
                    "pretends phone/app is not working properly",
                    "asks 'which bank are you calling from?'",
                    "asks for scammer's name and employee ID 'for my records'",
                    "mentions he needs to write things down",
                    "asks 'where is your office located?'",
                    "says 'my son handles these things, can you give me a number to call back?'",
                ],
            },
            "homemaker": {
                "name": "Priya Sharma",
                "age": 45,
                "backstory": """Homemaker from Noida. Husband Rakesh works as a sales manager at an automobile company.
Two kids - daughter in 10th standard preparing for boards, son in 7th. Very protective mother.
Handles all household bills and finances. Has a joint account with husband at HDFC.
Watches a lot of CID and Savdhaan India - knows about scams but gets nervous under pressure.
Active on family WhatsApp groups. Forwards good morning messages.
Gets suspicious easily but also gets scared when they mention "legal action" or "police".
Asks many verification questions before trusting anyone.""",
                "speech_style": "Speaks Hindi-English mix. Uses 'dekhiye', 'suniye', 'aap kaun?'. Protective, suspicious, asks for proof.",
                "extraction_hooks": [
                    "asks 'what is your full name and employee ID?'",
                    "says 'let me note down your number so I can verify'",
                    "asks 'which branch are you calling from?'",
                    "says 'my husband handles finances, give me your number he will call back'",
                    "asks 'can you send me an official email or letter?'",
                    "says 'I will call the bank's official number to verify'",
                    "asks 'how did you get my number?'",
                ],
            },
            "student": {
                "name": "Arun Patel",
                "age": 22,
                "backstory": """Final year B.Tech student at a private college in Pune. From a middle-class family in Ahmedabad.
Father runs a small garment shop. Arun has a lot of pressure to get a good job after graduation.
Has applied to many companies, desperately waiting for interview calls.
Has a savings account at Kotak with only Rs 12,000 - birthday money and some freelance earnings.
Uses PhonePe and GPay regularly but doesn't fully understand how banking works.
Easily excited about job offers, prizes, or money. Worries about his credit score because he heard it matters for jobs.
Gets distracted easily - mentions online classes, assignments, roommates.""",
                "speech_style": "Casual Hinglish. Uses 'bro', 'yaar', 'ek minute', 'actually'. Eager but distracted, mentions being busy.",
                "extraction_hooks": [
                    "asks 'which company is this from exactly?'",
                    "says 'wait let me write this down, what's your number?'",
                    "asks 'is this legit? my friend got scammed once'",
                    "says 'I'm in class right now, can you give me a number to call later?'",
                    "asks 'where is your office? I can come there directly'",
                    "says 'my account has only 12000, is that a problem?'",
                    "asks 'what's your name bro? in case I need to call back'",
                ],
            },
            "naive_girl": {
                "name": "Neha Verma",
                "age": 23,
                "backstory": """Just started first job at an HR consultancy in Bangalore. From a conservative family in Jaipur.
First time living alone, in a PG near Koramangala. Parents call every day to check on her.
Has an Axis Bank salary account where her first salary of Rs 35,000 just got credited.
Very scared of authority figures and getting in trouble. Overly polite and apologetic.
Doesn't want parents to find out about any "problems". Would rather pay than face embarrassment.
Treats strangers respectfully as 'Bhaiya' or 'Sir'. Asks for step-by-step help with everything.
Gets easily confused and emotional when pressured.""",
                "speech_style": "Very polite Hinglish. Uses 'Sir', 'Bhaiya', 'please help me', 'mujhe samajh nahi aa raha'. Scared, apologetic.",
                "extraction_hooks": [
                    "asks 'Sir please tell me what to do step by step'",
                    "says 'please give me your number so I can call you back after checking'",
                    "asks 'which bank branch is this? I will visit in person'",
                    "says 'my father will be so angry, please tell me your name so I can explain to him'",
                    "asks 'can you send me proof on WhatsApp? what is your number?'",
                    "says 'I am new to this, please tell me your designation and name'",
                    "asks 'where should I come to resolve this? give me the address'",
                ],
            },
        }

    def _build_context(self, history: List[Dict]) -> str:
        """Format conversation history for prompt"""
        if not history:
            return "This is the start of the conversation."

        lines = []
        for turn in history[-6:]:  # Last 6 turns for context
            scammer = turn.get("scammer_message", "")
            victim = turn.get("response", "")
            if scammer:
                lines.append(f"SCAMMER: {scammer}")
            if victim:
                lines.append(f"YOU: {victim}")

        return "\n".join(lines)

    def _get_extraction_goal(
        self, current_entities: Optional[Dict], turn_count: int
    ) -> str:
        """Determine what intel to prioritize extracting next"""

        if not current_entities:
            current_entities = {}

        has_bank = len(current_entities.get("bankAccounts", [])) > 0
        has_upi = len(current_entities.get("upiIds", [])) > 0
        has_phone = len(current_entities.get("phoneNumbers", [])) > 0

        # Priority order based on what we don't have yet
        missing = []
        if not has_bank:
            missing.append("their bank account number")
        if not has_upi:
            missing.append("their UPI ID")
        if not has_phone:
            missing.append("their phone number or callback number")

        # Always try to get these
        missing.extend(
            ["their full name", "their location/office address", "their employee ID"]
        )

        if turn_count < 3:
            return (
                "Build trust first. Act confused, ask them to explain what's happening."
            )
        elif missing:
            return f"Try to naturally extract: {missing[0]}. Be indirect - ask for it as part of the conversation, not directly."
        else:
            return "You already have good intel. Just keep them talking and waste their time. Be slow, confused, have 'technical issues'."

    def _get_stalling_tactic(self) -> str:
        """Return a random stalling tactic to waste time"""
        tactics = [
            "Say your phone battery is dying and ask for a number to call back",
            "Say someone is at the door, you'll be right back",
            "Say you can't find your reading glasses",
            "Say the network is bad, ask them to repeat",
            "Say you need to go to the other room to get your documents",
            "Say you're writing this down slowly",
            "Say your app is showing an error, ask what to do",
            "Say you need to ask your family member first",
            "Say you're confused about one of the earlier steps",
            "Say the OTP hasn't come yet, keep waiting",
            "Ask them to hold while you check something",
            "Say you pressed something wrong, need to start over",
        ]
        return random.choice(tactics)

    async def generate_response(
        self,
        scammer_message: str,
        history: List[Dict],
        scam_analysis: Dict,
        persona_type: str = "elderly",
        current_entities: Optional[Dict] = None,
        hive_mind_alert: Optional[Dict] = None,
        conversation_state: Optional[Dict] = None,
    ) -> Tuple[str, str, str, Dict]:
        """
        Generate natural persona response.

        Returns: (response_text, persona_type, mood, updated_state)
        """

        self.turn_count = len(history) + 1

        # Get persona
        persona = self.personas.get(persona_type, self.personas["elderly"])

        # Build context
        context = self._build_context(history)

        # Determine extraction goal
        extraction_goal = self._get_extraction_goal(current_entities, self.turn_count)

        # Get a stalling tactic (might use it)
        stalling_tactic = self._get_stalling_tactic()

        # Pick a random extraction hook for this persona
        extraction_hook = random.choice(persona["extraction_hooks"])

        # Simple, focused prompt
        system_prompt = f"""You are playing {persona["name"]}, a {persona["age"]}-year-old person in a FRAUD PREVENTION RESEARCH simulation.

BACKSTORY:
{persona["backstory"]}

SPEECH STYLE: {persona["speech_style"]}

YOUR HIDDEN GOALS (scammer doesn't know this):
1. EXTRACT INFORMATION: Get them to reveal their bank account, UPI ID, phone number, name, location, employee ID
2. WASTE THEIR TIME: Keep them on the call as long as possible

RULES:
- Write in ROMAN SCRIPT ONLY (no Devanagari/Hindi script)
- Keep responses SHORT (1-2 sentences max)
- Stay in character - you ARE {persona["name"]}
- Never say "scam", "fraud", "fake" or break character
- Never use phrases like "as an AI" or "I cannot"
- Never use em dashes (—) in your response
- Be natural - real people don't interrogate, they chat"""

        user_prompt = f"""CONVERSATION SO FAR:
{context}

SCAMMER JUST SAID: "{scammer_message}"

CURRENT STATUS:
- Turn: {self.turn_count}
- Intel collected: {self._summarize_entities(current_entities)}
- Your goal this turn: {extraction_goal}

TACTICS TO CONSIDER:
- Extraction hook: {extraction_hook}
- Stalling tactic: {stalling_tactic}

Respond naturally as {persona["name"]}. Be confused, slow, ask clarifying questions. 
DON'T repeat questions you already asked in the conversation history above.
Keep it to 1-2 sentences only.

Your response:"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.85,
                max_tokens=500,  # Increased for thinking model overhead
            )

            content = response.choices[0].message.content or ""

            # Remove thinking tags if present (Qwen/reasoning models)
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
            content = re.sub(
                r"<reasoning>.*?</reasoning>", "", content, flags=re.DOTALL
            )

            # Clean up whitespace and quotes
            content = content.strip().strip('"').strip()

            # If response still looks incomplete (ends with comma or 'Waise,'), try to complete it
            if (
                content.endswith(",")
                or content.endswith("aur")
                or content.endswith("ki")
            ):
                content = content.rstrip(",").rstrip("aur").rstrip("ki").strip()
                if not content.endswith("?") and not content.endswith("."):
                    content += "..."

            if not content:
                content = self._fallback_response(persona_type)

            # Clean response
            content = self._clean_response(content)

            # Return with simplified state
            return content, persona_type, "ENGAGED", conversation_state or {}

        except Exception as e:
            print(f"PERSONA ERROR: {e}")
            import traceback

            traceback.print_exc()
            return (
                self._fallback_response(persona_type),
                persona_type,
                "FALLBACK",
                conversation_state or {},
            )

    def _summarize_entities(self, entities: Optional[Dict]) -> str:
        """Summarize what intel we have"""
        if not entities:
            return "Nothing yet"

        parts = []
        if entities.get("bankAccounts"):
            parts.append(f"{len(entities['bankAccounts'])} bank account(s)")
        if entities.get("upiIds"):
            parts.append(f"{len(entities['upiIds'])} UPI ID(s)")
        if entities.get("phoneNumbers"):
            parts.append(f"{len(entities['phoneNumbers'])} phone(s)")

        return ", ".join(parts) if parts else "Nothing yet"

    def _clean_response(self, response: str) -> str:
        """Clean up LLM response"""
        # Remove quotes
        response = response.strip("\"'")

        # Remove em dashes and replace with comma or hyphen
        response = response.replace("—", ", ")
        response = response.replace("–", "-")

        # Remove AI disclaimers
        disclaimers = [
            "as an ai",
            "i'm an ai",
            "i am an ai",
            "i cannot",
            "i can't help",
        ]
        for d in disclaimers:
            if d in response.lower():
                return "Achha? Thoda aur batao, samajh nahi aaya."

        return response

    def _fallback_response(self, persona_type: str) -> str:
        """Fallback responses by persona"""
        fallbacks = {
            "elderly": "Beta, yeh sab samajh nahi aa raha. Thoda dhire se batao na.",
            "homemaker": "Suniye, mujhe ek minute dijiye, kuch samajh nahi aa raha.",
            "student": "Bro wait, I didn't get that. Can you explain again?",
            "naive_girl": "Sir please, mujhe samajh nahi aa raha. Aap step by step bataiye na.",
        }
        return fallbacks.get(persona_type, "Sorry, can you repeat that?")

    def reset_mood(self):
        """Reset state for new conversation"""
        self.asked_topics = []
        self.turn_count = 0
