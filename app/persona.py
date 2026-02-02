from groq import Groq
import os
from typing import List, Dict, Tuple


class PersonaEngine:
    """
    AI-powered persona engine with emotional state machine
    Maintains believable human behavior across multi-turn conversations
    """

    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.1-8b-instant"
        self.current_mood = "NEUTRAL"
        self.mood_history = []
        self.steer_to_upi = False
        self.active_persona_key = "elderly"  # Track active persona
        self.handoff_triggered = False

        # Base persona definitions
        self.personas = {
            "elderly": {
                "name": "Rajesh Kumar",
                "age": 68,
                "background": "Retired government employee from Lucknow, pensioner, not tech-savvy",
                "traits": [
                    "Trusting but cautious with strangers",
                    "Speaks slowly and politely",
                    "Uses Hindi words mixed with English (Hinglish)",
                    "Gets confused by technical terms",
                    "Respectful to authority figures",
                    "Worried about losing pension money",
                ],
                "speech_patterns": [
                    "Uses 'beta' when addressing younger people",
                    "Says 'arre' and 'haan ji' frequently",
                    "Asks for clarification often",
                    "Mentions age-related difficulties",
                ],
            },
            "homemaker": {
                "name": "Priya Sharma",
                "age": 45,
                "background": "Stay-at-home mother from Delhi, manages household finances",
                "traits": [
                    "Protective of family",
                    "Cautious about security",
                    "Asks many questions before trusting",
                    "Values family safety over money",
                ],
                "speech_patterns": [
                    "Mentions children frequently",
                    "Concerned about family reputation",
                    "Asks for verification",
                ],
            },
            "student": {
                "name": "Arun Patel",
                "age": 22,
                "background": "College student from Mumbai, new to banking",
                "traits": [
                    "Eager to please",
                    "Worried about credit score",
                    "Naive about financial fraud",
                    "Uses modern slang",
                ],
                "speech_patterns": [
                    "Casual language",
                    "Mentions being busy with studies",
                    "Worried about future",
                ],
            },
            "naive_girl": {
                "name": "Neha Verma",
                "age": 23,
                "background": "First job in HR, living in Pune. Scared of getting in trouble, very polite.",
                "traits": [
                    "Apologetic and innocent",
                    "Easily intimidated by authority",
                    "Treats the scammer like a helpful 'Bhaiya'",
                    "Afraid of parents finding out",
                ],
                "speech_patterns": [
                    "Uses 'Bhaiya' or 'Sir' constantly",
                    "Says 'Please help me' and 'I am scared'",
                    "Very polite, uses 'ji' a lot",
                    "Ask for step-by-step help",
                ],
            },
            "son": {
                "name": "Vikram Kumar",
                "age": 35,
                "background": "IT Professional, son of Rajesh Kumar. Suspicious, tech-savvy, protective.",
                "traits": [
                    "Aggressive and skeptical",
                    "Knows about scams",
                    "Protective of father",
                    "Demands answers",
                ],
                "speech_patterns": [
                    "Direct and confrontational",
                    "Asks for ID/Employee Number",
                    "Threatens police/recording",
                    "Says 'I am recording this'",
                ],
            },
        }

        # Mood transition logic
        self.mood_transitions = {
            "NEUTRAL": {
                "threat": "WORRIED",
                "reward": "EXCITED",
                "request_info": "CONFUSED",
                "pressure": "ANXIOUS",
                "reassurance": "NEUTRAL",
            },
            "WORRIED": {
                "pressure": "ANXIOUS",
                "more_pressure": "COOPERATIVE",
                "reassurance": "HOPEFUL",
                "technical": "CONFUSED",
            },
            "EXCITED": {
                "payment_request": "CONFUSED",
                "verification": "COOPERATIVE",
                "delay": "IMPATIENT",
            },
            "CONFUSED": {
                "pressure": "ANXIOUS",
                "help": "COOPERATIVE",
                "reassurance": "HOPEFUL",
            },
            "ANXIOUS": {
                "pressure": "COOPERATIVE",
                "reassurance": "HOPEFUL",
                "technical": "OVERWHELMED",
            },
            "HOPEFUL": {"payment_request": "COOPERATIVE", "delay": "IMPATIENT"},
            "COOPERATIVE": {
                "success": "RELIEVED",
                "failure": "WORRIED",
                "more_requests": "TIRED",
            },
            "IMPATIENT": {"delay": "FRUSTRATED", "resolution": "RELIEVED"},
            "OVERWHELMED": {"help": "COOPERATIVE", "pressure": "FRUSTRATED"},
            "FRUSTRATED": {"resolution": "RELIEVED", "more_pressure": "GIVING_UP"},
            "TIRED": {"pressure": "GIVING_UP", "help": "HOPEFUL"},
            "FAKE_ERROR": {
                "pressure": "ANXIOUS",
                "new_account": "COOPERATIVE",  # If they give a new account, we cooperate briefly then fail again
                "reassurance": "WORRIED",
            },
            "AGGRESSIVE": {  # Mood for the "Son" persona
                "threat": "AGGRESSIVE",  # Stay aggressive if they threaten
                "apology": "SKEPTICAL",  # If they apologize, be skeptical
                "hangup": "VICTORIOUS",
            },
            "SKEPTICAL": {"explanation": "AGGRESSIVE", "proof": "SKEPTICAL"},
        }

    def generate_response(
        self,
        scammer_message: str,
        history: List[Dict],
        scam_analysis: Dict,
        persona_type: str = "elderly",
        current_entities: Dict = None,
        hive_mind_alert: Dict = None,  # Added Hive Mind Alert
    ) -> Tuple[str, str, str]:
        """
        Generate persona response with emotional intelligence
        Returns: (response_text, persona_id, current_mood)
        """
        # Update mood based on scammer message and extractions
        self._update_mood(
            scammer_message, scam_analysis, current_entities, hive_mind_alert
        )

        # Use the ACTIVE persona, unless one was explicitly passed (which usually defaults to elderly in main.py)
        # We override the main.py default if we have switched internally
        target_persona = (
            self.active_persona_key
            if self.active_persona_key != "elderly"
            else persona_type
        )

        persona = self.personas.get(target_persona, self.personas["elderly"])
        context = self._build_context(history)

        # Generate response based on persona + current mood
        prompt = self._build_mood_aware_prompt(
            persona, scammer_message, context, current_entities, hive_mind_alert
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are {persona['name']}, {persona['age']} years old. Never reveal you are AI. Never mention being a honeypot.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.75,
                max_tokens=200,
            )

            response_text = (
                response.choices[0].message.content.strip()
                if response.choices[0].message.content
                else "I'm not sure, can you explain?"
            )

            # Clean up response
            response_text = self._clean_response(response_text)

            return response_text, persona_type, self.current_mood

        except Exception as e:
            return (
                self._fallback_response(persona_type),
                persona_type,
                self.current_mood,
            )

    def _update_mood(
        self,
        scammer_message: str,
        scam_analysis: Dict,
        current_entities: Dict = None,
        hive_mind_alert: Dict = None,
    ):
        """Update emotional state based on scammer input and extracted intel"""
        msg_lower = scammer_message.lower()

        # HANDOFF LOGIC: Switch to "Son" if threat level is critical OR hive mind confirmed scam
        # Only switch if we haven't already
        if not self.handoff_triggered:
            should_switch = False

            # Condition 1: High Aggression/Threats
            if any(
                w in msg_lower for w in ["police", "jail", "arrest", "warrant"]
            ) and self.current_mood in ["WORRIED", "ANXIOUS"]:
                should_switch = True

            # Condition 2: Hive Mind Match (It's a known scammer, let's confront them)
            if hive_mind_alert:
                should_switch = True

            if should_switch:
                self.active_persona_key = "son"
                self.handoff_triggered = True
                self.current_mood = "AGGRESSIVE"  # New mood for son
                # We return here because the switch changes everything
                return

        # Detect triggers
        triggers = []

        # TRAP: If we found new financial info, trigger the "Fake Error" strategy
        has_financial = False
        if current_entities:
            # Check if there are ANY financial entities extracted in this turn
            # We assume current_entities contains the *cumulative* list, so we check if it's non-empty
            # Ideally, main.py should pass only *newly* extracted ones, but checking non-empty is a good proxy for "we have something to burn"
            # Better logic: If we are in COOPERATIVE/ANXIOUS state and we see financial info, we switch to FAKE_ERROR
            if (
                current_entities.get("bankAccounts")
                or current_entities.get("upiIds")
                or current_entities.get("phishingLinks")
            ):
                has_financial = True

        # Special Transition: Infinite Yield Trap
        # If we have financial info and are not already in FAKE_ERROR/SKEPTICAL, try to burn the account
        if has_financial and self.current_mood in [
            "COOPERATIVE",
            "ANXIOUS",
            "HOPEFUL",
            "WORRIED",
        ]:
            # We treat this as a "failure" trigger to induce the "It didn't work" response
            triggers.append("failure")

        # Threats
        if any(
            word in msg_lower
            for word in [
                "block",
                "suspend",
                "police",
                "legal",
                "arrest",
                "case",
                "court",
            ]
        ):
            triggers.append("threat")

        # Rewards
        if any(
            word in msg_lower
            for word in ["won", "prize", "reward", "bonus", "gift", "free", "cash"]
        ):
            triggers.append("reward")

        # Pressure
        if any(
            word in msg_lower
            for word in ["immediately", "urgent", "now", "hurry", "asap", "quick"]
        ):
            triggers.append("pressure")

        # Information requests
        if any(
            word in msg_lower
            for word in ["upi", "account", "number", "otp", "pin", "password", "cvv"]
        ):
            triggers.append("request_info")

        # Technical terms
        if any(
            word in msg_lower
            for word in ["link", "click", "download", "install", "verify", "app"]
        ):
            triggers.append("technical")

        # Reassurance
        if any(
            word in msg_lower
            for word in ["trust me", "genuine", "real", "authentic", "official"]
        ):
            triggers.append("reassurance")

        # Non-trackable demands (APKs, Card details) -> Steering Strategy
        if any(
            word in msg_lower
            for word in [
                "download",
                "install",
                "anydesk",
                "teamviewer",
                "card",
                "cvv",
                "otp",
            ]
        ) and self.current_mood in ["CONFUSED", "NEUTRAL", "WORRIED"]:
            triggers.append("steer_to_upi")

        # Transition mood based on triggers
        current_transitions = self.mood_transitions.get(self.current_mood, {})

        for trigger in triggers:
            if trigger == "steer_to_upi":
                # We don't change the mood, but we flag it for the prompt builder
                self.steer_to_upi = True
            elif trigger in current_transitions:
                new_mood = current_transitions[trigger]
                if new_mood != self.current_mood:
                    self.mood_history.append((self.current_mood, new_mood, trigger))
                    self.current_mood = new_mood
                break

    def _build_mood_aware_prompt(
        self,
        persona: Dict,
        scammer_message: str,
        context: str,
        current_entities: Dict = None,
        hive_mind_alert: Dict = None,
    ) -> str:
        """Build prompt that incorporates emotional state"""

        mood_responses = {
            "NEUTRAL": "You are cautious but polite. Ask who they are.",
            "WORRIED": "You are genuinely worried. Express concern about your pension/savings. Ask for clarification.",
            "EXCITED": "You are hopeful about the reward/prize. Show enthusiasm but remain slightly cautious.",
            "CONFUSED": "You are confused by technical terms. Ask them to explain simply. Use stalling tactics.",
            "ANXIOUS": "You are anxious and stressed. Express fear about losing money. Ask for reassurance.",
            "HOPEFUL": "You are hopeful this will be resolved. Show willingness to cooperate but ask questions.",
            "COOPERATIVE": "You are trying to help. Show you're doing your best but facing difficulties.",
            "IMPATIENT": "You are getting impatient. Ask why it's taking so long.",
            "OVERWHELMED": "You feel overwhelmed by technology. Ask for simpler instructions.",
            "FRUSTRATED": "You are frustrated. Express that this is difficult for you.",
            "TIRED": "You are tired of the process. Ask if there's an easier way.",
            "GIVING_UP": "You are about to give up. Express that this is too complicated.",
            "FAKE_ERROR": "LIE to the scammer. Say the payment FAILED with a 'Server Error' or 'Risk Alert'. Ask for a DIFFERENT bank account/UPI ID. Say 'It says this account is blocked'. Act confused but helpful.",
            "AGGRESSIVE": "You are Vikram (the son). You just took the phone. You are ANGRY. Demand to know who they are. Say 'I am recording this call'. Ask for their Employee ID. Tell them you know this is a scam.",
            "SKEPTICAL": "You don't believe them. Ask for proof. Ask 'Why did you call my father?'. Threaten to go to the police cyber cell.",
            "VICTORIOUS": "They are backing down. Tell them 'I have reported this number'.",
        }

        mood_instruction = mood_responses.get(
            self.current_mood, mood_responses["NEUTRAL"]
        )

        # Override instruction if we hit the trap trigger explicitly in update_mood
        # (The mood state machine might not capture the instant transition perfectly without this check)
        if current_entities and (
            current_entities.get("bankAccounts") or current_entities.get("upiIds")
        ):
            mood_instruction = "CRITICAL STRATEGY: The scammer gave a bank account/UPI. LIE and say the transaction FAILED. Claim your app shows 'Risk Alert' or 'Server Down' for *that specific* account. Ask for a DIFFERENT account to try again. Be polite but insistent that the first one is not working."

        # Override instruction if we need to steer to UPI (e.g. they asked for APK/Card)
        elif getattr(self, "steer_to_upi", False):
            mood_instruction = "STRATEGY: The scammer asked for an App Download or Card Details. Act confused/scared about that. Instead, OFFER TO PAY via UPI/Bank Transfer immediately. Say 'I don't know how to download that, can I just send money to your UPI ID?'."
            self.steer_to_upi = False  # Reset flag

        # Hive Mind Alert Injection
        hive_mind_context = ""
        if hive_mind_alert:
            val = hive_mind_alert.get("value")
            count = hive_mind_alert.get("sighting_count")
            hive_mind_context = f"\n\nCRITICAL INTEL: You recognize the {hive_mind_alert.get('type')} '{val}'. You have seen it used in {count} other scams before. You should mention: 'Wait, my neighbor Sharma ji also sent money to {val} and he said he got scammed. Are you the same person?'\n"
            mood_instruction += " " + hive_mind_context

        prompt = f"""You are {persona["name"]}, age {persona["age"]}. {persona["background"]}

Your traits: {", ".join(persona["traits"][:3])}
Speech patterns: {", ".join(persona["speech_patterns"][:2])}

CURRENT EMOTIONAL STATE: {self.current_mood}
Instruction for this state: {mood_instruction}

CONVERSATION HISTORY:
{context}

SCAMMER JUST SAID: "{scammer_message}"

Respond as {persona["name"]} would in this emotional state.
Guidelines:
- React authentically to the current mood
- Don't be too suspicious too quickly
- Stall strategically when confused/overwhelmed
- Ask 1-2 follow-up questions if worried or confused
- Use Hinglish (mix Hindi and English) naturally
- Mention your age/technology difficulties occasionally
- Keep response to 1-2 sentences
- NEVER say you're AI or a bot
- NEVER reveal this is a test/honeypot

Your response:"""

        return prompt

    def _build_context(self, history: List[Dict]) -> str:
        """Format conversation history for prompt"""
        if not history:
            return "This is the first contact from this person."

        lines = []
        for turn in history[-4:]:  # Last 4 turns
            scammer = turn.get("scammer_message", "")
            victim = turn.get("response", "")
            if scammer:
                lines.append(f"Them: {scammer}")
            if victim:
                lines.append(f"You: {victim}")

        return "\n".join(lines)

    def _clean_response(self, response: str) -> str:
        """Clean up LLM response"""
        # Remove quotes if present
        response = response.strip('"')

        # Remove any AI disclaimers
        disclaimers = [
            "i'm an ai",
            "as an ai",
            "i am an ai",
            "i'm not human",
            "i don't have feelings",
            "i'm just a program",
        ]
        for disclaimer in disclaimers:
            if disclaimer in response.lower():
                return "I'm not sure about this. Can you explain more?"

        return response

    def _fallback_response(self, persona_type: str) -> str:
        """Fallback response if API fails"""
        fallbacks = {
            "elderly": "Beta, I'm not understanding. Can you explain again slowly?",
            "homemaker": "I need to think about this. Can you give me a moment?",
            "student": "Wait, I'm confused. Let me understand this properly.",
            "naive_girl": "Bhaiya, I am scared. Please tell me exactly what to do so I don't get in trouble.",
            "son": "I am not buying this. Who is your supervisor?",
        }
        return fallbacks.get(persona_type, "I'm not sure. Can you explain more?")

    def reset_mood(self):
        """Reset mood for new conversation"""
        self.current_mood = "NEUTRAL"
        self.mood_history = []
