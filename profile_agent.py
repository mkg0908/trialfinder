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

EXTRACT_SYSTEM = """Extract medical profile fields from the user message.
Return ONLY a JSON object: {"condition": "", "age": "", "location": "", "medications": ""}
Use "" for missing fields. Age must be a number string only (e.g. "54")."""

@protocol.on_message(ProfileRequest)
async def handle_profile_request(ctx: Context, sender: str, msg: ProfileRequest):
    ctx.logger.info(f"Profile extraction request for session {msg.session_id}")
    condition = age = location = medications = ""
    try:
        r = client.chat.completions.create(
            model="asi1",
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user",   "content": msg.text},
            ],
            max_tokens=150,
        )
        raw   = str(r.choices[0].message.content)
        start = raw.find("{"); end = raw.rfind("}") + 1
        data  = json.loads(raw[start:end])
        condition   = data.get("condition",   "").strip()
        age         = data.get("age",         "").strip()
        location    = data.get("location",    "").strip()
        medications = data.get("medications", "").strip()
    except Exception:
        ctx.logger.exception("Profile extraction failed")

    await ctx.send(sender, ProfileResponse(
        session_id=msg.session_id,
        condition=condition,
        age=age,
        location=location,
        medications=medications,
    ))

agent.include(protocol)

if __name__ == "__main__":
    print(f"\n✅ Profile Agent address: {agent.address}\n")
    print("   → Copy this address into config.py as PROFILE_AGENT_ADDRESS\n")
    agent.run()
