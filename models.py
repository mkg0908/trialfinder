from uagents import Model

# ── Orchestrator → Profile Agent ──────────────────────────────────────────────
class ProfileRequest(Model):
    session_id: str
    text: str

# ── Profile Agent → Orchestrator ──────────────────────────────────────────────
class ProfileResponse(Model):
    session_id: str
    condition:        str
    age:              str
    location:         str
    medications:      str
    comorbidities:    str   # other conditions, e.g. "hypertension, obesity"
    stage:            str   # disease stage or severity, e.g. "Stage 3", "HbA1c 9.2"
    prior_treatments: str   # past treatments, e.g. "metformin, insulin"
    gender:           str   # "male" | "female" | ""

# ── Orchestrator → Discovery Agent ────────────────────────────────────────────
class DiscoveryRequest(Model):
    session_id:       str
    condition:        str
    age:              str
    location:         str
    comorbidities:    str
    stage:            str
    prior_treatments: str
    gender:           str

# ── Discovery Agent → Orchestrator ────────────────────────────────────────────
class DiscoveryResponse(Model):
    session_id:  str
    trials_json: str   # JSON-encoded list of trial dicts
    total_found: int

# ── Orchestrator → Eligibility Agent ─────────────────────────────────────────
class EligibilityRequest(Model):
    session_id:  str
    trials_json: str   # JSON list of {nct_id, title, eligibility_criteria}
    profile_json: str  # patient profile dict as JSON

# ── Eligibility Agent → Orchestrator ─────────────────────────────────────────
class EligibilityResponse(Model):
    session_id:  str
    scores_json: str   # JSON: {nct_id: {score, verdict, met, failed, unknown}}

# ── Orchestrator → Inquiry Agent ──────────────────────────────────────────────
class InquiryRequest(Model):
    session_id:  str
    trial_json:  str   # JSON of one trial dict
    profile_json: str  # JSON of patient profile dict

# ── Inquiry Agent → Orchestrator ──────────────────────────────────────────────
class InquiryResponse(Model):
    session_id: str
    email_text: str
