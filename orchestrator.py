"""
Orchestrator Agent — the only agent users interact with via ASI:One.
Routes requests to Profile, Discovery, and Inquiry sub-agents.
"""
import json, re
from datetime import datetime
from uuid import uuid4
from urllib.parse import quote

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement, ChatMessage, TextContent, chat_protocol_spec,
)

from models import (
    ProfileRequest, ProfileResponse,
    DiscoveryRequest, DiscoveryResponse,
    InquiryRequest, InquiryResponse,
)
import config

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
        # Don't persist large trial lists — just the profile
        slim = {}
        for k, v in sessions.items():
            slim[k] = {
                "user_sender": v.get("user_sender", k),
                "profile":     v.get("profile", {}),
                "searched":    v.get("searched", False),
                "last_trials": v.get("last_trials", []),
                "state":       "idle",
            }
        with open(SESSIONS_FILE, "w") as f:
            json.dump(slim, f)
    except Exception:
        pass

sessions: dict[str, dict] = _load_sessions()

def get_session(sender: str) -> dict:
    if sender not in sessions:
        sessions[sender] = {
            "user_sender": sender,
            "profile":     {},
            "searched":    False,
            "last_trials": [],
            "state":       "idle",
        }
    return sessions[sender]

# ── Formatting helpers ────────────────────────────────────────────────────────
def fmt_age(s: str) -> str:
    if not s or s.lower() in ("n/a","not specified",""): return "Any"
    return re.sub(r"\s*years?\s*","y", s, flags=re.IGNORECASE)

def distance_label(d) -> str:
    if d is None:   return "International"
    if d < 400:     return f"{d:.1f} mi 🟢"
    if d < 1000:    return f"{d:.1f} mi 🟡"
    return                  f"{d:.1f} mi 🔴"

def build_response(trials: list, profile: dict) -> str:
    if not trials:
        return (
            f"No recruiting trials found for {profile.get('condition','').title()} "
            f"matching age {profile.get('age','?')} right now. "
            "Check back in a few weeks or speak with your specialist."
        )

    cond = profile.get("condition","").title()
    age  = profile.get("age","?")
    loc  = profile.get("location","")

    nearby   = [t for t in trials if t.get("distance_mi") is not None and t["distance_mi"] < 400]
    regional = [t for t in trials if t.get("distance_mi") is not None and 400 <= t["distance_mi"] < 1000]
    national = [t for t in trials if t.get("distance_mi") is not None and t["distance_mi"] >= 1000]
    intl     = [t for t in trials if t.get("distance_mi") is None]

    nearby   = [t for t in trials if t.get("distance_mi") is not None and t["distance_mi"] < 400]
    regional = [t for t in trials if t.get("distance_mi") is not None and 400 <= t["distance_mi"] < 1000]
    national = [t for t in trials if t.get("distance_mi") is not None and t["distance_mi"] >= 1000]
    intl     = [t for t in trials if t.get("distance_mi") is None]

    # ── Summary ───────────────────────────────────────────────────────────────
    lines = [f"🔍 {len(trials)} Recruiting Trials — {cond} | Age {age} | {loc}", ""]
    lines.append("📊 Results Summary:")
    if nearby:   lines.append(f"  🟢 Nearby (< 400 mi)       — {len(nearby)} trials")
    if regional: lines.append(f"  🟠 Regional (400–1000 mi)  — {len(regional)} trials")
    if national: lines.append(f"  🔴 National (1000+ mi)     — {len(national)} trials")
    if intl:     lines.append(f"  ⚫ International           — {len(intl)} trials")
    lines.append("")

    BR   = "  "
    SHOW = 20
    shown  = trials[:SHOW]
    hidden = len(trials) - SHOW

    for i, t in enumerate(shown, 1):
        best  = " 🏆 Best Match" if i == 1 else ""
        ages  = f"{fmt_age(t['min_age'])} – {fmt_age(t['max_age'])}"
        dist  = distance_label(t.get("distance_mi"))
        phase   = t.get("phase","N/A")
        sponsor = t.get("sponsor","") or "—"

        block  = f"{i}.{best} {t['title']}{BR}\n"
        block += f"📍 {t['location']} · {dist}{BR}\n"
        block += f"🔬 {phase} · {sponsor}{BR}\n"
        block += f"👤 Eligible Age: {ages}{BR}\n"
        if t.get("contact_name") or t.get("contact_email"):
            contact = " · ".join(filter(None,[t.get("contact_name",""), t.get("contact_email","")]))
            block += f"📧 {contact}{BR}\n"
        block += f"🔗 {t['url']}"
        lines.append(block)
        lines.append("")

    # ── Footer bullets ─────────────────────────────────────────────────────────
    lines.append("─" * 40)
    lines.append("📋 Next Steps:")
    if hidden > 0:
        lines.append(f"  • {hidden} more trials available — reply \"show more\" to see them")
    lines.append("  • Reply \"send pdf\" to get a PDF of all results")
    lines.append("  • Say \"email for trial 3\" to draft an inquiry email for any trial")
    lines.append("  • Share results with your doctor before taking any action")
    lines.append("")
    lines.append("⚠️  Always consult your doctor before enrolling in any clinical trial.")
    return "\n".join(lines)

def detect_email_request(text: str, last_trials: list) -> dict | None:
    if not last_trials: return None
    if not any(kw in text.lower() for kw in ("email","draft","inquiry","contact","write")): return None
    nums = re.findall(r"\b([1-9]\d?)\b", text)
    if nums:
        idx = int(nums[0]) - 1
        if 0 <= idx < len(last_trials): return last_trials[idx]
    return None

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
    # Strip @mention prefix (e.g. "@trailfinder" or "@agent1q...") so LLM gets clean input
    text = re.sub(r"^@\S+\s*", "", text).strip()
    session = get_session(sender)

    # ── Show more? ───────────────────────────────────────────────────────────
    if "show more" in text.lower() and session["last_trials"]:
        shown = session.get("_shown_count", 20)
        more  = session["last_trials"][shown:shown+20]
        if not more:
            await send_to_user(ctx, sender, "No more trials to show.")
        else:
            session["_shown_count"] = shown + len(more)
            BR = "  "
            lines = [f"Showing trials {shown+1}–{shown+len(more)}:\n"]
            for i, t in enumerate(more, shown+1):
                ages = f"{fmt_age(t['min_age'])} – {fmt_age(t['max_age'])}"
                dist = distance_label(t.get("distance_mi"))
                block  = f"{i}. {t['title']}{BR}\n"
                block += f"📍 {t['location']} · {dist}{BR}\n"
                block += f"🔬 {t.get('phase','N/A')} · {t.get('sponsor','—')}{BR}\n"
                block += f"👤 Eligible Age: {ages}{BR}\n"
                if t.get("contact_name") or t.get("contact_email"):
                    contact = " · ".join(filter(None,[t.get("contact_name",""), t.get("contact_email","")]))
                    block += f"📧 {contact}{BR}\n"
                block += f"🔗 {t['url']}"
                lines.append(block)
                lines.append("")
            remaining = len(session["last_trials"]) - session["_shown_count"]
            if remaining > 0:
                lines.append(f"📋 {remaining} more — reply \"show more\" to continue.")
            await send_to_user(ctx, sender, "\n".join(lines))
        return

    # ── Email request? ────────────────────────────────────────────────────────
    trial = detect_email_request(text, session["last_trials"])
    if trial:
        session["state"] = "waiting_inquiry"
        session["_pending_trial"] = trial
        await send_to_user(ctx, sender, "Drafting your inquiry email now...")
        await ctx.send(config.INQUIRY_AGENT_ADDRESS, InquiryRequest(
            session_id=sender,
            trial_json=json.dumps(trial),
            profile_json=json.dumps(session["profile"]),
        ))
        return

    # ── Detect new condition → reset ──────────────────────────────────────────
    # (quick keyword check — profile agent does the real extraction)
    text_lower = text.lower()
    current_cond = session["profile"].get("condition","").lower()
    if current_cond and current_cond not in text_lower and session["searched"]:
        # looks like a new condition — reset
        session["searched"]    = False
        session["last_trials"] = []
        session["profile"]     = {}

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
    ))

@chat_protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass

# ── Internal protocol: handle sub-agent responses ─────────────────────────────
@internal_protocol.on_message(ProfileResponse)
async def handle_profile_response(ctx: Context, sender: str, msg: ProfileResponse):
    session = get_session(msg.session_id)
    profile = session["profile"]

    # Detect condition change
    new_cond = msg.condition.strip()
    if new_cond and profile.get("condition") and new_cond.lower() != profile["condition"].lower():
        session["searched"]    = False
        session["last_trials"] = []
        profile.clear()

    # Merge extracted fields
    for k, v in [("condition",msg.condition),("age",msg.age),
                  ("location",msg.location),("medications",msg.medications)]:
        if v.strip(): profile[k] = v.strip()

    _save_sessions()
    ctx.logger.info(f"Profile updated: {profile}")
    has_enough = profile.get("condition") and profile.get("location")

    if has_enough and not session["searched"]:
        # ── Trigger Discovery ─────────────────────────────────────────────────
        session["searched"] = True
        session["state"]    = "waiting_discovery"
        await send_to_user(ctx, msg.session_id,
            f"Searching ClinicalTrials.gov for {profile['condition']} trials near {profile['location']}...")
        await ctx.send(config.DISCOVERY_AGENT_ADDRESS, DiscoveryRequest(
            session_id=msg.session_id,
            condition=profile.get("condition",""),
            age=profile.get("age",""),
            location=profile.get("location",""),
        ))
    else:
        # ── Not enough info yet — ask user ────────────────────────────────────
        missing = []
        if not profile.get("condition"): missing.append("medical condition")
        if not profile.get("location"):  missing.append("location (city, state)")
        if not profile.get("age"):       missing.append("age")
        if missing:
            reply = f"To find matching trials I still need: **{', '.join(missing)}**. Could you share those?"
        else:
            reply = "I have your information. Searching now..."
        await send_to_user(ctx, msg.session_id, reply)

@internal_protocol.on_message(DiscoveryResponse)
async def handle_discovery_response(ctx: Context, sender: str, msg: DiscoveryResponse):
    session = get_session(msg.session_id)
    trials  = json.loads(msg.trials_json)
    session["last_trials"]   = trials
    session["_shown_count"]  = 20
    session["state"]         = "idle"
    _save_sessions()

    ctx.logger.info(f"Discovery complete: {msg.total_found} trials")
    reply = build_response(trials, session["profile"])
    await send_to_user(ctx, msg.session_id, reply)

@internal_protocol.on_message(InquiryResponse)
async def handle_inquiry_response(ctx: Context, sender: str, msg: InquiryResponse):
    session = get_session(msg.session_id)
    session["state"] = "idle"

    trial = session.get("_pending_trial", {})
    trial_title = trial.get("title", "the selected trial")
    contact_email = trial.get("contact_email", "")
    nct_id = trial.get("nct_id", "")

    # Build Gmail compose URL with full body pre-filled
    subject = f"Inquiry about Clinical Trial {nct_id}"
    gmail_url = (
        f"https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={quote(contact_email)}"
        f"&su={quote(subject)}"
        f"&body={quote(msg.email_text)}"
    )

    reply = (
        f"Draft inquiry email for: {trial_title}\n\n"
        f"---\n\n{msg.email_text}\n\n---\n\n"
        f"📬 [Click to open pre-filled Gmail draft]({gmail_url})\n\n"
        "Feel free to personalise before sending. Always confirm with your doctor first."
    )
    await send_to_user(ctx, msg.session_id, reply)

agent.include(chat_protocol, publish_manifest=True)
agent.include(internal_protocol)

if __name__ == "__main__":
    print(f"\n✅ Orchestrator address: {agent.address}\n")
    if not config.PROFILE_AGENT_ADDRESS:
        print("⚠️  config.py is empty — run sub-agents first to get their addresses.\n")
    agent.run()
