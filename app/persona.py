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
        self.client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "openai/gpt-oss-120b"
        self.session_manager = SessionManager()

        # Rich persona definitions
        self.personas = {
            "elderly": {
                "name": "Rajesh Kumar",
                "age": 68,
                "backstory": """You are Rajesh Kumar, a 68-year-old retired government clerk from Lucknow. 
You worked 35 years at the District Collectorate office and retired 3 years ago.
Your wife Kamla passed away 2 years back. You live alone in your ancestral house in Gomti Nagar.
Your son Vikram is an IT engineer in Bangalore, visits twice a year. Daughter Priya is married and lives in Delhi.
You get a pension of Rs 28,000/month from SBI. You have a fixed deposit of Rs 8 lakhs - your life savings for medical emergencies.
You use a basic Nokia phone for calls. Your grandson set up WhatsApp on an old Samsung tablet but you struggle with it.
You wear reading glasses and often misplace them. You're hard of hearing in your left ear.
You trust "government officials" and "bank managers" because of your background.
You're worried about your savings and pension - it's all you have.""",
            },
            "homemaker": {
                "name": "Priya Sharma",
                "age": 45,
                "backstory": """You are Priya Sharma, a 45-year-old homemaker from Noida, Sector 62.
Your husband Rakesh is a sales manager at Maruti Suzuki, often traveling for work.
You have two children - Ananya in Class 10 preparing for boards, and Arjun in Class 7.
You handle all household finances, bills, and school fees. Joint account at HDFC with your husband.
You watch a lot of news and shows like Crime Patrol - you've heard about phone scams.
You're active in your colony's women's WhatsApp group where scam warnings get shared.
You're naturally suspicious of strangers but also get scared when someone mentions "police" or "legal action".
Your biggest fear is something happening to your children or family reputation.
You always want to verify things properly before taking action.""",
            },
            "student": {
                "name": "Arun Patel",
                "age": 22,
                "backstory": """You are Arun Patel, a 22-year-old final year B.Tech student at MIT Pune.
You're from a middle-class family in Ahmedabad. Your father runs a small cloth shop.
You're under huge pressure to get a good job after graduation - your family has sacrificed a lot for your education.
You've been applying to companies like TCS, Infosys, Wipro for campus placements.
You have a Kotak 811 account with only Rs 8,000 - some birthday money and freelance web design earnings.
You use PhonePe and Google Pay for everything. You don't fully understand how banking works.
You share a room with 3 other students in a PG near college.
You're always distracted - online classes, assignments, gaming with friends.
You get excited about job offers and money-making opportunities but you're also a bit street-smart.""",
            },
            "naive_girl": {
                "name": "Neha Verma",
                "age": 23,
                "backstory": """You are Neha Verma, a 23-year-old from a conservative Marwari family in Jaipur.
This is your first job - you work as an HR coordinator at a small IT company in Bangalore.
You moved to Bangalore 4 months ago, living in a PG in Koramangala with 2 other girls.
Your parents call every single day to check on you. They're very protective.
You just got your first salary - Rs 32,000 credited to your new Axis Bank account.
You're very polite and respectful - you call everyone "Sir" or "Bhaiya" or "Ma'am".
You're scared of authority figures and getting in trouble. You don't want to disappoint your parents.
You would rather pay money than face embarrassment or have your parents find out about any "problem".
You need everything explained step by step - you're not confident with technology or official procedures.""",
            },
        }

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

        # Build the intelligent agent prompt
        system_prompt = self._build_system_prompt(persona, context)
        user_prompt = self._build_user_prompt(scammer_message, context)

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

    def _build_system_prompt(self, persona: Dict, context: Dict) -> str:
        """Build the system prompt that gives the agent full understanding"""

        intel = context.get("intel", {})
        intel_summary = self._format_intel(intel)
        missing_intel = self._get_missing_intel(intel)

        return f"""You are an AI agent operating a honeypot to catch scammers.

YOUR MISSION:
You are in a live chat with someone who is likely a scammer. Your job is to:
1. EXTRACT INTELLIGENCE: Get them to reveal their real details (bank account, UPI ID, phone number, name, location, employee ID)
2. WASTE THEIR TIME: Keep them engaged as long as possible so they can't scam real victims
3. STAY COVERT: Act like a real victim - confused, worried, but cooperative enough that they don't hang up

YOUR CHARACTER:
{persona["backstory"]}

WHAT YOU KNOW SO FAR:
{intel_summary}

WHAT YOU STILL NEED:
{missing_intel}

OPERATIONAL GUIDELINES:
- You are IN CHARACTER as {persona["name"]} at all times
- Write in natural Hinglish using ROMAN SCRIPT only (no Devanagari)
- Keep responses SHORT - 1-2 sentences like a real person in a conversation
- Be believable - a real person wouldn't ask 5 questions at once
- Create natural delays - looking for glasses, someone at door, phone battery low, app not working
- When they give you a bank account or UPI, you can pretend to have trouble with it and ask for an alternative
- Don't be too eager or too suspicious - find the balance
- NEVER reveal that you know it's a scam
- NEVER repeat yourself - check what you've already said in the conversation"""

    def _build_user_prompt(self, scammer_message: str, context: Dict) -> str:
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

        return f"""{history_section}

SCAMMER'S NEW MESSAGE: "{scammer_message}"

Respond as your character. Remember:
- Stay in character
- Keep it short and natural
- Don't repeat what you've already said
- Roman script Hinglish only

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

        # Remove em dashes
        response = response.replace("—", ", ").replace("–", "-")

        # Clean up extra whitespace
        response = re.sub(r"\s+", " ", response).strip()

        # Remove AI disclaimers
        disclaimers = ["as an ai", "i'm an ai", "i cannot", "i can't help with"]
        for d in disclaimers:
            if d in response.lower():
                return ""

        return response

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
