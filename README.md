# TrialFinder 🏥
### AI-Powered Clinical Trial Navigator

> *"1 in 4 Americans can't afford their medication. 47,711 clinical trials are recruiting right now — offering free treatment. 60% of patients have never heard of this option."*

**TrialFinder** connects patients to recruiting clinical trials in seconds — using plain English. No forms, no medical jargon, no searching. Just a conversation.

🔗 **Try it live:** [@trialfinder on ASI:One](https://asi1.ai)
📦 **Built for:** Fetch.ai Stranger Builds Hackathon 2026

---

## The Problem

609,551 studies are registered on ClinicalTrials.gov across 226 countries. Thousands are actively recruiting patients — offering **free treatment, free medication, free monitoring** — paid entirely by pharmaceutical companies.

Yet:
- **60%** of patients have no knowledge of clinical trials *(JAMA Network Open, 2025)*
- **80%** of trials fail to enroll enough patients on time *(NIH/PMC)*
- **Only 5%** of eligible patients ever participate *(NCI HINTS)*

The website is built for researchers — not patients. A 57-year-old in Dallas with diabetes shouldn't need a medical degree to find a free trial 2 miles from their home.

---

## The Solution

Talk to **@trialfinder** on ASI:One in plain English:

```
"I have Type 2 Diabetes, I'm 57, and I live in Dallas TX"
```

TrialFinder will:
1. **Understand your profile** — condition, age, location, medications
2. **Search ClinicalTrials.gov live** — real data, no hallucinations
3. **Filter by age eligibility** — only trials you qualify for
4. **Sort by distance** — nearest trials first
5. **Show contact info** — coordinator name and email
6. **Draft your inquiry email** — personalised, professional, one click sends via Gmail

---

## Architecture

TrialFinder is built on **Fetch.ai uAgents** — 4 specialised agents working together:

```
You (ASI:One)
     │
     ▼
┌─────────────────────────────┐
│   MedBridge (Orchestrator)  │  ← The only agent you talk to
│   @trialfinder on ASI:One   │
└──────────┬──────────────────┘
           │
    ┌──────┼──────────────────┐
    ▼      ▼                  ▼
┌────────┐ ┌───────────┐ ┌──────────┐
│Profile │ │ Discovery │ │ Inquiry  │
│ Agent  │ │   Agent   │ │  Agent   │
└────────┘ └───────────┘ └──────────┘
    │            │              │
    ▼            ▼              ▼
 ASI-1 LLM  ClinicalTrials  ASI-1 LLM
 (extracts   .gov API v2    (drafts email)
  profile)   (live data)
```

### Agent Breakdown

| Agent | Port | Role |
|-------|------|------|
| **MedBridge** (Orchestrator) | 8001 | User-facing. Routes all requests. Formats responses. |
| **Profile Agent** | 8002 | Uses ASI-1 LLM to extract condition, age, location, medications from natural language |
| **Discovery Agent** | 8003 | Searches ClinicalTrials.gov API, filters by age, geocodes location, sorts by distance |
| **Inquiry Agent** | 8004 | Uses ASI-1 LLM to draft a personalised inquiry email to trial coordinator |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | Fetch.ai uAgents |
| Agent Registry | Agentverse |
| Chat Interface | ASI:One |
| AI / LLM | ASI-1 (OpenAI-compatible API) |
| Trial Data | ClinicalTrials.gov API v2 |
| Language | Python 3.11 |
| HTTP Client | httpx |
| Data Models | Pydantic |
| Distance Calc | Haversine formula |
| Session Storage | JSON (persists across restarts) |

---

## How to Run

### Prerequisites
```bash
pip install uagents uagents-core openai httpx pydantic
```

### Step 1 — Start the 3 sub-agents (in separate terminals)

```bash
# Terminal 1
python profile_agent.py
# Copy the printed address → paste into config.py as PROFILE_AGENT_ADDRESS

# Terminal 2
python discovery_agent.py
# Copy the printed address → paste into config.py as DISCOVERY_AGENT_ADDRESS

# Terminal 3
python inquiry_agent.py
# Copy the printed address → paste into config.py as INQUIRY_AGENT_ADDRESS
```

### Step 2 — Fill in config.py

```python
PROFILE_AGENT_ADDRESS   = "agent1q..."   # from profile_agent.py output
DISCOVERY_AGENT_ADDRESS = "agent1q..."   # from discovery_agent.py output
INQUIRY_AGENT_ADDRESS   = "agent1q..."   # from inquiry_agent.py output
```

### Step 3 — Start the orchestrator

```bash
# Terminal 4
python orchestrator.py
```

### Step 4 — Chat on ASI:One

Go to [asi1.ai](https://asi1.ai) → New Chat → type `@trialfinder` in the To: field → send your message.

---

## Example Conversations

**Finding trials:**
```
You:          "I have Parkinson's disease, age 65, San Francisco CA"
TrialFinder:  "Searching ClinicalTrials.gov for Parkinson's trials near San Francisco..."
              [Returns ranked list of trials with distance, phase, contact info]
```

**Requesting more results:**
```
You:          "show more"
TrialFinder:  [Shows trials 21-40 instantly from memory]
```

**Drafting an inquiry email:**
```
You:          "email for trial 3"
TrialFinder:  [Drafts personalised email + Gmail link pre-filled with To, Subject, Body]
```

---

## Features

- **Natural language understanding** — say it however you want
- **Live ClinicalTrials.gov data** — searches in real time, no stale database
- **Age filtering** — only shows trials you're eligible for
- **Distance sorting** — nearest trials first, with exact mileage
- **Progressive geo search** — 100mi → 400mi → 1000mi → nationwide
- **Condition synonyms** — "Type 2 Diabetes" also searches "T2DM", "Type 2 Diabetes Mellitus"
- **Zone summary** — see how many trials are nearby vs national vs international
- **Pagination** — top 20 shown, "show more" for next batch
- **Email drafting** — ASI-1 writes a professional 150-word inquiry email
- **Gmail integration** — one-click opens pre-filled Gmail compose window
- **Session memory** — remembers your profile across messages, persists across restarts
- **Condition switching** — detects when you ask about a new condition and resets automatically

---

## Project Structure

```
trialfinder/
├── orchestrator.py      # Main agent — user-facing, routes to sub-agents
├── profile_agent.py     # Extracts medical profile using ASI-1 LLM
├── discovery_agent.py   # Searches ClinicalTrials.gov, filters, ranks
├── inquiry_agent.py     # Drafts inquiry emails using ASI-1 LLM
├── models.py            # Shared Pydantic message models
├── config.py            # Sub-agent addresses (fill after first run)
└── sessions.json        # Auto-generated session persistence
```

---

## Sources & Statistics

| Statistic | Source |
|-----------|--------|
| 1 in 4 Americans can't afford medication | KFF Health Tracking Poll, 2026 |
| 609,551 studies on ClinicalTrials.gov | ClinicalTrials.gov, October 2026 |
| 47,711 actively recruiting trials | NIH/PMC, March 2025 |
| 80% of trials fail to enroll on time | PMC — Recruitment in Clinical Studies |
| 60% of cancer patients unaware of trials | JAMA Network Open, 2025 |
| Only 5% of patients ever participate | NCI HINTS Brief 57 |

---

## Built With ❤️ by Manali Gawande

Fetch.ai Stranger Builds Hackathon — October 2026

*Always consult your doctor before enrolling in any clinical trial.*
