# Sketric Chat Server — System Architecture

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            CLIENT LAYER                                │
│                  (Web App / Mobile App / API Consumer)                  │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │  HTTP / WebSocket
                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI SERVER                                 │
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │  /chat       │  │  /chat/stream│  │  /conversations│                │
│  │  (sync)      │  │  (SSE)       │  │  (CRUD)       │                 │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────┘                 │
│         │                 │                  │                          │
│  ┌──────▼─────────────────▼──────────────────▼────────┐                │
│  │              REQUEST PIPELINE                       │                │
│  │  1. Auth & Rate Limit                               │                │
│  │  2. Credit Balance Check                            │                │
│  │  3. Fetch Agent Config (DynamoDB)                   │                │
│  │  4. Build Agent (OpenAI Agents SDK)                 │                │
│  │  5. Execute Query                                   │                │
│  │  6. Store Messages & Traces (DynamoDB)              │                │
│  │  7. Emit Billing Event (SQS)                        │                │
│  └─────────┬──────────────┬───────────────┬────────────┘               │
│            │              │               │                             │
└────────────┼──────────────┼───────────────┼─────────────────────────────┘
             │              │               │
     ┌───────▼──────┐ ┌────▼─────┐  ┌──────▼──────┐
     │   DynamoDB   │ │   SQS    │  │ OpenAI API  │
     │              │ │ (Billing │  │ (Agents SDK)│
     │ - Agents     │ │  Queue)  │  │             │
     │ - Convos     │ └────┬─────┘  └─────────────┘
     │ - Messages   │      │
     │ - Traces     │      ▼
     │ - Credits    │ ┌──────────┐
     └──────────────┘ │ Billing  │
                      │ Worker   │
                      │ (Lambda) │
                      └──────────┘
```

---

## 2. Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **FastAPI Server** | Accepts chat requests (sync & streaming), orchestrates the full request pipeline, returns responses |
| **Request Pipeline** | Auth → credit check → agent build → execute → store → bill. Every request follows this sequence |
| **OpenAI Agents SDK** | Executes LLM calls, handles multi-agent handoffs, manages tool calls within agent workflows |
| **DynamoDB** | Persistent storage for agent configs, conversations, messages, execution traces, and credit balances |
| **SQS (Billing Queue)** | Decouples billing from the request path. Chat endpoint fires a billing event and returns immediately — no waiting for billing to complete |
| **Billing Worker (Lambda)** | Consumes SQS events, calculates token cost, deducts credits atomically in DynamoDB |

---

## 3. DynamoDB Schema Design

### Table: `Agents`

Stores agent configurations that define how each agent behaves.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `agent_id` | S | PK | Unique agent identifier |
| `org_id` | S | SK | Organization that owns this agent |
| `name` | S | — | Display name |
| `model` | S | — | LLM model (e.g. `gpt-4o-mini`) |
| `instructions` | S | — | System prompt |
| `tools` | L | — | List of tool configs (MCP, function tools) |
| `handoffs` | L | — | List of agent IDs this agent can delegate to |
| `tts_config` | M | — | Voice settings (if applicable) |
| `is_enabled` | BOOL | — | Whether the agent is active |
| `created_at` | S | — | ISO timestamp |
| `updated_at` | S | — | ISO timestamp |

**GSI:** `org_id-index` → PK: `org_id` (list all agents for an org)

---

### Table: `Conversations`

Each conversation is a session between a user and an agent.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `conversation_id` | S | PK | Unique conversation ID (ULID) |
| `org_id` | S | SK | Organization owner |
| `agent_id` | S | — | Agent handling this conversation |
| `user_id` | S | — | User who initiated |
| `title` | S | — | Auto-generated or user-set title |
| `status` | S | — | `active` / `archived` |
| `message_count` | N | — | Running count of messages |
| `total_tokens` | N | — | Cumulative token usage |
| `created_at` | S | — | ISO timestamp |
| `updated_at` | S | — | ISO timestamp |
| `version` | N | — | Optimistic locking version (for concurrency) |

**GSI:** `user_id-index` → PK: `user_id`, SK: `created_at` (list user's conversations)

---

### Table: `Messages`

Individual messages within a conversation (user, assistant, tool results).

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `conversation_id` | S | PK | Parent conversation |
| `message_id` | S | SK | ULID (time-sortable, globally unique) |
| `role` | S | — | `user` / `assistant` / `tool` / `system` |
| `content` | S | — | Message text |
| `agent_id` | S | — | Which agent produced this message |
| `tool_calls` | L | — | Tool calls made (if assistant) |
| `tool_results` | L | — | Tool results (if tool message) |
| `token_usage` | M | — | `{prompt_tokens, completion_tokens, total_tokens}` |
| `model` | S | — | Model used for this message |
| `created_at` | S | — | ISO timestamp |

**Access pattern:** Get all messages for a conversation, sorted by time → PK: `conversation_id`, SK: `message_id` (ULID is time-sorted).

---

### Table: `Traces`

Execution traces for observability and debugging.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `trace_id` | S | PK | Unique trace ID |
| `conversation_id` | S | SK | Linked conversation |
| `request_id` | S | — | Correlates to the HTTP request |
| `agent_id` | S | — | Agent that executed |
| `handoff_chain` | L | — | Ordered list of agents involved `[{agent_id, reason}]` |
| `tool_calls` | L | — | All tool calls in this execution |
| `token_usage` | M | — | Total tokens for this trace |
| `latency_ms` | N | — | End-to-end latency |
| `status` | S | — | `success` / `error` / `timeout` |
| `error` | S | — | Error message (if failed) |
| `created_at` | S | — | ISO timestamp |

**GSI:** `conversation_id-index` → PK: `conversation_id` (get all traces for a conversation)

---

### Table: `Credits`

Per-organization credit balance for billing.

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `org_id` | S | PK | Organization |
| `balance` | N | — | Current credit balance (atomic counter) |
| `reserved` | N | — | Credits reserved for in-flight requests |
| `total_spent` | N | — | Lifetime spend |
| `updated_at` | S | — | ISO timestamp |
| `version` | N | — | Optimistic locking version |

---

## 4. Chat Request Flow

### 4a. Non-Streaming Flow (`POST /chat`)

```
Client                    FastAPI                  DynamoDB         OpenAI          SQS
  │                         │                        │               │              │
  │  POST /chat             │                        │               │              │
  │  {conversation_id,      │                        │               │              │
  │   agent_id, message}    │                        │               │              │
  │ ───────────────────────►│                        │               │              │
  │                         │                        │               │              │
  │                         │  1. Check credits      │               │              │
  │                         │  (ConditionExpression:  │               │              │
  │                         │   balance >= reserve)   │               │              │
  │                         │ ──────────────────────►│               │              │
  │                         │  ◄─────── OK ──────────│               │              │
  │                         │                        │               │              │
  │                         │  2. Reserve credits     │               │              │
  │                         │  (atomic ADD reserved)  │               │              │
  │                         │ ──────────────────────►│               │              │
  │                         │                        │               │              │
  │                         │  3. Get agent config    │               │              │
  │                         │ ──────────────────────►│               │              │
  │                         │  ◄─── agent config ────│               │              │
  │                         │                        │               │              │
  │                         │  4. Get conversation    │               │              │
  │                         │     history (Messages)  │               │              │
  │                         │ ──────────────────────►│               │              │
  │                         │  ◄─── messages[] ──────│               │              │
  │                         │                        │               │              │
  │                         │  5. Build Agent (SDK)   │               │              │
  │                         │  6. Run agent           │               │              │
  │                         │ ──────────────────────────────────────►│              │
  │                         │  ◄──────────── completion ────────────│              │
  │                         │                        │               │              │
  │                         │  7. Store user msg +    │               │              │
  │                         │     assistant msg       │               │              │
  │                         │ ──────────────────────►│               │              │
  │                         │                        │               │              │
  │                         │  8. Store trace         │               │              │
  │                         │ ──────────────────────►│               │              │
  │                         │                        │               │              │
  │                         │  9. Emit billing event  │               │              │
  │                         │ ─────────────────────────────────────────────────────►│
  │                         │                        │               │              │
  │  ◄── 200 {response} ───│                        │               │              │
  │                         │                        │               │              │
```

**Response payload:**
```json
{
  "conversation_id": "01JXYZ...",
  "message_id": "01JXYZ...",
  "content": "Here is a spreadsheet named Expenses...",
  "agent_id": "agent_google_sheets",
  "model": "gpt-4o-mini",
  "token_usage": {
    "prompt_tokens": 342,
    "completion_tokens": 87,
    "total_tokens": 429
  }
}
```

---

### 4b. Streaming Flow (`POST /chat/stream`)

Uses Server-Sent Events (SSE) to stream tokens as they arrive.

```
Client                    FastAPI                  DynamoDB         OpenAI          SQS
  │                         │                        │               │              │
  │  POST /chat/stream      │                        │               │              │
  │ ───────────────────────►│                        │               │              │
  │                         │                        │               │              │
  │                         │  Steps 1-4: same as non-streaming      │              │
  │                         │  (credit check, reserve, fetch config, │              │
  │                         │   fetch history)       │               │              │
  │                         │                        │               │              │
  │                         │  5. Build Agent (SDK)   │               │              │
  │                         │  6. Run agent (stream)  │               │              │
  │                         │ ──────────────────────────────────────►│              │
  │                         │                        │               │              │
  │  ◄── SSE: event=start ──│                        │               │              │
  │      {conversation_id}  │                        │               │              │
  │                         │                        │               │              │
  │  ◄── SSE: event=delta ──│  ◄──── token chunk ──────────────────│              │
  │      {content: "Here"}  │                        │               │              │
  │  ◄── SSE: event=delta ──│  ◄──── token chunk ──────────────────│              │
  │      {content: " is"}   │                        │               │              │
  │  ◄── SSE: event=delta ──│  ◄──── token chunk ──────────────────│              │
  │      {content: " a..."}│                        │               │              │
  │         ...              │                        │               │              │
  │                         │                        │               │              │
  │                         │  ◄──── stream done ──────────────────│              │
  │                         │                        │               │              │
  │                         │  7. Store messages      │               │              │
  │                         │ ──────────────────────►│               │              │
  │                         │  8. Store trace         │               │              │
  │                         │ ──────────────────────►│               │              │
  │                         │  9. Emit billing event  │               │              │
  │                         │ ─────────────────────────────────────────────────────►│
  │                         │                        │               │              │
  │  ◄── SSE: event=done ───│                        │               │              │
  │      {token_usage, id}  │                        │               │              │
  │                         │                        │               │              │
```

**SSE event types:**
| Event | Payload | When |
|-------|---------|------|
| `start` | `{conversation_id, message_id}` | Stream begins |
| `delta` | `{content: "token"}` | Each token chunk from LLM |
| `tool_call` | `{name, arguments}` | Agent invokes a tool |
| `tool_result` | `{name, result}` | Tool returns a result |
| `handoff` | `{from_agent, to_agent, reason}` | Agent delegates to another |
| `done` | `{token_usage, message_id}` | Stream complete |
| `error` | `{code, message}` | Error occurred |

---

## 5. Billing Flow

Billing is **decoupled** from the chat request path via SQS to avoid adding latency.

```
┌────────────────────┐         ┌──────────┐         ┌──────────────────┐
│   FastAPI Server    │         │   SQS    │         │  Billing Worker  │
│                     │         │  Queue   │         │  (Lambda)        │
│  1. Reserve credits │         │          │         │                  │
│     (atomic)        │         │          │         │                  │
│                     │         │          │         │                  │
│  2. Execute query   │         │          │         │                  │
│                     │         │          │         │                  │
│  3. Send billing    │────────►│  Event   │────────►│  4. Calculate    │
│     event to SQS    │         │  queued  │         │     actual cost  │
│                     │         │          │         │                  │
│  4. Return response │         │          │         │  5. Deduct from  │
│     to client       │         │          │         │     balance      │
│                     │         │          │         │     (atomic)     │
│                     │         │          │         │                  │
│                     │         │          │         │  6. Release      │
│                     │         │          │         │     reservation  │
└────────────────────┘         └──────────┘         └──────────────────┘
```

**SQS billing event payload:**
```json
{
  "event_type": "chat_completion",
  "org_id": "org_abc123",
  "conversation_id": "01JXYZ...",
  "trace_id": "trace_001",
  "model": "gpt-4o-mini",
  "token_usage": {
    "prompt_tokens": 342,
    "completion_tokens": 87,
    "total_tokens": 429
  },
  "timestamp": "2026-02-22T03:45:00Z"
}
```

**Credit reservation pattern (prevents overspend):**

1. **Before execution:** Atomically reserve an estimated credit amount
   ```
   UpdateItem: SET reserved = reserved + :estimate
   ConditionExpression: balance - reserved >= :estimate
   ```
   If the condition fails → reject request with 402 (insufficient credits).

2. **After execution:** Billing worker calculates actual cost, deducts, and releases reservation
   ```
   UpdateItem: SET balance = balance - :actual_cost,
                   reserved = reserved - :estimate,
                   total_spent = total_spent + :actual_cost
   ```

This two-phase approach ensures users cannot overspend even under concurrent requests.

---

## 6. Concurrency & Race-Condition Prevention

### Problem 1: Concurrent messages to the same conversation

Two requests arrive simultaneously for the same `conversation_id`. Both read the message history, both append — one overwrites the other's message.

**Solution: ULID message IDs + append-only writes**

Messages are stored with `conversation_id` as PK and `message_id` (ULID) as SK. Each write is an independent `PutItem` — no read-modify-write cycle. ULIDs are time-sorted and globally unique, so concurrent writes never collide.

```python
# Each message is an independent PutItem — no conflict possible
table.put_item(Item={
    "conversation_id": convo_id,
    "message_id": ulid.new().str,  # globally unique, time-sorted
    "role": "assistant",
    "content": response_text,
})
```

### Problem 2: Concurrent credit deductions (double-spend)

Two requests pass the balance check simultaneously, both deduct, and the org goes negative.

**Solution: Atomic conditional updates with reservation**

DynamoDB's `ConditionExpression` ensures atomicity at the item level. The reservation pattern (Section 5) guarantees that even under concurrent requests, the total reserved amount never exceeds the balance.

```python
# Atomic reservation — fails if insufficient balance
credits_table.update_item(
    Key={"org_id": org_id},
    UpdateExpression="SET reserved = reserved + :est",
    ConditionExpression="balance - reserved >= :est",
    ExpressionAttributeValues={":est": estimated_cost},
)
# If another request runs concurrently, DynamoDB evaluates the condition
# against the LATEST value — one will succeed, one will fail if balance is low
```

### Problem 3: Conversation metadata race condition

Two requests update `message_count` and `updated_at` on the same conversation simultaneously.

**Solution: Atomic counters + optimistic locking**

```python
# Atomic increment — no read-modify-write needed
conversations_table.update_item(
    Key={"conversation_id": convo_id, "org_id": org_id},
    UpdateExpression="SET message_count = message_count + :inc, updated_at = :now",
    ExpressionAttributeValues={":inc": 1, ":now": now},
)
```

For fields that require read-modify-write (like `status` changes), use optimistic locking with a `version` attribute:

```python
conversations_table.update_item(
    Key={"conversation_id": convo_id, "org_id": org_id},
    UpdateExpression="SET status = :new_status, version = version + :inc",
    ConditionExpression="version = :expected_version",
    ExpressionAttributeValues={
        ":new_status": "archived",
        ":inc": 1,
        ":expected_version": current_version,
    },
)
# If another request changed the version, this fails → retry with fresh read
```

### Problem 4: In-flight request and server crash

Server crashes after executing the LLM call but before storing messages or billing.

**Solution: Idempotent writes + SQS retry**

- Every request gets a unique `request_id`. Message writes use this as a condition to prevent duplicate inserts on retry.
- SQS has built-in retry with dead-letter queue (DLQ). If the billing worker fails, the event is retried automatically.
- Traces record the request status (`success`/`error`/`timeout`) — incomplete traces can be reconciled by a background job.

### Problem 5: Streaming disconnect mid-response

Client disconnects while tokens are still streaming.

**Solution: Graceful cleanup in `finally` block**

```python
async def stream_chat(request):
    reserved = False
    accumulated_content = ""
    try:
        await reserve_credits(org_id, estimate)
        reserved = True

        async for chunk in agent.run_stream(messages):
            accumulated_content += chunk.content
            yield sse_event("delta", chunk.content)

        # Stream completed successfully
        await store_messages(convo_id, user_msg, accumulated_content)
        await emit_billing_event(org_id, token_usage)
        yield sse_event("done", token_usage)

    except asyncio.CancelledError:
        # Client disconnected — still store partial result
        if accumulated_content:
            await store_messages(convo_id, user_msg, accumulated_content, partial=True)
        raise
    finally:
        if reserved:
            await release_reservation(org_id, estimate)
```

---

## 7. Multi-Agent Workflow Handling

### How agents hand off to each other

The OpenAI Agents SDK supports agent handoffs natively. In our architecture, we use a **delegation pattern** — the entry agent stays in control and delegates sub-tasks to specialist agents.

```
┌──────────────┐     delegates     ┌──────────────┐
│  Entry Agent │ ────────────────► │ Specialist A │
│  (Router)    │ ◄──── result ──── │ (e.g. Sheets)│
│              │                   └──────────────┘
│              │     delegates     ┌──────────────┐
│              │ ────────────────► │ Specialist B │
│              │ ◄──── result ──── │ (e.g. Search)│
└──────────────┘                   └──────────────┘
```

### Workflow execution steps

1. **Fetch agent config** from DynamoDB `Agents` table (includes `handoffs` list)
2. **Build agent graph** — entry agent + all reachable specialist agents
3. **Execute with delegation** — when the LLM decides to delegate:
   - The entry agent calls a delegation tool (e.g. `ask_web_search_agent(query)`)
   - The tool makes an internal LLM call with the specialist's instructions
   - The result is returned as text to the entry agent
   - The entry agent incorporates it into its response
4. **Record handoff chain** in the trace: `[{agent: "entry", reason: "..."}, {agent: "search", reason: "..."}]`

### Why delegation over permanent handoff

| Approach | Pros | Cons |
|----------|------|------|
| **Permanent handoff** | Native SDK support | User stuck with specialist; can't route back easily |
| **Delegation** (our choice) | Entry agent stays in control, can combine results from multiple specialists | Extra LLM call per delegation |

Delegation is simpler, more predictable, and avoids the "stuck agent" problem where a user gets permanently routed to a specialist that can't handle follow-up questions.

### Agent config in DynamoDB

```json
{
  "agent_id": "agent_entry",
  "name": "Main Assistant",
  "instructions": "You are a helpful assistant...",
  "model": "gpt-4o-mini",
  "tools": [
    {"type": "mcp", "url": "https://mcp.zapier.com/...", "allowed_tools": ["google_sheets_*"]}
  ],
  "handoffs": [
    {"agent_id": "agent_search", "description": "Delegate web search queries"}
  ]
}
```

---

## 8. API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Non-streaming chat completion |
| `POST` | `/chat/stream` | Streaming chat via SSE |
| `POST` | `/conversations` | Create a new conversation |
| `GET` | `/conversations/{id}` | Get conversation details |
| `GET` | `/conversations/{id}/messages` | List messages (paginated) |
| `DELETE` | `/conversations/{id}` | Archive a conversation |
| `GET` | `/agents/{id}` | Get agent configuration |
| `GET` | `/credits` | Check organization credit balance |

---

## 9. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **DynamoDB over PostgreSQL** | Single-digit millisecond reads at scale, no connection pooling needed, natural fit for key-value access patterns (conversation → messages) |
| **SQS for billing** | Decouples billing from request latency. If billing fails, the message retries — the user isn't blocked |
| **ULID for IDs** | Time-sortable (messages come back in order without a secondary index), globally unique (safe for concurrent writes), compact |
| **Credit reservation** | Two-phase reserve → deduct prevents overspend under concurrency without distributed locks |
| **Delegation over handoff** | Entry agent stays in control — simpler state management, predictable UX, no "stuck agent" problem |
| **Append-only messages** | No read-modify-write for messages — eliminates the most common race condition in chat systems |
| **Traces as first-class entities** | Every execution is auditable — critical for debugging multi-agent workflows and billing disputes |
