import json, re, urllib.request, sys

# Greenhouse boards to scan (well-known tech/data companies that use Greenhouse)
boards = [
  "figma","brex","ethoslife","datadog","airtable","notion","intercom",
  "launchdarkly","sentry","snyk","hashicorp","confluent","mongodb","elastic",
  "auth0","twilio","databricks","snowflake","cloudera","conduit","ramp",
  "mercury","navan","gusto","ramp","plaid","wise","revolut","klarna",
  "shopify","canva","spotify","vercel","stripe","plaid","coinbase","kraken",
  "databricks","databricks","airtable","asana","slack","zoom","hubspot",
  "salesforce","workday","sap","oracle","servicenow","atlassian","jira",
  "linear","supabase","prisma","drift","drift","intercom","front","kustomer",
]
# dedupe preserve order
seen=set(); boards=[b for b in boards if not (b in seen or seen.add(b))]

applied_ids = {"8433546002","6130865004"}  # Brex, Figma already done

# senior title keywords + data/ai domain keywords
senior = re.compile(r"\b(director|vp|vice president|s\W?vp|head of|chief|cdo|principal)\b", re.I)
domain = re.compile(r"\b(data|analytics|analytic|machine learning|ml|ai|artificial intelligence|data science|data platform|data engineering|data infra|analytics|insight|decision)\b", re.I)
exclude = re.compile(r"\b(security|legal|finance|marketing|design|sales|support|customer success|people|hr|recruiting|devops|sre|platform engineering|web development|frontend|backend|full.?stack|mobile|ios|android|qa|testing|pm|product manager|engineering manager)\b", re.I)

results = {}
for b in boards:
    url = f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs?content=false"
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        continue
    for j in data.get("jobs", []):
        title = j.get("title","")
        loc = (j.get("location") or {}).get("name","")
        # must be US/remote, senior, data/ai domain, not an excluded area
        if not senior.search(title): continue
        if not domain.search(title): continue
        if exclude.search(title): continue
        jid = str(j.get("id"))
        if jid in applied_ids: continue
        if not re.search(r"\b(united states|remote|usa|chicago|il)\b", loc, re.I):
            # keep US roles; remote often says "United States"
            if "united states" not in loc.lower(): continue
        results[jid] = {
            "title": title,
            "board": b,
            "location": loc,
            "url": j.get("absolute_url") or f"https://boards.greenhouse.io/{b}/jobs/{jid}",
            "updated": j.get("updated_at","")[:10],
        }

# sort: most senior + data/ai
print(f"=== {len(results)} candidate senior data/AI roles ===")
for jid, r in sorted(results.items(), key=lambda x: x[1]["updated"], reverse=True):
    print(f"[{r['board']}] {r['title']} — {r['location']} ({r['updated']})\n   {r['url']}")
