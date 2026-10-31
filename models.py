from uagents import Model

# ── Orchestrator → Profile Agent ──────────────────────────────────────────────
class ProfileRequest(Model):
    session_id: str
    text: str

# ── Profile Agent → Orchestrator ──────────────────────────────────────────────
class ProfileResponse(Model):
    session_id: str
    condition: str
    age: str
    location: str
    medications: str

# ── Orchestrator → Discovery Agent ────────────────────────────────────────────
class DiscoveryRequest(Model):
    session_id: str
    condition: str
    age: str
    location: str

# ── Discovery Agent → Orchestrator ────────────────────────────────────────────
class DiscoveryResponse(Model):
    session_id: str
    trials_json: str   # JSON-encoded list of trial dicts
    total_found: int

# ── Orchestrator → Inquiry Agent ──────────────────────────────────────────────
class InquiryRequest(Model):
    session_id: str
    trial_json: str    # JSON of one trial dict
    profile_json: str  # JSON of patient profile dict

# ── Inquiry Agent → Orchestrator ──────────────────────────────────────────────
class InquiryResponse(Model):
    session_id: str
    email_text: str
