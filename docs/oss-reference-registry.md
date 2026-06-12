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
      "id": "oh-my-pi",
      "source_url": "https://github.com/can1357/oh-my-pi",
      "pinned_head_sha": "bbe85b66617d00e723bda6d126f577b54bd1f70a",
      "observed_at": "2026-06-10",
      "license": "pending-review",
      "popularity_signal": "user-supplied OSS reference; upstream of gajae-code",
      "local_problem_matched": "approval tier algebra, canonical model identity, privacy data contracts",
      "adoption_status": "reference-only",
      "local_mapping": "PreToolUse gate as a tier/policy/override decision table; model catalog identity, equivalence, and context-promotion semantics; two-mode pseudonymization and consent-gated self-QA ledger contracts; route-pack bucket ingestion.",
      "must_not_copy": "Do not adopt yolo defaults, headless-yolo subagents, the 40-provider runtime, or any second agent loop; invert every borrowed default to always-ask, deny-unknown, consent-before-write.",
      "privacy_boundary": "data contracts only; reverse maps and ledgers stay in private profile state",
      "freshness_note": "Pinned at v15.10.12; re-verify identity-layer semantics before V5 Track B implementation."
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
    },
    {
      "id": "hermes-agent",
      "source_url": "https://github.com/sibyllinesoft/hermes",
      "pinned_head_sha": "a87f0a82a52178b05ff7405e9af7137e20a70bbf",
      "observed_at": "2026-06-11",
      "license": "MIT",
      "popularity_signal": "golden-standard comparison set",
      "local_problem_matched": "Google Workspace token bridge and consent-flow UX for the gws CLI",
      "adoption_status": "structural-reference",
      "local_mapping": "gws_auth/gws_api reimplement the token-refresh and scope-check shape with the standard library; no Google SDK dependency.",
      "must_not_copy": "Do not copy the gateway/messaging machinery, the external gws binary bridge, or Contacts/Docs scopes.",
      "privacy_boundary": "tokens live in the teacher's user home, never in repo or context",
      "freshness_note": "Reference the consent-flow UX only; endpoints are pinned in gws_api."
    },
    {
      "id": "open-design",
      "source_url": "https://github.com/nexu-io/open-design",
      "pinned_head_sha": "8359fb6d2c254fb83716b35a4ad7863a6221bc28",
      "observed_at": "2026-06-12",
      "license": "Apache-2.0",
      "popularity_signal": "side-panel design-system reference set",
      "local_problem_matched": "portable design systems as authored data",
      "adoption_status": "structural-reference",
      "local_mapping": "Use a repo/profile DESIGN.md convention for side-panel design systems; keep generated artifacts separate from promotion.",
      "must_not_copy": "Do not copy daemon internals, marketplace behavior, model-router internals, unified billing, or any always-on network service.",
      "privacy_boundary": "design-system defaults are public repo data; profile overrides stay in private profile state",
      "freshness_note": "Pinned with git ls-remote on 2026-06-12; re-check before engine integration."
    },
    {
      "id": "impeccable",
      "source_url": "https://github.com/pbakaus/impeccable",
      "pinned_head_sha": "92d6141cdf61f9943dfc8e2e46870e54e46d8641",
      "observed_at": "2026-06-12",
      "license": "Apache-2.0",
      "popularity_signal": "deterministic AI-design anti-pattern detector",
      "local_problem_matched": "advisory slop detection for generated side-panel HTML",
      "adoption_status": "optional-advisory",
      "local_mapping": "Run a pinned local npx detector from design lint when available and attach findings under advisory.impeccable without changing lint pass/fail.",
      "must_not_copy": "Do not re-implement or vendor detector rules, require it as a hard CI gate when absent, or run its LLM critique modes in tests.",
      "privacy_boundary": "detector input is the local artifact being linted; no profile secrets or learner records are committed",
      "freshness_note": "Pinned with git ls-remote on 2026-06-12 and npm package version 2.3.2 for the local npx command."
    },
    {
      "id": "toss-design-language",
      "source_url": "https://developers-apps-in-toss.toss.im/design/components.html",
      "pinned_head_sha": "",
      "observed_at": "2026-06-12",
      "license": "proprietary-reference",
      "popularity_signal": "user-requested default visual direction",
      "local_problem_matched": "clear mobile-first side-panel design defaults",
      "adoption_status": "principles-only",
      "local_mapping": "Express Toss-style principles in our own DESIGN.md: one accent, whitespace, hierarchy, mobile-first single column, restrained motion, and polite Korean voice.",
      "must_not_copy": "Do not copy proprietary TDS assets, fonts, icons, copy, CSS, packages, screenshots, or scraped implementation details.",
      "privacy_boundary": "only public principles are referenced; no Toss assets or private design files enter the repo",
      "freshness_note": "Source URL verified on 2026-06-12; use principles only."
    },
    {
      "id": "pretendard",
      "source_url": "https://github.com/orioncactus/pretendard",
      "pinned_head_sha": "",
      "observed_at": "2026-06-12",
      "license": "SIL OFL 1.1",
      "popularity_signal": "Korean product typography convention",
      "local_problem_matched": "readable Korean-first side-panel typography",
      "adoption_status": "font-stack-reference",
      "local_mapping": "Use a Pretendard-first CSS font-family convention with platform fallbacks; do not bundle font files.",
      "must_not_copy": "Do not commit font binaries, hosted font CSS, CDN links, or bundled font files.",
      "privacy_boundary": "font stack text only; no external font assets are stored in repo or profile state",
      "freshness_note": "Source URL and OFL reference verified on 2026-06-12."
    }
  ]
}
```
