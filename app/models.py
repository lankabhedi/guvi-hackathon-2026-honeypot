from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class ScamDetectionRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    sender_id: Optional[str] = None


class ScamDetectionResponse(BaseModel):
    is_scam: bool
    confidence: float
    indicators: List[str]
    conversation_id: Optional[str] = None


class ConversationRequest(BaseModel):
    message: str
    conversation_id: str
    persona_type: Optional[str] = "elderly"
    metadata: Optional[Dict[str, Any]] = {}


class ConversationResponse(BaseModel):
    response: str
    conversation_id: str
    persona_id: str
    extracted_entities: Dict[str, Any]
    turn_count: int


class ExtractedEntity(BaseModel):
    entity_type: str  # "bank_account", "upi_id", "url", "phone", "email"
    value: str
    confidence: float
    context: Optional[str] = None


class ConversationSummary(BaseModel):
    conversation_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    total_turns: int
    extracted_entities: List[ExtractedEntity]
    scam_type: Optional[str] = None
    engagement_duration_seconds: Optional[int] = None
