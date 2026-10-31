"""
Inquiry Agent — drafts personalised inquiry emails to trial coordinators.
Registered on Agentverse independently. Receives InquiryRequest from orchestrator.
"""
import json
from openai import OpenAI
from uagents import Agent, Context, Protocol

from models import InquiryRequest, InquiryResponse

ASI1_API_KEY = "sk_1760bf82a6cf4388a8f72bdf4b4081d383446c4a62f846bb97bdff74bb136ad2"
client = OpenAI(base_url="https://api.asi1.ai/v1", api_key=ASI1_API_KEY)

agent = Agent(
    name="trialfinder-inquiry",
    seed="trialfinder inquiry agent medbridge 2026",
    port=8004,
    mailbox=True,
    publish_agent_details=True,
)

protocol = Protocol(name="trialfinder-internal", version="1.0.0")

@protocol.on_message(InquiryRequest)
async def handle_inquiry_request(ctx: Context, sender: str, msg: InquiryRequest):
    ctx.logger.info(f"Inquiry email request for session {msg.session_id}")
    email_text = "Unable to draft email. Please try again."
    try:
        trial   = json.loads(msg.trial_json)
        profile = json.loads(msg.profile_json)

        prompt = (
            f"Write a 150-word professional inquiry email from a patient to a clinical trial coordinator.\n\n"
            f"Patient: {profile.get('condition','?')}, age {profile.get('age','?')}, "
            f"in {profile.get('location','?')}, medications: {profile.get('medications','none listed')}.\n\n"
            f"Trial: {trial.get('title','?')} ({trial.get('nct_id','')})\n"
            f"Sites: {trial.get('location','?')}\n"
            f"Contact: {trial.get('contact_name','')} {trial.get('contact_email','')}\n\n"
            "The email should: mention they found it on ClinicalTrials.gov, briefly describe "
            "the patient's condition, ask if they might be eligible, ask about visit frequency "
            "and whether any visits can be remote, thank the coordinator, ask for next steps.\n"
            "Sign off as: 'A Prospective Participant'"
        )
        r = client.chat.completions.create(
            model="asi1",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )
        email_text = str(r.choices[0].message.content)
    except Exception:
        ctx.logger.exception("Email drafting failed")

    await ctx.send(sender, InquiryResponse(
        session_id=msg.session_id,
        email_text=email_text,
    ))

agent.include(protocol)

if __name__ == "__main__":
    print(f"\n✅ Inquiry Agent address: {agent.address}\n")
    print("   → Copy this address into config.py as INQUIRY_AGENT_ADDRESS\n")
    agent.run()
