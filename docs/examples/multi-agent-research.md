# Example: Web Research Pipeline (Perplexity-style)

A two-agent system where a **parent agent** receives a research question and delegates live web search to a **researcher sub-agent** that has the Brave Search MCP wired in. The parent synthesises the findings into a cited, structured answer.

**What this demonstrates:**
- Sub-agent pattern (Phase 5): parent calls `call_researcher` as a tool
- MCP integration: researcher uses Brave Search via `@modelcontextprotocol/server-brave-search`
- Multi-container Docker Compose: two independent agent instances
- Session ID propagation across agent boundaries

---

## Architecture

```
Client
  │
  ▼
Parent Agent  (port 8000)
  │
  │  tool call: call_researcher("What are the latest LLM context window sizes?")
  ▼
Researcher Sub-agent  (port 8001)
  │
  │  MCP tool: brave_search(query)
  ▼
Brave Search API  →  live web results
  │
  ▼  returns: summarised findings with sources
Parent Agent
  │
  ▼  synthesises into structured answer with citations
Client
```

---

## Prerequisites

- [Brave Search API key](https://brave.com/search/api/) — free tier available (2000 queries/month)
- Node.js (for `npx @modelcontextprotocol/server-brave-search`)
- Docker Compose

---

## Setup

### 1. Project layout

```
ai-agent-template/
  docker-compose.yml          # base: Langfuse + Qdrant
  docker-compose.research.yml # overlay: parent + researcher containers
  .env.parent                 # parent agent config
  .env.researcher             # researcher sub-agent config
  prompts/
    v1/system.md              # parent prompt (default)
    researcher/system.md      # researcher-specific prompt
```

### 2. Researcher system prompt

Create `prompts/researcher/system.md`:

```markdown
You are a web research specialist. When given a question, search the web for
the most current and relevant information. Return your findings as a structured
summary with:

1. Key facts and figures (with approximate dates)
2. Notable sources (publication name and approximate date — do not fabricate URLs)
3. Any significant caveats or conflicting information

Be factual. Do not extrapolate beyond what the search results contain.
```

### 3. Researcher config (`.env.researcher`)

```env
TENANT_ID=research-system
ENVIRONMENT=production

LLM__PROVIDER=anthropic
LLM__MODEL=claude-sonnet-4-6
LLM__API_KEY=sk-ant-...

LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=http://langfuse:3000

AGENT__NAME=researcher
AGENT__PROMPT_VERSION=researcher   # maps to prompts/researcher/system.md
AGENT__MAX_ITERATIONS=5

# Brave Search MCP
MCP_SERVERS='[{
  "name": "brave-search",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-brave-search"],
  "env": {"BRAVE_API_KEY": "BSA..."}
}]'

# Lock researcher to only the search tool
AGENT__ALLOWED_TOOLS='["brave_search"]'
```

> **Alternative search providers:** Tavily MCP (`@tavily/mcp-server`) and Exa MCP (`@exa-ai/mcp-server-exa`) work as drop-in replacements — same config shape, different `command`/`args` and API key.

### 4. Parent config (`.env.parent`)

```env
TENANT_ID=research-system
ENVIRONMENT=production

LLM__PROVIDER=anthropic
LLM__MODEL=claude-sonnet-4-6
LLM__API_KEY=sk-ant-...

LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=http://langfuse:3000

AGENT__NAME=research-orchestrator
AGENT__PROMPT_VERSION=v1
AGENT__MAX_ITERATIONS=5

# Register the researcher as a callable sub-agent
AGENT__SUB_AGENTS='[{
  "name": "researcher",
  "url": "http://researcher:8001",
  "description": "Searches the live web for current information on any topic using Brave Search. Returns a structured summary of findings with sources. Use this whenever the question requires up-to-date information beyond your training data.",
  "timeout": 60.0
}]'
```

### 5. Docker Compose overlay (`docker-compose.research.yml`)

```yaml
services:
  researcher:
    build: .
    env_file: .env.researcher
    ports:
      - "8001:8000"
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000

  parent:
    build: .
    env_file: .env.parent
    ports:
      - "8000:8000"
    depends_on:
      - researcher
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### 6. Start everything

```bash
# Start Langfuse + Qdrant
docker compose up -d

# Start parent + researcher agents
docker compose -f docker-compose.research.yml up --build
```

---

## Querying

### Gradio demo UI (optional)

```bash
docker compose -f docker-compose.yml \
               -f docker-compose.research.yml \
               -f docker-compose.demo.yml up --build
```

Open **http://localhost:7860**. The Config sidebar should point at `http://localhost:8001` (the parent agent's mapped port). The researcher sub-agent is called internally — you only interact with the parent.

> The demo UI is for development and showcasing only. It is not included in the production `docker-compose.yml`.

---

### curl

```bash
curl -X POST http://localhost:8000/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "research-system",
    "input": "What are the largest LLM context windows available today and which models offer them?"
  }'
```

**What happens internally:**

1. Parent agent reasons: this needs live data → calls `call_researcher`
2. Researcher sub-agent calls `brave_search("largest LLM context windows 2025")`
3. Brave returns 10 web results
4. Researcher synthesises findings, returns to parent
5. Parent formats a structured answer with source attribution

**Response**

```json
{
  "session_id": "a1b2c3...",
  "tenant_id": "research-system",
  "output": "As of mid-2025, the largest publicly available context windows are:\n\n**1M tokens**\n- Google Gemini 1.5 Pro (Google AI, May 2025)\n- Gemini 1.5 Flash\n\n**200K tokens**\n- Anthropic Claude 3.5 / claude-sonnet-4-6\n\n**128K tokens**\n- OpenAI GPT-4o\n- Mistral Large\n\nSources: The Verge (Apr 2025), Anthropic blog (May 2025), OpenAI docs.",
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
curl -X POST http://localhost:8000/v1/agent/stream \
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

var response = await http.PostAsJsonAsync("http://localhost:8000/v1/agent/run", payload);
var result = await response.Content.ReadFromJsonAsync<AgentResponse>();

Console.WriteLine(result?.Output);
Console.WriteLine($"Cost: ${result?.CostUsd:F4}");
```

---

## How sub-agent delegation works

The parent agent sees `call_researcher` as a standard tool with this schema:

```json
{
  "name": "call_researcher",
  "description": "Searches the live web for current information...",
  "input_schema": {
    "type": "object",
    "properties": {
      "task": {"type": "string", "description": "The task or question to delegate"}
    },
    "required": ["task"]
  }
}
```

When the LLM calls `call_researcher`, the execute node:
1. Detects the `call_` prefix and routes to `AgentRegistry` instead of `MCPRegistry`
2. `SubAgentClient` sends a `POST /v1/agent/run` to `http://researcher:8001`
3. The session ID is scoped: `{parent_session_id}-researcher-{random8hex}`
4. The researcher's response text is returned to the parent as the tool result

The parent then reasons over the result and produces the final response. Both runs appear as separate traces in Langfuse, linked by the session ID prefix.

---

## Extending the pipeline

**Add a writer sub-agent** that takes the researcher's raw findings and formats them into a polished report (markdown, executive summary, bullet points). Register it alongside the researcher:

```env
AGENT__SUB_AGENTS='[
  {
    "name": "researcher",
    "url": "http://researcher:8001",
    "description": "Searches the live web for current information."
  },
  {
    "name": "writer",
    "url": "http://writer:8002",
    "description": "Takes raw research findings and formats them into a polished, structured report with an executive summary."
  }
]'
```

The parent now has two tools: `call_researcher` and `call_writer`. It can use them in sequence — research first, then write — without any changes to the parent's code.

---

## Observability

Each layer traces independently to Langfuse:

- **Parent trace**: shows the `call_researcher` tool call and the final synthesis
- **Researcher trace**: shows the `brave_search` MCP call and web results

Filter by session ID prefix to correlate both traces for a single user query. Both traces include `cost_usd` scores, so you can sum the full pipeline cost.
