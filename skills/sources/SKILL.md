---
name: ed-sources
description: "Unified access to external and internal sources. Search, routing, tradecraft. Triggers on: sources, onde acho, where is, como acessar, buscar, search, sources, tradecraft."
user-invocable: true
---

# /ed-sources — Unified Access to External and Internal Sources

**RULE: For external searches, ALWAYS use `edge-sources` (executable script) instead of WebSearch directly.** Agents and subagents call via Bash. WebSearch only as a complement when edge-sources doesn't cover.

Centralized layer for accessing the external world. Like `/ed-context` is for internal status, `/ed-sources` is for the outside world — X, Web, ArXiv, GitHub, backend.

## Executable Script: edge-sources

```bash
edge-sources "topic"                          # default: research
edge-sources "topic" --intent strategy      # routing by intent
edge-sources "topic" --sources x,hn,arxiv     # override sources
edge-sources --front-page                     # headlines (heartbeat)
edge-sources "topic" --json                   # JSON output
```

The script runs sources in parallel (X, HN, ArXiv, Semantic Scholar, Reddit, GitHub, HF Papers), filters by signal, and returns structured markdown. Code: `~/edge/tools/edge-sources`.

Any skill calls `/ed-sources` with an intent and topic. `/ed-sources` runs edge-sources, adds LLM curation, and returns.

---

## Usage

```
/ed-sources [intent] [topic]
```

**Available intents:**

| Intent | Description | Example |
|--------|-------------|---------|
| `research` | Directed deep dive on a topic | `/ed-sources research "DSPy vs SPL"` |
| `discovery` | Free exploration, find new things | `/ed-sources discovery "AI agents"` |
| `leisure` | Creative inspiration | `/ed-sources leisure "entropy information theory"` |
| `strategy` | Trends and strategic signals | `/ed-sources strategy "multi-agent production"` |
| `heartbeat` | Lightweight headline scan | `/ed-sources heartbeat` |
| `reflection` | Problem-oriented search | `/ed-sources reflection "how to reduce hallucination in RAG"` |
| `planner` | Implementation and best practices | `/ed-sources planner "eval framework LLM"` |
| `execute` | Gotchas and production patterns | `/ed-sources execute "circuit breaker python"` |
| `report` | Comprehensive search for report | `/ed-sources report "prompt optimization"` |

When called without intent, infer from the context of the calling skill.

---

## Source Registry

### 1. X (Twitter)

- **What it provides:** Practitioner insights, emerging trends, real-world experiences, what the traditional web hasn't indexed yet
- **Access:** tweepy (API v2)
- **Credentials:** `~/edge/secrets/x-api.env`
- **Cost:** Pay-per-use (~$0.02-0.05/search, ~$0.005/read, ~$0.01/profile)
- **Rate limits:** 60 searches/15min, 15 timeline/15min, 300 user lookups/15min
- **Username:** `@edge_of_chaos__` | **User ID:** `2025643124668993536`

**Quick command (PREFERRED):**

```bash
edge-x "topic"                       # smart multi-strategy search
edge-x "topic" --from karpathy swyx  # search specific accounts
edge-x "topic" --min-followers 500   # more aggressive filter
edge-x "topic" --json                # JSON output for processing
```

`edge-x` does multi-strategy search (broad + practitioner terms + trusted accounts), filters by quality (followers >= 100 OR engagement >= 2), and sorts by signal.

**Hardcoded trusted accounts:** karpathy, swyx, simonw, jxnlco, hwchase17, AnthropicAI, OpenAI, alexalbert__, DrJimFan, eugeneyan, shreyar, jerryjliu0, GregKamradt and others. Editable in `~/edge/tools/edge-x`.

**Query operators:** `-is:retweet`, `lang:en`, `has:links`, `has:media`
**DO NOT use:** `min_faves`, `min_retweets`, `sample:` (require Pro tier $5000/mo)

---

### 2. Web (WebSearch + WebFetch)

- **What it provides:** Papers, docs, tutorials, benchmarks, blog posts, Stack Overflow
- **Access:** Built-in tools (WebSearch, WebFetch)
- **Credentials:** none
- **Cost:** free
- **Limitation:** WebFetch fails on authenticated URLs (Google Docs, Confluence, Jira)

**How to use:**
- `WebSearch` for broad queries
- `WebFetch` to read specific URLs (papers, docs, blog posts)

---

### 3. ArXiv

- **What it provides:** Academic papers, cutting-edge research, pre-prints
- **Access:** REST API (free, no auth)
- **Credentials:** none
- **Cost:** free
- **Relevant areas:** cs.CL (Computation and Language), cs.IR (Information Retrieval), cs.AI, cs.SE (Software Engineering)

**Helper — ArXiv Search:**

```bash
python3 << 'PYEOF'
import urllib.request, urllib.parse, xml.etree.ElementTree as ET

QUERY = 'all:"TOPIC"'  # or cat:cs.CL AND all:"TOPIC"
url = f"http://export.arxiv.org/api/query?search_query={urllib.parse.quote(QUERY)}&start=0&max_results=10&sortBy=submittedDate&sortOrder=descending"

resp = urllib.request.urlopen(url)
root = ET.fromstring(resp.read())
ns = {'a': 'http://www.w3.org/2005/Atom'}

for entry in root.findall('a:entry', ns):
    title = entry.find('a:title', ns).text.strip().replace('\n', ' ')
    published = entry.find('a:published', ns).text[:10]
    summary = entry.find('a:summary', ns).text.strip()[:200].replace('\n', ' ')
    link = entry.find('a:id', ns).text
    authors = [a.find('a:name', ns).text for a in entry.findall('a:author', ns)]
    print(f"\n[{published}] {title}")
    print(f"  Authors: {', '.join(authors[:3])}{'...' if len(authors) > 3 else ''}")
    print(f"  {summary}...")
    print(f"  URL: {link}")
PYEOF
```

---

### 4. Hacker News

- **What it provides:** Tech community sentiment, launches, deep technical discussions, practitioner insights in comments
- **Access:** Algolia API + Firebase API (free, no auth)
- **Credentials:** none
- **Cost:** free

**Quick command (PREFERRED):**

```bash
edge-hn "topic"                       # search stories by relevance
edge-hn "topic" --comments            # search comments too (insights buried in threads)
edge-hn "topic" --min-points 50       # only high-signal stories
edge-hn "topic" --days 7              # last 7 days
edge-hn "topic" --front-page          # also show current front page
edge-hn "topic" --json                # JSON output for processing
```

`edge-hn` searches via Algolia (stories + comments), filters by points and date, sorts by signal (points + comments), and shows HN URLs and original article URLs. Comments are cleaned of HTML and truncated.

**Standalone front page:** `edge-hn --front-page` (no topic — just current top 10)

---

### 5. GitHub

- **What it provides:** Project releases, issues, code search, trending repos
- **Access:** `gh` CLI (authenticated)
- **Credentials:** keyring (configured via `gh auth login`)
- **Cost:** free

**Useful operations:**

```bash
# Recent releases of a project
gh release list --repo stanfordnlp/dspy --limit 5

# Search repos by topic
gh search repos "prompt evaluation" --sort stars --limit 10

# Search code
gh search code "RAG pipeline" --language python --limit 10

# Issues/PRs of a repo
gh issue list --repo stanfordnlp/dspy --state open --sort updated --limit 10

# Trending (via web)
# WebFetch https://github.com/trending/python?since=weekly
```

---

### 6. Database / Backend (EXAMPLE — customize for your project)

- **What it provides:** Platform usage data — sessions, messages, documents, user feedback, statistics
- **Access:** SSH to VM (`$YOUR_VM`) + admin scripts
- **Credentials:** SSH key configured
- **Cost:** free
- **Prerequisites:** Backend running, admin scripts deployed

**Access example (adapt to your project):**

```bash
ssh $YOUR_VM 'python3 ~/admin/query.py overview' 2>/dev/null || echo "VM_UNREACHABLE"
```

**Output:** JSON with anonymized fields when necessary. **NEVER** access the database directly — always via admin scripts on the VM. PII never transits through the network.

---

### 9. Reddit (JSON API)

- **What it provides:** Deep technical discussions, real-world experiences, practitioner debates
- **Access:** Public JSON API (append `.json` to any Reddit URL)
- **Credentials:** none
- **Cost:** free
- **Relevant subreddits:** r/MachineLearning, r/LocalLLaMA, r/ClaudeAI, r/LangChain, r/ArtificialIntelligence

**Helper — Reddit Search:**

```bash
python3 << 'PYEOF'
import urllib.request, json, urllib.parse

SUBREDDIT = 'MachineLearning'  # or LocalLLaMA, ClaudeAI, LangChain
QUERY = 'TOPIC'
url = f"https://www.reddit.com/r/{SUBREDDIT}/search.json?q={urllib.parse.quote(QUERY)}&restrict_sr=1&sort=relevance&t=month&limit=10"

req = urllib.request.Request(url, headers={'User-Agent': 'edge-of-chaos/1.0'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

for post in data.get('data', {}).get('children', []):
    d = post['data']
    score = d.get('score', 0)
    comments = d.get('num_comments', 0)
    title = d.get('title', '')[:120]
    url = f"https://www.reddit.com{d.get('permalink', '')}"
    print(f"\n[{score}pts {comments}c] {title}")
    print(f"  URL: {url}")
PYEOF
```

**Variant — Hot posts (no query):**
```bash
# Replace search.json with hot.json:
# https://www.reddit.com/r/MachineLearning/hot.json?limit=10
```

---

### 10. Semantic Scholar

- **What it provides:** Papers with citation graph, influence, related areas, semantic search
- **Access:** Free REST API (api.semanticscholar.org)
- **Credentials:** none (generous rate limit: 100 req/5min without key)
- **Cost:** free

**Helper — Semantic Scholar Search:**

```bash
python3 << 'PYEOF'
import urllib.request, json, urllib.parse

QUERY = 'TOPIC'
fields = 'title,year,citationCount,influentialCitationCount,authors,url,tldr'
url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(QUERY)}&limit=10&fields={fields}"

req = urllib.request.Request(url, headers={'User-Agent': 'edge-of-chaos/1.0'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

for paper in data.get('data', []):
    title = paper.get('title', '')
    year = paper.get('year', '?')
    cites = paper.get('citationCount', 0)
    influential = paper.get('influentialCitationCount', 0)
    authors = ', '.join(a['name'] for a in (paper.get('authors') or [])[:3])
    tldr = (paper.get('tldr') or {}).get('text', '')[:150]
    url = paper.get('url', '')
    print(f"\n[{year}, {cites} cites, {influential} influential] {title}")
    print(f"  Authors: {authors}")
    if tldr: print(f"  TL;DR: {tldr}")
    print(f"  URL: {url}")
PYEOF
```

**Advantage over ArXiv:** semantic search (not just keyword), citation graph, AI-generated `tldr` field, `influentialCitationCount` filters papers that actually impacted the field.

---

### 11. Product Hunt

- **What it provides:** New tools, market trends, what builders are launching
- **Access:** WebFetch (API requires OAuth — use lightweight scraping)
- **Credentials:** none
- **Cost:** free

**How to use:**

```bash
# Via WebSearch (more reliable than direct scraping)
# WebSearch "site:producthunt.com [TOPIC] 2026"
```

Or WebFetch on specific topic pages. No helper script because the public API was deprecated — WebSearch is sufficient to find relevant launches.

---

### 12. Primary Blogs (Anthropic, OpenAI, Google DeepMind)

- **What it provides:** Primary research sources, launches, API changes, strategic vision
- **Access:** WebFetch on blog URLs
- **Credentials:** none
- **Cost:** free
- **URLs:**
  - Anthropic: `https://www.anthropic.com/research`
  - OpenAI: `https://openai.com/ed-blog`
  - Google DeepMind: `https://deepmind.google/discover/blog/`

**How to use:**

```bash
# Via WebSearch for recent news
# WebSearch "site:anthropic.com/research [TOPIC]"
# WebSearch "site:openai.com/ed-blog [TOPIC]"

# Or WebFetch directly on the blog for headline scanning
# WebFetch https://www.anthropic.com/research "list titles and dates of last 10 posts"
```

**When to consult:** research (primary sources), strategy (signals of change), heartbeat (releases).

---

### 13. Papers With Code

- **What it provides:** Papers with implementation, benchmarks, state-of-the-art by task, trending papers
- **Access:** Free REST API (paperswithcode.com/api/v1)
- **Credentials:** none
- **Cost:** free

**Helper — Papers With Code Search:**

```bash
python3 << 'PYEOF'
import urllib.request, json, urllib.parse

QUERY = 'TOPIC'
url = f"https://paperswithcode.com/api/v1/search/?q={urllib.parse.quote(QUERY)}"

req = urllib.request.Request(url, headers={'User-Agent': 'edge-of-chaos/1.0'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())

for item in data.get('results', [])[:10]:
    title = item.get('paper', {}).get('title', '') if item.get('paper') else item.get('title', '')
    url = item.get('paper', {}).get('url_abs', '') if item.get('paper') else ''
    repo = item.get('repository', {}).get('url', '') if item.get('repository') else ''
    stars = item.get('repository', {}).get('stars', 0) if item.get('repository') else 0
    print(f"\n{title}")
    if url: print(f"  Paper: {url}")
    if repo: print(f"  Code: {repo} ({stars} stars)")
PYEOF
```

**Variant — Trending:**
```bash
# WebFetch https://paperswithcode.com/trending "list the 10 trending papers with links and stars"
```

**Advantage over ArXiv/Semantic Scholar:** each paper has a direct link to code, comparative benchmarks, and ranking by task. Ideal for `/ed-research` and `/ed-discovery` when needing papers WITH implementation.

---

## Routing and Preferences

Routing by intent is hardcoded in `edge-sources` (ROUTING variable). Each intent maps to primary and secondary sources. The script also adds an automatic wildcard (random source outside the routing, for serendipity).

---

## Curation Criteria (unified)

### Quality signals (apply to ALL sources)

| Signal | What it indicates | Weight |
|--------|-------------------|--------|
| Builder sharing real experience | Practical tip, tested in production | HIGH |
| Thread/discussion with many replies | Multiple perspectives, real debate | HIGH |
| Concrete data (benchmark, metric, number) | Evidence, not opinion | HIGH |
| Emerging tool/concept | Traditional web hasn't indexed yet | MEDIUM |
| Counter-intuitive insight | Challenges assumptions — worth investigating | MEDIUM |
| Paper with available code | Reproducible, not just theory | MEDIUM |
| Recent release of tracked project | May change trade-offs | MEDIUM |

### Filters (discard)

- Engagement bait, hot takes without substance
- Reposts without added value
- Generic content ("10 tips for better prompts")
- Papers without empirical results (when seeking practical solutions)
- Reheated news from press releases

---

## Protocol

### Step 1: Run edge-sources (MANDATORY)

```bash
edge-sources "topic" --intent [intent]
```

The script already handles: routing by intent, parallel execution of all scriptable sources (X, HN, ArXiv, Semantic Scholar, Reddit, GitHub, HF Papers), automatic wildcard, and structured markdown output.

**If called by another skill:** infer intent from the calling skill's name, topic from the work in progress.

### Step 2: Complement with WebSearch (when necessary)

edge-sources covers APIs but **does not cover WebSearch/WebFetch** (Claude tools, not scriptable). Use WebSearch for:
- Official documentation (Anthropic, OpenAI, Google)
- Specific blogs/articles
- Product Hunt
- Any URL that needs direct fetch

**DO NOT use WebSearch for X or HN** — edge-sources already uses the real APIs (tweepy, Algolia).

### Step 3: Curate results (LLM)

Apply curation criteria to the edge-sources output:
1. Passes quality criteria? If not, discard.
2. Is it relevant to the topic? If tangential, mark as "tangential but interesting".
3. Reliable source? Builder > commenter. Paper > blog. Data > opinion.

### Step 4: Synthesize and return

Organize by relevance (not by source). Return format:

```markdown
## External Sources — [topic]

### High Relevance Insights
[Best results, regardless of source]
- **[source]** @author/title: [insight in 1-2 lines]
  URL: [link]

### Complementary
[Good results but not essential]

### Tangential (for future reference)
[Found but not directly relevant — may feed /ed-discovery]

### Sources Consulted
- X: N queries, N useful results (~$X.XX)
- Web: N queries
- ArXiv: N papers found
- [etc.]
```

---

## Algorithmic Curation (AUTOMATIC)

When searching X, `/ed-sources` automatically engages with quality content to train the feed algorithm. The goal: see more of what matters, less noise.

### Auto-engagement (during any X Search)

After curating results, for each tweet that passed quality criteria:

```python
# Auto-like relevant content (trains the algorithm)
for tweet_id in quality_tweet_ids:
    try:
        client.like(tweet_id)
    except Exception:
        pass  # rate limit or already liked — continue
```

**Criteria for auto-like:** tweet that meets 2+ quality signals from the curation table (builder + concrete data, insight + high reply_count, etc.). Don't like everything — only what genuinely improves the feed.

**Criteria for auto-bookmark:** exceptional tweet that deserves re-reading. Save via API if available.

### Engagement weights (X algorithm reference)

| Action | Algorithm weight | When to use |
|--------|-----------------|-------------|
| Bookmark | 10x | Exceptional tweet, future reference |
| Like | 1x | Baseline — every quality tweet |

**Rule:** Like and bookmark are automatic (low cost, high impact on algorithm). Reply, retweet, and follow are NOT allowed (restriction since 2026-03-03).

### Engagement output

At the end of results, report:

```markdown
### Algorithmic Curation
- Auto-liked: N tweets (URLs listed)
- Auto-bookmarked: N tweets
```

---

## Tradecraft — What Works for What (absorbed from /nexus)

Tradecraft is accumulated knowledge about HOW to search, not WHAT to search. Lives in `~/edge/autonomy/tradecraft.md` and grows with use.

### File: `~/edge/autonomy/tradecraft.md`

Structure:

```markdown
# Tradecraft — Search Heuristics

## By Information Type

| I need... | Best source | Query that works | What does NOT work |
|-----------|------------|------------------|--------------------|
| Recent paper with code | Papers With Code > ArXiv | search by task name | search by author |
| Real production experience | X (practitioners) > HN comments | edge-x "topic" --from [builders] | generic queries |
| Deep technical debate | Reddit r/MachineLearning > HN | subreddit search, sort by top | front page (too broad) |
| State of the art by task | Semantic Scholar | query with task name, sort by citations | overly specific queries |
| Emerging tool | HN Show > GitHub trending | edge-hn "topic" --min-points 20 | search by name (don't know the name yet) |
| Official documentation | WebFetch directly on URL | site:docs.anthropic.com | generic WebSearch |

## Surprise Log (append-only)

When a source surprises (found something unexpected, failed where it should work, or an unusual query yielded results), record:

- **[YYYY-MM-DD]** [source] query "[query]": [what was surprising]. Implication: [new heuristic].
```

### Tradecraft Protocol

1. **At the end of each search:** If a source surprised (positively or negatively), append to the surprise log
2. **During /ed-reflection:** Consolidate surprises into heuristics in the main table
3. **Any skill can consult:** `cat ~/edge/autonomy/tradecraft.md` before deciding query/source

### "Where do I find X?" (internal routing)

`/ed-sources` also answers "where do I find X?" for INTERNAL sources — not just external:

| Type | Where | How to access |
|------|-------|---------------|
| Persistent memories | `~/.claude/projects/$MEMORY_PROJECT_DIR/memory/*.md` | Read directly |
| Blog entries | `~/edge/blog/entries/*.md` or `http://localhost:8766/blog/entries/` (JSON) | Read / curl |
| HTML reports | `~/edge/reports/*.html` | Read / browser |
| Loose notes | `~/edge/notes/*.md` | Read / grep |
| Investigation threads | `~/edge/threads/*.md` | Read (YAML frontmatter + markdown) |
| Previous sessions | `~/.claude/projects/$MEMORY_PROJECT_DIR/*.jsonl` | grep (heavy, last resort) |
| Semantic search | `edge-search "query"` | Hybrid FTS + embeddings search |
| Work projects | `~/work/CLAUDE.md` (project map) | Read |
| Autonomy | `~/edge/autonomy/*.md` | Read |
| Heartbeat logs | `~/edge/logs/heartbeat-YYYY-MM-DD.log` | Read / grep |
| Consult logs | `~/edge/logs/consult/*.json` | Read |
| Events | `~/edge/logs/events.jsonl` | grep |

When a skill asks "where do I find data about X?", `/ed-sources` first checks if the answer is internal (routing table above) before searching externally.

---

## Notes

- `/ed-sources` READS and ENGAGES automatically (like/bookmark) to curate the algorithm. Does NOT post, comment, retweet, or follow (restriction since 2026-03-03)
- Database/Backend (if configured) requires working SSH — if it fails, continue without. Not critical except for intent `strategy`
- X cost is pay-per-use — check balance on Developer Console periodically
- Run queries in parallel when possible to minimize time
- Tradecraft (`~/edge/autonomy/tradecraft.md`) grows with use — append surprises, consolidate during reflection
- /nexus was absorbed here (2026-03-11). Routing + tradecraft + "where do I find?" now live in /ed-sources
