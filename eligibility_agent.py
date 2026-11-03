"""
Eligibility Agent — scores a patient's likelihood of qualifying for each trial.
Reads the trial's free-text eligibility criteria + patient profile, sends to
ASI-1 LLM, returns a structured score per trial.
"""
import json
from openai import OpenAI
from uagents import Agent, Context, Protocol

from models import EligibilityRequest, EligibilityResponse

ASI1_API_KEY = "sk_1760bf82a6cf4388a8f72bdf4b4081d383446c4a62f846bb97bdff74bb136ad2"
client = OpenAI(base_url="https://api.asi1.ai/v1", api_key=ASI1_API_KEY)

agent = Agent(
    name="trialfinder-eligibility",
    seed="trialfinder eligibility screener medbridge 2026",
    port=8005,
    mailbox=True,
    publish_agent_details=True,
)

protocol = Protocol(name="trialfinder-internal", version="1.0.0")

SYSTEM_PROMPT = """You are a clinical trial eligibility expert.
Given a patient profile and the eligibility criteria for several trials,
score each trial's suitability for this patient.

Return ONLY a valid JSON object — one key per nct_id — with this structure:
{
  "NCT12345678": {
    "score": 82,
    "verdict": "Likely eligible — HbA1c and metformin use fit well",
    "met": ["Age 57 within range", "HbA1c 9.2 fits 7.5–11%", "On metformin ≥ 3 months"],
    "failed": ["Prior insulin use may disqualify"],
    "unknown": ["BMI not provided", "eGFR not provided"]
  },
  ...
}

Scoring guide:
- 80–100: Likely eligible — most criteria clearly met, no clear disqualifiers
- 50–79:  Possibly eligible — some criteria met, some unknown or borderline
- 20–49:  Unlikely eligible — one or more clear disqualifiers
- 0–19:   Very unlikely — multiple hard disqualifiers

Be concise. Max 3 items per list. If eligibility text is missing, return score 50 and verdict "Eligibility criteria not available"."""


def build_prompt(trials: list, profile: dict) -> str:
    profile_str = (
        f"Condition: {profile.get('condition','unknown')}\n"
        f"Age: {profile.get('age','unknown')}\n"
        f"Gender: {profile.get('gender','unknown')}\n"
        f"Medications: {profile.get('medications','none stated')}\n"
        f"Comorbidities: {profile.get('comorbidities','none stated')}\n"
        f"Disease stage/severity: {profile.get('stage','not specified')}\n"
        f"Prior treatments tried: {profile.get('prior_treatments','none stated')}"
    )

    trials_str = ""
    for t in trials:
        crit = t.get("eligibility_criteria","").strip() or "Not available"
        trials_str += f"\n---\nNCT ID: {t['nct_id']}\nTitle: {t['title']}\nEligibility Criteria:\n{crit}\n"

    return f"PATIENT PROFILE:\n{profile_str}\n\nTRIALS TO SCREEN:{trials_str}"


@protocol.on_message(EligibilityRequest)
async def handle_eligibility_request(ctx: Context, sender: str, msg: EligibilityRequest):
    ctx.logger.info(f"Eligibility screening for session {msg.session_id}")
    scores_json = "{}"
    try:
        trials  = json.loads(msg.trials_json)
        profile = json.loads(msg.profile_json)

        if not trials:
            await ctx.send(sender, EligibilityResponse(
                session_id=msg.session_id, scores_json=scores_json))
            return

        prompt = build_prompt(trials, profile)

        r = client.chat.completions.create(
            model="asi1",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1000,
        )
        raw   = str(r.choices[0].message.content)
        start = raw.find("{"); end = raw.rfind("}") + 1
        scores = json.loads(raw[start:end])
        scores_json = json.dumps(scores)
        ctx.logger.info(f"Screened {len(scores)} trials")
    except Exception:
        ctx.logger.exception("Eligibility screening failed")

    await ctx.send(sender, EligibilityResponse(
        session_id=msg.session_id,
        scores_json=scores_json,
    ))

agent.include(protocol)

if __name__ == "__main__":
    print(f"\n✅ Eligibility Agent address: {agent.address}\n")
    print("   → Copy this address into config.py as ELIGIBILITY_AGENT_ADDRESS\n")
    agent.run()
