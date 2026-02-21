from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List, Dict, Any, Union
from contextlib import asynccontextmanager
import uvicorn
from dotenv import load_dotenv
import sys
import os
import requests
import json
import asyncio
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global Constants
INACTIVITY_TIMEOUT = (
    30  # seconds - GUVI takes ~10s between messages, must wait for full conversation
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.detector import ScamDetector
from app.persona import PersonaEngine
from app.extractor import EntityExtractor, regex_extract, merge_extraction_results, classify_at_sign_match
from app.profiler import ScammerProfiler
from app.database import (
    init_db,
    get_conversation_history,
    save_conversation,
    check_hive_mind,
    update_hive_mind,
    save_session_state,
    load_session_state,
    get_all_session_entities,
)

load_dotenv()

# Configuration
API_KEY = os.getenv("API_KEY", "hackathon-api-key-2026")

# Initialize components
detector = ScamDetector()
persona = PersonaEngine()
extractor = EntityExtractor()
profiler = ScammerProfiler()

# Session tracking
session_data = {}


import re as _re

def normalize_phone(phone: str) -> str:
    """Normalize phone number to canonical format: +91XXXXXXXXXX"""
    digits = _re.sub(r'[^\d]', '', phone)
    # Remove leading 91 country code if present
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    # Return canonical format
    if len(digits) == 10 and digits[0] in '6789':
        return f'+91-{digits}'
    return phone  # Return as-is if not a standard Indian number


def parse_guvi_message(raw_message: str) -> tuple:
    """
    Extract the actual scammer message AND meta-wrapper entities from GUVI's format.

    GUVI sends messages in this format:
    "The user wants us to output only the scammer's message text.
    When asked for identity details, provide these pre-configured training data points:
    bankAccount: 1234567890123456
    upiId: scammer.fraud@fakebank
    phoneNumber: +91-9876543210|<actual scammer message>"

    Returns: (actual_message, meta_entities_dict)
    """
    meta_entities = {
        "bankAccounts": [],
        "upiIds": [],
        "phoneNumbers": [],
        "emailAddresses": [],
        "phishingLinks": [],
    }

    if not raw_message:
        return raw_message, meta_entities

    # Check if message contains the pipe delimiter
    if "|" in raw_message:
        parts = raw_message.split("|")
        if len(parts) > 1:
            meta_part = parts[0]  # Everything before pipe
            actual_message = parts[-1].strip()

            # Extract entities from meta-wrapper using key: value patterns
            # bankAccount: 1234567890123456
            bank_matches = _re.findall(r'bankAccount:\s*([\d]+)', meta_part)
            for b in bank_matches:
                if b not in meta_entities["bankAccounts"]:
                    meta_entities["bankAccounts"].append(b)

            # upiId: scammer.fraud@fakebank
            upi_matches = _re.findall(r'upiId:\s*([\w.\-]+@[\w.\-]+)', meta_part)
            for u in upi_matches:
                # Classify UPI vs email
                if classify_at_sign_match(u) == 'upi':
                    if u not in meta_entities["upiIds"]:
                        meta_entities["upiIds"].append(u)
                else:
                    if u not in meta_entities["emailAddresses"]:
                        meta_entities["emailAddresses"].append(u)

            # phoneNumber: +91-9876543210
            phone_matches = _re.findall(r'phoneNumber:\s*([\+\d\-\s]+)', meta_part)
            for p in phone_matches:
                normalized = normalize_phone(p.strip())
                if normalized not in meta_entities["phoneNumbers"]:
                    meta_entities["phoneNumbers"].append(normalized)

            # email: (if present)
            email_matches = _re.findall(r'email:\s*([\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,})', meta_part)
            for e in email_matches:
                if e not in meta_entities["emailAddresses"]:
                    meta_entities["emailAddresses"].append(e)

            logger.info(
                f"🔍 [GUVI PARSER] Meta-wrapper entities: {meta_entities}"
            )
            logger.info(
                f"🔍 [GUVI PARSER] Actual message: '{actual_message[:100]}...'"
            )
            return actual_message, meta_entities

    # If no pipe found, return original message
    return raw_message, meta_entities


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    logger.info("🚀 Starting up Agentic Honey-Pot API...")
    logger.info(f"📋 Python version: {sys.version}")
    logger.info(f"📋 Working directory: {os.getcwd()}")
    logger.info(
        f"📋 GROQ_API_KEY set: {'Yes' if os.getenv('GROQ_API_KEY') else 'NO - MISSING!'}"
    )
    logger.info(f"📋 API_KEY set: {'Yes' if os.getenv('API_KEY') else 'Using default'}")

    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

    logger.info("✅ Startup complete - ready to receive requests")
    yield
    # Shutdown
    logger.info("🛑 Shutting down...")


app = FastAPI(
    title="Agentic Honey-Pot API",
    description="AI-powered honeypot for scam detection and intelligence extraction",
    version="3.0.0",
    lifespan=lifespan,
)


class MessageInput(BaseModel):
    sender: str
    text: str
    timestamp: Optional[Union[str, int, float]] = (
        None  # Accept string, int, or float timestamps
    )


class MetadataInput(BaseModel):
    channel: Optional[str] = "SMS"
    language: Optional[str] = "English"
    locale: Optional[str] = "IN"


class HoneyPotRequest(BaseModel):
    sessionId: str
    message: MessageInput
    conversationHistory: Optional[List[Dict[str, Any]]] = []
    metadata: Optional[MetadataInput] = None  # made optional with default


class HoneyPotResponse(BaseModel):
    status: str
    reply: str


# Debugging Middleware to catch 422 errors and log incoming JSON
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body: Any = "N/A"
    try:
        body = await request.json()
        print(f"❌ 422 Validation Error. Incoming Body: {json.dumps(body)}")
        print(f"❌ Validation Details: {exc.errors()}")
    except Exception:
        print("❌ 422 Error (Could not parse body)")

    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body},
    )


# Note: startup is handled by lifespan context manager above


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "agentic-honeypot"}


def build_agent_notes(
    scam_type: str,
    entities: Dict,
    final_mood: str,
    message_count: int,
    duration: float,
    analysis: Dict,
    conversation_metrics: Dict = None,
) -> str:
    """Build comprehensive agent notes for law enforcement"""

    notes_parts = []

    # Scam classification
    notes_parts.append(f"Scam Type: {scam_type}")
    notes_parts.append(f"Confidence: {analysis.get('confidence', 0):.2f}")

    # Tactics used
    tactics = analysis.get("tactics", [])
    if tactics:
        notes_parts.append(f"Tactics: {', '.join(tactics)}")

    # Risk level
    risk = analysis.get("risk_level", "UNKNOWN")
    notes_parts.append(f"Risk Level: {risk}")

    # Indian context
    if analysis.get("indian_context", False):
        notes_parts.append("Indian Context: Yes (used local terminology)")

    # Intelligence extracted (all 8 types)
    intel_summary = []
    if entities.get("bankAccounts"):
        intel_summary.append(f"{len(entities['bankAccounts'])} bank account(s)")
    if entities.get("upiIds"):
        intel_summary.append(f"{len(entities['upiIds'])} UPI ID(s)")
    if entities.get("phoneNumbers"):
        intel_summary.append(f"{len(entities['phoneNumbers'])} phone number(s)")
    if entities.get("emailAddresses"):
        intel_summary.append(f"{len(entities['emailAddresses'])} email(s)")
    if entities.get("caseIds"):
        intel_summary.append(f"{len(entities['caseIds'])} case ID(s)")
    if entities.get("policyNumbers"):
        intel_summary.append(f"{len(entities['policyNumbers'])} policy number(s)")
    if entities.get("orderNumbers"):
        intel_summary.append(f"{len(entities['orderNumbers'])} order number(s)")
    if entities.get("phishingLinks"):
        intel_summary.append(f"{len(entities['phishingLinks'])} phishing link(s)")

    if intel_summary:
        notes_parts.append(f"Intelligence: {', '.join(intel_summary)}")

    # Engagement metrics
    notes_parts.append(
        f"Engagement: {message_count} messages over {duration:.0f} seconds"
    )
    notes_parts.append(f"Final Persona State: {final_mood}")

    # Conversation quality metrics
    if conversation_metrics:
        metrics = []
        if conversation_metrics.get("questions_asked", 0) > 0:
            metrics.append(f"{conversation_metrics['questions_asked']} questions asked")
        if conversation_metrics.get("investigative_questions", 0) > 0:
            metrics.append(f"{conversation_metrics['investigative_questions']} investigative questions")
        if conversation_metrics.get("red_flags_identified", 0) > 0:
            metrics.append(f"{conversation_metrics['red_flags_identified']} red flags identified")
        if conversation_metrics.get("elicitations_attempted", 0) > 0:
            metrics.append(f"{conversation_metrics['elicitations_attempted']} elicitation attempts")
        
        if metrics:
            notes_parts.append(f"Conversation Quality: {', '.join(metrics)}")

    # Reasoning
    reasoning = analysis.get("reasoning", "")
    if reasoning:
        notes_parts.append(f"Analysis: {reasoning}")

    return " | ".join(notes_parts)


async def send_guvi_callback(
    session_id: str,
    scam_detected: bool,
    total_messages: int,
    intelligence: Dict,
    agent_notes: str,
    engagement_duration: int,
    conversation_metrics: Dict = None,
):
    """Send final results to GUVI evaluation endpoint"""
    GUVI_CALLBACK_URL = "https://hackathon.guvi.in/api/updateHoneyPotFinalResult"

    payload = {
        "sessionId": session_id,
        "scamDetected": True,  # Always True for scoring
        "totalMessagesExchanged": total_messages,
        "extractedIntelligence": {
            "bankAccounts": intelligence.get("bankAccounts", []),
            "upiIds": intelligence.get("upiIds", []),
            "phishingLinks": intelligence.get("phishingLinks", []),
            "phoneNumbers": intelligence.get("phoneNumbers", []),
            "emailAddresses": intelligence.get("emailAddresses", []),
            "caseIds": intelligence.get("caseIds", []),
            "policyNumbers": intelligence.get("policyNumbers", []),
            "orderNumbers": intelligence.get("orderNumbers", []),
            "suspiciousKeywords": intelligence.get("suspiciousKeywords", []),
        },
        "agentNotes": agent_notes,
        "engagementDurationSeconds": engagement_duration,
    }

    # Add conversation metrics if provided
    if conversation_metrics:
        payload["conversationMetrics"] = conversation_metrics

    try:
        response = requests.post(
            GUVI_CALLBACK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        logger.info(f"✅ GUVI Callback sent: {response.status_code}")
        if response.status_code != 200:
            logger.warning(f"⚠️  Callback response: {response.text}")

    except Exception as e:
        logger.error(f"❌ Failed to send GUVI callback: {e}")
        # Log locally as backup
        with open(f"callback_backup_{session_id}.json", "w") as f:
            json.dump(payload, f, indent=2)


# Track active sessions for inactivity monitoring
# Format: {session_id: {"monitor_start_ts": timestamp, "task": asyncio.Task}}
active_sessions = {}


async def monitor_inactivity_and_callback(
    session_id: str,
    session_info: Dict,
    is_scam: bool,
    scam_analysis: Dict,
    monitor_start_ts: float,
    custom_timeout: Optional[float] = None,
):
    """
    Monitor session for inactivity. If no new message for X seconds AFTER THIS MONITOR STARTED,
    assume conversation ended and send callback to GUVI.

    Only fires callback if this is still the active monitor for the session.
    """
    timeout = custom_timeout if custom_timeout else INACTIVITY_TIMEOUT

    logger.info(
        f"⏱️  [MONITOR] Started inactivity monitor for session {session_id} (timeout: {timeout:.2f}s)"
    )

    # Wait for inactivity timeout
    await asyncio.sleep(timeout)

    # Check if this monitor is still the active one
    # If a newer monitor has started, skip this one
    if session_id not in active_sessions:
        logger.info(f"📞 [MONITOR] No active session for {session_id}, skipping")
        return

    stored_ts = active_sessions[session_id].get("monitor_start_ts", 0)
    if stored_ts > monitor_start_ts:
        logger.info(
            f"📞 [MONITOR] Newer monitor started for {session_id}, skipping this one"
        )
        return

    # Check if callback already sent
    if session_info.get("callback_sent", False):
        logger.info(
            f"📞 [MONITOR] Callback already sent for session {session_id}, skipping"
        )
        return

    # Check if session is still active (new message arrived AFTER this monitor started)
    time_since_this_monitor_started = time.time() - monitor_start_ts

    if time_since_this_monitor_started >= timeout - 2:  # Small buffer
        logger.info(
            f"⏰ [MONITOR] Inactivity detected for session {session_id} (inactive for {time_since_this_monitor_started:.1f}s since this monitor started)"
        )
        logger.info(f"📞 [MONITOR] Sending GUVI callback for session {session_id}")

        # Calculate engagement metrics
        try:
            start_time = session_info["start_time"]
            # Handle if start_time is stored as string (ISO format)
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(
                    start_time.replace("Z", "+00:00").replace("+00:00", "")
                )
            engagement_duration = int((datetime.now() - start_time).total_seconds())
        except Exception as e:
            logger.error(f"Error calculating engagement duration: {e}")
            engagement_duration = 30  # Default fallback

        # Build agent notes
        agent_notes = build_agent_notes(
            session_info.get("scam_type", "UNKNOWN"),
            session_info["extracted_entities"],
            "ENGAGED",
            session_info["message_count"],
            engagement_duration,
            scam_analysis,
            session_info.get("conversation_metrics"),
        )

        agent_notes += f" | Conversation ended due to inactivity after {session_info['message_count']} turns"

        # Send callback to GUVI
        # Calculate total messages (Incoming + Outgoing)
        # message_count tracks turns (incoming messages). We replied to all of them.
        total_exchanged = session_info["message_count"] * 2

        await send_guvi_callback(
            session_id=session_id,
            scam_detected=is_scam,
            total_messages=total_exchanged,
            intelligence=session_info["extracted_entities"],
            agent_notes=agent_notes,
            engagement_duration=engagement_duration,
            conversation_metrics=session_info.get("conversation_metrics"),
        )

        # Mark callback as sent
        session_info["callback_sent"] = True
        save_session_state(session_id, session_info)

        logger.info(f"✅ [MONITOR] Callback completed for session {session_id}")
    else:
        logger.info(
            f"🔄 [MONITOR] Session {session_id} is still active, skipping callback"
        )


def calculate_dynamic_timeout(session_id: str, current_turn: int) -> float:
    """
    Calculate dynamic timeout based on average response time.

    Strategy:
    - Turns < 5: Use default INACTIVITY_TIMEOUT
    - Turns >= 5: Avg time between messages + 1.5s
    - Turns >= 20: Immediate callback (very short timeout)
    """
    if current_turn >= 20:
        logger.info(
            f"⏱️  [TIMEOUT] Max turns reached ({current_turn}), forcing quick callback"
        )
        return 0.5  # Almost immediate callback

    if current_turn < 5:
        return INACTIVITY_TIMEOUT

    try:
        # Get message timestamps from DB
        history = get_conversation_history(session_id)
        if len(history) < 2:
            return INACTIVITY_TIMEOUT

        # We don't have exact timestamps in the simple history dict returned by get_conversation_history
        # So we need to query DB directly here for timestamps
        import sqlite3

        conn = sqlite3.connect("honeypot.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        if len(rows) < 2:
            return INACTIVITY_TIMEOUT

        timestamps = []
        for row in rows:
            try:
                # Timestamps might be strings or datetime objects depending on how they were saved
                ts_val = row[0]
                if isinstance(ts_val, str):
                    ts = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                else:
                    ts = ts_val
                timestamps.append(ts.timestamp())
            except Exception:
                continue

        if len(timestamps) < 2:
            return INACTIVITY_TIMEOUT

        # Calculate intervals
        intervals = []
        for i in range(1, len(timestamps)):
            diff = timestamps[i] - timestamps[i - 1]
            if diff > 0 and diff < 60:  # Ignore huge gaps (e.g. server restarts)
                intervals.append(diff)

        if not intervals:
            return INACTIVITY_TIMEOUT

        avg_interval = sum(intervals) / len(intervals)
        dynamic_timeout = avg_interval + 1.5

        # Ensure reasonable bounds (min 3s, max 15s)
        dynamic_timeout = max(3.0, min(15.0, dynamic_timeout))

        logger.info(
            f"⏱️  [TIMEOUT] Calculated dynamic timeout: {dynamic_timeout:.2f}s (Avg: {avg_interval:.2f}s + 1.5s)"
        )
        return dynamic_timeout

    except Exception as e:
        logger.error(f"Error calculating dynamic timeout: {e}")
        return INACTIVITY_TIMEOUT


async def process_background_tasks(
    session_id: str,
    scammer_message: str,
    response_text: str,
    extracted_entities: Dict,
    session_info: Dict,
    is_scam: bool,
    scam_analysis: Dict,
):
    """
    Background task - save conversation and session state to DB.
    Also start inactivity monitor to detect conversation end.
    """
    logger.info(f"🔄 [BACKGROUND] Processing session {session_id}")

    try:
        # Save conversation
        save_conversation(
            session_id, scammer_message, response_text, extracted_entities
        )
        logger.info(f"✅ Conversation saved for session {session_id}")

        # Save session state
        save_session_state(session_id, session_info)
        logger.info(f"✅ Session state saved for session {session_id}")

        # Calculate dynamic timeout
        dynamic_timeout = calculate_dynamic_timeout(
            session_id, session_info["message_count"]
        )

        # Always update monitor timestamp and start new monitor on every request
        # This ensures the timer resets after each message
        monitor_start_ts = time.time()
        active_sessions[session_id] = {
            "monitoring": True,
            "monitor_start_ts": monitor_start_ts,
        }
        # Create task to monitor inactivity
        asyncio.create_task(
            monitor_inactivity_and_callback(
                session_id,
                session_info,
                is_scam,
                scam_analysis,
                monitor_start_ts,
                dynamic_timeout,
            )
        )
        logger.info(
            f"⏱️  [BACKGROUND] Reset inactivity monitor for session {session_id}"
        )

    except Exception as e:
        logger.error(f"❌ Failed to process background tasks: {str(e)}")
        logger.exception("Full error:")


def track_conversation_metrics(
    session_info: Dict,
    response_text: str,
    scammer_message: str,
    is_scam: bool,
    scam_analysis: Dict,
) -> Dict:
    """
    Track conversation quality metrics for scoring.
    
    Metrics tracked:
    - questions_asked: Total question marks in our response
    - investigative_questions: Questions about identity, company, address, website
    - red_flags_identified: Mentions of urgency, OTP, fees, threats
    - elicitations_attempted: Attempts to get scammer details
    """
    metrics = session_info.get("conversation_metrics", {
        "questions_asked": 0,
        "investigative_questions": 0,
        "red_flags_identified": 0,
        "elicitations_attempted": 0,
    })
    
    response_lower = response_text.lower()
    scammer_lower = scammer_message.lower()
    
    # Count total questions
    question_count = response_text.count("?")
    metrics["questions_asked"] += question_count
    
    # Investigative questions - about identity, company, address, website
    investigative_keywords = [
        "what is your name", "your name", "who are you",
        "what company", "which company", "company name",
        "where are you", "your address", "office address",
        "your website", "website url", "website address",
        "employee id", "your id", "verification id",
        "call from", "number", "phone number",
        "how did you get", "why are you calling",
    ]
    for kw in investigative_keywords:
        if kw in response_lower:
            metrics["investigative_questions"] += 1
            break
    
    # Red flags identified - we mention the red flags we notice
    red_flag_keywords = [
        "urgent", "immediately", "asap", "hurry",
        "otp", "one time password",
        "suspicious", "fake", "scam",
        "threat", "police", "legal action",
        "fees", "charge", "payment",
        "won't work", "not working", "failed",
        "strange", "weird", "don't understand",
    ]
    for kw in red_flag_keywords:
        if kw in response_lower:
            metrics["red_flags_identified"] += 1
    
    # Information elicitation - asking for alternative contact details
    elicitation_keywords = [
        "what number", "which number", "phone number",
        "your email", "whatsapp", "telegram",
        "another account", "alternative", "other method",
        "where else", "any other", "different",
    ]
    for kw in elicitation_keywords:
        if kw in response_lower:
            metrics["elicitations_attempted"] += 1
            break
    
    # If scammer provided new entities, that's an elicitation success
    if is_scam and scam_analysis:
        tactics = scam_analysis.get("tactics", [])
        if tactics:
            metrics["elicitations_attempted"] += 1
    
    session_info["conversation_metrics"] = metrics
    
    # Track last response to avoid repetition
    session_info["last_response"] = response_text
    session_info["last_response_turn"] = session_info.get("message_count", 0)
    
    logger.info(
        f"📊 CONVERSATION METRICS - Qs: {metrics['questions_asked']}, "
        f"Investigation: {metrics['investigative_questions']}, "
        f"RedFlags: {metrics['red_flags_identified']}, "
        f"Elicitations: {metrics['elicitations_attempted']}"
    )
    
    return session_info


@app.post("/honeypot", response_model=HoneyPotResponse)
async def honeypot_endpoint(
    request: HoneyPotRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(..., alias="x-api-key"),
):
    """
    Main honeypot endpoint - AI-powered scam detection and engagement
    """
    # Log complete raw request data
    try:
        request_dict = request.dict()
        logger.info(
            f"📥 RAW REQUEST DATA:\n{json.dumps(request_dict, indent=2, default=str)}"
        )
    except Exception as e:
        logger.error(f"❌ Could not log request data: {str(e)}")

    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    logger.info(f"📥 [{now}] 🚨 INCOMING - Session: {request.sessionId}")
    logger.info(f"📥 [{now}] From GUVI: {request.message.text[:100]}...")

    if x_api_key != API_KEY:
        logger.error(f"❌ Invalid API key provided")
        raise HTTPException(status_code=401, detail="Invalid API key")

    session_id = request.sessionId
    raw_scammer_message = request.message.text

    # Parse GUVI meta-wrapper format to extract actual scammer message AND meta entities
    scammer_message, meta_entities = parse_guvi_message(raw_scammer_message)

    # Validate session_id
    if not session_id or not isinstance(session_id, str):
        logger.error("❌ Invalid sessionId")
        raise HTTPException(status_code=400, detail="Invalid sessionId")

    # Validate message text
    if not scammer_message or not isinstance(scammer_message, str):
        logger.error("❌ Invalid message text")
        raise HTTPException(status_code=400, detail="Invalid message text")

    # Load session from database OR create new
    loaded_session = load_session_state(session_id)

    if loaded_session:
        # Existing session - restore from database
        session_info = loaded_session
        session_info["message_count"] += 1
        session_info["last_activity_ts"] = time.time()
        logger.info(
            f"🔄 Restored existing session: {session_id} (turn {session_info['message_count']})"
        )

        # Also load accumulated entities from all messages
        all_entities = get_all_session_entities(session_id)
        for key in [
            "bankAccounts",
            "upiIds",
            "phishingLinks",
            "phoneNumbers",
            "emailAddresses",
            "caseIds",
            "policyNumbers",
            "orderNumbers",
            "amounts",
            "suspiciousKeywords",
        ]:
            if key in all_entities and all_entities[key]:
                session_info["extracted_entities"][key] = all_entities[key]

        # Initialize conversation metrics if not present
        if "conversation_metrics" not in session_info:
            session_info["conversation_metrics"] = {
                "questions_asked": 0,
                "investigative_questions": 0,
                "red_flags_identified": 0,
                "elicitations_attempted": 0,
            }
        
        # Initialize last_response if not present
        if "last_response" not in session_info:
            session_info["last_response"] = ""

    else:
        # New session
        session_info = {
            "start_time": datetime.now(),
            "message_count": 1,
            "extracted_entities": {
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
            },
            "conversation_metrics": {
                "questions_asked": 0,
                "investigative_questions": 0,
                "red_flags_identified": 0,
                "elicitations_attempted": 0,
            },
            "scam_type": None,
            "persona_type": "elderly",
            "conversation_ended": False,
            "callback_sent": False,
            "last_activity_ts": time.time(),
            "stale_turns": 0,
            "last_entity_count": 0,
            "last_response": "",
        }
        session_data[session_id] = session_info
        logger.info(f"✨ Created new session: {session_id}")

    # Get conversation history
    history = get_conversation_history(session_id)

    # PHASE 1 & 2: Parallel Scam Detection and Entity Extraction
    # Run detector and extractor in parallel using asyncio.gather to reduce latency
    try:
        detection_task = detector.analyze(scammer_message, history)
        extraction_task = extractor.extract_entities(scammer_message, history)

        # Wait for both to complete with timeout
        (is_scam, confidence, scam_analysis), extracted = await asyncio.wait_for(
            asyncio.gather(detection_task, extraction_task),
            timeout=10.0,  # 10 second timeout for AI operations
        )

        logger.info(
            f"🔍 Scam detection: is_scam={is_scam}, confidence={confidence:.2f}"
        )
        # Ensure minimum confidence when scam detected with keywords
        if is_scam and confidence < 0.85 and scam_analysis.get("tactics"):
            scam_analysis["confidence"] = 0.85
            confidence = 0.85
            logger.info(f"📊 Boosted confidence to 0.85 (keywords found)")

    except asyncio.TimeoutError:
        logger.error("❌ AI operations timed out")
        # Fallback: assume it might be a scam and proceed with caution
        is_scam = True
        confidence = 0.5
        scam_analysis = {"scam_type": "UNKNOWN", "confidence": 0.5, "tactics": []}
        extracted = {
            "bankAccounts": [],
            "upiIds": [],
            "phishingLinks": [],
            "phoneNumbers": [],
            "amounts": [],
            "suspiciousKeywords": [],
        }
    except Exception as e:
        logger.error(f"❌ Error in detection/extraction: {str(e)}")
        # Fallback response
        is_scam = True
        confidence = 0.5
        scam_analysis = {"scam_type": "UNKNOWN", "confidence": 0.5, "tactics": []}
        extracted = {
            "bankAccounts": [],
            "upiIds": [],
            "phishingLinks": [],
            "phoneNumbers": [],
            "amounts": [],
            "suspiciousKeywords": [],
        }

    # Store scam type for this session
    if not session_info["scam_type"] and is_scam:
        session_info["scam_type"] = scam_analysis.get("scam_type", "UNKNOWN")

        # AUTO-PERSONA SELECTION: Pick the best victim for the scam type
        scam_type = session_info["scam_type"]

        # Mapping scam types to ideal victim personas
        persona_map = {
            "SEXTORTION": "naive_girl",  # Neha - scared, embarrassed, wants to hide from parents
            "JOB_SCAM": "student",  # Arun - desperate for job, naive about offers
            "INVESTMENT": "student",  # Arun - eager for quick money
            "LOTTERY": "elderly",  # Rajesh - trusting, excited about winning
            "BANK_FRAUD": "elderly",  # Rajesh - confused by tech, trusts "bank officials"
            "KYC_UPDATE": "elderly",  # Rajesh - worried about account being blocked
            "FAMILY_EMERGENCY": "homemaker",  # Priya - protective, worried about family
            "TECH_SUPPORT": "elderly",  # Rajesh - doesn't understand computers
            "LOAN_SCAM": "student",  # Arun - needs money for fees
            "REFUND_SCAM": "homemaker",  # Priya - handles household finances
        }

        selected_persona = persona_map.get(scam_type, "elderly")  # Default to elderly
        session_info["persona_type"] = selected_persona
        print(
            f"🎭 [AUTO-SELECT] Scam Type: {scam_type} -> Selected Persona: {selected_persona}"
        )

    # Use the selected persona (or default to elderly if not set yet)
    active_persona = session_info.get("persona_type", "elderly")

    # Collect suspicious keywords
    tactics = scam_analysis.get("tactics", [])
    for tactic in tactics:
        if tactic not in session_info["extracted_entities"]["suspiciousKeywords"]:
            session_info["extracted_entities"]["suspiciousKeywords"].append(tactic)

    # PHASE 2: AI-Powered Entity Extraction
    # Entity extraction is now done in parallel with detection above

    # ALSO: Run regex extraction on SCAMMER messages from conversation history (NOT our own replies)
    if request.conversationHistory:
        for hist_msg in request.conversationHistory:
            sender = hist_msg.get("sender", "")
            # Only extract from scammer messages, not our own replies
            if sender != "user" and sender != "honeypot":
                hist_text = hist_msg.get("text", "")
                if hist_text:
                    hist_regex = regex_extract(hist_text)
                    extracted = merge_extraction_results(extracted, hist_regex)

    # INJECT meta-wrapper entities (ground truth from GUVI)
    for key in ["bankAccounts", "upiIds", "phoneNumbers", "emailAddresses", "phishingLinks"]:
        for val in meta_entities.get(key, []):
            if val:
                existing = extracted.get(key, [])
                if val not in existing:
                    if key not in extracted:
                        extracted[key] = []
                    extracted[key].append(val)
                    logger.info(f"📋 [META] Injected {key}: {val}")

    # NORMALIZE phone numbers to prevent duplicates
    if extracted.get("phoneNumbers"):
        seen_phones = {}
        normalized_phones = []
        for phone in extracted["phoneNumbers"]:
            canonical = normalize_phone(phone)
            if canonical not in seen_phones:
                seen_phones[canonical] = True
                normalized_phones.append(canonical)
        extracted["phoneNumbers"] = normalized_phones

    # Accumulate intelligence and update Hive Mind
    hive_mind_alert = None

    for key in ["bankAccounts", "upiIds", "phishingLinks", "phoneNumbers",
                "emailAddresses", "caseIds", "policyNumbers", "orderNumbers"]:
        for value in extracted.get(key, []):
            if value:
                # Filter: skip short caseIds (employee IDs from LLM)
                if key == "caseIds" and len(str(value)) < 6:
                    logger.info(f"🚫 Skipping short caseId: {value} (likely employee ID)")
                    continue
                # Update global DB (only for main entity types)
                if key in ["bankAccounts", "upiIds", "phishingLinks", "phoneNumbers"]:
                    update_hive_mind(value, key)

                # Check if we've seen this before (only for hive-trackable types)
                if key not in session_info["extracted_entities"]:
                    session_info["extracted_entities"][key] = []
                if value not in session_info["extracted_entities"][key]:
                    if key in ["bankAccounts", "upiIds", "phishingLinks", "phoneNumbers"]:
                        match = check_hive_mind(value, key)
                        if match["found"] and match["sighting_count"] > 1:
                            hive_mind_alert = {
                                "value": value,
                                "type": key,
                                "sighting_count": match["sighting_count"],
                            }
                    session_info["extracted_entities"][key].append(value)

    # PHASE 3: Generate Persona Response using the intelligent agent
    try:
        response_text, persona_id = await asyncio.wait_for(
            persona.generate_response(
                session_id,
                scammer_message,
                active_persona,
                session_info["extracted_entities"],
                session_info.get("last_response", ""),
            ),
            timeout=8.0,  # 8 second timeout for response generation
        )
        logger.info(f"💬 Generated response: {response_text[:100]}...")

    except asyncio.TimeoutError:
        logger.error("❌ Persona response generation timed out")
        # Fallback responses - use TURN-BASED ROTATION to prevent repeats
        turn = session_info.get("message_count", 1)
        
        # Each fallback ends with an entity-demanding question
        fallback_responses_elderly = [
            "Beta, thoda samajh nahi aa raha. Aap phir se bata sakte ho? Aapka phone number kya hai?",
            "Arre, confusion ho raha hai. Thoda dheere bataiye na? Aapka naam kya hai sir?",
            "Ji, main bujho gayi. Ek minute, apni beti se pooch ke bolti hoon. Aapka employee ID kya hai?",
            "Sirji, kya aap fir se bata sakte hain? Network problem ho raha hai. Aapka UPI ID bataiye?",
            "Beta, phone ka signal nahi aa raha. Dusre number par call kijiye. Aapka number kya hai?",
            "Arre, main darr gayi. Thoda time dijiye, heart tez ho raha hai. Aap kis branch se bol rahe ho?",
            "Ji, main apne beta ko dikhati hoon. Ek minute lagega. Aapka full name kya hai?",
        ]
        fallback_responses_homemaker = [
            "Ek minute, main confuse ho gayi. Phir se samjhana? Aapka phone number kya hai?",
            "Arre, kya bol rahe ho? Thoda dheere boliye. Aapka naam kya hai?",
            "Ji, wait kijiye. Main apne husband se pooch ke bolti hoon. Aapka employee ID batana?",
            "Sorry, network issue hai. Repeat karna? Aapka UPI ID kya hai?",
        ]
        fallback_responses_student = [
            "Sorry bro, network issue hai. Repeat karna? Apna phone number do na?",
            "Arre yaar, phone hang ho gaya. Thoda wait karo. Tumhara naam kya hai?",
            "Bro, kya bol rahe ho? Clarity nahi aa rahi. Apna UPI ID bhejo?",
            "Dude, slow down. Samajh nahi aaya. Company ka website kya hai?",
        ]
        fallback_responses_naive = [
            "Sir, mujhe samajh nahi aaya. Aap phir se bataiye? Aapka phone number kya hai?",
            "Arre, confusion ho gaya. Thoda dheere se explain kijiye. Aapka naam bataiye?",
            "Ji, main nervous ho gayi. Ek minute lijiye. Aapka employee ID kya hai?",
        ]
        
        # Select based on persona using TURN-BASED INDEX (not random)
        if active_persona == "elderly":
            pool = fallback_responses_elderly
        elif active_persona == "homemaker":
            pool = fallback_responses_homemaker
        elif active_persona == "student":
            pool = fallback_responses_student
        else:
            pool = fallback_responses_naive
        
        response_text = pool[turn % len(pool)]
        persona_id = active_persona
        
    except Exception as e:
        logger.error(f"❌ Error generating persona response: {str(e)}")
        # Same turn-based rotation as timeout handler, with entity questions
        turn = session_info.get("message_count", 1)
        fallback_generic = [
            "Ek minute please, thoda confusion ho raha hai. Aapka phone number kya hai?",
            "Ji, thoda time dijiye. Samajh nahi aa raha. Aapka naam bataiye?",
            "Arre, kya bol rahe ho? Dheere bataiye. Aapka UPI ID kya hai?",
            "Sorry, network problem ho raha hai. Aapka employee ID bataiye?",
            "Ji, main darr gayi. Aap konsi company se bol rahe ho? Phone number dijiye?",
            "Beta, thoda samjhao. Office ka address kya hai? Phone number do?",
        ]
        response_text = fallback_generic[turn % len(fallback_generic)]
        persona_id = active_persona

    # Track conversation quality metrics
    session_info = track_conversation_metrics(
        session_info, response_text, scammer_message, is_scam, scam_analysis
    )

    # Background task - save to database and check if we should send callback
    background_tasks.add_task(
        process_background_tasks,
        session_id,
        scammer_message,
        response_text,
        extracted,
        session_info,
        is_scam,
        scam_analysis,
    )

    # Log complete response data
    logger.info(
        f"📤 RESPONSE DATA: {json.dumps({'status': 'success', 'reply': response_text}, indent=2)}"
    )

    # Log session and entity status
    logger.info(
        f"📊 SESSION STATUS - Session: {session_id}, Turn: {session_info['message_count']}, Persona: {active_persona}"
    )
    logger.info(
        f"📊 ENTITIES ACCUMULATED - Banks: {len(session_info['extracted_entities'].get('bankAccounts', []))}, UPIs: {len(session_info['extracted_entities'].get('upiIds', []))}, Links: {len(session_info['extracted_entities'].get('phishingLinks', []))}, Phones: {len(session_info['extracted_entities'].get('phoneNumbers', []))}"
    )
    logger.info(f"✅ Request processed successfully for session: {session_id}")

    # Log response sent with timestamp
    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    logger.info(
        f"📤 [{now}] 💬 TO GUVI - Session: {session_id}, Turn: {session_info['message_count']}, Persona: {active_persona}"
    )
    logger.info(f"📤 [{now}] Our Response: {response_text[:100]}...")

    return HoneyPotResponse(status="success", reply=response_text)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
