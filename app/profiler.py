from typing import List, Dict, Any
from datetime import datetime
import json


class ScammerProfiler:
    """
    Profiles scammer behavior across conversations
    Identifies patterns, tactics, and potential scammer networks
    """

    def __init__(self):
        self.scammer_profiles = {}

    def analyze_scammer(
        self,
        session_id: str,
        conversation_history: List[Dict],
        extracted_entities: Dict,
        scam_analysis: Dict,
    ) -> Dict[str, Any]:
        """
        Build a behavioral profile of the scammer
        """
        profile = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "behavioral_metrics": self._calculate_behavioral_metrics(
                conversation_history
            ),
            "tactics_used": scam_analysis.get("tactics", []),
            "communication_style": self._analyze_communication_style(
                conversation_history
            ),
            "technical_sophistication": self._assess_technical_sophistication(
                extracted_entities
            ),
            "response_patterns": self._analyze_response_patterns(conversation_history),
            "indian_context_signals": self._extract_indian_context(
                conversation_history
            ),
            "pressure_escalation": self._analyze_pressure_escalation(
                conversation_history
            ),
            "patience_level": self._calculate_patience_level(conversation_history),
            "adaptability": self._assess_adaptability(conversation_history),
            "success_indicators": self._check_success_indicators(
                conversation_history, extracted_entities
            ),
        }

        # Store profile
        self.scammer_profiles[session_id] = profile

        return profile

    def _calculate_behavioral_metrics(self, history: List[Dict]) -> Dict[str, Any]:
        """Calculate key behavioral metrics"""
        if not history:
            return {"aggression_level": 0.0, "persistence": 0, "message_frequency": 0}

        total_turns = len(history)

        # Count aggressive language
        aggression_markers = [
            "immediately",
            "urgent",
            "now",
            "hurry",
            "asap",
            "quick",
            "blocked",
            "suspended",
            "police",
            "legal",
            "action",
            "arrest",
            "must",
            "have to",
            "need to",
            "required",
        ]

        aggression_count = 0
        for turn in history:
            msg = turn.get("scammer_message", "").lower()
            aggression_count += sum(1 for marker in aggression_markers if marker in msg)

        aggression_level = min(aggression_count / max(total_turns * 2, 1), 1.0)

        # Calculate persistence (follow-ups after resistance)
        persistence_count = 0
        for i, turn in enumerate(history[1:], 1):
            # If victim showed resistance (asked questions, expressed doubt)
            prev_response = history[i - 1].get("response", "").lower()
            if any(
                word in prev_response
                for word in ["not sure", "confused", "don't understand", "why"]
            ):
                # And scammer continued anyway
                persistence_count += 1

        return {
            "aggression_level": round(aggression_level, 2),
            "persistence": persistence_count,
            "total_turns": total_turns,
            "message_frequency": total_turns,
        }

    def _analyze_communication_style(self, history: List[Dict]) -> str:
        """Analyze the scammer's communication style"""
        if not history:
            return "unknown"

        all_text = " ".join(
            [turn.get("scammer_message", "").lower() for turn in history]
        )

        # Check for different styles
        if any(word in all_text for word in ["sir", "ma'am", "madam", "ji", "beta"]):
            if any(
                word in all_text for word in ["immediately", "urgent", "now", "hurry"]
            ):
                return "polite_authoritative_urgent"
            return "respectful_manipulative"

        if any(word in all_text for word in ["buddy", "friend", "dear", "bro"]):
            return "friendly_approach"

        if (
            sum(
                1
                for word in ["immediately", "urgent", "now", "asap", "quick"]
                if word in all_text
            )
            > 2
        ):
            return "aggressive_pressure"

        if any(
            word in all_text
            for word in ["congratulations", "won", "selected", "lucky", "prize"]
        ):
            return "reward_focused"

        return "neutral_professional"

    def _assess_technical_sophistication(self, entities: Dict) -> str:
        """Assess the technical sophistication of the scam"""
        score = 0

        # Points for various technical elements
        if entities.get("phishingLinks"):
            score += 2
        if entities.get("malicious_apps"):
            score += 3
        if entities.get("fake_websites"):
            score += 2

        # High sophistication indicators
        if any("https" in link for link in entities.get("phishingLinks", [])):
            score += 1

        if score >= 5:
            return "high"
        elif score >= 3:
            return "medium"
        elif score >= 1:
            return "low"
        return "minimal"

    def _analyze_response_patterns(self, history: List[Dict]) -> Dict[str, Any]:
        """Analyze how scammer responds to victim resistance"""
        patterns = {
            "responds_to_questions": False,
            "escalates_on_resistance": False,
            "provides_reassurance": False,
            "changes_tactics": False,
            "becomes_aggressive": False,
        }

        if len(history) < 2:
            return patterns

        for i in range(1, len(history)):
            prev_response = history[i - 1].get("response", "").lower()
            current_msg = history[i].get("scammer_message", "").lower()

            # Check if victim asked questions
            if any(
                word in prev_response for word in ["what", "why", "how", "who", "?"]
            ):
                patterns["responds_to_questions"] = True

                # Check if scammer provided info or just repeated
                if any(
                    word in current_msg
                    for word in ["because", "since", "as you know", "the reason"]
                ):
                    pass  # They answered
                elif (
                    len(current_msg)
                    < len(history[i - 1].get("scammer_message", "")) * 0.8
                ):
                    patterns["escalates_on_resistance"] = True

            # Check for reassurance
            if any(
                word in current_msg
                for word in [
                    "trust me",
                    "genuine",
                    "real",
                    "authentic",
                    "safe",
                    "secure",
                ]
            ):
                patterns["provides_reassurance"] = True

            # Check for aggression escalation
            if i > 1:
                prev_msg = history[i - 1].get("scammer_message", "").lower()
                aggression_words = ["immediately", "urgent", "now", "must", "have to"]
                current_aggression = sum(
                    1 for word in aggression_words if word in current_msg
                )
                prev_aggression = sum(
                    1 for word in aggression_words if word in prev_msg
                )
                if current_aggression > prev_aggression:
                    patterns["becomes_aggressive"] = True

        return patterns

    def _extract_indian_context(self, history: List[Dict]) -> List[str]:
        """Extract Indian-specific context and terminology"""
        if not history:
            return []

        all_text = " ".join(
            [turn.get("scammer_message", "").lower() for turn in history]
        )

        indian_signals = []

        # Honorifics and terms
        if "beta" in all_text:
            indian_signals.append("used_beta")
        if any(term in all_text for term in ["ji", "sir ji", "madam ji"]):
            indian_signals.append("used_ji_honorific")

        # Indian organizations
        indian_orgs = [
            "sbi",
            "hdfc",
            "icici",
            "axis",
            "pnb",
            "bob",
            "rbi",
            "sebi",
            "npci",
            "uidai",
        ]
        for org in indian_orgs:
            if org in all_text:
                indian_signals.append(f"mentioned_{org}")

        # Indian documents
        if any(doc in all_text for doc in ["aadhar", "pan card", "voter id"]):
            indian_signals.append("mentioned_indian_documents")

        # Indian payment systems
        if any(
            payment in all_text
            for payment in ["paytm", "phonepe", "gpay", "google pay", "bhim", "upi"]
        ):
            indian_signals.append("mentioned_indian_payment")

        # Cultural references
        if any(
            ref in all_text for ref in ["pension", "retirement", "government", "govt"]
        ):
            indian_signals.append("targeted_government_employees")

        return indian_signals

    def _analyze_pressure_escalation(self, history: List[Dict]) -> List[Dict[str, Any]]:
        """Analyze how pressure escalates over time"""
        escalation_points = []

        if len(history) < 2:
            return escalation_points

        urgency_words = ["urgent", "immediately", "now", "asap", "quick", "hurry"]
        threat_words = ["blocked", "suspended", "police", "legal", "action"]

        for i, turn in enumerate(history):
            msg = turn.get("scammer_message", "").lower()
            urgency_count = sum(1 for word in urgency_words if word in msg)
            threat_count = sum(1 for word in threat_words if word in msg)

            if urgency_count > 0 or threat_count > 0:
                escalation_points.append(
                    {
                        "turn": i + 1,
                        "urgency_level": urgency_count,
                        "threat_level": threat_count,
                        "pressure_score": urgency_count + (threat_count * 2),
                    }
                )

        return escalation_points

    def _calculate_patience_level(self, history: List[Dict]) -> str:
        """Calculate scammer's patience level"""
        if len(history) < 3:
            return "unknown"

        # Check how many turns before showing frustration
        frustration_markers = ["why", "what", "listen", "understand", "wait"]

        for i, turn in enumerate(history[3:], 3):  # Start after turn 3
            msg = turn.get("scammer_message", "").lower()
            if any(marker in msg for marker in frustration_markers):
                if i <= 5:
                    return "low_impatient"
                elif i <= 10:
                    return "moderate"
                else:
                    return "high_persistent"

        return "very_high_highly_persistent"

    def _assess_adaptability(self, history: List[Dict]) -> str:
        """Assess how adaptive the scammer is"""
        if len(history) < 3:
            return "low"

        # Check if scammer changes approach when victim resists
        resistance_count = 0
        adaptation_count = 0

        for i in range(1, len(history)):
            victim_response = history[i - 1].get("response", "").lower()
            scammer_followup = history[i].get("scammer_message", "").lower()

            # Check for victim resistance
            if any(
                word in victim_response
                for word in ["not sure", "confused", "don't understand", "why", "what"]
            ):
                resistance_count += 1

                # Check if scammer adapted (changed approach)
                if i > 1:
                    prev_approach = history[i - 1].get("scammer_message", "").lower()
                    if (
                        len(set(prev_approach.split()) & set(scammer_followup.split()))
                        < len(prev_approach.split()) * 0.5
                    ):
                        adaptation_count += 1

        if resistance_count == 0:
            return "untested"

        adaptation_rate = adaptation_count / max(resistance_count, 1)

        if adaptation_rate >= 0.7:
            return "high_very_adaptive"
        elif adaptation_rate >= 0.4:
            return "moderate_adaptive"
        else:
            return "low_repetitive"

    def _check_success_indicators(
        self, history: List[Dict], entities: Dict
    ) -> Dict[str, Any]:
        """Check if scammer succeeded in extracting victim info"""
        return {
            "victim_provided_info": len(entities.get("victim_info", [])) > 0,
            "victim_clicked_link": any(
                "clicked" in turn.get("response", "").lower() for turn in history
            ),
            "victim_showed_interest": any(
                word in " ".join([turn.get("response", "").lower() for turn in history])
                for word in ["ok", "yes", "sure", "will do", "sending"]
            ),
            "conversation_completed": len(history) >= 5,
            "scammer_got_account": len(entities.get("bankAccounts", [])) > 0
            or len(entities.get("upiIds", [])) > 0,
        }

    def get_profile_summary(self, session_id: str) -> str:
        """Get a human-readable summary of scammer profile"""
        if session_id not in self.scammer_profiles:
            return "No profile available"

        profile = self.scammer_profiles[session_id]

        summary_parts = [
            f"Scammer Profile for {session_id}",
            f"Communication Style: {profile['communication_style']}",
            f"Aggression Level: {profile['behavioral_metrics']['aggression_level']}/1.0",
            f"Persistence: {profile['behavioral_metrics']['persistence']} resistance overcomes",
            f"Technical Sophistication: {profile['technical_sophistication']}",
            f"Patience Level: {profile['patience_level']}",
            f"Adaptability: {profile['adaptability']}",
            f"Indian Context: {', '.join(profile['indian_context_signals']) if profile['indian_context_signals'] else 'None detected'}",
        ]

        return "\n".join(summary_parts)

    def export_profile(self, session_id: str) -> Dict:
        """Export profile for law enforcement or analysis"""
        if session_id not in self.scammer_profiles:
            return {}

        return self.scammer_profiles[session_id]
