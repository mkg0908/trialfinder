"""
Discovery Agent — searches ClinicalTrials.gov, filters by age, sorts by distance.
Registered on Agentverse independently. Receives DiscoveryRequest from orchestrator.
"""
import json, re, math
import httpx
from uagents import Agent, Context, Protocol

from models import DiscoveryRequest, DiscoveryResponse

agent = Agent(
    name="trialfinder-discovery",
    seed="trialfinder discovery agent medbridge 2026",
    port=8003,
    mailbox=True,
    publish_agent_details=True,
)

protocol = Protocol(name="trialfinder-internal", version="1.0.0")

# ── Geocoding ─────────────────────────────────────────────────────────────────
CITY_COORDS = {
    "san francisco":(37.7749,-122.4194),"sf":(37.7749,-122.4194),
    "los angeles":(34.0522,-118.2437),"la":(34.0522,-118.2437),
    "san diego":(32.7157,-117.1611),"san jose":(37.3382,-121.8863),
    "sacramento":(38.5816,-121.4944),"oakland":(37.8044,-122.2712),
    "palo alto":(37.4419,-122.1430),"seattle":(47.6062,-122.3321),
    "portland":(45.5051,-122.6750),"las vegas":(36.1699,-115.1398),
    "phoenix":(33.4484,-112.0740),"denver":(39.7392,-104.9903),
    "salt lake city":(40.7608,-111.8910),"slc":(40.7608,-111.8910),
    "chicago":(41.8781,-87.6298),"new york":(40.7128,-74.0060),
    "nyc":(40.7128,-74.0060),"boston":(42.3601,-71.0589),
    "houston":(29.7604,-95.3698),"dallas":(32.7767,-96.7970),
    "miami":(25.7617,-80.1918),"atlanta":(33.7490,-84.3880),
    "philadelphia":(39.9526,-75.1652),"washington":(38.9072,-77.0369),
    "baltimore":(39.2904,-76.6122),"minneapolis":(44.9778,-93.2650),
}
STATE_CENTROIDS = {
    "ca":(36.7783,-119.4179),"tx":(31.9686,-99.9018),"fl":(27.6648,-81.5158),
    "ny":(42.1657,-74.9481),"pa":(41.2033,-77.1945),"il":(40.3495,-88.9861),
    "oh":(40.3888,-82.7649),"ga":(32.1656,-82.9001),"nc":(35.6301,-79.8064),
    "mi":(44.3148,-85.6024),"wa":(47.7511,-120.7401),"az":(34.0489,-111.0937),
    "ma":(42.4072,-71.3824),"co":(39.0598,-105.3111),"or":(44.5720,-122.0709),
    "nv":(38.8026,-116.4194),"mn":(46.3297,-94.3213),"ut":(39.3210,-111.0937),
    "tn":(35.7478,-86.6923),"wi":(43.7844,-88.7879),"mo":(38.4561,-92.2884),
    "va":(37.7693,-78.1700),"in":(40.2672,-86.1349),"la":(30.9843,-91.9623),
    "ky":(37.6681,-84.6701),"al":(32.3617,-86.2792),"sc":(33.8361,-81.1637),
    "ok":(35.5653,-96.9289),"ar":(34.7465,-92.2896),"ia":(41.8780,-93.0977),
    "ks":(39.0119,-98.4842),"nm":(34.5199,-105.8701),"ne":(41.4925,-99.9018),
    "wv":(38.5976,-80.4549),"id":(44.2405,-114.4788),"mt":(46.8797,-110.3626),
    "sd":(43.9695,-99.9018),"nd":(47.5515,-101.0020),"wy":(43.0760,-107.2903),
    "nh":(43.1939,-71.5724),"me":(45.2538,-69.4455),"vt":(44.0459,-72.7107),
    "ri":(41.5801,-71.4774),"ct":(41.6032,-73.0877),"de":(38.9108,-75.5277),
    "nj":(40.0583,-74.4057),"md":(39.0458,-76.6413),"ms":(32.3547,-89.3985),
    "hi":(19.8968,-155.5828),"ak":(64.2008,-153.4937),
}

def geocode(location: str):
    loc = location.lower().strip()
    if loc in CITY_COORDS: return CITY_COORDS[loc]
    city = re.split(r"[,\s]+(?:[a-z]{2})?$", loc)[0].strip()
    if city in CITY_COORDS: return CITY_COORDS[city]
    for p in reversed(re.split(r"[,\s]+", loc)):
        p = p.strip().lower()
        if p in STATE_CENTROIDS: return STATE_CENTROIDS[p]
        if p in CITY_COORDS: return CITY_COORDS[p]
    return None

def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8
    d = math.radians
    a = math.sin(d(lat2-lat1)/2)**2 + math.cos(d(lat1))*math.cos(d(lat2))*math.sin(d(lon2-lon1)/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# ── Age helpers ───────────────────────────────────────────────────────────────
def parse_age_years(s):
    if not s or s.lower() in ("not specified","n/a",""): return None
    m = re.match(r"(\d+)\s*(year|month|week|day)?s?", s, re.IGNORECASE)
    if not m: return None
    val, unit = int(m.group(1)), (m.group(2) or "year").lower()
    return val//12 if unit.startswith("month") else val//52 if unit.startswith("week") else val//365 if unit.startswith("day") else val

def age_ok(trial, user_age):
    if user_age is None: return True
    mn, mx = parse_age_years(trial["min_age"]), parse_age_years(trial["max_age"])
    return (mn is None or user_age >= mn) and (mx is None or user_age <= mx)

# ── Synonyms ──────────────────────────────────────────────────────────────────
SYNONYMS = {
    "type 2 diabetes":["Type 2 Diabetes Mellitus","T2DM"],
    "parkinson":["Parkinson Disease","Parkinson's Disease"],
    "alzheimer":["Alzheimer Disease"],
    "breast cancer":["breast neoplasm","breast carcinoma"],
    "lung cancer":["non-small cell lung cancer","NSCLC"],
    "depression":["major depressive disorder","MDD"],
    "heart failure":["congestive heart failure","CHF"],
    "multiple sclerosis":["MS","relapsing remitting MS"],
    "hypertension":["high blood pressure","HTN"],
}
def get_terms(condition):
    for k,v in SYNONYMS.items():
        if k in condition.lower(): return [condition]+v
    return [condition]

# ── ClinicalTrials.gov ────────────────────────────────────────────────────────
CTGOV = "https://clinicaltrials.gov/api/v2/studies"

def parse_study(s, user_coords):
    proto = s.get("protocolSection",{})
    id_mod = proto.get("identificationModule",{})
    desc = proto.get("descriptionModule",{})
    elig = proto.get("eligibilityModule",{})
    cl = proto.get("contactsLocationsModule",{})
    design = proto.get("designModule",{})
    sponsors = proto.get("sponsorCollaboratorsModule",{})
    locs = cl.get("locations",[])

    us_locs = [l for l in locs if l.get("country","").strip().lower() in ("united states","us","usa")]
    has_us = bool(us_locs)
    distance_mi = None
    if user_coords and us_locs:
        for loc in us_locs:
            gp = loc.get("geoPoint",{})
            if gp.get("lat") and gp.get("lon"):
                d = haversine(user_coords[0], user_coords[1], gp["lat"], gp["lon"])
                if distance_mi is None or d < distance_mi: distance_mi = d

    priority = sorted(us_locs, key=lambda l: haversine(user_coords[0], user_coords[1],
        l.get("geoPoint",{}).get("lat",0), l.get("geoPoint",{}).get("lon",0))
        if user_coords and l.get("geoPoint",{}).get("lat") else 99999) if us_locs else locs

    loc_parts, seen = [], set()
    for loc in priority:
        city = loc.get("city",""); state = loc.get("state","")
        key = f"{city},{state}"
        if key not in seen and (city or state):
            seen.add(key)
            loc_parts.append(", ".join(filter(None,[city,state])))
        if len(loc_parts) >= 2: break

    # Abbreviate state names
    state_map = {"California":"CA","Texas":"TX","New York":"NY","Florida":"FL","Illinois":"IL",
        "Pennsylvania":"PA","Ohio":"OH","Georgia":"GA","North Carolina":"NC","Michigan":"MI",
        "Washington":"WA","Arizona":"AZ","Massachusetts":"MA","Colorado":"CO","Oregon":"OR",
        "Nevada":"NV","Minnesota":"MN","Utah":"UT","Tennessee":"TN","Wisconsin":"WI",
        "Missouri":"MO","Virginia":"VA","Indiana":"IN","Louisiana":"LA","Kentucky":"KY",
        "Alabama":"AL","South Carolina":"SC","Oklahoma":"OK","Arkansas":"AR","Iowa":"IA",
        "Kansas":"KS","New Mexico":"NM","Nebraska":"NE","West Virginia":"WV","Idaho":"ID",
        "Montana":"MT","South Dakota":"SD","North Dakota":"ND","Wyoming":"WY","New Hampshire":"NH",
        "Maine":"ME","Vermont":"VT","Rhode Island":"RI","Connecticut":"CT","Delaware":"DE",
        "New Jersey":"NJ","Maryland":"MD","Mississippi":"MS","Hawaii":"HI","Alaska":"AK",
    }
    loc_str = " | ".join(loc_parts)
    for full, abbr in state_map.items():
        loc_str = loc_str.replace(f", {full}", f", {abbr}")

    total = len(us_locs) if us_locs else len(locs)
    if total > 2: loc_str += f" (+{total-2} sites)"

    contacts = cl.get("centralContacts",[])
    phases_raw = design.get("phases",[])
    phase = "/".join(p.replace("PHASE","Phase ") for p in phases_raw) if phases_raw else "N/A"
    sponsor = sponsors.get("leadSponsor",{}).get("name","")
    if len(sponsor) > 50: sponsor = sponsor[:48]+"…"

    return {
        "nct_id": id_mod.get("nctId",""),
        "title": id_mod.get("briefTitle",""),
        "summary": desc.get("briefSummary","")[:200].strip(),
        "min_age": elig.get("minimumAge","N/A"),
        "max_age": elig.get("maximumAge","N/A"),
        "location": loc_str or ("International" if not has_us else "Sites not listed"),
        "has_us": has_us,
        "distance_mi": distance_mi,
        "phase": phase,
        "sponsor": sponsor,
        "contact_name": contacts[0].get("name","") if contacts else "",
        "contact_email": contacts[0].get("email","") if contacts else "",
        "url": f"https://clinicaltrials.gov/study/{id_mod.get('nctId','')}",
    }

def search_all(condition, user_age, user_coords):
    terms = get_terms(condition)
    seen, results = set(), []
    phases = []
    if user_coords:
        phases = [
            (f"distance({user_coords[0]},{user_coords[1]},100mi)", "100mi"),
            (f"distance({user_coords[0]},{user_coords[1]},400mi)", "400mi"),
            (f"distance({user_coords[0]},{user_coords[1]},1000mi)","1000mi"),
        ]
    phases.append((None, "nationwide"))

    for geo_filter, _ in phases:
        for term in terms[:2]:
            params = {"query.cond":term,"filter.overallStatus":"RECRUITING","pageSize":50,"format":"json"}
            if geo_filter: params["filter.geo"] = geo_filter
            try:
                r = httpx.get(CTGOV, params=params, timeout=20)
                r.raise_for_status()
                for s in r.json().get("studies",[]):
                    nct = s.get("protocolSection",{}).get("identificationModule",{}).get("nctId","")
                    if nct and nct not in seen:
                        seen.add(nct)
                        parsed = parse_study(s, user_coords)
                        if age_ok(parsed, user_age):
                            results.append(parsed)
            except Exception: pass
        us_eligible = [t for t in results if t["has_us"]]
        if geo_filter and len(us_eligible) >= 10: break

    results.sort(key=lambda t: t["distance_mi"] if t["distance_mi"] is not None else 999999)
    return results

# ── Handler ───────────────────────────────────────────────────────────────────
@protocol.on_message(DiscoveryRequest)
async def handle_discovery_request(ctx: Context, sender: str, msg: DiscoveryRequest):
    ctx.logger.info(f"Discovery request: {msg.condition} | age={msg.age} | loc={msg.location}")
    try:
        user_age    = int(msg.age) if msg.age.isdigit() else None
        user_coords = geocode(msg.location)
        trials      = search_all(msg.condition, user_age, user_coords)
        trials_json = json.dumps(trials)
    except Exception:
        ctx.logger.exception("Discovery search failed")
        trials_json = "[]"
        trials      = []

    await ctx.send(sender, DiscoveryResponse(
        session_id=msg.session_id,
        trials_json=trials_json,
        total_found=len(trials),
    ))

agent.include(protocol)

if __name__ == "__main__":
    print(f"\n✅ Discovery Agent address: {agent.address}\n")
    print("   → Copy this address into config.py as DISCOVERY_AGENT_ADDRESS\n")
    agent.run()
