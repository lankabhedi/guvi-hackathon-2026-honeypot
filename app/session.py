"""
Session Manager for Honeypot Agent

Manages conversation context with a sliding window of messages.
When messages exceed the window size, older messages are summarized.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from groq import AsyncGroq
import os


class SessionManager:
    """
    Manages session context for the honeypot agent.

    - Stores conversation history in SQLite
    - Maintains a context window of last N message pairs
    - Summarizes older messages to preserve context without bloating
    - Tracks what the agent has asked for to avoid repetition
    """

    def __init__(self, db_path: str = "honeypot.db", context_window_size: int = 10):
        self.db_path = db_path
        self.context_window_size = context_window_size
        self._client = None
        self.summary_model = "llama-3.1-8b-instant"  # Fast model for summarization
        self._init_tables()

    @property
    def client(self):
        """Lazy initialization of Groq client"""
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable not set")
            self._client = AsyncGroq(api_key=api_key)
        return self._client

    def _init_tables(self):
        """Create session-specific tables if they don't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Session context table
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

        # Session messages table (for context window)
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

        conn.commit()
        conn.close()

    def get_or_create_session(self, session_id: str, persona: str = "elderly") -> Dict:
        """Get existing session or create new one"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT persona, summary, memory, turn_count FROM session_context WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()

        if row:
            context = {
                "session_id": session_id,
                "persona": row[0],
                "summary": row[1],
                "memory": json.loads(row[2]) if row[2] else {},
                "turn_count": row[3],
            }
        else:
            # Create new session
            now = datetime.now()
            cursor.execute(
                """
                INSERT INTO session_context (session_id, persona, summary, memory, turn_count, created_at, updated_at)
                VALUES (?, ?, '', '{}', 0, ?, ?)
                """,
                (session_id, persona, now, now),
            )
            conn.commit()
            context = {
                "session_id": session_id,
                "persona": persona,
                "summary": "",
                "memory": {},
                "turn_count": 0,
            }

        conn.close()
        return context

    def get_messages(self, session_id: str, limit: Optional[int] = None) -> List[Dict]:
        """Get messages for a session, optionally limited to last N pairs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if limit:
            # Get last N*2 messages (N pairs)
            cursor.execute(
                """
                SELECT role, content, turn_number FROM session_messages 
                WHERE session_id = ? 
                ORDER BY turn_number DESC, id DESC
                LIMIT ?
                """,
                (session_id, limit * 2),
            )
            rows = cursor.fetchall()
            rows.reverse()  # Put back in chronological order
        else:
            cursor.execute(
                """
                SELECT role, content, turn_number FROM session_messages 
                WHERE session_id = ? 
                ORDER BY turn_number, id
                """,
                (session_id,),
            )
            rows = cursor.fetchall()

        conn.close()

        return [{"role": row[0], "content": row[1], "turn": row[2]} for row in rows]

    def add_message(self, session_id: str, role: str, content: str, turn_number: int):
        """Add a message to the session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO session_messages (session_id, role, content, turn_number, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, turn_number, datetime.now()),
        )

        # Update session turn count
        cursor.execute(
            "UPDATE session_context SET turn_count = ?, updated_at = ? WHERE session_id = ?",
            (turn_number, datetime.now(), session_id),
        )

        conn.commit()
        conn.close()

    def update_memory(self, session_id: str, memory: Dict):
        """Update session memory"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE session_context SET memory = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(memory), datetime.now(), session_id),
        )

        conn.commit()
        conn.close()

    def update_summary(self, session_id: str, summary: str):
        """Update the summary of older messages"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE session_context SET summary = ?, updated_at = ? WHERE session_id = ?",
            (summary, datetime.now(), session_id),
        )

        conn.commit()
        conn.close()

    def get_message_count(self, session_id: str) -> int:
        """Get total number of message pairs in session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT MAX(turn_number) FROM session_messages WHERE session_id = ?",
            (session_id,),
        )
        result = cursor.fetchone()
        conn.close()

        return result[0] if result[0] else 0

    async def summarize_old_messages(self, session_id: str) -> str:
        """
        When context window overflows, summarize the oldest messages.
        Returns the new summary.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get current summary
        cursor.execute(
            "SELECT summary FROM session_context WHERE session_id = ?", (session_id,)
        )
        row = cursor.fetchone()
        current_summary = row[0] if row and row[0] else ""

        # Get messages outside the context window
        total_turns = self.get_message_count(session_id)
        if total_turns <= self.context_window_size:
            conn.close()
            return current_summary

        # Get the oldest messages that need summarizing
        cutoff_turn = total_turns - self.context_window_size
        cursor.execute(
            """
            SELECT role, content, turn_number FROM session_messages 
            WHERE session_id = ? AND turn_number <= ?
            ORDER BY turn_number, id
            """,
            (session_id, cutoff_turn),
        )
        old_messages = cursor.fetchall()
        conn.close()

        if not old_messages:
            return current_summary

        # Format old messages for summarization
        old_convo = "\n".join([f"{m[0].upper()}: {m[1]}" for m in old_messages])

        # Generate summary using LLM
        try:
            response = await self.client.chat.completions.create(
                model=self.summary_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are summarizing a conversation between a scammer and a honeypot. Be brief and factual. Focus on: what the scammer claimed, what info was exchanged, and how the conversation progressed.",
                    },
                    {
                        "role": "user",
                        "content": f"Previous summary:\n{current_summary}\n\nNew messages to add to summary:\n{old_convo}\n\nWrite an updated brief summary (2-3 sentences max):",
                    },
                ],
                temperature=0.3,
                max_tokens=200,
            )

            new_summary = response.choices[0].message.content or ""
            new_summary = new_summary.strip()

            # Save the new summary
            self.update_summary(session_id, new_summary)

            # Delete the old messages that are now summarized
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM session_messages WHERE session_id = ? AND turn_number <= ?",
                (session_id, cutoff_turn),
            )
            conn.commit()
            conn.close()

            return new_summary

        except Exception as e:
            print(f"Summary generation failed: {e}")
            return current_summary

    def build_context_for_prompt(self, session_id: str, current_intel: Dict) -> Dict:
        """
        Build the full context needed for the agent prompt.
        Returns a dict with summary, recent messages, and memory.
        """
        context = self.get_or_create_session(session_id)
        messages = self.get_messages(session_id, limit=self.context_window_size)

        # Format messages as conversation
        formatted_messages = []
        for msg in messages:
            role_label = "SCAMMER" if msg["role"] == "scammer" else "YOU"
            formatted_messages.append(f"{role_label}: {msg['content']}")

        return {
            "summary": context["summary"],
            "messages": formatted_messages,
            "memory": context["memory"],
            "turn_count": context["turn_count"],
            "persona": context["persona"],
            "intel": current_intel,
        }

    def update_persona(self, session_id: str, persona: str):
        """Update the persona for a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE session_context SET persona = ?, updated_at = ? WHERE session_id = ?",
            (persona, datetime.now(), session_id),
        )

        conn.commit()
        conn.close()
