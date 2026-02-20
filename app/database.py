import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
import os
import json


def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect("honeypot.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT UNIQUE,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            total_turns INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            turn_number INTEGER,
            scammer_message TEXT,
            response TEXT,
            extracted_entities TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS known_scammers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            value TEXT UNIQUE,
            type TEXT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            sighting_count INTEGER DEFAULT 1,
            risk_score FLOAT DEFAULT 0.0
        )
    """)

    # Session context tables for the intelligent agent
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_context (
            session_id TEXT PRIMARY KEY,
            persona TEXT,
            summary TEXT DEFAULT '',
            memory TEXT DEFAULT '{}',
            turn_count INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            turn_number INTEGER,
            timestamp TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES session_context(session_id)
        )
    """)

    # NEW: Session state table to persist session_data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_state (
            session_id TEXT PRIMARY KEY,
            start_time TIMESTAMP,
            message_count INTEGER DEFAULT 0,
            extracted_entities TEXT DEFAULT '{}',
            scam_type TEXT,
            persona_type TEXT DEFAULT 'elderly',
            conversation_ended BOOLEAN DEFAULT 0,
            last_activity_ts TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def get_conversation_history(conversation_id: str) -> List[Dict]:
    """Get conversation history from database"""
    conn = sqlite3.connect("honeypot.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT turn_number, scammer_message, response, extracted_entities
        FROM messages
        WHERE conversation_id = ?
        ORDER BY turn_number
    """,
        (conversation_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    history = []
    for row in rows:
        history.append(
            {
                "turn_number": row[0],
                "scammer_message": row[1],
                "response": row[2],
                "extracted_entities": row[3],
            }
        )

    return history


def save_session_state(session_id: str, session_info: Dict[str, Any]):
    """Save session state to database for persistence"""
    conn = sqlite3.connect("honeypot.db")
    cursor = conn.cursor()

    # Convert extracted_entities dict to JSON string
    entities_json = json.dumps(session_info.get("extracted_entities", {}))

    cursor.execute(
        """
        INSERT OR REPLACE INTO session_state 
        (session_id, start_time, message_count, extracted_entities, scam_type, 
         persona_type, conversation_ended, last_activity_ts, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            session_id,
            session_info.get("start_time", datetime.now()),
            session_info.get("message_count", 0),
            entities_json,
            session_info.get("scam_type"),
            session_info.get("persona_type", "elderly"),
            session_info.get("conversation_ended", False),
            session_info.get("last_activity_ts", datetime.now().timestamp()),
            datetime.now(),
        ),
    )

    conn.commit()
    conn.close()


def load_session_state(session_id: str) -> Optional[Dict[str, Any]]:
    """Load session state from database"""
    conn = sqlite3.connect("honeypot.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT start_time, message_count, extracted_entities, scam_type, 
               persona_type, conversation_ended, last_activity_ts
        FROM session_state WHERE session_id = ?
    """,
        (session_id,),
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        # Parse JSON entities
        try:
            extracted_entities = json.loads(row[2])
        except:
            extracted_entities = {
                "bankAccounts": [],
                "upiIds": [],
                "phishingLinks": [],
                "phoneNumbers": [],
                "amounts": [],
                "suspiciousKeywords": [],
            }

        return {
            "start_time": row[0],
            "message_count": row[1],
            "extracted_entities": extracted_entities,
            "scam_type": row[3],
            "persona_type": row[4] or "elderly",
            "conversation_ended": bool(row[5]),
            "last_activity_ts": row[6],
            "stale_turns": 0,
            "last_entity_count": 0,
        }

    return None


def get_all_session_entities(session_id: str) -> Dict[str, Any]:
    """Get all extracted entities from all messages in a session"""
    conn = sqlite3.connect("honeypot.db")
    cursor = conn.cursor()

    # Get all entities from messages table
    cursor.execute(
        """
        SELECT extracted_entities FROM messages 
        WHERE conversation_id = ? ORDER BY turn_number
    """,
        (session_id,),
    )

    rows = cursor.fetchall()
    conn.close()

    # Aggregate all entities
    aggregated = {
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
    }

    for row in rows:
        try:
            entities = json.loads(row[0])
            for key in aggregated.keys():
                if key in entities and isinstance(entities[key], list):
                    # Add unique values only
                    for val in entities[key]:
                        if val and val not in aggregated[key]:
                            aggregated[key].append(val)
        except:
            pass

    return aggregated


def save_conversation(
    conversation_id: str, scammer_message: str, response: str, entities: Dict[str, Any]
):
    """Save a conversation turn"""
    conn = sqlite3.connect("honeypot.db")
    cursor = conn.cursor()

    # Check if conversation exists
    cursor.execute(
        "SELECT id FROM conversations WHERE conversation_id = ?", (conversation_id,)
    )
    if not cursor.fetchone():
        cursor.execute(
            """
            INSERT INTO conversations (conversation_id, start_time, total_turns)
            VALUES (?, ?, 0)
        """,
            (conversation_id, datetime.now()),
        )

    # Get next turn number
    cursor.execute(
        """
        SELECT MAX(turn_number) FROM messages WHERE conversation_id = ?
    """,
        (conversation_id,),
    )
    result = cursor.fetchone()
    turn_number = (result[0] or 0) + 1

    # Insert message
    cursor.execute(
        """
        INSERT INTO messages (conversation_id, turn_number, scammer_message, response, extracted_entities, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            conversation_id,
            turn_number,
            scammer_message,
            response,
            json.dumps(entities),  # Use json.dumps for proper JSON
            datetime.now(),
        ),
    )

    # Update conversation
    cursor.execute(
        """
        UPDATE conversations SET total_turns = ? WHERE conversation_id = ?
    """,
        (turn_number, conversation_id),
    )

    conn.commit()
    conn.close()


def check_hive_mind(entity_value: str, entity_type: str) -> Dict[str, Any]:
    """Check if an entity exists in the global scammer database"""
    conn = sqlite3.connect("honeypot.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT first_seen, sighting_count, risk_score FROM known_scammers WHERE value = ?",
        (entity_value,),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "found": True,
            "first_seen": row[0],
            "sighting_count": row[1],
            "risk_score": row[2],
        }
    return {"found": False}


def update_hive_mind(entity_value: str, entity_type: str):
    """Add or update an entity in the global scammer database"""
    conn = sqlite3.connect("honeypot.db")
    cursor = conn.cursor()

    # Check if exists
    cursor.execute(
        "SELECT id, sighting_count FROM known_scammers WHERE value = ?", (entity_value,)
    )
    row = cursor.fetchone()

    if row:
        # Update existing
        new_count = row[1] + 1
        cursor.execute(
            """
            UPDATE known_scammers 
            SET sighting_count = ?, last_seen = ?, risk_score = risk_score + 0.1
            WHERE id = ?
            """,
            (new_count, datetime.now(), row[0]),
        )
    else:
        # Insert new
        cursor.execute(
            """
            INSERT INTO known_scammers (value, type, first_seen, last_seen, sighting_count, risk_score)
            VALUES (?, ?, ?, ?, 1, 0.5)
            """,
            (entity_value, entity_type, datetime.now(), datetime.now()),
        )

    conn.commit()
    conn.close()
