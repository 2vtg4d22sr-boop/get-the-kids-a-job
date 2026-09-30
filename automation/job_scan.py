import json, os, re, sys, urllib.request, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
from openai import OpenAI

SUPABASE_URL=os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY=os.environ["SUPABASE_SERVICE_ROLE_KEY"]
TODAY=datetime.now(ZoneInfo("America/Chicago")).date().isoformat()

PROMPT=r"""
You are the production job scanner for the McGovern family Job Hub. Search the CURRENT public web thoroughly, open/verify postings where possible, and return ONLY qualified, currently active jobs. Accuracy is more important than quantity. It is acceptable to return zero jobs.

BAILEY:
- Westminster, Colorado centered, roughly <=45 minute commute; hybrid/remote preferred, onsite okay.
- Full-time permanent. Base target >= $65,000; do not count bonus.
- Primary: Operations. Secondary: Business Operations, Project/Program Coordination, Commercial/Sales Operations, Client/Account Operations, corporate/property/retail operations, selective non-creative Marketing Operations/Admin.
- Exclude commission, cold calling, product-demo sales, call centers, pure sales, temp/contract, ordinary store retail.
- Background: Marketing & Management degree; 4+ years retail leadership/operations; $3M-$5M operations, staffing/scheduling, onboarding/training, KPI/reporting, brand execution, promotions/events, inventory/material control, customer escalation, cross-functional coordination, Microsoft Office/Google.
- Do NOT invent specialized corporate/domain experience or professional content creation.
- Must credibly satisfy about 70-80% of meaningful requirements. Unsupported substantive must-have => omit. Usually omit >2-3 years specialized experience he lacks.
- Stretch only when missing one meaningful qualification and otherwise strong.

MORGAN:
- Greater St. Louis + Metro East within roughly 45 minutes of Collinsville, IL; hybrid/remote US included.
- Full-time stable roles. Prefer >=$50K and prioritize $55K-$70K. $47K-$50K only unusually strong. Salary-undisclosed may be retained if strong.
- Marketing/communications, social/content, multimedia/video, production coordination, publishing/editorial, brand/creative coordination, event marketing, film/entertainment production.
- Background: BA English, Cinema minor; Wise Pod co-producer/social media manager; short-form editing, social calendar, analytics, graphics; production internship; arts/entertainment editor; film festival design; Premiere Pro, Photoshop basic, DaVinci Resolve, Canva, O365/Google.
- No InDesign/Illustrator. Do not convert projects/internships into years of specialized full-time experience.
- Omit roles requiring 2+ years specialized experience plus critical unsupported tools/domain expertise or senior management.

FOR EVERY RETAINED JOB:
- Verify currentness using employer-hosted careers/posting whenever possible.
- company_apply_url must be exact employer-hosted job/application URL or null.
- job_site_url must be exact third-party posting or null.
- company_careers_url must be employer careers/reference page or null.
- Research a LinkedIn follow-up person in this order: actual poster/hiring manager, recruiter/TA, department leader, useful peer. Never guess. If none substantiated, use "No verified contact found" and null linkedin_url.
- Preserve factual distinctions between required and preferred qualifications.
- Use fit_level Strong Match / Match / Stretch and priority High / Medium.
- Do not return SKIP jobs.
- Prefer a small number of high-confidence jobs over weak quantity.

Return strict JSON only, no markdown, with this shape:
{"jobs":[{...}]}
Each job object MUST contain ALL of these keys:
candidate,company,job_title,location,work_setting,employment_type,
base_salary_min,base_salary_max,salary_display,priority,fit_level,job_status,
posting_date,posting_freshness,high_level_job_info,why_candidate_fits,
hard_requirements,preferred_learnable_gaps,potential_concerns,
company_apply_url,job_site_url,company_careers_url,
linkedin_contact,contact_title,linkedin_url,why_this_contact,
contact_verification,linkedin_intro.
Use null only for genuinely unavailable dates/numbers/URLs. For unavailable descriptive/contact fields use explicit text such as "Not disclosed / verify" or "Not available — no verified contact found".
"""

def stable_key(j):
    candidate=j["candidate"].strip().upper()
    direct=(j.get("company_apply_url") or "").strip()
    if direct:
        return candidate+"|"+direct
    def norm(v):
        return re.sub(r"[^A-Z0-9]+"," ",(v or "").upper()).strip()
    return "|".join([candidate,norm(j["company"]),norm(j["job_title"]),norm(j["location"])])

def api(method,path,data=None,prefer=None):
    body=None if data is None else json.dumps(data).encode()
    headers={"apikey":SUPABASE_KEY,"Authorization":"Bearer "+SUPABASE_KEY}
    if body is not None: headers["Content-Type"]="application/json"
    if prefer: headers["Prefer"]=prefer
    req=urllib.request.Request(SUPABASE_URL+path,data=body,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=45) as r:
        raw=r.read().decode()
        return json.loads(raw) if raw else None

def clean_job(j):
    required=["candidate","company","job_title","location","work_setting","employment_type",
      "salary_display","priority","fit_level","job_status","high_level_job_info",
      "why_candidate_fits","hard_requirements","preferred_learnable_gaps","potential_concerns",
      "linkedin_contact","contact_title","why_this_contact","contact_verification","linkedin_intro"]
    missing=[k for k in required if not j.get(k)]
    if missing: raise ValueError(f"Unexplained blank fields for {j.get('company')}: {missing}")
    if j["candidate"] not in ("Bailey","Morgan"): raise ValueError("Bad candidate")
    for k in ("company_apply_url","job_site_url","company_careers_url","linkedin_url"):
        if j.get(k) is not None and not str(j[k]).startswith("https://"):
            raise ValueError(f"Malformed URL {k}: {j[k]}")
    j["job_key"]=stable_key(j)
    j["last_verified"]=TODAY
    j["source_scan_date"]=TODAY
    return j

client=OpenAI()
response=client.responses.create(
    model="gpt-5",
    tools=[{"type":"web_search","search_context_size":"high"}],
    input=PROMPT,
    max_tool_calls=24,
)
text=response.output_text.strip()
if text.startswith("~~~") or text.startswith("```"):
    text=re.sub(r"^```(?:json)?\s*|\s*```$","",text,flags=re.I|re.S)
payload=json.loads(text)
jobs=[clean_job(x) for x in payload.get("jobs",[])]
print(f"Validated {len(jobs)} retained jobs for {TODAY}")

for j in jobs:
    key=j["job_key"]
    q=urllib.parse.quote(key,safe="")
    existing=api("GET",f'/rest/v1/GETTHEKIDSAJOB?job_key=eq.{q}&select=id,date_found,interested,applied,interview,offer,date_applied,application_status,notes')
    protected={"interested","applied","interview","offer","date_applied","application_status","notes"}
    scanner={k:v for k,v in j.items() if k not in protected}
    if existing:
        scanner.pop("date_found",None)
        api("PATCH",f'/rest/v1/GETTHEKIDSAJOB?job_key=eq.{q}',scanner,prefer="return=minimal")
        print("UPDATED",j["candidate"],j["company"],j["job_title"])
    else:
        scanner["date_found"]=TODAY
        api("POST",'/rest/v1/GETTHEKIDSAJOB',scanner,prefer="return=minimal")
        print("INSERTED",j["candidate"],j["company"],j["job_title"])

# Post-sync QA: every current key must exist exactly once.
for j in jobs:
    q=urllib.parse.quote(j["job_key"],safe="")
    rows=api("GET",f'/rest/v1/GETTHEKIDSAJOB?job_key=eq.{q}&select=id,candidate,job_key,last_verified,source_scan_date')
    if len(rows)!=1 or rows[0]["candidate"]!=j["candidate"]:
        raise RuntimeError("Post-sync QA failed for "+j["job_key"])
print("FIELD VALIDATION AND POST-SYNC QA PASSED")
