from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from typing import Optional, List, Dict, Any, Union

# ... imports ...


class MessageInput(BaseModel):
    sender: str
    text: str
    timestamp: Union[str, int, float]  # Allow int/float timestamps too


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


@app.on_event("startup")
async def startup_event():
    init_db()


@app.post("/honeypot", response_model=HoneyPotResponse)
async def honeypot_endpoint(request: HoneyPotRequest, x_api_key: str = Header(...)):
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
            "persona_mood": "NEUTRAL",
            "conversation_ended": False,
        }
        persona.reset_mood()

    session_info = session_data[session_id]
    session_info["message_count"] += 1

    # Get conversation history
    history = get_conversation_history(session_id)

    # PHASE 1: AI-Powered Scam Detection
    is_scam, confidence, scam_analysis = detector.analyze(scammer_message, history)

    # Store scam type for this session
    if not session_info["scam_type"] and is_scam:
        session_info["scam_type"] = scam_analysis.get("scam_type", "UNKNOWN")

        # AUTO-PERSONA SELECTION: Pick the best victim for the scam
        scam_type = session_info["scam_type"]
        selected_persona = "elderly"  # Default

        if scam_type == "SEXTORTION":
            selected_persona = "naive_girl"  # Neha acts scared/ashamed
        elif scam_type == "JOB_SCAM" or scam_type == "INVESTMENT":
            selected_persona = "student"  # Arun is desperate/greedy
        elif scam_type == "FAMILY_EMERGENCY":
            selected_persona = "homemaker"  # Priya is protective

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
    extracted = extractor.extract_entities(scammer_message, history)

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

    # PHASE 3: Generate Persona Response with Emotional Intelligence
    response_text, persona_id, current_mood = persona.generate_response(
        scammer_message,
        history,
        scam_analysis,
        active_persona,  # Use auto-selected persona
        session_info["extracted_entities"],
        hive_mind_alert,  # Pass the alert to persona
    )

    # Log persona changes for demo visibility
    if persona_id != active_persona:
        print(
            f"🔄 [PERSONA SWITCH] Switched from {active_persona} to {persona_id} (Mood: {current_mood})"
        )
        session_info["persona_type"] = persona_id  # Persist the switch

    session_info["persona_mood"] = current_mood

    # Save conversation
    save_conversation(session_id, scammer_message, response_text, extracted)

    # PHASE 4: Intelligent Conversation Lifecycle Management
    should_end, end_reason, intel_completeness = (
        extractor.analyze_conversation_for_termination(
            history + [{"scammer_message": scammer_message, "response": response_text}],
            session_info["extracted_entities"],
        )
    )

    # Check hard limits
    if session_info["message_count"] >= MAX_CONVERSATION_TURNS:
        should_end = True
        end_reason = "MAX_TURNS"

    # End conversation if needed
    if should_end and is_scam and not session_info["conversation_ended"]:
        session_info["conversation_ended"] = True

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

        # Send callback to GUVI
        await send_guvi_callback(
            session_id=session_id,
            scam_detected=is_scam,
            total_messages=session_info["message_count"],
            intelligence=session_info["extracted_entities"],
            agent_notes=agent_notes,
            engagement_duration=int(engagement_duration),
        )

        # Cleanup after delay (keep for 1 hour then remove)
        # In production, use background task or Redis TTL

    return HoneyPotResponse(status="success", reply=response_text)


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


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "honey-pot-api",
        "version": "2.0",
        "features": [
            "ai-powered-detection",
            "emotional-state-machine",
            "intelligent-extraction",
            "conversation-lifecycle-management",
        ],
    }


@app.get("/session/{session_id}")
async def get_session_info(session_id: str, x_api_key: str = Header(...)):
    """Get session information and extracted intelligence (for debugging)"""
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if session_id not in session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "sessionId": session_id,
        "data": session_data[session_id],
        "history": get_conversation_history(session_id),
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
