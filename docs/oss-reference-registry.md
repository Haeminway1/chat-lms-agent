# OSS Reference Registry

This is the canonical public registry for external references used by Chat LMS Agent.
Entries are architecture references unless `adoption_status` says otherwise.

```json
{
  "schema_version": "oss-reference-registry-v1",
  "observed_at": "2026-06-09",
  "references": [
    {
      "id": "agents-md",
      "source_url": "https://github.com/openai/agents.md",
      "pinned_head_sha": "",
      "observed_at": "2026-06-09",
      "license": "pending-review",
      "popularity_signal": "cross-agent convention",
      "local_problem_matched": "predictable repository instructions",
      "adoption_status": "direct-now",
      "local_mapping": "AGENTS.md remains the public cross-agent rulebook.",
      "must_not_copy": "Do not store private profile data or volatile runtime state in public AGENTS.md.",
      "privacy_boundary": "public docs only",
      "freshness_note": "Verify before changing semantics."
    },
    {
      "id": "agent-skills",
      "source_url": "https://agentskills.io/specification",
      "pinned_head_sha": "",
      "observed_at": "2026-06-09",
      "license": "pending-review",
      "popularity_signal": "agent skill packaging convention",
      "local_problem_matched": "reusable workflow drawers",
      "adoption_status": "direct-now",
      "local_mapping": "Local skills use SKILL.md plus optional scripts/references/assets.",
      "must_not_copy": "Do not make large always-loaded skills or hidden write scripts.",
      "privacy_boundary": "public skills only; private memory stays in profile state",
      "freshness_note": "Keep skills small and progressively disclosed."
    },
    {
      "id": "headroom",
      "source_url": "https://github.com/chopratejas/headroom",
      "pinned_head_sha": "9579567b7dae31b226a634b7f63a988253fc03b8",
      "observed_at": "2026-06-09",
      "license": "pending-review",
      "popularity_signal": "user-supplied OSS reference",
      "local_problem_matched": "reversible context compression and offload",
      "adoption_status": "candidate-next",
      "local_mapping": "Use local offload ids, summaries, and exact original retrieval before any dependency adoption.",
      "must_not_copy": "Do not wrap or proxy Codex Desktop traffic by default.",
      "privacy_boundary": "private originals stay in profile state; summaries are redacted views",
      "freshness_note": "Evaluate with synthetic fixtures before real profile use."
    },
    {
      "id": "tencentdb-agent-memory",
      "source_url": "https://github.com/TencentCloud/TencentDB-Agent-Memory",
      "pinned_head_sha": "f92b10259b8b5780f8b0056b5c8526fc98f5646f",
      "observed_at": "2026-06-09",
      "license": "pending-review",
      "popularity_signal": "user-supplied OSS reference",
      "local_problem_matched": "layered symbolic memory",
      "adoption_status": "reference-only",
      "local_mapping": "Map L0-L3 ideas into local Chat LMS memory levels.",
      "must_not_copy": "Do not import OpenClaw/Hermes patches, Docker sidecars, gateways, or default model endpoints.",
      "privacy_boundary": "local profile memory remains the source of truth",
      "freshness_note": "Use as memory architecture reference only."
    },
    {
      "id": "roach-pi",
      "source_url": "https://github.com/tmdgusya/roach-pi",
      "pinned_head_sha": "a2da093fd7cd00d1204b6c7eabc50245f71cde98",
      "observed_at": "2026-06-09",
      "license": "pending-review",
      "popularity_signal": "user-supplied OSS reference",
      "local_problem_matched": "verifier-gated durable agentic work",
      "adoption_status": "reference-only",
      "local_mapping": "Use verifier receipts and lazy discovery patterns over existing Chat LMS trace/audit/closeout surfaces.",
      "must_not_copy": "Do not add a second coding-agent runtime, write-capable MCP proxy, or process manager.",
      "privacy_boundary": "goal evidence stays in private profile state",
      "freshness_note": "Reference verifier semantics only."
    }
  ]
}
```
