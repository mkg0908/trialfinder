"""
Profile Agent — extracts structured medical profile from plain English.
Registered on Agentverse independently. Receives ProfileRequest from orchestrator.
"""
import json
from openai import OpenAI
from uagents import Agent, Context, Protocol

from models import ProfileRequest, ProfileResponse

ASI1_API_KEY = "sk_1760bf82a6cf4388a8f72bdf4b4081d383446c4a62f846bb97bdff74bb136ad2"
client = OpenAI(base_url="https://api.asi1.ai/v1", api_key=ASI1_API_KEY)

agent = Agent(
    name="trialfinder-profile",
    seed="trialfinder profile agent medbridge 2026",
    port=8002,
    mailbox=True,
    publish_agent_details=True,
)

protocol = Protocol(name="trialfinder-internal", version="1.0.0")

EXTRACT_SYSTEM = """You extract a patient's medical profile from their message to help find clinical trials.
Return ONLY a valid JSON object with these fields:
{
  "condition": "",        // primary condition being searched (e.g. "Type 2 Diabetes")
  "age": "",              // age as a number string only (e.g. "57"), or ""
  "location": "",         // city and/or state (e.g. "Dallas TX"), or ""
  "medications": "",      // current medications, comma-separated (e.g. "metformin, lisinopril")
  "comorbidities": "",    // other medical conditions, comma-separated (e.g. "hypertension, obesity")
  "stage": "",            // disease stage or severity (e.g. "Stage 3", "HbA1c 9.2", "moderate")
  "prior_treatments": "", // past treatments or therapies tried (e.g. "metformin, insulin therapy")
  "gender": ""            // "male", "female", or ""
}
Use "" for any field not mentioned. Never guess. Age must be a number string only."""

@protocol.on_message(ProfileRequest)
async def handle_profile_request(ctx: Context, sender: str, msg: ProfileRequest):
    ctx.logger.info(f"Profile extraction for session {msg.session_id}: {msg.text[:80]}")
    condition = age = location = medications = comorbidities = stage = prior_treatments = gender = ""
    try:
        r = client.chat.completions.create(
            model="asi1",
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user",   "content": msg.text},
            ],
            max_tokens=250,
        )
        raw   = str(r.choices[0].message.content)
        start = raw.find("{"); end = raw.rfind("}") + 1
        data  = json.loads(raw[start:end])
        condition        = data.get("condition",        "").strip()
        age              = data.get("age",              "").strip()
        location         = data.get("location",         "").strip()
        medications      = data.get("medications",      "").strip()
        comorbidities    = data.get("comorbidities",    "").strip()
        stage            = data.get("stage",            "").strip()
        prior_treatments = data.get("prior_treatments", "").strip()
        gender           = data.get("gender",           "").strip().lower()
        if gender not in ("male", "female"):
            gender = ""
    except Exception:
        ctx.logger.exception("Profile extraction failed")

    await ctx.send(sender, ProfileResponse(
        session_id=msg.session_id,
        condition=condition,
        age=age,
        location=location,
        medications=medications,
        comorbidities=comorbidities,
        stage=stage,
        prior_treatments=prior_treatments,
        gender=gender,
    ))

agent.include(protocol)

if __name__ == "__main__":
    print(f"\n✅ Profile Agent address: {agent.address}\n")
    print("   → Copy this address into config.py as PROFILE_AGENT_ADDRESS\n")
    agent.run()
