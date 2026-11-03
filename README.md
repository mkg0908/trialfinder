# TrialFinder 🏥
### AI-Powered Clinical Trial Navigator

> *"1 in 4 Americans can't afford their medication. 47,711 clinical trials are recruiting right now — offering free treatment. 60% of patients have never heard of this option."*

**TrialFinder** connects patients to recruiting clinical trials in seconds — using plain English. No forms, no medical jargon, no searching. Just a conversation.

🔗 **Try it live:** [@trialfinder on ASI:One](https://asi1.ai)
📦 **Built for:** Fetch.ai Stranger Builds Hackathon 2026
🏆 **Winner:** Overall Best Project — Fetch.ai SF In-Person Event

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
"I have Type 2 Diabetes, I'm 57, female, Dallas TX — already tried metformin"
```

TrialFinder will:
1. **Understand your full profile** — condition, age, location, medications, comorbidities, disease stage, prior treatments, gender
2. **Clarify if vague** — asks once if condition is broad (e.g. "cancer" → "what type?")
3. **Search ClinicalTrials.gov live** — real data, no hallucinations
4. **Filter by age + sex** — only trials you qualify for
5. **Sort by distance** — nearest trials first
6. **Screen your eligibility** — AI reads each trial's eligibility criteria and scores your match (0–100%)
7. **Show contact info** — coordinator name and email
8. **Draft your inquiry email** — personalised, professional, one click sends via Gmail

---

## Architecture

TrialFinder is built on **Fetch.ai uAgents** — 5 specialised agents working together:

```
You (ASI:One)
     │
     ▼
┌──────────────────────────────┐
│   MedBridge (Orchestrator)   │  ← The only agent you talk to
│   @trialfinder on ASI:One    │
└──────────┬───────────────────┘
           │
    ┌──────┼────────────────────────┐
    ▼      ▼           ▼            ▼
┌────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐
│Profile │ │Discovery│ │ Inquiry │ │ Eligibility │
│ Agent  │ │  Agent  │ │  Agent  │ │   Screener  │
└────────┘ └─────────┘ └─────────┘ └─────────────┘
    │           │            │              │
    ▼           ▼            ▼              ▼
 ASI-1 LLM  ClinTrials  ASI-1 LLM     ASI-1 LLM
 (extracts   .gov API   (drafts       (scores patient
  profile)   v2 live     email)        eligibility
                data)                  0–100%)
```

### Agent Breakdown

| Agent | Port | Role |
|-------|------|------|
| **MedBridge** (Orchestrator) | 8001 | User-facing. Routes all requests. Manages session and conversation flow. |
| **Profile Agent** | 8002 | Uses ASI-1 LLM to extract condition, age, location, medications, comorbidities, stage, prior treatments, gender |
| **Discovery Agent** | 8003 | Searches ClinicalTrials.gov API v2, filters by age + sex, geocodes location, sorts by distance |
| **Inquiry Agent** | 8004 | Uses ASI-1 LLM to draft a personalised inquiry email to the trial coordinator |
| **Eligibility Screener** | 8005 | Uses ASI-1 LLM to read each trial's eligibility criteria and score the patient's match (0–100%) |

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

### Step 1 — Start the 4 sub-agents (each in a separate terminal)

```bash
# Terminal 1
python3 profile_agent.py
# Copy the printed address → paste into config.py as PROFILE_AGENT_ADDRESS

# Terminal 2
python3 discovery_agent.py
# Copy the printed address → paste into config.py as DISCOVERY_AGENT_ADDRESS

# Terminal 3
python3 inquiry_agent.py
# Copy the printed address → paste into config.py as INQUIRY_AGENT_ADDRESS

# Terminal 4
python3 eligibility_agent.py
# Copy the printed address → paste into config.py as ELIGIBILITY_AGENT_ADDRESS
```

### Step 2 — Fill in config.py

```python
PROFILE_AGENT_ADDRESS     = "agent1q..."   # from profile_agent.py output
DISCOVERY_AGENT_ADDRESS   = "agent1q..."   # from discovery_agent.py output
INQUIRY_AGENT_ADDRESS     = "agent1q..."   # from inquiry_agent.py output
ELIGIBILITY_AGENT_ADDRESS = "agent1q..."   # from eligibility_agent.py output
```

### Step 3 — Create mailboxes on Agentverse

For each agent, open the inspector URL printed in the terminal and click **Connect** to create a mailbox. This enables communication via ASI:One.

### Step 4 — Start the orchestrator

```bash
# Terminal 5
python3 orchestrator.py
```

### Step 5 — Chat on ASI:One

Go to [asi1.ai](https://asi1.ai) → New Chat → type `@trialfinder` in the To: field → send your message.

---

## Example Conversations

**Finding trials (with vague condition clarification):**
```
You:          "48 cancer sunnyvale ca"
TrialFinder:  "Cancer is quite broad — what type of cancer?
               (e.g. breast, lung, colorectal, leukemia, lymphoma)
               Or say 'search anyway' to see all results."
You:          "breast cancer"
TrialFinder:  [Profile card shown, then searches breast cancer trials near Sunnyvale]
```

**Rich profile — better results:**
```
You:          "Type 2 Diabetes, 57, female, Dallas TX, on metformin, HbA1c 9.2, also have hypertension"
TrialFinder:  [Profile card confirms all fields]
              [Searches with sex filter=FEMALE, stage + comorbidity as extra search terms]
              [Returns ranked trials, then screens top 5 for eligibility]
```

**Eligibility screening (automatic after search):**
```
TrialFinder:  "🎯 Eligibility Screening Results (Top 5 Trials):
               🟢 Trial #1 — 88% match — Likely eligible
                  ✅ Age fits · HbA1c 9.2 fits · Metformin use fits
                  ❓ BMI not provided · eGFR unknown

               🟡 Trial #2 — 62% match — Possibly eligible
                  ✅ Age fits
                  ❌ Prior insulin use may disqualify
                  ❓ Cardiovascular history unknown"
```

**On-demand eligibility check:**
```
You:          "am I eligible for trial 7"
TrialFinder:  [Screens trial #7 specifically and returns score + breakdown]
```

**Conversational filters:**
```
You:          "phase 3 only"         → filters current results by phase instantly
You:          "within 100 miles"     → filters by distance
You:          "remote only"          → shows virtual/telehealth trials only
You:          "clear filters"        → removes all filters
```

**More results + email:**
```
You:          "show more"
TrialFinder:  [Shows trials 21–40 from memory, no new search]

You:          "email for trial 3"
TrialFinder:  [Drafts personalised email + Gmail link pre-filled with To, Subject, Body]
```

**Profile commands:**
```
You:          "my profile"           → shows everything stored about you
You:          "I also have obesity"  → adds comorbidity, shows updated profile card
You:          "search again"         → re-runs search with updated profile
```

---

## Features

### Profile & Understanding
- **Natural language** — say it however you want, profile agent extracts structure
- **Rich medical profile** — condition, age, location, medications, comorbidities, disease stage, prior treatments, gender
- **Vague condition clarification** — asks once if condition is too broad, then searches regardless
- **Smart profile updates** — detects condition/age changes and asks before re-searching (no silent resets)
- **Session memory** — remembers profile across messages, persists across restarts
- **Profile card** — shown before every search so patient can verify what's being used

### Search & Matching
- **Live ClinicalTrials.gov data** — real-time API, no stale database
- **Sex filter** — `filter.sex=FEMALE/MALE` passed directly to ClinicalTrials.gov API
- **Age filtering** — only shows trials within eligible age range
- **Stage + prior treatment matching** — added to `query.term` to surface relevant trials
- **Condition synonyms** — "Type 2 Diabetes" also searches "T2DM", "Type 2 Diabetes Mellitus"
- **Progressive geo search** — 100mi → 400mi → 1000mi → nationwide
- **Distance sorting** — nearest trials first, with exact mileage

### Eligibility Screening
- **Automatic screening** — top 5 trials screened immediately after every search
- **On-demand** — say "am I eligible for trial 7" to screen any specific trial
- **0–100% match score** with verdict, met criteria, failed criteria, unknowns
- **Plain English** — no medical jargon in the output

### Filters (apply without re-searching)
- `"phase 3 only"` / `"phase 2"` — filter by trial phase
- `"within 100 miles"` — filter by distance
- `"remote only"` / `"virtual visits"` — filter for telehealth-friendly trials
- `"clear filters"` — remove all filters

### Communication
- **Pagination** — top 20 shown, "show more" for next batch
- **Zone summary** — breakdown by nearby / regional / national / international
- **Email drafting** — ASI-1 writes a professional personalised inquiry email
- **Gmail integration** — one-click opens pre-filled Gmail compose window

---

## Project Structure

```
trialfinder/
├── orchestrator.py        # Main agent — user-facing, routes to sub-agents
├── profile_agent.py       # Extracts full medical profile using ASI-1 LLM
├── discovery_agent.py     # Searches ClinicalTrials.gov, filters, ranks
├── inquiry_agent.py       # Drafts inquiry emails using ASI-1 LLM
├── eligibility_agent.py   # Screens patient eligibility per trial using ASI-1 LLM
├── models.py              # Shared Pydantic message models
├── config.py              # Sub-agent addresses (fill after first run)
└── sessions.json          # Auto-generated session persistence
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
