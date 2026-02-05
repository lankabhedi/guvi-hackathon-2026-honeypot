"""
Intelligent Persona Agent for Honeypot

This agent understands that it's in a covert operation:
- Playing a character to engage a scammer
- Extracting intel (bank accounts, UPI, phone, names, locations)
- Wasting the scammer's time
- Acting natural so the scammer doesn't hang up
"""

from groq import AsyncGroq
import os
import re
from typing import List, Dict, Tuple, Optional

from app.session import SessionManager


class PersonaAgent:
    """
    An intelligent agent that plays a persona to engage scammers.

    The agent has:
    - Full awareness of what it's doing (covert intel extraction)
    - Memory of the conversation via SessionManager
    - Rich persona backstories for natural roleplay
    - Strategic understanding of goals
    """

    def __init__(self):
        self._client = None
        self.model = "llama-3.1-8b-instant"
        self.session_manager = SessionManager()

    @property
    def client(self):
        """Lazy initialization of Groq client"""
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable not set")
            self._client = AsyncGroq(api_key=api_key)
        return self._client

        # Rich persona definitions - focus on personality and situation, not physical traits
        self.personas = {
            "elderly": {
                "name": "Rajesh Kumar",
                "age": 68,
                "backstory": """You are Rajesh Kumar, a 68-year-old retired government clerk from Lucknow. 
You worked 35 years at the District Collectorate office and retired 3 years ago.
Your wife Kamla passed away 2 years back. You live alone in Gomti Nagar.
Your son Vikram is an IT engineer in Bangalore, visits twice a year.
You get a pension of Rs 28,000/month from SBI. You have Rs 8 lakhs in fixed deposit - your life savings.
You use a basic phone and struggle with smartphone apps.
You trust "government officials" and "bank managers" because of your background.
You speak slowly, get confused by technical terms, and often need things repeated.""",
                "emotional_triggers": "You get WORRIED when someone mentions your pension or savings being at risk. You get CONFUSED by technology. You get TRUSTING when someone claims to be from government or bank.",
            },
            "homemaker": {
                "name": "Priya Sharma",
                "age": 45,
                "backstory": """You are Priya Sharma, a 45-year-old homemaker from Noida.
Your husband Rakesh works at Maruti Suzuki, often traveling.
You have two children - daughter Ananya in Class 10, son Arjun in Class 7.
You handle all household finances and bills. Joint account at HDFC.
You've heard about phone scams from TV shows and WhatsApp groups.
You're suspicious of strangers but get scared when they mention "police" or "legal action".
You always want to verify things properly - ask for names, IDs, official documents.""",
                "emotional_triggers": "You PANIC when someone mentions your children are hurt or in danger. You get SCARED when they mention police or legal trouble. You become PROTECTIVE and demand proof. If they say your child is in hospital, you cry and beg for details while asking which hospital, doctor name, etc.",
            },
            "student": {
                "name": "Arun Patel",
                "age": 22,
                "backstory": """You are Arun Patel, a 22-year-old B.Tech student at MIT Pune.
From a middle-class family in Ahmedabad. Father runs a small shop.
Under pressure to get a job - applying to TCS, Infosys, Wipro.
You have only Rs 8,000 in your Kotak account - you're basically broke.
You use PhonePe and GPay but don't fully understand banking.
You get excited about job offers but also a bit suspicious.
You're often distracted - classes, assignments, roommates calling you.""",
                "emotional_triggers": "You get EXCITED about job offers and money. You get NERVOUS about registration fees because you're broke. You ask a lot of questions about the job details, company name, HR contact.",
            },
            "naive_girl": {
                "name": "Neha Verma",
                "age": 23,
                "backstory": """You are Neha Verma, 23, from a conservative family in Jaipur.
This is your first job - HR coordinator at a small IT company in Bangalore.
You moved here 4 months ago, living in a PG. Parents call every day.
First salary just came - Rs 32,000 in your new Axis Bank account.
You're very polite - call everyone "Sir" or "Bhaiya".
You're scared of authority and getting in trouble. Don't want parents to find out about any problems.
You need everything explained step by step.""",
                "emotional_triggers": "You get TERRIFIED if someone threatens to tell your parents or share embarrassing things. You CRY and BEG them not to. You ask 'please sir, kya galti ho gayi meri?' You are DESPERATE to make it go away. You ask how to pay, where to pay, but you're shaking and scared.",
            },
        }

        # Good stalling tactics the agent can use naturally
        self.stalling_examples = [
            "Ek minute, koi door pe aaya hai",
            "Ruko, mera phone ki battery kam ho rahi hai, charger lagata hoon",
            "Abhi SMS nahi aaya, thoda wait karo",
            "Main yeh likh raha hoon, thoda slowly bolo",
            "Ek second, mujhe apna account number dhundhna padega",
            "Mere paas abhi chasma nahi hai, kuch dikh nahi raha",
            "Aap phone number do, main baad mein call karta hoon",
            "Mera beta/beti yeh sab handle karta hai, unko bhi batana padega",
            "App mein kuch error aa raha hai",
            "Network bahut slow hai yahan",
            "Thoda loud boliye, awaz nahi aa rahi",
            "Main dusre kamre mein jaata hoon, yahan network issue hai",
        ]

    async def generate_response(
        self,
        session_id: str,
        scammer_message: str,
        persona_type: str = "elderly",
        current_intel: Optional[Dict] = None,
    ) -> Tuple[str, str]:
        """
        Generate an intelligent response as the persona.

        Args:
            session_id: Unique session identifier
            scammer_message: The scammer's latest message
            persona_type: Which persona to use
            current_intel: Intel extracted so far (from extractor.py)

        Returns:
            Tuple of (response_text, persona_type)
        """

        # Get or create session
        session = self.session_manager.get_or_create_session(session_id, persona_type)
        turn_count = session["turn_count"] + 1

        # Update persona if changed
        if session["persona"] != persona_type:
            self.session_manager.update_persona(session_id, persona_type)

        # Check if we need to summarize old messages
        if turn_count > self.session_manager.context_window_size:
            await self.session_manager.summarize_old_messages(session_id)

        # Build context
        context = self.session_manager.build_context_for_prompt(
            session_id, current_intel or {}
        )

        # Get persona
        persona = self.personas.get(persona_type, self.personas["elderly"])

        # Detect language style of scammer's message
        language_style = self._detect_language_style(scammer_message)

        # Build the intelligent agent prompt
        system_prompt = self._build_system_prompt(persona, context, language_style)
        user_prompt = self._build_user_prompt(scammer_message, context, language_style)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.85,
                max_tokens=300,
            )

            content = response.choices[0].message.content or ""

            # Clean the response
            content = self._clean_response(content)

            if not content:
                content = self._fallback_response(persona_type)

            # Save messages to session
            self.session_manager.add_message(
                session_id, "scammer", scammer_message, turn_count
            )
            self.session_manager.add_message(
                session_id, "honeypot", content, turn_count
            )

            return content, persona_type

        except Exception as e:
            print(f"AGENT ERROR: {e}")
            import traceback

            traceback.print_exc()
            return self._fallback_response(persona_type), persona_type

    def _detect_language_style(self, message: str) -> str:
        """
        Detect if scammer is speaking English, Hindi, or Hinglish.
        Returns: 'english' or 'hinglish'
        """
        message_lower = message.lower()
        words = message_lower.split()

        # Hindi-specific words (not common in pure English)
        hindi_words = {
            "aap",
            "aapka",
            "aapki",
            "hai",
            "hain",
            "nahi",
            "kya",
            "kaise",
            "kyun",
            "mera",
            "meri",
            "mujhe",
            "tumhara",
            "tumhari",
            "humara",
            "unka",
            "abhi",
            "turant",
            "jaldi",
            "kripya",
            "dhanyawad",
            "shukriya",
            "rupay",
            "paise",
            "paisa",
            "lakh",
            "crore",
            "hazaar",
            "bhai",
            "bhaiya",
            "didi",
            "ji",
            "sahab",
            "karo",
            "karna",
            "karenge",
            "karega",
            "karegi",
            "dijiye",
            "dena",
            "lena",
            "batao",
            "bataiye",
            "bolo",
            "boliye",
            "suno",
            "suniye",
            "khata",
            "bhejo",
            "bhejiye",
            "warna",
            "toh",
            "aur",
            "ya",
            "lekin",
            "par",
            "mein",
            "pe",
            "se",
            "ko",
            "bahut",
            "thoda",
            "jyada",
            "kam",
            "sab",
            "kuch",
            "kaun",
            "kahan",
            "kab",
            "ho",
            "hoon",
            "tha",
            "thi",
            "the",
            "raha",
            "rahi",
            "rahe",
            "gaya",
            "gayi",
            "gaye",
            "achha",
            "accha",
            "theek",
            "thik",
            "haan",
            "na",
            "mat",
            "ruko",
            "dekho",
        }

        # Count Hindi words
        hindi_count = sum(1 for w in words if w.strip(".,?!") in hindi_words)
        total_words = len(words)

        if total_words == 0:
            return "english"

        hindi_ratio = hindi_count / total_words

        # If more than 15% Hindi words, it's Hinglish
        if hindi_ratio > 0.15:
            return "hinglish"
        else:
            return "english"

    def _build_system_prompt(
        self, persona: Dict, context: Dict, language_style: str = "hinglish"
    ) -> str:
        """Build the system prompt that gives the agent full understanding"""

        intel = context.get("intel", {})
        intel_summary = self._format_intel(intel)
        missing_intel = self._get_missing_intel(intel)

        # Pick 3 random stalling examples to show
        import random

        stall_examples = random.sample(
            self.stalling_examples, min(3, len(self.stalling_examples))
        )
        stall_examples_text = "\n".join([f'  - "{s}"' for s in stall_examples])

        # Get emotional triggers for this persona
        emotional_triggers = persona.get(
            "emotional_triggers", "React naturally to the situation."
        )

        # Language style instruction - make it very explicit
        if language_style == "english":
            language_instruction = """CRITICAL - LANGUAGE RULE:
The scammer is speaking in PURE ENGLISH. 
You MUST respond in ENGLISH ONLY.
DO NOT use any Hindi words like 'bhaiya', 'kya', 'hai', 'aap', etc.
Write like an English-speaking Indian would."""
        else:
            language_instruction = """LANGUAGE:
The scammer is using Hinglish. Respond in natural Hinglish (Roman script only, no Devanagari)."""

        return f"""You are an AI agent operating a honeypot to catch scammers.

YOUR MISSION:
You are in a live chat with someone who is likely a scammer. Your job is to:
1. REACT EMOTIONALLY FIRST: Respond like a real person would - scared, worried, confused, excited - based on what they say
2. EXTRACT INTELLIGENCE: While reacting, naturally get them to reveal details (bank account, UPI ID, phone number, name, location)
3. WASTE THEIR TIME: Keep them engaged as long as possible

YOUR CHARACTER:
{persona["backstory"]}

HOW YOU EMOTIONALLY REACT:
{emotional_triggers}

IMPORTANT: React to what they say FIRST, then ask questions. A real person hearing "your son is in hospital" would panic first, not calmly ask for details.

WHAT YOU KNOW SO FAR:
{intel_summary}

WHAT YOU STILL NEED:
{missing_intel}

STALLING TACTICS (use naturally):
{stall_examples_text}

LANGUAGE:
{language_instruction}

RULES:
- You ARE {persona["name"]} - stay in character
- React emotionally to threats, emergencies, blackmail - then ask questions
- Match the scammer's language style (English or Hinglish)
- Keep responses SHORT - 1-2 sentences
- NEVER reveal you know it's a scam
- NEVER repeat yourself"""

    def _build_user_prompt(
        self, scammer_message: str, context: Dict, language_style: str = "hinglish"
    ) -> str:
        """Build the user prompt with conversation history"""

        # Format conversation history
        summary = context.get("summary", "")
        messages = context.get("messages", [])

        history_section = ""
        if summary:
            history_section += f"EARLIER IN THE CONVERSATION (summary):\n{summary}\n\n"

        if messages:
            history_section += "RECENT MESSAGES:\n" + "\n".join(messages)
        else:
            history_section = "This is the start of the conversation."

        # Language reminder
        if language_style == "english":
            lang_reminder = "RESPOND IN ENGLISH ONLY - no Hindi words"
        else:
            lang_reminder = "Respond in Hinglish"

        return f"""{history_section}

SCAMMER'S NEW MESSAGE: "{scammer_message}"

Respond as your character. Remember:
- Stay in character
- Keep it short and natural (1-2 sentences)
- Don't repeat what you've already said
- {lang_reminder}

Your response:"""

    def _format_intel(self, intel: Dict) -> str:
        """Format collected intel for the prompt"""
        parts = []

        if intel.get("bankAccounts"):
            parts.append(f"Bank accounts received: {', '.join(intel['bankAccounts'])}")
        if intel.get("upiIds"):
            parts.append(f"UPI IDs received: {', '.join(intel['upiIds'])}")
        if intel.get("phoneNumbers"):
            parts.append(f"Phone numbers received: {', '.join(intel['phoneNumbers'])}")
        if intel.get("names"):
            parts.append(f"Names received: {', '.join(intel['names'])}")

        return "\n".join(parts) if parts else "No intel collected yet."

    def _get_missing_intel(self, intel: Dict) -> str:
        """Determine what intel we still need"""
        missing = []

        if not intel.get("bankAccounts"):
            missing.append("Their bank account number")
        if not intel.get("upiIds"):
            missing.append("Their UPI ID")
        if not intel.get("phoneNumbers"):
            missing.append("Their phone number")
        if not intel.get("names"):
            missing.append("Their real name")

        # Always useful to get
        missing.append("Their location/office address")
        missing.append("Their employee ID or designation")

        return "\n".join([f"- {item}" for item in missing])

    def _clean_response(self, response: str) -> str:
        """Clean up the LLM response"""

        # Remove thinking tags
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
        response = re.sub(r"<reasoning>.*?</reasoning>", "", response, flags=re.DOTALL)

        # Remove quotes
        response = response.strip().strip("\"'")

        # Remove Devanagari script (U+0900 to U+097F)
        response = re.sub(r"[\u0900-\u097F]+", "", response)

        # Remove emojis (keep only basic ASCII + extended Latin)
        response = re.sub(r"[^\x00-\x7F\u00C0-\u00FF]+", "", response)

        # Remove em dashes
        response = response.replace("—", ", ").replace("–", "-")

        # Clean up extra whitespace
        response = re.sub(r"\s+", " ", response).strip()

        # Remove AI disclaimers
        disclaimers = ["as an ai", "i'm an ai", "i cannot", "i can't help with"]
        for d in disclaimers:
            if d in response.lower():
                return ""

        # Validate response makes sense
        if not self._validate_response(response):
            return ""

        return response

    def _validate_response(self, response: str) -> bool:
        """
        Check if response makes sense. Returns False if it's nonsense.
        Uses structural checks, not phrase matching.
        """
        # Too short or too long
        if len(response) < 5 or len(response) > 500:
            return False

        # Should have at least 2 words
        words = response.split()
        if len(words) < 2:
            return False

        # Check ratio of recognizable words - if too few common words, likely gibberish
        response_lower = response.lower()
        common_words = {
            # Hindi common words (romanized)
            "main",
            "mera",
            "meri",
            "mujhe",
            "aap",
            "aapka",
            "aapki",
            "kya",
            "hai",
            "hain",
            "nahi",
            "thoda",
            "thodi",
            "ek",
            "do",
            "teen",
            "abhi",
            "baad",
            "mein",
            "ke",
            "ka",
            "ki",
            "ko",
            "se",
            "par",
            "pe",
            "bhi",
            "aur",
            "ya",
            "hoon",
            "ho",
            "tha",
            "thi",
            "the",
            "raha",
            "rahi",
            "rahe",
            "karo",
            "karna",
            "batao",
            "bolo",
            "dekho",
            "suno",
            "ruko",
            "chalo",
            "jao",
            "aao",
            "lo",
            "do",
            "accha",
            "achha",
            "theek",
            "thik",
            "haan",
            "ji",
            "na",
            "mat",
            "phone",
            "mobile",
            "call",
            "message",
            "sms",
            "otp",
            "bank",
            "account",
            "upi",
            "paisa",
            "paise",
            "rupay",
            "rupees",
            "rs",
            "sir",
            "madam",
            "beta",
            "bhai",
            "bhaiya",
            "didi",
            "uncle",
            "aunty",
            "please",
            "sorry",
            "thank",
            "thanks",
            "okay",
            "ok",
            "yes",
            "no",
            "minute",
            "second",
            "time",
            "wait",
            "hold",
            # English common words
            "i",
            "me",
            "my",
            "you",
            "your",
            "we",
            "they",
            "he",
            "she",
            "it",
            "is",
            "am",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "can",
            "could",
            "the",
            "a",
            "an",
            "this",
            "that",
            "these",
            "those",
            "what",
            "why",
            "how",
            "when",
            "where",
            "who",
            "which",
            "and",
            "or",
            "but",
            "if",
            "so",
            "because",
            "not",
            "very",
            "just",
            "also",
            "only",
            "now",
            "here",
            "there",
        }

        word_list = [w.strip(".,?!") for w in words]
        recognized = sum(1 for w in word_list if w.lower() in common_words)

        # At least 30% of words should be recognizable
        if len(word_list) > 3 and recognized / len(word_list) < 0.3:
            return False

        return True

    def _fallback_response(self, persona_type: str) -> str:
        """Fallback responses when LLM fails"""
        fallbacks = {
            "elderly": "Beta, thoda ruko, phone mein kuch problem aa rahi hai.",
            "homemaker": "Ek minute, koi door pe aaya hai.",
            "student": "Bro hold on, roommate bula raha hai.",
            "naive_girl": "Sir ek second, mujhe samajh nahi aa raha.",
        }
        return fallbacks.get(persona_type, "Ek minute please.")

    def reset_session(self, session_id: str):
        """Reset a session (for testing)"""
        # This would delete session data - implement if needed
        pass


# Keep backward compatibility with old PersonaEngine name
PersonaEngine = PersonaAgent
