# OSS Source Map

This file tracks the public software we plan to use, how it maps to the product, and license/compliance notes to verify before commercial use.

| ID | Source | Role | License posture | Use decision |
| --- | --- | --- | --- | --- |
| `deer-flow` | https://github.com/bytedance/deer-flow | Core super-agent harness: planning, sub-agents, memory, sandboxes, skills | MIT | Adopt as core engine |
| `dify` | https://github.com/langgenius/dify | Workflow builder, RAG, model management, observability, backend APIs | Modified Apache-2.0 style with extra conditions | Adopt with legal review before multi-tenant launch |
| `openmanus` | https://github.com/FoundationAgents/OpenManus | General AI agent reference/prototype layer | MIT | Keep as fallback/reference |
| `presenton` | https://github.com/presenton/presenton | AI presentation generation and editable PPTX/PDF export | Apache-2.0 | Adopt for slides |
| `crawl4ai` | https://github.com/unclecode/crawl4ai | LLM-ready crawling, markdown conversion, structured extraction | Apache-2.0 plus attribution requirement | Adopt, include attribution |
| `searxng` | https://github.com/searxng/searxng | Self-hosted metasearch | AGPL-3.0 | Use carefully behind internal boundary; review obligations |
| `browser-use` | https://github.com/browser-use/browser-use | Browser automation for agents | MIT | Adopt for browser actions |
| `coze-studio` | https://github.com/coze-dev/coze-studio | Visual agent/workflow builder alternative | Apache-2.0 from public repository metadata | Optional Dify alternative |
| `ui-tars-desktop` | https://github.com/bytedance/UI-TARS-desktop | Multimodal GUI/computer-use stack | Apache-2.0 from public repository metadata | Optional advanced computer-use layer |

## Functional Mapping

| Genspark-like capability | OSS foundation | Product code we still need |
| --- | --- | --- |
| One prompt to many outputs | DeerFlow + Zeropark gateway | Task router, progress stream, artifact registry |
| Deep research with sources | DeerFlow + SearXNG + Crawl4AI | Citation normalization, source trust scoring, report templates |
| Slides | Presenton + DeerFlow | Brand kits, fact-check loop, deck viewer, export UX |
| Sheets | Dify + DeerFlow + Python data tooling | Spreadsheet artifact model, `.xlsx` writer, formula/chart verifier |
| Live dashboards | Dify + Python data tooling | Chart specs, refresh scheduler, share pages |
| Web/browser actions | Browser-use + optional UI-TARS | Browser session manager, allowlists, audit logs |
| RAG and workflow apps | Dify | App registry, workflow import/export, tenant boundary |
| Agent skills | DeerFlow skills + custom markdown skills | Zeropark skill pack, evals, versioning |

## Commercial Launch Checklist

- Confirm every license and NOTICE file from pinned commits.
- Do not remove Dify frontend branding unless allowed by license/commercial agreement.
- Decide whether SearXNG is internal-only, unmodified, or replaced with a permissive search API adapter.
- Add Crawl4AI attribution in product credits and docs if used.
- Keep each external OSS repo pinned by commit/tag for reproducible builds.
- Track modifications to third-party source separately from product code.

