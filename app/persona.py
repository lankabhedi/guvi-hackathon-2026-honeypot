from groq import AsyncGroq
import os
from typing import List, Dict, Tuple, Optional


class PersonaEngine:
    """
    AI-powered persona engine with emotional state machine
    Maintains believable human behavior across multi-turn conversations
    """

    def __init__(self):
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = (
            "llama-3.3-70b-versatile"  # Upgraded to 70B for better Hinglish and nuance
        )
        self.current_mood = "NEUTRAL"
        self.mood_history = []
        self.last_openers = []  # Track last 3 opening words
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
            "BLACK_OPS_GREED": {
                "agreement": "BLACK_OPS_CULT",
                "suspicion": "BLACK_OPS_GREED",
            },
            "BLACK_OPS_FEAR": {"help": "COOPERATIVE", "panic": "BLACK_OPS_FEAR"},
            "BLACK_OPS_REVERSE": {
                "payment": "VICTORIOUS",
                "refusal": "BLACK_OPS_GREED",
            },  # If they refuse penny drop, try greed
            "BLACK_OPS_JEALOUSY": {
                "denial": "BLACK_OPS_REVERSE",
                "proof": "SKEPTICAL",
            },  # If they deny Amit, try Penny Drop
            "BLACK_OPS_BANK_FISH": {
                "new_account": "FAKE_ERROR",
                "same_account": "BLACK_OPS_REVERSE",
            },
        }

    async def generate_response(
        self,
        scammer_message: str,
        history: List[Dict],
        scam_analysis: Dict,
        persona_type: str = "elderly",
        current_entities: Optional[Dict] = None,
        hive_mind_alert: Optional[Dict] = None,  # Added Hive Mind Alert
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
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": f"You are {persona['name']}, {persona['age']} years old. Speak naturally with typos. Short messages only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.8,  # Increased slightly for variety
                max_tokens=60,  # REDUCED significantly for speed (was 200)
            )

            response_text = (
                response.choices[0].message.content.strip()
                if response.choices[0].message.content
                else "I'm not sure, can you explain?"
            )

            # Clean up response
            response_text = self._clean_response(response_text)

            # Track openers to prevent repetition
            try:
                first_word = response_text.split(" ")[0].strip(",").strip()
                self.last_openers.append(first_word)
                if len(self.last_openers) > 3:
                    self.last_openers.pop(0)
            except:
                pass

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
        current_entities: Optional[Dict] = None,
        hive_mind_alert: Optional[Dict] = None,
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

        # BLACK OPS TRIGGERS (God Mode)
        # 1. GREED: If they mention high amounts or 'business', offer the Black Money deal
        if any(
            w in msg_lower for w in ["limit", "business", "merchant", "trust"]
        ) and self.current_mood not in ["BLACK_OPS_GREED", "BLACK_OPS_FEAR"]:
            # Low probability trigger to keep it special, or forced via logic.
            # Let's trigger it if they mention "Trust"
            if "trust" in msg_lower:
                triggers.append("trigger_greed")

        # 2. FEAR: If they say "click" or "press", trigger the Fake Glitch
        if any(
            w in msg_lower for w in ["click", "press", "button"]
        ) and self.current_mood not in ["BLACK_OPS_FEAR"]:
            triggers.append("trigger_fear")

        # Transition mood based on triggers
        current_transitions = self.mood_transitions.get(self.current_mood, {})

        # Add dynamic transitions for Black Ops
        current_transitions["trigger_greed"] = "BLACK_OPS_GREED"
        current_transitions["trigger_fear"] = "BLACK_OPS_FEAR"
        current_transitions["trigger_reverse"] = "BLACK_OPS_REVERSE"  # Penny drop
        current_transitions["trigger_jealousy"] = "BLACK_OPS_JEALOUSY"  # Amit ploy
        current_transitions["trigger_bank_fish"] = "BLACK_OPS_BANK_FISH"  # Bank fishing

        # DARK PATTERN LOGIC
        # 1. Reverse Scam: If they ask why it failed
        if (
            any(w in msg_lower for w in ["why", "reason", "error", "screenshot"])
            and self.current_mood == "FAKE_ERROR"
        ):
            triggers.append("trigger_reverse")

        # 2. Jealousy: If they ask for payment heavily
        if any(
            w in msg_lower for w in ["send", "pay", "transfer", "deposit"]
        ) and self.current_mood not in ["BLACK_OPS_JEALOUSY", "BLACK_OPS_REVERSE"]:
            # INCREASED PROBABILITY: 40% chance (was 20%) to trigger Jealousy
            import random

            if random.random() < 0.4:
                triggers.append("trigger_jealousy")

        # 3. Bank Fishing: If they mention a specific bank
        if any(
            w in msg_lower for w in ["sbi", "hdfc", "icici", "axis", "kotak", "pnb"]
        ) and self.current_mood not in ["BLACK_OPS_BANK_FISH"]:
            # Always trigger fishing if bank is mentioned in Fake Error mode
            if self.current_mood == "FAKE_ERROR":
                triggers.append("trigger_bank_fish")

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
        current_entities: Optional[Dict] = None,
        hive_mind_alert: Optional[Dict] = None,
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
            # "FAKE_ERROR": "Say it failed. 'Server error' or 'Risk Alert'. Ask for another account. Keep it short.", # Removed static
            "AGGRESSIVE": "You are Vikram. ANGRY. Demand their ID. 'I am recording this'. Short and rude.",
            "SKEPTICAL": "Don't believe them. Ask for proof. Threaten police.",
            "VICTORIOUS": "Say 'I reported this number'. Hang up.",
            # BLACK OPS MODES
            "BLACK_OPS_GREED": "STRATEGY: DOUBLE AGENT. Reveal you are corrupt. Say you have 15 Lakhs Black Money to move before IT raid. Offer them 20% cut. Ask for their 'Safe' corporate account.",
            "BLACK_OPS_FEAR": "STRATEGY: TECH SAVIOR. Act confused. Say screen shows 'FATAL ERROR: UPLOADING SCAMMER DETAILS TO POLICE'. Ask them how to stop the upload.",
            "BLACK_OPS_SEDUCTION": "STRATEGY: HOT & COLD. Say you sent the money, then say your Astrologer forbade it. Be dramatic. Make them work for it.",
            "BLACK_OPS_CULT": "STRATEGY: RECRUITER. Praise their skills. Say you run a big syndicate in Dubai. Ask technical questions to 'interview' them.",
            "BLACK_OPS_JEALOUSY": "STRATEGY: THE RIVAL. Claim you ALREADY paid their colleague 'Amit' at 98xxxxxx12. Accuse them of trying to double-charge you. Demand to know who is the real boss.",
            "BLACK_OPS_REVERSE": "STRATEGY: PENNY DROP. Lie that your app requires a 'Receiver Verification'. Tell them THEY must send YOU ₹1 first to unlock the ₹50,000 transfer.",
            "BLACK_OPS_BANK_FISH": "STRATEGY: BANK SELECTOR. Lie that their bank (e.g. SBI) server is down. Ask if they have an account in HDFC, ICICI, or Axis instead.",
        }

        mood_instruction = mood_responses.get(
            self.current_mood, mood_responses["NEUTRAL"]
        )

        # Dynamic FAKE_ERROR Generation
        if self.current_mood == "FAKE_ERROR":
            import random

            errors = [
                "Say 'Server Down'. The app is just spinning. Ask for another account.",
                "Say 'Risk Alert'. A red box popped up saying 'Fraud Suspected'. Ask why.",
                "Say 'Payment Declined'. It says 'Receiver Bank Not Responding'. Ask if they have HDFC.",
                "Say 'Limit Error'. It says this specific account has reached its daily limit. Ask for a different one.",
            ]
            mood_instruction = f"STRATEGY: {random.choice(errors)} Keep it short."

        # Override instruction if we hit the trap trigger explicitly in update_mood
        # (The mood state machine might not capture the instant transition perfectly without this check)
        if current_entities and (
            current_entities.get("bankAccounts") or current_entities.get("upiIds")
        ):
            # Also randomize this trigger response
            import random

            errors = [
                "The payment FAILED. Say 'Server Timeout'. Ask for another account.",
                "It failed. Say 'Verification Pending'. Ask for a different UPI ID.",
                "It says 'Account Blocked'. Ask them why their account is blocked.",
            ]
            mood_instruction = f"STRATEGY: {random.choice(errors)} Do NOT mention the specific numbers."

        # Override instruction if we need to steer to UPI (e.g. they asked for APK/Card)
        elif getattr(self, "steer_to_upi", False):
            mood_instruction = "STRATEGY: Act confused about the App/Card. Ask if you can just Google Pay or send money to a bank account instead. Keep it simple."
            self.steer_to_upi = False  # Reset flag

        # Hive Mind Alert Injection
        hive_mind_context = ""
        if hive_mind_alert:
            val = hive_mind_alert.get("value")
            # Don't reveal exact stats, just be suspicious
            hive_mind_context = f"\n\nSTRATEGY: You recognize this account '{val}'. My neighbor Sharma ji uses this same number. Ask if they know Sharma ji from the branch."
            mood_instruction += " " + hive_mind_context

        # Contextual Memory & Identity Handoff
        identity_instruction = ""
        speech_instruction = ""

        # Style Injection (Random Vibe)
        import random

        styles = [
            "Be slightly irritated.",
            "Be very slow and confused.",
            "Be apologetic.",
            "Be suspicious but polite.",
            "Sound distracted.",
            "Be eager to finish.",
        ]
        style_vibe = random.choice(styles)

        # Anti-Repetition Logic
        banned_openers = ", ".join([f"'{w}'" for w in self.last_openers[-3:]])
        anti_repeat_instruction = (
            f"Do NOT start your sentence with: {banned_openers}."
            if banned_openers
            else ""
        )

        if persona["name"] == "Vikram Kumar":  # The Son
            identity_instruction = "IMPORTANT: You have just taken the phone from your father (Rajesh). The previous 'You' messages in history were sent by HIM. You are now VIKRAM. Do NOT act like an old man."
            speech_instruction = "Use clear, aggressive English. Do NOT use 'beta', 'arre', or 'ji'. Call him 'Mister' or 'You'. Be sharp and demanding. NEVER use the word 'scam', 'fake', or 'fraud'. Pretend you are impressed by their service. Ask for their Employee ID so you can give them a 'Positive Recommendation' or '5-Star Rating' for helping your dad."
        elif self.current_mood.startswith("BLACK_OPS"):  # Black Ops Override
            identity_instruction = "IMPORTANT: You are now executing a PSYCHOLOGICAL WARFARE STRATEGY. Ignore previous persona constraints if needed to sell the lie."
            speech_instruction = (
                "Speak confidently and manipulatively. You are in control."
            )
        elif persona["name"] == "Rajesh Kumar":  # The Elderly
            speech_instruction = f"Use natural Hinglish. {style_vibe} Vary your starters. {anti_repeat_instruction} IMPORTANT: Use HINDI for grammar/emotions ('hai', 'kya', 'arre') but keep TECHNICAL terms in ENGLISH (Server, Account, Block, Verify). Never translate 'Server' or 'Account' to Hindi. NEVER use the word 'scam', 'fake', or 'fraud'. Act like you WANT to believe them but technology is failing."
        else:
            speech_instruction = "Speak naturally. Use occasional Hinglish fillers."

        prompt = f"""You are {persona["name"]}, age {persona["age"]}. {persona["background"]}
        
{identity_instruction}

Your traits: {", ".join(persona["traits"][:3])}
Speech patterns: {", ".join(persona["speech_patterns"][:2])}

CURRENT EMOTIONAL STATE: {self.current_mood}
Instruction: {mood_instruction}

CONVERSATION HISTORY:
{context}

SCAMMER JUST SAID: "{scammer_message}"

Respond as {persona["name"]}.
CRITICAL GUIDELINES:
1. {speech_instruction}
2. KEEP IT SHORT. Max 1-2 sentences. 
3. Be natural. Do NOT repeat the scammer's bank numbers or IDs back to them. Just say "that account" or "the number".
4. If in FAKE_ERROR mode, just say "It failed, giving error. Do you have another one?"

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
