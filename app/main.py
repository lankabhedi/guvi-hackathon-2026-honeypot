from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from typing import Optional, List, Dict, Any, Union
import uvicorn
from dotenv import load_dotenv
import sys
import os
import requests
import json
import asyncio
import time
from datetime import datetime

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
)

load_dotenv()

app = FastAPI(title="Agentic Honey-Pot API - Intelligence Grade")

# Configuration
API_KEY = os.getenv("API_KEY", "hackathon-api-key-2026")
GUVI_CALLBACK_URL = "https://hackathon.guvi.in/api/updateHoneyPotFinalResult"
MAX_CONVERSATION_TURNS = 20
STALE_TURN_LIMIT = 5  # End if no new intel for 5 turns
INACTIVITY_TIMEOUT = 60  # End if no message for 60 seconds

# Initialize components
detector = ScamDetector()
persona = PersonaEngine()
extractor = EntityExtractor()
profiler = ScammerProfiler()

# Session tracking
session_data = {}


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


@app.on_event("startup")
async def startup_event():
    init_db()


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

        print(f"✅ GUVI Callback sent: {response.status_code}")
        if response.status_code != 200:
            print(f"⚠️  Callback response: {response.text}")

    except Exception as e:
        print(f"❌ Failed to send GUVI callback: {e}")
        # Log locally as backup
        with open(f"callback_backup_{session_id}.json", "w") as f:
            json.dump(payload, f, indent=2)


async def monitor_inactivity(session_id: str):
    """Wait for inactivity timeout and trigger termination if needed"""
    print(
        f"⏳ [MONITOR] Started inactivity monitor for {session_id} (Timeout: {INACTIVITY_TIMEOUT}s)"
    )
    # Wait 60 seconds (or configured timeout)
    await asyncio.sleep(INACTIVITY_TIMEOUT)

    # Check if session still exists and needs termination
    if session_id not in session_data:
        return

    session_info = session_data[session_id]

    # If conversation already ended, do nothing
    if session_info.get("conversation_ended", False):
        return

    # Check time since last activity
    time_since_activity = time.time() - session_info["last_activity_ts"]

    # Allow a small buffer (e.g., 2 seconds) for processing time variance
    if time_since_activity >= INACTIVITY_TIMEOUT - 2:
        print(
            f"⏰ [TIMEOUT] Session {session_id} inactive for {time_since_activity:.1f}s. Ending."
        )

        # Trigger termination logic
        # We need to construct the necessary data for the callback
        # Since this runs in background, we fetch latest state

        # Mark as ended to prevent duplicates
        session_info["conversation_ended"] = True

        # Calculate duration
        engagement_duration = (
            datetime.now() - session_info["start_time"]
        ).total_seconds()

        # Generate final notes
        agent_notes = build_agent_notes(
            session_info["scam_type"] or "UNKNOWN",
            session_info["extracted_entities"],
            "TIMEOUT",
            session_info["message_count"],
            engagement_duration,
            {"confidence": 0, "risk_level": "UNKNOWN"},  # Placeholder analysis
        )

        agent_notes += " | Ended due to inactivity timeout."

        # Send callback
        await send_guvi_callback(
            session_id=session_id,
            scam_detected=True,  # Assuming true if we engaged this long
            total_messages=session_info["message_count"],
            intelligence=session_info["extracted_entities"],
            agent_notes=agent_notes,
            engagement_duration=int(engagement_duration),
        )


def check_staleness(session_info: Dict) -> bool:
    """
    Check if we are getting new intel.
    Returns True if conversation is STALE (no new intel for N turns).
    """
    current_entities = session_info["extracted_entities"]

    # Calculate a hash/count of current known entities
    current_count = 0
    for key in [
        "bankAccounts",
        "upiIds",
        "phishingLinks",
        "phoneNumbers",
        "suspiciousKeywords",
    ]:
        current_count += len(current_entities.get(key, []))

    prev_count = session_info.get("last_entity_count", 0)

    if current_count > prev_count:
        # We got new intel! Reset stale counter
        session_info["stale_turns"] = 0
        session_info["last_entity_count"] = current_count
        print(
            f"✨ New intel detected! Stale counter reset. (Total entities: {current_count})"
        )
        return False
    else:
        # No new intel
        session_info["stale_turns"] += 1
        print(
            f"⚠️ No new intel. Stale turns: {session_info['stale_turns']}/{STALE_TURN_LIMIT}"
        )
        return session_info["stale_turns"] >= STALE_TURN_LIMIT


async def process_background_tasks(
    session_id: str,
    scammer_message: str,
    response_text: str,
    history: List[Dict],
    session_info: Dict,
    is_scam: bool,
    scam_analysis: Dict,
    current_mood: str,
    extracted_entities: Dict,  # Pass extracted entities to save function
):
    """
    Handle post-response logic: DB Save, Staleness Check, Timeout Monitor
    Run in background to avoid API timeouts.
    """
    print(f"🔄 [BACKGROUND] Processing post-response tasks for session {session_id}")

    # Save conversation (Moved to background to unblock response)
    save_conversation(session_id, scammer_message, response_text, extracted_entities)

    # Check Staleness (Engagement Sufficiency)
    is_stale = check_staleness(session_info)
    should_end = False
    end_reason = ""

    if is_stale:
        should_end = True
        end_reason = "STALE_INTERACTION"
    elif session_info["message_count"] >= MAX_CONVERSATION_TURNS:
        should_end = True
        end_reason = "MAX_TURNS"

    # End conversation if needed
    if should_end and is_scam and not session_info["conversation_ended"]:
        session_info["conversation_ended"] = True
        print(f"🛑 [BACKGROUND] Ending conversation. Reason: {end_reason}")

        # Calculate engagement metrics
        engagement_duration = (
            datetime.now() - session_info["start_time"]
        ).total_seconds()

        # Build scammer profile
        scammer_profile = profiler.analyze_scammer(
            session_id, history, session_info["extracted_entities"], scam_analysis
        )

        # Prepare comprehensive intelligence report
        agent_notes = build_agent_notes(
            session_info["scam_type"],
            session_info["extracted_entities"],
            current_mood,
            session_info["message_count"],
            engagement_duration,
            scam_analysis,
        )

        # Add profiling insights to agent notes
        agent_notes += f" | Scammer Profile: {scammer_profile['communication_style']}, "
        agent_notes += (
            f"Aggression: {scammer_profile['behavioral_metrics']['aggression_level']}, "
        )
        agent_notes += f"Persistence: {scammer_profile['patience_level']}"
        agent_notes += f" | Ended reason: {end_reason}"

        # Send callback to GUVI
        await send_guvi_callback(
            session_id=session_id,
            scam_detected=is_scam,
            total_messages=session_info["message_count"],
            intelligence=session_info["extracted_entities"],
            agent_notes=agent_notes,
            engagement_duration=int(engagement_duration),
        )


@app.post("/honeypot", response_model=HoneyPotResponse)
async def honeypot_endpoint(
    request: HoneyPotRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(...),
):
    """
    Main honeypot endpoint - AI-powered scam detection and engagement
    """
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    session_id = request.sessionId
    scammer_message = request.message.text

    # Initialize session if new
    if session_id not in session_data:
        session_data[session_id] = {
            "start_time": datetime.now(),
            "message_count": 0,
            "extracted_entities": {
                "bankAccounts": [],
                "upiIds": [],
                "phishingLinks": [],
                "phoneNumbers": [],
                "amounts": [],
                "suspiciousKeywords": [],
            },
            "scam_type": None,
            "persona_type": "elderly",  # Default
            "conversation_ended": False,
            # New tracking fields
            "last_activity_ts": time.time(),
            "stale_turns": 0,
            "last_entity_count": 0,
        }

    session_info = session_data[session_id]
    session_info["message_count"] += 1
    session_info["last_activity_ts"] = time.time()  # Update activity timestamp

    # Get conversation history
    history = get_conversation_history(session_id)

    # PHASE 1 & 2: Parallel Scam Detection and Entity Extraction
    # Run detector and extractor in parallel using asyncio.gather to reduce latency
    detection_task = detector.analyze(scammer_message, history)
    extraction_task = extractor.extract_entities(scammer_message, history)

    # Wait for both to complete
    (is_scam, confidence, scam_analysis), extracted = await asyncio.gather(
        detection_task, extraction_task
    )

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
    response_text, persona_id = await persona.generate_response(
        session_id,
        scammer_message,
        active_persona,
        session_info["extracted_entities"],
    )

    # For backward compatibility with background tasks
    current_mood = "ENGAGED"

    # PHASE 4: Background Processing (Lifecycle & Callback)
    # This prevents the API from timing out while doing heavy analysis/reporting

    # 1. Process post-response logic (save to DB, check staleness, send callback if stale)
    background_tasks.add_task(
        process_background_tasks,
        session_id,
        scammer_message,
        response_text,
        history,
        session_info,
        is_scam,
        scam_analysis,
        current_mood,
        extracted,  # Pass extracted entities
    )

    # 2. Launch Inactivity Monitor (Timeout)
    # This will sleep for 60s and check if no new activity happened
    background_tasks.add_task(monitor_inactivity, session_id)

    return HoneyPotResponse(status="success", reply=response_text)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
