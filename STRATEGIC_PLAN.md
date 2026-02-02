# Strategic Plan: Agentic Honey-Pot for India AI Impact Buildathon

## Executive Summary
Current Status: Functional MVP with rule-based detection and extraction
Target Status: Intelligence-grade AI system with dynamic behavior analysis

---

## Phase 1: Core Architecture Upgrades (Priority: CRITICAL)

### 1.1 Replace Regex with LLM Intelligence

**Current State:**
- `detector.py`: Regex pattern matching (urgent, blocked, verify)
- `extractor.py`: Regex entity extraction (grabs any 10-digit number)

**Proposed State:**
- `detector.py`: Groq-powered scam classification with confidence scoring
- `extractor.py`: Context-aware entity extraction (only extracts what scammer requests)

**Implementation:**
```python
# New detector approach
def analyze_with_groq(message, history):
    prompt = f"""
    Analyze this message in the context of Indian financial fraud:
    Message: "{message}"
    
    Classify as one of:
    - UPI_FRAUD (payment requests, UPI ID demands)
    - PHISHING (links, verification requests)
    - KYC_SCAM (account suspension threats)
    - LOTTERY (prize notifications)
    - JOB_SCAM (work from home offers)
    - SEXTORTION (threats with videos/images)
    - FAMILY_EMERGENCY (relative in hospital)
    - LEGITIMATE (genuine bank communication)
    
    Return JSON:
    {{
        "is_scam": true/false,
        "scam_type": "UPI_FRAUD",
        "confidence": 0.95,
        "tactics": ["urgency", "authority_impersonation"],
        "risk_level": "HIGH"
    }}
    """
```

**Benefits:**
- Detects sophisticated scams that bypass keyword filters
- Classifies scam type for strategic response
- Provides confidence scores for decision making

---

### 1.2 Dynamic Persona State Machine

**Current State:**
- Static personas (always "elderly Rajesh")
- No emotional progression
- Fixed behavior regardless of scammer tactics

**Proposed State:**
- Emotional state machine with 5 states
- Mood transitions based on scammer input
- Strategic "confusion" and "technical difficulties"

**Emotional States:**
1. **NEUTRAL/CURIOUS** (Turn 1-2): "Hello? Who is this?"
2. **WORRIED/ANXIOUS** (When threatened): "Oh no! My pension is in that account!"
3. **EXCITED/HOPEFUL** (When promised money): "Really? I could use that money!"
4. **CONFUSED/TECHNOLOGICALLY-CHALLENGED** (Stalling tactic): "Beta, I don't understand this phone..."
5. **COOPERATIVE/BUT-STRUGGLING** (End game): "I'm trying to send it but..."

**State Transitions:**
```python
mood_transitions = {
    "NEUTRAL": {
        "threat": "WORRIED",
        "reward": "EXCITED", 
        "request_info": "CONFUSED"
    },
    "WORRIED": {
        "pressure": "COOPERATIVE",
        "reassurance": "CONFUSED"  # Buy time
    },
    "EXCITED": {
        "payment_request": "CONFUSED",  # Slow down
        "verification": "COOPERATIVE"
    }
}
```

**Benefits:**
- More believable human behavior
- Strategic stalling to extract more information
- Natural conversation flow

---

### 1.3 Intelligent Conversation Lifecycle Management

**Current State:**
- Hard stop at 15 messages
- Simple keyword detection for end signals

**Proposed State:**
- Objective-based termination
- Groq-powered conversation analysis
- Maximum extraction strategy

**Termination Triggers (in priority order):**
1. **INTEL_COMPLETE**: We have bank account + UPI + phone + URLs
2. **SCAMMER_EXITED**: Scammer said goodbye/stopped responding
3. **SCAMMER_SUSPICIOUS**: Scammer said "are you a bot?" or "this is fake"
4. **MAX_TURNS**: Safety limit at 20 messages
5. **TIMEOUT**: No response for 5 minutes

**Intelligence Maximization Strategy:**
```python
def should_end_conversation(history, extracted_entities):
    intel_score = calculate_intel_completeness(extracted_entities)
    scammer_frustration = detect_scammer_frustration(history)
    
    if intel_score >= 0.9:  # We have everything
        return True, "INTEL_COMPLETE"
    elif scammer_frustration > 0.8:  # Scammer leaving
        return True, "SCAMMER_EXITED"
    elif len(history) >= 20:
        return True, "MAX_TURNS"
    else:
        return False, "CONTINUE"
```

---

## Phase 2: Intelligence & Analytics Layer (Priority: HIGH)

### 2.1 Advanced Entity Extraction

**Current:** Regex grabs any number
**Proposed:** Context-aware extraction

**What to Extract:**
- **Financial Details**: Bank accounts, UPI IDs, IFSC codes, Wallet IDs
- **Contact Information**: Scammer's phone, email, WhatsApp numbers
- **Infrastructure**: Phishing URLs, APK download links, fake website domains
- **Operational Details**: Transaction amounts, "fees" requested, "prize" amounts
- **Social Engineering Tactics**: Urgency triggers, fear keywords, authority claims

**Groq Prompt:**
```
Analyze this conversation and extract only information the SCAMMER provided:

Financial Details:
- Bank accounts they want money sent TO (not victim's account)
- UPI IDs they provided
- QR codes mentioned

Contact Details:
- Phone numbers they called from
- WhatsApp numbers they shared
- Email addresses they used

Infrastructure:
- Links they asked victim to click
- Apps they asked victim to install
- Websites they mentioned

Do NOT extract:
- Victim's personal information
- Random numbers that aren't account numbers
- Dates or times

Return structured JSON.
```

---

### 2.2 Scammer Behavior Profiling

**New Feature:** Build a profile of the scammer's tactics

**Profile Elements:**
```json
{
  "scammer_profile": {
    "aggression_level": 0.7,  // 0-1 scale
    "persistence": 8,  // Number of follow-ups
    "tactics_used": ["urgency", "authority", "fear", "reciprocity"],
    "communication_style": "aggressive_pressure",
    "response_to_stalling": "increased_threats",
    "technical_sophistication": "medium",  // Quality of fake websites
    "indian_context_signals": ["beta", "sir/ma'am", "PAN card", "Aadhar"]
  }
}
```

**Usage:**
- Share intelligence with law enforcement
- Identify scammer networks (same tactics = same group)
- Train detection models

---

### 2.3 Real-time Intelligence Dashboard (Optional but Impressive)

**If time permits:** Simple web dashboard showing:
- Active honeypot conversations
- Extracted intelligence in real-time
- Scam type distribution
- Geographic patterns (if metadata available)
- Scammer behavior profiles

**Tech:** Simple HTML + JavaScript polling the API

---

## Phase 3: Strategic Enhancements (Priority: MEDIUM)

### 3.1 Multi-Language Support

**Current:** English only
**Proposed:** Hinglish, Hindi, Tamil support

**Implementation:**
- Use Groq for translation
- Persona responds in same language as scammer
- Maintain conversation context across languages

**Persona Prompt Addition:**
```
If the scammer messages in Hindi/Hinglish, respond in the same language.
Example:
Scammer: "Aapka account block ho jayega"
Persona: "Arre beta, matlab kya ho raha hai? Main samjhi nahi..."
```

---

### 3.2 Adaptive Persona Selection

**Current:** Always uses "elderly"
**Proposed:** Select persona based on scam type

**Matching Strategy:**
- **UPI Fraud** → Elderly persona (confused about technology)
- **Job Scam** → Student persona (looking for work)
- **Lottery** → Homemaker persona (excited about prize)
- **KYC** → Any persona (worried about account)
- **Sextortion** → Student persona (fear of shame)

---

### 3.3 Counter-Intelligence Features

**New Capabilities:**
1. **Scammer Time Wasting**: Keep them engaged longer = less time for real victims
2. **False Flag Operations**: Feed fake information (invalid accounts, wrong OTPs)
3. **Pattern Learning**: Each conversation improves detection for next time
4. **Network Detection**: Identify when same scammer contacts multiple personas

---

## Phase 4: Deployment & Submission (Priority: CRITICAL)

### 4.1 Infrastructure Requirements

**Deployment Target:** Render.com (free tier) or Railway.app

**Environment Variables:**
```bash
GROQ_API_KEY=gsk_...              # LLM provider
API_KEY=hackathon-2026-secret     # API authentication
DATABASE_URL=sqlite:///data.db    # SQLite for persistence
PORT=8001                         # Server port
GUVI_CALLBACK_URL=https://...     # Evaluation endpoint
```

### 4.2 Performance Optimization

**Current Issues:**
- 3 Groq API calls per turn (detection + extraction + response)
- ~2-3 seconds response time

**Optimization:**
1. **Batch Analysis**: One Groq call for detection + extraction
2. **Response Caching**: Cache common scammer messages
3. **Async Processing**: Database writes in background

**Target:** <1.5 second response time

### 4.3 Testing Strategy

**Test Scenarios:**
1. UPI fraud with QR code
2. Bank KYC with phishing link
3. Lottery scam with "processing fee"
4. Job scam with "training fee"
5. Multi-turn conversation (10+ messages)
6. Scammer giving up mid-conversation
7. Invalid API key rejection

---

## Implementation Timeline

### Day 1 (Today, Feb 2) - COMPLETE ✅
- [x] Basic API structure
- [x] Groq integration for personas
- [x] SQLite database
- [x] Rule-based detection/extraction
- [x] GUVI callback structure

### Day 2 (Feb 3) - CORE UPGRADES
- [ ] Replace detector with Groq-powered classification
- [ ] Replace extractor with Groq-powered extraction
- [ ] Implement emotional state machine
- [ ] Add intelligent conversation ending
- [ ] Test multi-turn conversations

### Day 3 (Feb 4) - POLISH & DEPLOY
- [ ] Add multi-language support (Hinglish)
- [ ] Create simple analytics dashboard
- [ ] Performance optimization
- [ ] Deploy to Render/Railway
- [ ] End-to-end testing with evaluation flow

### Day 4-5 (Feb 5) - SUBMISSION
- [ ] Documentation
- [ ] Demo video
- [ ] Submit to GUVI

---

## Risk Analysis & Mitigation

### Risk 1: Groq Rate Limits
**Mitigation:** Implement caching, use groq's free tier limits (1M tokens/day)

### Risk 2: GUVI Callback Endpoint Issues
**Mitigation:** Retry logic, local logging as backup

### Risk 3: Deployment Failures
**Mitigation:** Test locally thoroughly, have backup deployment target

### Risk 4: Time Constraints
**Mitigation:** Prioritize Phase 1 (core upgrades), Phase 2 is bonus

---

## Success Metrics

**Minimum Viable Win:**
- API responds correctly to evaluation requests
- Extracts at least 1 bank account or UPI ID per scam conversation
- Maintains conversation for 5+ turns
- Callback to GUVI succeeds

**Competitive Win:**
- >90% scam detection accuracy
- >80% entity extraction precision
- Average 8+ turns per conversation
- Multi-language support
- Real-time dashboard

---

## Open Questions for Deliberation

1. **Should we use one Groq call or multiple?**
   - One call: Faster, cheaper
   - Multiple calls: Better separation of concerns, easier to debug

2. **How aggressive should the stalling tactics be?**
   - Conservative: Just act confused
   - Aggressive: Technical difficulties, wrong OTPs, fake transfer failures

3. **Should we implement real-time dashboard?**
   - Pros: Impressive to judges, shows live intelligence
   - Cons: Takes time, not required for evaluation

4. **Do we need multi-language from start or as enhancement?**
   - Start with English, add Hindi/Hinglish if time permits?

5. **What persona selection strategy?**
   - Random rotation?
   - Match to scam type?
   - Always elderly (safest)?

6. **Should we implement "counter-intelligence" (feeding fake data)?**
   - Ethical concerns?
   - Legal implications?
   - Judges' perception?

---

## Recommended Next Steps

**Immediate (Next 2 hours):**
1. Decide on Groq strategy (one call vs multiple)
2. Implement Groq-powered detector
3. Test with 5 different scam messages

**Short-term (Today):**
4. Implement Groq-powered extractor
5. Add emotional state machine
6. Test multi-turn conversation flow

**This Week:**
7. Deploy and test end-to-end
8. Optimize performance
9. Create documentation

---

## Competitive Advantage Strategy

**What makes us different:**
1. **True AI Agent**: Not just rule-based, actually reasons about conversation
2. **Intelligence Quality**: Context-aware extraction, not regex matching
3. **Strategic Engagement**: Dynamic emotions, optimal extraction timing
4. **Scammer Profiling**: Building behavioral profiles for law enforcement
5. **Multi-Language**: Hinglish/Hindi support (critical for Indian context)

**Elevator Pitch:**
"While others use regex to detect 'urgent' and grab any 10-digit number, we use LLMs to understand context, classify scam types, and strategically extract only relevant intelligence. Our agent doesn't just reply—it performs, adapts, and maximizes intelligence extraction while maintaining perfect cover."

---

*Document Version: 1.0*
*Date: Feb 2, 2026*
*Status: Strategic Planning Phase*
