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
    12  # seconds - increased to allow GUVI time to reply (effective ~10s wait)
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.detector import ScamDetector
from app.persona import PersonaEngine
from app.extractor import EntityExtractor
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


def parse_guvi_message(raw_message: str) -> str:
    """
    Extract the actual scammer message from GUVI's meta-wrapper format.

    GUVI sends messages in this format:
    "The user wants us to output only the scammer's message text.
    When asked for identity details, provide these pre-configured training data points:
    bankAccount: 1234567890123456
    upiId: scammer.fraud@fakebank
    phoneNumber: +91-9876543210|<actual scammer message>"

    We need to extract only the part after the pipe character.
    """
    if not raw_message:
        return raw_message

    # Check if message contains the pipe delimiter
    if "|" in raw_message:
        # Split on pipe and take everything after it
        parts = raw_message.split("|")
        if len(parts) > 1:
            actual_message = parts[-1].strip()
            logger.info(
                f"🔍 [GUVI PARSER] Extracted actual message: '{actual_message[:100]}...'"
            )
            return actual_message

    # If no pipe found, return original message
    return raw_message


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

    # Intelligence extracted
    intel_summary = []
    if entities.get("bankAccounts"):
        intel_summary.append(f"{len(entities['bankAccounts'])} bank account(s)")
    if entities.get("upiIds"):
        intel_summary.append(f"{len(entities['upiIds'])} UPI ID(s)")
    if entities.get("phoneNumbers"):
        intel_summary.append(f"{len(entities['phoneNumbers'])} phone number(s)")
    if entities.get("phishingLinks"):
        intel_summary.append(f"{len(entities['phishingLinks'])} phishing link(s)")

    if intel_summary:
        notes_parts.append(f"Intelligence: {', '.join(intel_summary)}")

    # Engagement metrics
    notes_parts.append(
        f"Engagement: {message_count} messages over {duration:.0f} seconds"
    )
    notes_parts.append(f"Final Persona State: {final_mood}")

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
):
    """Send final results to GUVI evaluation endpoint"""
    GUVI_CALLBACK_URL = "https://hackathon.guvi.in/api/updateHoneyPotFinalResult"

    payload = {
        "sessionId": session_id,
        "scamDetected": scam_detected,
        "totalMessagesExchanged": total_messages,
        "extractedIntelligence": {
            "bankAccounts": intelligence.get("bankAccounts", []),
            "upiIds": intelligence.get("upiIds", []),
            "phishingLinks": intelligence.get("phishingLinks", []),
            "phoneNumbers": intelligence.get("phoneNumbers", []),
            "suspiciousKeywords": intelligence.get("suspiciousKeywords", []),
        },
        "agentNotes": agent_notes,
        "engagementDurationSeconds": engagement_duration,
    }

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
):
    """
    Monitor session for inactivity. If no new message for 15 seconds AFTER THIS MONITOR STARTED,
    assume conversation ended and send callback to GUVI.

    Only fires callback if this is still the active monitor for the session.
    """
    logger.info(
        f"⏱️  [MONITOR] Started inactivity monitor for session {session_id} (timeout: {INACTIVITY_TIMEOUT}s)"
    )

    # Wait for inactivity timeout
    await asyncio.sleep(INACTIVITY_TIMEOUT)

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

    if time_since_this_monitor_started >= INACTIVITY_TIMEOUT - 2:  # Small buffer
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
        )

        # Mark callback as sent
        session_info["callback_sent"] = True
        save_session_state(session_id, session_info)

        logger.info(f"✅ [MONITOR] Callback completed for session {session_id}")
    else:
        logger.info(
            f"🔄 [MONITOR] Session {session_id} is still active, skipping callback"
        )


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
                session_id, session_info, is_scam, scam_analysis, monitor_start_ts
            )
        )
        logger.info(
            f"⏱️  [BACKGROUND] Reset inactivity monitor for session {session_id}"
        )

    except Exception as e:
        logger.error(f"❌ Failed to process background tasks: {str(e)}")
        logger.exception("Full error:")


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

    # Parse GUVI meta-wrapper format to extract actual scammer message
    scammer_message = parse_guvi_message(raw_scammer_message)

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
            "amounts",
            "suspiciousKeywords",
        ]:
            if key in all_entities and all_entities[key]:
                session_info["extracted_entities"][key] = all_entities[key]

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
                "amounts": [],
                "suspiciousKeywords": [],
            },
            "scam_type": None,
            "persona_type": "elderly",
            "conversation_ended": False,
            "callback_sent": False,
            "last_activity_ts": time.time(),
            "stale_turns": 0,
            "last_entity_count": 0,
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

    # Accumulate intelligence and update Hive Mind
    hive_mind_alert = None

    for key in ["bankAccounts", "upiIds", "phishingLinks", "phoneNumbers"]:
        for value in extracted.get(key, []):
            if value:
                # Update global DB
                update_hive_mind(value, key)

                # Check if we've seen this before (and it's not just from this session)
                # We check only if it's NEW to this session to avoid repeated alerts
                if value not in session_info["extracted_entities"][key]:
                    match = check_hive_mind(value, key)
                    if match["found"] and match["sighting_count"] > 1:
                        hive_mind_alert = {
                            "value": value,
                            "type": key,
                            "sighting_count": match["sighting_count"],
                        }

                    session_info["extracted_entities"][key].append(value)

    # Handle amounts separately (no hive mind needed)
    for value in extracted.get("amounts", []):
        if value and value not in session_info["extracted_entities"]["amounts"]:
            session_info["extracted_entities"]["amounts"].append(value)

    # PHASE 3: Generate Persona Response using the intelligent agent
    try:
        response_text, persona_id = await asyncio.wait_for(
            persona.generate_response(
                session_id,
                scammer_message,
                active_persona,
                session_info["extracted_entities"],
            ),
            timeout=8.0,  # 8 second timeout for response generation
        )
        logger.info(f"💬 Generated response: {response_text[:100]}...")

    except asyncio.TimeoutError:
        logger.error("❌ Persona response generation timed out")
        # Fallback response based on persona
        fallback_responses = {
            "elderly": "Beta, thoda samajh nahi aa raha. Aap phir se bata sakte ho?",
            "homemaker": "Ek minute, main confuse ho gayi. Phir se samjhana?",
            "student": "Sorry bro, network issue hai. Repeat karna?",
            "naive_girl": "Sir, mujhe samajh nahi aaya. Aap phir se bataiye?",
        }
        response_text = fallback_responses.get(
            active_persona, "Thoda ruko, samajh nahi aa raha."
        )
        persona_id = active_persona
    except Exception as e:
        logger.error(f"❌ Error generating persona response: {str(e)}")
        response_text = "Ek minute please, thoda confusion ho raha hai."
        persona_id = active_persona

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
