# Example: Web Research Pipeline (Perplexity-style)

A two-agent system where a **parent agent** receives a research question and delegates live web search to a **researcher sub-agent** that has Brave Search and page-fetch MCP tools wired in. The parent synthesises the findings into a cited, structured answer.

**What this demonstrates:**
- Sub-agent pattern (Phase 5): parent calls `call_researcher` as a tool
- MCP integration: researcher uses Brave Search + URL fetch via MCP
- Multi-container Docker Compose: two independent agent instances
- Session ID propagation across agent boundaries

---

## Architecture

```
Client
  │
  ▼
Parent Agent  (host port 8080)
  │
  │  tool call: call_researcher("What are the latest LLM context window sizes?")
  ▼
Researcher Sub-agent  (host port 8001, internal port 8000)
  │
  ├── MCP: brave_web_search(query)  →  Brave Search API  →  10 results with URLs
  │
  └── MCP: fetch(url)  →  full page content for top result
  │
  ▼  returns: summarised findings with sources
Parent Agent
  │
  ▼  synthesises into structured answer with citations
Client
```

---

## Prerequisites

- [Brave Search API key](https://brave.com/search/api/) — free tier (2000 queries/month)
- Node.js + npm (for `npx @modelcontextprotocol/server-brave-search`) — **already included in the Dockerfile**
- Docker Compose

---

## Setup

### 1. Project layout

```
ai-agent-template/
  docker-compose.yml           # base: Langfuse + Qdrant
  docker-compose.research.yml  # overlay: parent + researcher containers
  docker-compose.demo.yml      # overlay: Gradio UI
  .env.parent                  # parent agent config
  .env.researcher              # researcher sub-agent config
  prompts/
    v1/system.md               # parent prompt
    researcher/system.md       # researcher-specific prompt
```

### 2. Researcher system prompt

Create `prompts/researcher/system.md`:

```markdown
You are a web research specialist. Your job is to report what the search results say — not what you think you know.

## Process
1. Call brave_web_search with an appropriate query.
2. Read the results carefully. If a result explicitly states a current fact (e.g. who holds an office, a price, a score), treat that as authoritative — even if it contradicts your training data.
3. If the answer is still unclear, call fetch on the most authoritative URL from the search results to read the full page.
4. Return a structured summary.

## CRITICAL RULE
Your training data has a knowledge cutoff. Search results are newer and more accurate. If a search result says X is the current holder of an office, report X — do NOT fall back to who you think held the office based on your training. Phrases like "speculative" or "future-dated" must NOT be applied to search results that describe the present.

## Output format
- Key facts and figures (with dates from the sources)
- Notable sources (title and URL)
- Any genuine conflicts between sources
```

> **Note:** `PromptManager` automatically prepends `Today's date is YYYY-MM-DD.` to every prompt at runtime, which prevents the model from treating recent search results as "future" events relative to its training cutoff.

### 3. Researcher config (`.env.researcher`)

```env
TENANT_ID=research-system
ENVIRONMENT=production

LLM__PROVIDER=openrouter          # or anthropic / openai
LLM__MODEL=google/gemma-4-26b-a4b-it
LLM__API_KEY=sk-or-...

LANGFUSE__ENABLED=true
LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=http://langfuse:3000

AGENT__NAME=researcher
AGENT__PROMPT_VERSION=researcher  # maps to prompts/researcher/system.md
AGENT__MAX_ITERATIONS=5

# Brave Search MCP (search) + fetch MCP (read full pages)
MCP_SERVERS='[{
  "name": "brave-search",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-brave-search"],
  "env": {"BRAVE_API_KEY": "BSA..."}
},{
  "name": "fetch",
  "transport": "stdio",
  "command": "uv",
  "args": ["tool", "run", "mcp-server-fetch"]
}]'

# Lock researcher to these two tools only
# IMPORTANT: the Brave MCP tool is named brave_web_search, not brave_search
AGENT__ALLOWED_TOOLS='["brave_web_search", "fetch"]'
```

> **Why two MCP tools?** Brave Search returns snippets and URLs but does not fetch full page content. Cached snippets are often stale. The `fetch` tool (`mcp-server-fetch`, a Python package bundled via `uv tool run`) reads the actual page, giving the researcher access to current content.

> **Alternative search providers:** Tavily MCP (`@tavily/mcp-server`) and Exa MCP (`@exa-ai/mcp-server-exa`) work as drop-in replacements — same config shape, different `command`/`args` and API key.

### 4. Parent config (`.env.parent`)

```env
TENANT_ID=research-system
ENVIRONMENT=production

LLM__PROVIDER=openrouter
LLM__MODEL=google/gemma-4-26b-a4b-it
LLM__API_KEY=sk-or-...

LANGFUSE__ENABLED=true
LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=http://langfuse:3000

AGENT__NAME=research-orchestrator
AGENT__PROMPT_VERSION=v1
AGENT__MAX_ITERATIONS=5

# Register the researcher as a callable sub-agent
# IMPORTANT: URL must use the container's internal port (8000), not the host-mapped port (8001)
AGENT__SUB_AGENTS='[{
  "name": "researcher",
  "url": "http://researcher:8000",
  "description": "Searches the live web for current information on any topic using Brave Search. Returns a structured summary of findings with sources. Use this whenever the question requires up-to-date information beyond your training data.",
  "timeout": 60.0
}]'
```

### 5. Docker Compose overlay (`docker-compose.research.yml`)

```yaml
networks:
  default:
    name: ai-agent-template_default
    external: true   # joins the network created by docker-compose.yml

services:
  researcher:
    build: .
    env_file: .env.researcher
    environment:
      MEMORY__QDRANT_URL: http://qdrant:6333
    ports:
      - "8001:8000"   # host 8001 → container 8000
    command: uv run uvicorn api.main:app --host 0.0.0.0 --port 8000

  parent:
    build: .
    env_file: .env.parent
    environment:
      MEMORY__QDRANT_URL: http://qdrant:6333
    ports:
      - "127.0.0.1:8080:8000"   # host 8080 → container 8000
    depends_on:
      - researcher
    command: uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

> **Network note:** The `external: true` network makes the research containers share the same Docker network as Langfuse and Qdrant started from `docker-compose.yml`, so `http://qdrant:6333` and `http://langfuse:3000` resolve correctly.

### 6. Start everything

```bash
# 1. Start infrastructure (Langfuse + Qdrant) from the base compose file.
#    Specify services explicitly to avoid starting the 'agent' service,
#    which requires a .env file you may not have yet.
docker compose up langfuse qdrant -d

# 2. Start parent + researcher agents
docker-compose -f docker-compose.research.yml up --build
```

---

## Querying

### Gradio demo UI (optional)

```bash
AGENT_URL=http://parent:8000 docker-compose \
  -f docker-compose.research.yml \
  -f docker-compose.demo.yml up --build
```

Open **http://localhost:7860**. In the Config sidebar set the Agent URL to `http://localhost:8080` (the parent's host-mapped port). The researcher sub-agent is called internally — you only interact with the parent.

> The demo UI is for development and showcasing only.

---

### curl

```bash
curl -X POST http://localhost:8080/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "research-system",
    "input": "What are the largest LLM context windows available today and which models offer them?"
  }'
```

**What happens internally:**

1. Parent agent reasons: this needs live data → calls `call_researcher` (forced on first iteration)
2. Researcher sub-agent calls `brave_web_search("largest LLM context windows 2025")`
3. Brave returns 10 results with URLs and snippets
4. Researcher calls `fetch(top_url)` to read full page content
5. Researcher synthesises findings, returns to parent
6. Parent formats a structured answer with source attribution

**Response**

```json
{
  "session_id": "a1b2c3...",
  "tenant_id": "research-system",
  "output": "As of mid-2025, the largest publicly available context windows are:\n\n**1M tokens**\n- Google Gemini 1.5 Pro\n\n**200K tokens**\n- Anthropic Claude 3.5\n\nSources: The Verge (Apr 2025), Anthropic blog.",
  "tool_calls": [
    {
      "tool_name": "call_researcher",
      "args": {"task": "What are the largest LLM context windows available today?"},
      "result": "Gemini 1.5 Pro leads with 1M tokens...",
      "success": true
    }
  ],
  "cost_usd": 0.0043,
  "trace_id": "lf-..."
}
```

### Streaming

```bash
curl -X POST http://localhost:8080/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "research-system",
    "input": "What are the most recent open-source LLM releases in the past month?"
  }' \
  --no-buffer
```

### From .NET (C#)

```csharp
var payload = new
{
    tenant_id = "research-system",
    input = "What are the latest developments in AI coding assistants?"
};

using var http = new HttpClient();
http.Timeout = TimeSpan.FromSeconds(120); // researcher may take time

var response = await http.PostAsJsonAsync("http://localhost:8080/v1/agent/run", payload);
var result = await response.Content.ReadFromJsonAsync<AgentResponse>();

Console.WriteLine(result?.Output);
Console.WriteLine($"Cost: ${result?.CostUsd:F4}");
```

---

## How sub-agent delegation works

The parent agent sees `call_researcher` as a standard OpenAI-format tool:

```json
{
  "type": "function",
  "function": {
    "name": "call_researcher",
    "description": "Searches the live web for current information...",
    "parameters": {
      "type": "object",
      "properties": {
        "task": {"type": "string", "description": "The task or question to delegate"}
      },
      "required": ["task"]
    }
  }
}
```

When the LLM calls `call_researcher`, the execute node:
1. Detects the `call_` prefix and routes to `AgentRegistry` instead of `MCPRegistry`
2. `SubAgentClient` sends a `POST /v1/agent/run` to `http://researcher:8000`
3. The session ID is scoped: `{parent_session_id}-researcher-{random8hex}`
4. The researcher's response text is returned to the parent as the tool result

**tool_choice behaviour:** On the first iteration the parent uses `tool_choice="required"` (it only has `call_*` tools, so it always delegates before answering from training data). The researcher uses `tool_choice={"type":"function","function":{"name":"brave_web_search"}}` on its first iteration, ensuring it always searches before synthesising.

The parent then reasons over the result and produces the final response. Both runs appear as separate traces in Langfuse, linked by the session ID prefix.

---

## Observability

Enable tracing by setting `LANGFUSE__ENABLED=true` in both env files (it defaults to `false`).

Each layer traces independently to Langfuse:

- **Parent trace**: shows the `call_researcher` tool call and the final synthesis
- **Researcher trace**: shows the `brave_web_search` and `fetch` MCP calls and results

Filter by session ID prefix to correlate both traces for a single user query.

---

## Extending the pipeline

**Add a writer sub-agent** that takes the researcher's raw findings and formats them into a polished report. Register it alongside the researcher:

```env
AGENT__SUB_AGENTS='[
  {
    "name": "researcher",
    "url": "http://researcher:8000",
    "description": "Searches the live web for current information."
  },
  {
    "name": "writer",
    "url": "http://writer:8000",
    "description": "Takes raw research findings and formats them into a polished report."
  }
]'
```

The parent now has two tools: `call_researcher` and `call_writer`. It can use them in sequence — research first, then write — without any changes to the parent's code.

---

## Scheduled runs

Add these to `.env.parent`:

```env
SCHEDULE__ENABLED=true
SCHEDULE__CRON="0 7 * * 1-5"    # weekdays at 07:00 UTC
SCHEDULE__INPUT="Research the most important AI and machine learning developments from the past 24 hours. Produce a structured summary with key findings, notable model releases, and any significant industry news."
SCHEDULE__TENANT_ID=research-system
SCHEDULE__SESSION_ID_PREFIX=digest
```

Each scheduled run delegates to `call_researcher` as normal. The synthesised digest is captured in a Langfuse trace tagged `research-system`.

**Cron expression examples:**

| Expression | Schedule |
|---|---|
| `0 7 * * 1-5` | Weekdays at 07:00 UTC |
| `0 */6 * * *` | Every 6 hours |
| `0 9 * * 1` | Monday mornings at 09:00 |
