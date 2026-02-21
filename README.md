# Agentic Honey-Pot API

AI-powered honeypot system for scam detection and intelligence extraction. Built for the India AI Impact Buildathon 2026.

## Overview

This system detects scam messages and autonomously engages with scammers using AI-powered personas to extract actionable intelligence without revealing detection.

## Features

✅ **Scam Detection**: Rule-based pattern matching with confidence scoring  
✅ **AI Agent**: LLM-powered personas (elderly, homemaker, student) using Groq  
✅ **Multi-turn Conversations**: Maintains conversation history and context  
✅ **Entity Extraction**: Automatically extracts bank accounts, UPI IDs, URLs, phone numbers  
✅ **Intelligence Tracking**: Accumulates scammer data across conversation  
✅ **GUVI Callback**: Automatically sends final results to evaluation endpoint  
✅ **API Security**: Protected with x-api-key authentication  

## API Endpoints

### Health Check
```
GET /health
```

### Main Honeypot Endpoint
```
POST /honeypot
Headers:
  Content-Type: application/json
  x-api-key: YOUR_API_KEY
```

**Request Format:**
```json
{
  "sessionId": "wertyu-dfghj-ertyui",
  "message": {
    "sender": "scammer",
    "text": "Your bank account will be blocked today. Verify immediately.",
    "timestamp": "2026-01-21T10:15:30Z"
  },
  "conversationHistory": [],
  "metadata": {
    "channel": "SMS",
    "language": "English",
    "locale": "IN"
  }
}
```

**Response Format:**
```json
{
  "status": "success",
  "reply": "Why is my account being suspended?"
}
```

## Architecture

```
Incoming Message
    ↓
Scam Detection (Rule-based + ML)
    ↓
AI Agent Activated
    ↓
Persona Engine (Groq LLM)
    ↓
Generate Response
    ↓
Entity Extraction
    ↓
Save to Database
    ↓
Return JSON Response
    ↓
[If conversation ends] → Send to GUVI
```

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip3 install -r requirements.txt --break-system-packages
```

3. Set up environment variables in `.env`:
```
GROQ_API_KEY=your_groq_api_key
API_KEY=your_api_key_for_authentication
```

4. Run the server:
```bash
python3 app/main.py
```

Server will start on `http://localhost:8001`

## Testing

Run the test suite:
```bash
python3 test_api.py
```

## Deployment

### Deploy to Render (Recommended)

1. Push code to GitHub
2. Connect Render to your repo
3. Set environment variables in Render dashboard
4. Deploy automatically

### Environment Variables

Required:
- `GROQ_API_KEY` - Your Groq API key (free tier available)
- `API_KEY` - API key for client authentication
- `PORT` - Server port (default: 8001)

## How It Works

### 1. Scam Detection
Analyzes incoming messages for:
- Urgency keywords ("immediately", "urgent", "hurry")
- Threats ("account suspended", "blocked")
- Payment requests ("verify", "click link")
- Personal info requests ("account number", "UPI ID")

### 2. AI Personas
Three believable victim personas:
- **Elderly (Rajesh, 68)**: Trusting, not tech-savvy, asks questions
- **Homemaker (Priya, 45)**: Cautious, family-focused, concerned
- **Student (Arun, 22)**: Naive, worried about credit, eager to please

### 3. Intelligence Extraction
Automatically extracts:
- Bank account numbers (9-18 digits)
- UPI IDs (user@provider format)
- Phishing URLs (http/https links)
- Phone numbers (+91 or 10 digits)
- Email addresses
- Suspicious keywords

### 4. Conversation Management
- Tracks up to 15 messages per session
- Maintains conversation history
- Detects conversation end signals
- Triggers GUVI callback when complete

## GUVI Integration

The system automatically sends final results to:
```
POST https://hackathon.guvi.in/api/updateHoneyPotFinalResult
```

Payload includes:
- sessionId
- scamDetected (true/false)
- totalMessagesExchanged
- extractedIntelligence (bank accounts, UPI IDs, URLs, etc.)
- agentNotes (summary)

## Configuration

### Changing API Key
Edit `.env` file:
```
API_KEY=your-new-api-key
```

### Changing LLM Model
Edit `app/persona.py`:
```python
self.model = "llama-3.1-8b-instant"  # or other Groq models
```

### Adding New Personas
Edit `app/persona.py` and add to `self.personas` dictionary.

## Monitoring

Check server logs:
```bash
tail -f server.log
```

## License

MIT License - Built for educational purposes and fraud prevention.

## Team

**Team BinaryBonsai** 🏆 **10th Place | Score: 87**

Built for India AI Impact Buildathon 2026
Problem Statement 2: Agentic Honey-Pot for Scam Detection & Intelligence Extraction
