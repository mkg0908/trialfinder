"""
Orchestrator Agent — the only agent users interact with via ASI:One.
Routes requests to Profile, Discovery, Eligibility, and Inquiry sub-agents.
Includes Payment Protocol (Stripe) for eligibility screening.
"""
import json, re, time
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import quote

import stripe
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement, ChatMessage, TextContent, chat_protocol_spec,
)
from uagents_core.contrib.protocols.payment import (
    CommitPayment, CompletePayment, RejectPayment,
    Funds, RequestPayment, payment_protocol_spec,
)

from models import (
    ProfileRequest, ProfileResponse,
    DiscoveryRequest, DiscoveryResponse,
    EligibilityRequest, EligibilityResponse,
    InquiryRequest, InquiryResponse,
)
import config

# ── Stripe Config ────────────────────────────────────────────────────────────
import os
STRIPE_SECRET_KEY      = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_CURRENCY        = "usd"
STRIPE_AMOUNT_CENTS    = 99  # $0.99 per eligibility screening
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ── Agent ─────────────────────────────────────────────────────────────────────
agent = Agent(
    name="trialfinder-medbridge",
    seed="medbridge trialfinder stranger builds 2026",
    port=8001,
    mailbox=True,
    publish_agent_details=True,
)

chat_protocol     = Protocol(spec=chat_protocol_spec)
internal_protocol = Protocol(name="trialfinder-internal", version="1.0.0")
payment_protocol  = Protocol(spec=payment_protocol_spec, role="seller")

# ── Sessions ──────────────────────────────────────────────────────────────────
SESSIONS_FILE = "sessions.json"

def _load_sessions() -> dict:
    try:
        with open(SESSIONS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_sessions():
    try:
        slim = {}
        for k, v in sessions.items():
            slim[k] = {
                "user_sender": v.get("user_sender", k),
                "profile":     v.get("profile", {}),
                "searched":    v.get("searched", False),
                "last_trials": v.get("last_trials", []),
                "state":       "idle",
                "filters":     v.get("filters", {}),
            }
        with open(SESSIONS_FILE, "w") as f:
            json.dump(slim, f)
    except Exception:
        pass

sessions: dict[str, dict] = _load_sessions()

def get_session(sender: str) -> dict:
    if sender not in sessions:
        sessions[sender] = {
            "user_sender":  sender,
            "profile":      {},
            "searched":     False,
            "last_trials":  [],
            "state":        "idle",
            "filters":      {},
        }
    return sessions[sender]

# ── Formatting helpers ────────────────────────────────────────────────────────
def fmt_age(s: str) -> str:
    if not s or s.lower() in ("n/a","not specified",""): return "Any"
    return re.sub(r"\s*years?\s*","y", s, flags=re.IGNORECASE)

def distance_label(d) -> str:
    if d is None:   return "🌍 International"
    if d < 400:     return f"🟢 {d:.1f} mi"
    if d < 1000:    return f"🟡 {d:.1f} mi"
    return                  f"🔴 {d:.1f} mi"

def filter_summary(filters: dict) -> str:
    parts = []
    if filters.get("phase"):     parts.append(f"Phase {filters['phase']} only")
    if filters.get("remote"):    parts.append("Remote/virtual visits")
    if filters.get("max_dist"):  parts.append(f"Within {filters['max_dist']} mi")
    return " · ".join(parts) if parts else ""

def apply_filters(trials: list, filters: dict) -> list:
    if not filters:
        return trials
    result = trials
    if filters.get("phase"):
        ph = filters["phase"].lower()
        result = [t for t in result if ph in (t.get("phase","") or "").lower()]
    if filters.get("remote"):
        kw = ("remote","virtual","telehealth","online")
        result = [t for t in result
                  if any(k in (t.get("title","") + t.get("summary","")).lower() for k in kw)]
    if filters.get("max_dist") is not None:
        md = filters["max_dist"]
        result = [t for t in result
                  if t.get("distance_mi") is not None and t["distance_mi"] <= md]
    return result

def build_response(trials: list, profile: dict, filters: dict | None = None,
                   start_idx: int = 0, show: int = 20) -> str:
    filters = filters or {}
    display = apply_filters(trials, filters)

    if not display:
        cond = profile.get("condition","your condition").title()
        if filters:
            fsum = filter_summary(filters)
            return (
                f"No trials match your current filters ({fsum}) for {cond}.\n"
                "Try removing a filter — say \"clear filters\" or \"show all results\"."
            )
        return (
            f"No recruiting trials found for {cond} "
            f"matching age {profile.get('age','?')} right now. "
            "Check back in a few weeks or speak with your specialist."
        )

    cond = profile.get("condition","").title()
    age  = profile.get("age","?")
    loc  = profile.get("location","")

    nearby   = [t for t in display if t.get("distance_mi") is not None and t["distance_mi"] < 400]
    regional = [t for t in display if t.get("distance_mi") is not None and 400 <= t["distance_mi"] < 1000]
    national = [t for t in display if t.get("distance_mi") is not None and t["distance_mi"] >= 1000]
    intl     = [t for t in display if t.get("distance_mi") is None]

    # ── Header ────────────────────────────────────────────────────────────────
    lines = []
    fsum = filter_summary(filters)
    if fsum:
        lines.append(f"🔍 {len(display)} Trials — {cond} | Age {age} | {loc}")
        lines.append(f"🎛️  Filters active: {fsum}")
    else:
        lines.append(f"🔍 {len(display)} Recruiting Trials — {cond} | Age {age} | {loc}")
    lines.append("")

    # ── Zone summary ──────────────────────────────────────────────────────────
    if len(display) > 1:
        lines.append("📊 Results by distance:")
        if nearby:   lines.append(f"  🟢 Nearby (< 400 mi)      — {len(nearby)} trials")
        if regional: lines.append(f"  🟡 Regional (400–1000 mi) — {len(regional)} trials")
        if national: lines.append(f"  🔴 National (1000+ mi)    — {len(national)} trials")
        if intl:     lines.append(f"  🌍 International          — {len(intl)} trials")
        lines.append("")

    # ── Trial cards ───────────────────────────────────────────────────────────
    BR     = "  "
    page   = display[start_idx:start_idx + show]
    hidden = len(display) - start_idx - len(page)

    for i, t in enumerate(page, start_idx + 1):
        badge  = " 🏆 Best Match" if i == 1 and start_idx == 0 else ""
        ages   = f"{fmt_age(t['min_age'])} – {fmt_age(t['max_age'])}"
        dist   = distance_label(t.get("distance_mi"))
        phase   = t.get("phase","N/A")
        sponsor = t.get("sponsor","") or "—"

        lines.append(f"{'─'*38}")
        lines.append(f"#{i}{badge}")
        lines.append(f"📌 {t['title']}{BR}")
        lines.append(f"📍 {t['location']}")
        lines.append(f"📏 {dist}  |  🔬 {phase}  |  🏢 {sponsor}{BR}")
        lines.append(f"👤 Age eligible: {ages}{BR}")
        if t.get("contact_name") or t.get("contact_email"):
            contact = " · ".join(filter(None,[t.get("contact_name",""), t.get("contact_email","")]))
            lines.append(f"📧 {contact}{BR}")
        lines.append(f"🔗 {t['url']}")
        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    lines.append("─" * 38)
    lines.append("💡 What you can do next:")
    if hidden > 0:
        lines.append(f"  • \"{hidden} more trials\" — say \"show more\"")
    lines.append("  • \"email for trial 3\" — draft an inquiry email")
    lines.append("  • \"phase 3 only\" — filter by trial phase")
    lines.append("  • \"within 100 miles\" — filter by distance")
    lines.append("  • \"remote only\" — show virtual visit trials")
    if filters:
        lines.append("  • \"clear filters\" — remove all filters")
    lines.append("")
    lines.append("⚠️  Always consult your doctor before enrolling in any clinical trial.")
    return "\n".join(lines)

# ── Vague condition detection ─────────────────────────────────────────────────
VAGUE_CONDITIONS = {
    "cancer":        "What type of cancer? (e.g. breast, lung, colorectal, leukemia, lymphoma)",
    "tumor":         "What type of tumor? (e.g. brain tumor, solid tumor, glioblastoma)",
    "diabetes":      "Type 1 or Type 2 diabetes? (or gestational, MODY, pre-diabetes?)",
    "heart disease": "What type? (e.g. heart failure, coronary artery disease, atrial fibrillation)",
    "heart failure": None,   # specific enough — no follow-up
    "arthritis":     "Rheumatoid arthritis or osteoarthritis? (or psoriatic, ankylosing spondylitis?)",
    "liver disease": "What type? (e.g. hepatitis B, hepatitis C, cirrhosis, NAFLD/NASH)",
    "lung disease":  "What type? (e.g. COPD, asthma, pulmonary fibrosis, lung cancer)",
    "kidney disease":"What type? (e.g. chronic kidney disease, IgA nephropathy, polycystic kidney)",
    "depression":    None,   # specific enough
    "pain":          "What condition causes the pain? (e.g. chronic back pain, fibromyalgia, neuropathy)",
    "skin disease":  "What type? (e.g. psoriasis, eczema, melanoma, acne)",
    "eye disease":   "What type? (e.g. macular degeneration, diabetic retinopathy, glaucoma)",
    "autoimmune":    "Which autoimmune condition? (e.g. lupus, rheumatoid arthritis, Crohn's disease)",
    "infection":     "Which infection? (e.g. HIV, hepatitis C, UTI, COVID-19)",
    "mental health": "Which condition? (e.g. depression, anxiety, bipolar disorder, schizophrenia)",
    "blood disease": "Which blood condition? (e.g. anemia, leukemia, sickle cell, thrombocytopenia)",
}

def get_vague_followup(condition: str) -> str | None:
    """Returns a follow-up question if the condition is too broad, else None."""
    c = condition.lower().strip()
    for vague, question in VAGUE_CONDITIONS.items():
        if c == vague or c == vague + "s":
            return question   # None means it's in our list but specific enough
    return None   # not vague — proceed

# ── Filter detection ──────────────────────────────────────────────────────────
def build_profile_card(profile: dict) -> str:
    """Renders a compact profile summary card."""
    lines = ["👤 Your Profile:"]
    if profile.get("condition"):
        stage = f" — {profile['stage']}" if profile.get("stage") else ""
        lines.append(f"  🏥 Condition:    {profile['condition'].title()}{stage}")
    if profile.get("age"):
        gender = f" · {profile['gender'].title()}" if profile.get("gender") else ""
        lines.append(f"  🎂 Age:          {profile['age']}{gender}")
    if profile.get("location"):
        lines.append(f"  📍 Location:     {profile['location']}")
    if profile.get("medications"):
        lines.append(f"  💊 Medications:  {profile['medications']}")
    if profile.get("comorbidities"):
        lines.append(f"  ➕ Also has:     {profile['comorbidities']}")
    if profile.get("prior_treatments"):
        lines.append(f"  🔁 Prior Tx:     {profile['prior_treatments']}")
    lines.append("")
    lines.append("_Tell me anything else — I'll use it to find better matches._")
    return "\n".join(lines)

def detect_filter_command(text: str) -> dict | None:
    """Returns a filter update dict, or None if not a filter command."""
    t = text.lower().strip()

    # Clear filters
    if any(p in t for p in ("clear filter","no filter","remove filter","show all","reset filter")):
        return {"_clear": True}

    filters = {}

    # Phase filter — "phase 3", "phase 2/3", "phase iii"
    pm = re.search(r"phase\s*([123iii/iv]+)", t, re.IGNORECASE)
    if pm:
        raw = pm.group(1).lower().replace("iii","3").replace("iv","4").replace("ii","2")
        filters["phase"] = raw.strip("/").strip()

    # Remote / virtual
    if any(p in t for p in ("remote","virtual","telehealth","online visit","no travel")):
        filters["remote"] = True

    # Distance filter — "within 50 miles", "less than 200 miles", "50 mile radius"
    dm = re.search(r"(?:within|less than|under|<)\s*(\d+)\s*mi", t)
    if not dm:
        dm = re.search(r"(\d+)\s*mi(?:le)?\s*(?:radius|range|of me)?", t)
    if dm:
        filters["max_dist"] = int(dm.group(1))

    return filters if filters else None

# ── Email request detection ───────────────────────────────────────────────────
def detect_email_request(text: str, last_trials: list) -> dict | None:
    if not last_trials: return None
    if not any(kw in text.lower() for kw in ("email","draft","inquiry","contact","write")): return None
    nums = re.findall(r"\b([1-9]\d?)\b", text)
    if nums:
        idx = int(nums[0]) - 1
        if 0 <= idx < len(last_trials): return last_trials[idx]
    return None

# ── Profile update confirmation ───────────────────────────────────────────────
def detect_yes(text: str) -> bool:
    return text.lower().strip() in ("yes","y","yep","yeah","sure","ok","okay","yes please","yup","confirm")

def detect_no(text: str) -> bool:
    return text.lower().strip() in ("no","n","nope","nah","no thanks","keep","keep it","same","cancel")

async def send_to_user(ctx: Context, sender: str, text: str):
    await ctx.send(sender, ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    ))

# ── Chat protocol: handle user messages ───────────────────────────────────────
@chat_protocol.on_message(ChatMessage)
async def handle_user_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(
        timestamp=datetime.now(), acknowledged_msg_id=msg.msg_id
    ))

    text = "".join(item.text for item in msg.content if isinstance(item, TextContent))
    # Strip @mention prefix so LLM gets clean input
    text = re.sub(r"^@\S+\s*", "", text).strip()
    session = get_session(sender)

    # ── Handle pending profile-change confirmation ────────────────────────────
    if session.get("_pending_profile_change") and session["last_trials"]:
        pending = session["_pending_profile_change"]
        if detect_yes(text):
            # User confirmed — apply the new profile and re-search
            session["_pending_profile_change"] = None
            session["searched"]    = False
            session["last_trials"] = []
            session["filters"]     = {}
            session["profile"].update({k: v for k, v in pending.items() if v})
            profile = session["profile"]
            if profile.get("condition") and profile.get("location"):
                session["searched"] = True
                session["state"]    = "waiting_discovery"
                await send_to_user(ctx, sender,
                    f"Searching ClinicalTrials.gov for {profile['condition']} trials near {profile['location']}...")
                await ctx.send(config.DISCOVERY_AGENT_ADDRESS, DiscoveryRequest(
                    session_id=sender,
                    condition=profile.get("condition",""),
                    age=profile.get("age",""),
                    location=profile.get("location",""),
                    comorbidities=profile.get("comorbidities",""),
                    stage=profile.get("stage",""),
                    prior_treatments=profile.get("prior_treatments",""),
                    gender=profile.get("gender",""),
                ))
            return
        elif detect_no(text):
            session["_pending_profile_change"] = None
            cond = session["profile"].get("condition","your condition").title()
            await send_to_user(ctx, sender,
                f"Got it — keeping your profile as {cond}. "
                "What else would you like to do? You can ask for more trials, filter results, or draft an email.")
            return
        # Not yes/no — fall through to normal handling

    # ── "Search anyway" — skip vague follow-up ──────────────────────────────
    text_lower = text.lower()
    if any(p in text_lower for p in ("search anyway","just search","skip","show anyway","proceed")) \
            and session.get("_asked_clarification") and session["profile"].get("condition"):
        session["_asked_clarification"] = False
        profile = session["profile"]
        if profile.get("condition") and profile.get("location"):
            session["searched"] = True
            session["state"]    = "waiting_discovery"
            await send_to_user(ctx, sender,
                f"🔍 Searching for **{profile['condition']}** trials near **{profile['location']}**...")
            await ctx.send(config.DISCOVERY_AGENT_ADDRESS, DiscoveryRequest(
                session_id=sender,
                condition=profile.get("condition",""),
                age=profile.get("age",""),
                location=profile.get("location",""),
                comorbidities=profile.get("comorbidities",""),
                stage=profile.get("stage",""),
                prior_treatments=profile.get("prior_treatments",""),
                gender=profile.get("gender",""),
            ))
            return

    # ── My profile? ─────────────────────────────────────────────────────────
    if any(p in text_lower for p in ("my profile","show profile","what do you know","profile?")) and session["profile"]:
        await send_to_user(ctx, sender, build_profile_card(session["profile"]))
        return

    # ── Search again with current profile ────────────────────────────────────
    if any(p in text_lower for p in ("search again","re-search","redo search","search with new")) and session["profile"]:
        profile = session["profile"]
        if profile.get("condition") and profile.get("location"):
            session["searched"] = True
            session["state"]    = "waiting_discovery"
            session["filters"]  = {}
            await send_to_user(ctx, sender,
                f"🔍 Re-searching with your updated profile...")
            await ctx.send(config.DISCOVERY_AGENT_ADDRESS, DiscoveryRequest(
                session_id=sender,
                condition=profile.get("condition",""),
                age=profile.get("age",""),
                location=profile.get("location",""),
                comorbidities=profile.get("comorbidities",""),
                stage=profile.get("stage",""),
                prior_treatments=profile.get("prior_treatments",""),
                gender=profile.get("gender",""),
            ))
            return

    # ── Show more? ───────────────────────────────────────────────────────────
    if "show more" in text_lower and session["last_trials"]:
        shown   = session.get("_shown_count", 20)
        filters = session.get("filters", {})
        display = apply_filters(session["last_trials"], filters)
        more    = display[shown:shown+20]
        if not more:
            await send_to_user(ctx, sender, "You've seen all available trials. Say \"clear filters\" to widen your search.")
        else:
            session["_shown_count"] = shown + len(more)
            BR = "  "
            lines = [f"📋 Trials {shown+1}–{shown+len(more)}:\n"]
            for i, t in enumerate(more, shown+1):
                ages = f"{fmt_age(t['min_age'])} – {fmt_age(t['max_age'])}"
                dist = distance_label(t.get("distance_mi"))
                lines.append(f"{'─'*36}")
                lines.append(f"#{i} {t['title']}{BR}")
                lines.append(f"📍 {t['location']}  |  {dist}{BR}")
                lines.append(f"🔬 {t.get('phase','N/A')}  |  🏢 {t.get('sponsor','—')}{BR}")
                lines.append(f"👤 Age eligible: {ages}{BR}")
                if t.get("contact_name") or t.get("contact_email"):
                    contact = " · ".join(filter(None,[t.get("contact_name",""), t.get("contact_email","")]))
                    lines.append(f"📧 {contact}{BR}")
                lines.append(f"🔗 {t['url']}")
                lines.append("")
            remaining = len(display) - session["_shown_count"]
            if remaining > 0:
                lines.append(f"📋 {remaining} more — reply \"show more\" to continue.")
            await send_to_user(ctx, sender, "\n".join(lines))
        return

    # ── Filter command? ───────────────────────────────────────────────────────
    filter_cmd = detect_filter_command(text)
    if filter_cmd and session["last_trials"]:
        if filter_cmd.get("_clear"):
            session["filters"] = {}
            session["_shown_count"] = 20
            reply = build_response(session["last_trials"], session["profile"],
                                   filters={}, start_idx=0, show=20)
            await send_to_user(ctx, sender, "Filters cleared.\n\n" + reply)
        else:
            session["filters"].update(filter_cmd)
            session["_shown_count"] = 20
            fsum = filter_summary(session["filters"])
            filtered = apply_filters(session["last_trials"], session["filters"])
            if not filtered:
                await send_to_user(ctx, sender,
                    f"No trials match \"{fsum}\" from your current results. "
                    "Try adjusting the filter or say \"clear filters\" to start over.")
            else:
                reply = build_response(session["last_trials"], session["profile"],
                                       filters=session["filters"], start_idx=0, show=20)
                await send_to_user(ctx, sender, f"Filter applied: {fsum}\n\n" + reply)
        return

    # ── On-demand eligibility check? ─────────────────────────────────────────
    if any(p in text_lower for p in ("eligible","eligib","qualify","do i qualify")) and session["last_trials"]:
        nums = re.findall(r"\b([1-9]\d?)\b", text)
        if nums:
            idx   = int(nums[0]) - 1
            trial = session["last_trials"][idx] if 0 <= idx < len(session["last_trials"]) else None
        else:
            trial = None

        if trial and config.ELIGIBILITY_AGENT_ADDRESS:
            await send_to_user(ctx, sender, f"🔎 Checking your eligibility for trial #{idx+1}...")
            await ctx.send(config.ELIGIBILITY_AGENT_ADDRESS, EligibilityRequest(
                session_id=sender,
                trials_json=json.dumps([{
                    "nct_id": trial["nct_id"],
                    "title":  trial["title"],
                    "eligibility_criteria": trial.get("eligibility_criteria",""),
                }]),
                profile_json=json.dumps(session["profile"]),
            ))
            return
        elif session.get("eligibility_scores"):
            # Show already-cached scores
            scores = session["eligibility_scores"]
            if scores:
                lines = ["🎯 Eligibility scores from your last search:\n"]
                for nct_id, r in scores.items():
                    t_idx = next((i+1 for i, t in enumerate(session["last_trials"]) if t["nct_id"]==nct_id), "?")
                    lines.append(f"{score_emoji(r.get('score',50))} Trial #{t_idx} — {r.get('score',50)}% — {r.get('verdict','')}")
                await send_to_user(ctx, sender, "\n".join(lines))
                return

    # ── Email request? ────────────────────────────────────────────────────────
    trial = detect_email_request(text, session["last_trials"])
    if trial:
        session["state"] = "waiting_inquiry"
        session["_pending_trial"] = trial
        await send_to_user(ctx, sender, "✍️ Drafting your inquiry email...")
        await ctx.send(config.INQUIRY_AGENT_ADDRESS, InquiryRequest(
            session_id=sender,
            trial_json=json.dumps(trial),
            profile_json=json.dumps(session["profile"]),
        ))
        return

    # ── Send to Profile Agent ─────────────────────────────────────────────────
    session["state"] = "waiting_profile"
    session["_pending_text"] = text

    if not config.PROFILE_AGENT_ADDRESS:
        await send_to_user(ctx, sender,
            "Sub-agents not configured yet. Please fill in config.py with agent addresses.")
        return

    await ctx.send(config.PROFILE_AGENT_ADDRESS, ProfileRequest(
        session_id=sender,
        text=text,
        known_profile=json.dumps(session.get("profile", {})),
    ))

@chat_protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass

# ── Internal protocol: handle sub-agent responses ─────────────────────────────
@internal_protocol.on_message(ProfileResponse)
async def handle_profile_response(ctx: Context, sender: str, msg: ProfileResponse):
    session = get_session(msg.session_id)
    profile = session["profile"]

    new_cond = msg.condition.strip()
    new_age  = msg.age.strip()
    new_loc  = msg.location.strip()

    # ── Detect condition change → ask user instead of auto-resetting ──────────
    # Skip if we just asked for clarification (user is refining, not changing)
    has_existing = bool(profile.get("condition")) and session["searched"]

    if has_existing and new_cond and new_cond.lower() != profile.get("condition","").lower() \
            and not session.get("_asked_clarification"):
        # Store the pending change and ask for confirmation
        session["_pending_profile_change"] = {
            "condition": new_cond,
            "age":       new_age  or profile.get("age",""),
            "location":  new_loc  or profile.get("location",""),
        }
        old_cond = profile["condition"].title()
        await send_to_user(ctx, msg.session_id,
            f"I see you mentioned **{new_cond.title()}** — but your current profile is set to **{old_cond}**.\n\n"
            f"Should I update your profile and search for **{new_cond.title()}** trials? (yes / no)")
        return

    # ── Check for age update ──────────────────────────────────────────────────
    if has_existing and new_age and new_age != profile.get("age","") and not new_cond:
        old_age = profile.get("age","?")
        # Age update is less disruptive — just confirm and re-search
        session["_pending_profile_change"] = {
            "condition": profile.get("condition",""),
            "age":       new_age,
            "location":  new_loc or profile.get("location",""),
        }
        await send_to_user(ctx, msg.session_id,
            f"Your age was {old_age} — should I update it to **{new_age}** and re-search? (yes / no)")
        return

    # ── Merge all fields into profile ────────────────────────────────────────
    new_fields = {
        "condition":        new_cond,
        "age":              new_age,
        "location":         new_loc,
        "medications":      msg.medications.strip(),
        "comorbidities":    msg.comorbidities.strip(),
        "stage":            msg.stage.strip(),
        "prior_treatments": msg.prior_treatments.strip(),
        "gender":           msg.gender.strip(),
    }
    for k, v in new_fields.items():
        if v: profile[k] = v

    _save_sessions()
    ctx.logger.info(f"Profile updated: {profile}")

    has_enough = profile.get("condition") and profile.get("location")

    # ── Check if condition is too vague — ask once regardless of searched state ─
    if has_enough:
        followup = get_vague_followup(profile.get("condition",""))
        if followup and not session.get("_asked_clarification"):
            session["_asked_clarification"] = True
            session["searched"] = False   # reset so we search fresh after clarification
            session["last_trials"] = []
            await send_to_user(ctx, msg.session_id,
                f"**{profile['condition'].title()}** is quite broad — I want to find the most relevant trials for you.\n\n"
                f"💬 {followup}\n\n"
                "_Or say **\"search anyway\"** to see all results now._")
            return

    if has_enough and not session["searched"]:
        session["_asked_clarification"] = False
        # ── Trigger Discovery ─────────────────────────────────────────────────
        session["searched"] = True
        session["state"]    = "waiting_discovery"
        await send_to_user(ctx, msg.session_id,
            build_profile_card(profile) + "\n\n" +
            f"🔍 Searching ClinicalTrials.gov for matching trials...")
        await ctx.send(config.DISCOVERY_AGENT_ADDRESS, DiscoveryRequest(
            session_id=msg.session_id,
            condition=profile.get("condition",""),
            age=profile.get("age",""),
            location=profile.get("location",""),
            comorbidities=profile.get("comorbidities",""),
            stage=profile.get("stage",""),
            prior_treatments=profile.get("prior_treatments",""),
            gender=profile.get("gender",""),
        ))
    elif has_enough and session["searched"]:
        # Profile updated mid-session — show updated card
        await send_to_user(ctx, msg.session_id,
            build_profile_card(profile) + "\n\n" +
            "Profile updated! Your existing results are still showing. "
            "Say \"search again\" to re-run the search with your new details, "
            "or keep browsing current results.")
    else:
        # ── Ask for the single most important missing field ───────────────────
        if not profile.get("condition"):
            reply = "What medical condition or diagnosis are you searching trials for?"
        elif not profile.get("location"):
            reply = (
                f"Got it — searching for **{profile['condition'].title()}** trials. "
                "What city and state are you in? (e.g. Dallas TX)"
            )
        else:
            # Has condition + location, missing age — proceed anyway
            session["searched"] = True
            session["state"]    = "waiting_discovery"
            await send_to_user(ctx, msg.session_id,
                build_profile_card(profile) + "\n\n" +
                f"🔍 Searching ClinicalTrials.gov for matching trials...")
            await ctx.send(config.DISCOVERY_AGENT_ADDRESS, DiscoveryRequest(
                session_id=msg.session_id,
                condition=profile.get("condition",""),
                age=profile.get("age",""),
                location=profile.get("location",""),
                comorbidities=profile.get("comorbidities",""),
                stage=profile.get("stage",""),
                prior_treatments=profile.get("prior_treatments",""),
                gender=profile.get("gender",""),
            ))
            return
        await send_to_user(ctx, msg.session_id, reply)

@internal_protocol.on_message(DiscoveryResponse)
async def handle_discovery_response(ctx: Context, sender: str, msg: DiscoveryResponse):
    session = get_session(msg.session_id)
    trials  = json.loads(msg.trials_json)
    session["last_trials"]        = trials
    session["_shown_count"]       = 20
    session["filters"]            = {}
    session["eligibility_scores"] = {}
    session["state"]              = "idle"
    _save_sessions()

    ctx.logger.info(f"Discovery complete: {msg.total_found} trials")
    reply = build_response(trials, session["profile"])
    await send_to_user(ctx, msg.session_id, reply)

    # ── Offer eligibility screening (paid via Stripe) ──────────────────────────
    if trials and config.ELIGIBILITY_AGENT_ADDRESS:
        try:
            checkout = create_eligibility_checkout(msg.session_id, msg.session_id)
            payment_req = RequestPayment(
                accepted_funds=[
                    Funds(currency="USD", amount="0.99", payment_method="stripe")
                ],
                recipient=str(agent.address),
                deadline_seconds=1800,
                reference=f"eligibility-{msg.session_id[:16]}",
                description="Eligibility Screening — AI scores your match against the top 5 trials (0-100%) with plain English breakdown of what you meet, fail, and what's unknown.",
                metadata={"stripe": checkout},
            )
            await send_to_user(ctx, msg.session_id,
                "🎯 **Want to know if you qualify?**\n"
                "For $0.99, our AI Eligibility Screener will read each trial's criteria and score your match 0-100%.\n"
                "Complete the payment below to unlock screening.")
            await ctx.send(msg.session_id, payment_req)
        except Exception as e:
            ctx.logger.exception("Stripe checkout failed — running eligibility for free")
            # Fallback: run eligibility for free if Stripe fails
            top5 = [
                {"nct_id": t["nct_id"], "title": t["title"],
                 "eligibility_criteria": t.get("eligibility_criteria","")}
                for t in trials[:5]
            ]
            await send_to_user(ctx, msg.session_id,
                "🔎 Screening your eligibility for the top 5 trials...")
            await ctx.send(config.ELIGIBILITY_AGENT_ADDRESS, EligibilityRequest(
                session_id=msg.session_id,
                trials_json=json.dumps(top5),
                profile_json=json.dumps(session["profile"]),
            ))

def score_emoji(score: int) -> str:
    if score >= 80: return "🟢"
    if score >= 50: return "🟡"
    return "🔴"

@internal_protocol.on_message(EligibilityResponse)
async def handle_eligibility_response(ctx: Context, sender: str, msg: EligibilityResponse):
    session = get_session(msg.session_id)
    try:
        scores = json.loads(msg.scores_json)
    except Exception:
        scores = {}

    if not scores:
        return

    session["eligibility_scores"] = scores

    # ── Build eligibility report ───────────────────────────────────────────────
    trials = session["last_trials"]
    nct_to_idx = {t["nct_id"]: i+1 for i, t in enumerate(trials)}

    lines = ["🎯 Eligibility Screening Results (Top 5 Trials):\n"]
    for nct_id, result in scores.items():
        idx     = nct_to_idx.get(nct_id, "?")
        score   = result.get("score", 50)
        verdict = result.get("verdict", "")
        met     = result.get("met", [])
        failed  = result.get("failed", [])
        unknown = result.get("unknown", [])
        emoji   = score_emoji(score)

        lines.append(f"{emoji} Trial #{idx} — {score}% match")
        lines.append(f"   {verdict}")
        if met:
            lines.append("   ✅ " + " · ".join(met))
        if failed:
            lines.append("   ❌ " + " · ".join(failed))
        if unknown:
            lines.append("   ❓ " + " · ".join(unknown))
        lines.append("")

    lines.append("💡 Say \"eligible for trial 3\" to screen any other trial.")
    lines.append("⚠️  Always confirm eligibility with your doctor.")
    await send_to_user(ctx, msg.session_id, "\n".join(lines))

@internal_protocol.on_message(InquiryResponse)
async def handle_inquiry_response(ctx: Context, sender: str, msg: InquiryResponse):
    session = get_session(msg.session_id)
    session["state"] = "idle"

    trial = session.get("_pending_trial", {})
    trial_title   = trial.get("title", "the selected trial")
    contact_email = trial.get("contact_email", "")
    nct_id        = trial.get("nct_id", "")

    # Build Gmail compose URL with pre-filled body
    subject   = f"Inquiry about Clinical Trial {nct_id}"
    gmail_url = (
        f"https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={quote(contact_email)}"
        f"&su={quote(subject)}"
        f"&body={quote(msg.email_text)}"
    )

    reply = (
        f"✉️ Inquiry email for:\n**{trial_title}**\n\n"
        f"---\n\n{msg.email_text}\n\n---\n\n"
        f"📬 [Open pre-filled Gmail draft]({gmail_url})\n\n"
        "Personalise before sending. Always confirm with your doctor first."
    )
    await send_to_user(ctx, msg.session_id, reply)

# ── Payment Protocol: Stripe for eligibility screening ───────────────────────
def create_eligibility_checkout(user_address: str, session_id: str) -> dict:
    """Create a Stripe Checkout Session for eligibility screening."""
    expires_at = int(time.time()) + 1800  # 30 min
    session = stripe.checkout.Session.create(
        ui_mode="embedded",
        redirect_on_completion="if_required",
        # payment methods managed via Stripe Dashboard
        mode="payment",
        return_url=f"https://asi1.ai?session_id={{CHECKOUT_SESSION_ID}}",
        expires_at=expires_at,
        line_items=[{
            "price_data": {
                "currency": STRIPE_CURRENCY,
                "product_data": {
                    "name": "TrialFinder Eligibility Screening",
                    "description": "AI screens your match against the top 5 clinical trials — 0-100% score with plain English breakdown",
                },
                "unit_amount": STRIPE_AMOUNT_CENTS,
            },
            "quantity": 1,
        }],
        metadata={"user_address": user_address, "session_id": session_id},
    )
    return {
        "client_secret": str(session.client_secret or ""),
        "id": str(session.id),
        "checkout_session_id": str(session.id),
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "currency": STRIPE_CURRENCY,
        "amount_cents": str(STRIPE_AMOUNT_CENTS),
        "ui_mode": "embedded",
    }


@payment_protocol.on_message(CommitPayment)
async def handle_commit_payment(ctx: Context, sender: str, msg: CommitPayment):
    """User completed Stripe checkout — verify and run eligibility screening."""
    if msg.funds.payment_method != "stripe" or not msg.transaction_id:
        await ctx.send(sender, RejectPayment(reason="Unsupported payment method."))
        return

    # Verify with Stripe
    try:
        checkout = stripe.checkout.Session.retrieve(msg.transaction_id)
        if checkout.payment_status != "paid":
            await ctx.send(sender, RejectPayment(reason="Payment not completed. Please finish checkout."))
            return
    except Exception as e:
        await ctx.send(sender, RejectPayment(reason=f"Payment verification failed: {e}"))
        return

    # Payment verified
    await ctx.send(sender, CompletePayment(transaction_id=msg.transaction_id))

    ctx.logger.info(f"Payment verified for {sender} — running eligibility screening")

    # Find the session and run eligibility
    session = get_session(sender)
    trials = session.get("last_trials", [])
    if not trials:
        await send_to_user(ctx, sender, "Payment received! But no trials found yet. Search for trials first, then screening will run automatically.")
        return

    # Run eligibility screening
    top5 = [
        {"nct_id": t["nct_id"], "title": t["title"],
         "eligibility_criteria": t.get("eligibility_criteria", "")}
        for t in trials[:5]
    ]
    await send_to_user(ctx, sender,
        "✅ Payment received! Screening your eligibility for the top 5 trials...")
    await ctx.send(config.ELIGIBILITY_AGENT_ADDRESS, EligibilityRequest(
        session_id=sender,
        trials_json=json.dumps(top5),
        profile_json=json.dumps(session["profile"]),
    ))


@payment_protocol.on_message(RejectPayment)
async def handle_reject_payment(ctx: Context, sender: str, msg: RejectPayment):
    await send_to_user(ctx, sender, f"Payment cancelled. {msg.reason or ''}\nYou can still browse trials for free.")


agent.include(chat_protocol, publish_manifest=True)
agent.include(internal_protocol)
agent.include(payment_protocol, publish_manifest=True)

if __name__ == "__main__":
    print(f"\n✅ Orchestrator address: {agent.address}\n")
    if not config.PROFILE_AGENT_ADDRESS:
        print("⚠️  config.py is empty — run sub-agents first to get their addresses.\n")
    agent.run()
