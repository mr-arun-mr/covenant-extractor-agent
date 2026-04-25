# Model Alternatives — Covenant Extractor Agent

Comparison of LLM alternatives to the current `claude-sonnet-4-6` for running the covenant extraction agent. Covers accuracy, cost, integration effort, and recommended use cases.

> **Pricing note:** All prices are approximate as of mid-2025. Verify current rates at each provider's pricing page before committing to a model in production.

---

## What the Agent Demands from a Model

The agent runs a structured multi-round tool-use loop over legal PDF content. A suitable model must:

| Requirement | Why it matters |
|---|---|
| **Native tool use** | The agent loop depends on structured tool calls and results |
| **Long context (≥ 128K tokens)** | Conversation history grows to 50K–100K tokens for large agreements |
| **Instruction following** | Must execute a fixed 6-step workflow reliably, every run |
| **JSON schema compliance** | Final output must pass Pydantic validation without correction |
| **Legal domain comprehension** | Covenants use precise, nested legal language with cross-references |
| **Determinism** | `temperature=0` must produce stable output across runs |

---

## Model Overview

### Anthropic — Claude Family

| Model | Context | Accuracy tier | Tool use |
|---|---|---|---|
| `claude-opus-4-7` | 200K | Excellent | Native |
| `claude-sonnet-4-6` *(current)* | 200K | Very Good | Native |
| `claude-haiku-4-5` | 200K | Good | Native |

**Strengths across the Claude family:**
- Prompt caching on system prompt reduces per-run cost on repeated runs
- Anthropic SDK already integrated — zero migration effort
- Consistent instruction following and schema compliance
- 200K context handles even large agreement history without truncation

---

### `claude-opus-4-7` — Highest accuracy, highest cost

**Accuracy:** Excellent  
Best legal comprehension in the Claude family. Handles deeply nested covenants, complex amendment chains, and ambiguous cross-references more reliably than Sonnet. Recommended when extraction errors carry significant downstream risk (e.g., automated compliance workflows).

**Accuracy advantages over Sonnet:**
- Lower hallucination rate on numeric thresholds
- Better at resolving conflicting or ambiguous clause language
- More reliable when covenants span multiple cross-referenced sections

**Migration effort:** Change one constant in `agent.py`:
```python
MODEL = "claude-opus-4-7"
```

**Cost:**

| Agreement size | Estimated cost |
|---|---|
| Small (50 pages, ~15 covenants) | ~$3.54 |
| Medium (150 pages, ~25 covenants) | ~$9.19 |
| Large (300 pages, ~40 covenants) | ~$22.43 |

**When to use:** High-stakes covenant extraction where a human review step costs more than the model price difference. Syndicated loans, regulatory filings, M&A due diligence.

---

### `claude-haiku-4-5` — Lowest cost in the Claude family

**Accuracy:** Good (sufficient for standard agreements)  
Handles well-structured, standard-form agreements reliably. Risk increases with atypical covenant structures, heavily amended documents, or agreements with many cross-references. May require an additional validation pass for complex cases.

**Known limitations for this task:**
- Higher miss rate on covenants embedded in definitions or recitals
- May produce slightly less precise `obligation_text` (paraphrasing instead of verbatim)
- Less reliable on unusual threshold structures (tiered ratios, step-downs)

**Migration effort:** Change one constant in `agent.py`:
```python
MODEL = "claude-haiku-4-5"
```

**Cost:**

| Agreement size | Estimated cost |
|---|---|
| Small (50 pages, ~15 covenants) | ~$0.19 |
| Medium (150 pages, ~25 covenants) | ~$0.49 |
| Large (300 pages, ~40 covenants) | ~$1.20 |

**When to use:** High-volume batch processing of standard-form agreements (e.g., LSTA/LMA template loans). Consider a Haiku first-pass → Sonnet validation pattern.

---

### OpenAI — GPT-4o Family

| Model | Context | Accuracy tier | Tool use |
|---|---|---|---|
| `gpt-4o` | 128K | Very Good | Native function calling |
| `gpt-4o-mini` | 128K | Fair | Native function calling |
| `o4-mini` | 128K | Very Good | Native function calling |

**Migration effort:** Medium — requires replacing the Anthropic SDK with the OpenAI SDK, adapting the tool definition format (OpenAI uses `functions` schema), and updating `agent.py`'s message loop. The tool definition JSON schemas are similar but not identical.

**No prompt caching benefit** without additional engineering (OpenAI's caching applies automatically at 50% discount on cached prefix portions, but requires stable prefix ordering — achievable with minor refactoring).

---

### `gpt-4o` — Closest GPT alternative to Sonnet

**Accuracy:** Very Good  
Strong instruction following and JSON schema compliance. Slightly lower legal domain depth than Claude Sonnet on highly complex clause structures, but close enough for most standard agreements. Context window (128K) is sufficient for most agreements but may truncate conversation history for very large (300+ page) documents near the end of extraction.

**Cost:**

| Agreement size | Estimated cost |
|---|---|
| Small (50 pages, ~15 covenants) | ~$0.57 |
| Medium (150 pages, ~25 covenants) | ~$1.50 |
| Large (300 pages, ~40 covenants) | ~$3.69 |

**When to use:** Teams already standardised on OpenAI infrastructure who want Sonnet-level accuracy.

---

### `gpt-4o-mini` — Cheapest viable GPT option

**Accuracy:** Fair  
Adequate for simple, well-structured agreements. Not recommended for production use on complex or heavily amended documents without a post-processing validation layer. JSON schema compliance is less consistent — may require more validation retries.

**Cost:**

| Agreement size | Estimated cost |
|---|---|
| Small (50 pages, ~15 covenants) | ~$0.03 |
| Medium (150 pages, ~25 covenants) | ~$0.09 |
| Large (300 pages, ~40 covenants) | ~$0.22 |

**When to use:** Pre-screening or triage pass (e.g., classify covenant type before full extraction). Not recommended as a sole extraction model.

---

### `o4-mini` — Reasoning model for complex agreements

**Accuracy:** Very Good  
OpenAI's compact reasoning model. The chain-of-thought reasoning helps with ambiguous or nested covenant structures. Slower than GPT-4o (internal reasoning tokens add latency) but substantially cheaper than `o3`. Does not outperform Sonnet for straightforward agreements — the reasoning overhead adds cost without benefit there.

**Cost:**

| Agreement size | Estimated cost |
|---|---|
| Small (50 pages, ~15 covenants) | ~$0.25 |
| Medium (150 pages, ~25 covenants) | ~$0.66 |
| Large (300 pages, ~40 covenants) | ~$1.62 |

**When to use:** Agreements with complex or novel covenant structures where standard models produce errors. The reasoning capability helps resolve ambiguities in threshold definitions and condition precedents.

---

### Google — Gemini Family

| Model | Context | Accuracy tier | Tool use |
|---|---|---|---|
| `gemini-2.5-pro` | 1M+ | Very Good | Native function calling |
| `gemini-2.0-flash` | 1M | Good | Native function calling |

**Migration effort:** Medium — requires the `google-generativeai` SDK and adapting the tool schema format. Gemini's 1M+ token context window is a significant advantage for very large agreements: the growing conversation history never approaches the limit.

---

### `gemini-2.5-pro` — Best context window, competitive accuracy

**Accuracy:** Very Good  
Strong legal comprehension and instruction following. The 1M token context window eliminates any risk of history truncation, even for 500-page agreements extracted page by page. JSON schema compliance is good but occasionally requires a retry on complex nested structures.

**Cost:**

| Agreement size | Estimated cost |
|---|---|
| Small (50 pages, ~15 covenants) | ~$0.31 |
| Medium (150 pages, ~25 covenants) | ~$0.80 |
| Large (300 pages, ~40 covenants) | ~$1.92 |

**When to use:** Very large credit agreements (300+ pages) or portfolios of agreements where context window overflow is a concern. Also a strong cost/accuracy choice for teams on Google Cloud.

---

### `gemini-2.0-flash` — Lowest cost overall

**Accuracy:** Good (for simple agreements)  
Very fast and extremely cheap. Acceptable accuracy on standard LSTA/LMA form agreements. Similar limitations to GPT-4o-mini on complex structures. The 1M context window is a notable advantage over mini/haiku class models.

**Cost:**

| Agreement size | Estimated cost |
|---|---|
| Small (50 pages, ~15 covenants) | ~$0.02 |
| Medium (150 pages, ~25 covenants) | ~$0.06 |
| Large (300 pages, ~40 covenants) | ~$0.15 |

**When to use:** Batch preprocessing of large portfolios, or triage pass before a more capable model handles flagged agreements.

---

## Full Cost Comparison

All figures in USD. Token volumes derived from agent profiling on representative agreements (see [Cost Analysis](#cost-analysis) section).

| Model | Small (50p) | Medium (150p) | Large (300p) | $/page (medium) |
|---|---|---|---|---|
| `claude-opus-4-7` | $3.54 | $9.19 | $22.43 | $0.061 |
| `claude-sonnet-4-6` | $0.71 | $1.84 | $4.49 | $0.012 |
| `gpt-4o` | $0.57 | $1.50 | $3.69 | $0.010 |
| `o4-mini` | $0.25 | $0.66 | $1.62 | $0.004 |
| `gemini-2.5-pro` | $0.31 | $0.80 | $1.92 | $0.005 |
| `claude-haiku-4-5` *(current)* | $0.19 | $0.49 | $1.20 | $0.003 |
| `gpt-4o-mini` | $0.03 | $0.09 | $0.22 | $0.001 |
| `gemini-2.0-flash` | $0.02 | $0.06 | $0.15 | $0.000 |

**Why input cost dominates:** The agent resends the full conversation history every round. By round 17 of a medium extraction, the context reaches ~45K tokens and is sent again each round. This makes the input token price the primary lever, not output price.

---

## Accuracy Comparison

Assessed across four dimensions relevant to covenant extraction:

| Model | Legal comprehension | Schema compliance | Amendment detection | Complex clauses |
|---|---|---|---|---|
| `claude-opus-4-7` | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ |
| `claude-sonnet-4-6` | ★★★★☆ | ★★★★★ | ★★★★☆ | ★★★★☆ |
| `gpt-4o` | ★★★★☆ | ★★★★☆ | ★★★★☆ | ★★★★☆ |
| `gemini-2.5-pro` | ★★★★☆ | ★★★★☆ | ★★★☆☆ | ★★★★☆ |
| `o4-mini` | ★★★★☆ | ★★★★☆ | ★★★☆☆ | ★★★★★ |
| `claude-haiku-4-5` | ★★★☆☆ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ |
| `gpt-4o-mini` | ★★☆☆☆ | ★★★☆☆ | ★★☆☆☆ | ★★☆☆☆ |
| `gemini-2.0-flash` | ★★★☆☆ | ★★★☆☆ | ★★☆☆☆ | ★★☆☆☆ |

> **Amendment detection** refers to the model correctly interpreting `red_spans` and `strikethrough_spans` from tool results and mapping them to the `is_amended` / `amendment` schema fields. This is instruction-following, not vision — the PDF tool does the detection; the model interprets the structured output.

---

## Recommendation Matrix

| Scenario | Recommended model | Reason |
|---|---|---|
| Production, standard agreements | `claude-sonnet-4-6` | Proven, reliable, manageable cost |
| Highest accuracy required | `claude-opus-4-7` | Best legal comprehension |
| Already on OpenAI stack | `gpt-4o` | Near-Sonnet accuracy, similar cost |
| Very large agreements (300+ pages) | `gemini-2.5-pro` | 1M context; no truncation risk |
| High-volume batch, standard forms | `claude-haiku-4-5` | 4× cheaper than Sonnet, acceptable accuracy |
| Complex / novel covenant structures | `o4-mini` | Reasoning helps with ambiguity |
| Triage / pre-screening pass | `gemini-2.0-flash` or `gpt-4o-mini` | Minimal cost, flag for human review |
| Zero cloud cost tolerance | Self-hosted Llama 3.1 405B | Open-weight; requires on-prem GPU infra |

---

## Cost Analysis

Token volumes used in the cost model above. Methodology: agent loop was instrumented and run against the sample agreement; volumes were then scaled linearly for medium and large agreements.

| Component | Tokens (medium run) | Notes |
|---|---|---|
| System prompt (cached) | 1,229 | Written once, read 16× |
| Tool definitions | 479 per round | Not cached; resent every round |
| `get_pdf_structure` result | ~3,000 | Scales with document section count |
| `extract_pdf_pages` per 10 pages | ~6,000 | ~600 tokens/page of legal text |
| `validate_covenants` result | ~7 | Tiny — just status + count |
| `lookup_source_clause` result | ~150 | Per lookup call |
| Final JSON output | ~179 per covenant | Pydantic-serialised schema |

**Key cost driver:** Cumulative input grows quadratically with rounds. A 17-round medium extraction accumulates ~560K total input tokens because every round resends the full history.

### Reducing cost

1. **Batch more pages per call** — increase from 10 to 20 pages per `extract_pdf_pages` call, halving extraction rounds and the quadratic growth.
2. **Cache tool results** — apply `cache_control: ephemeral` to stable early tool results (structure + first extraction pages) in the Anthropic SDK. Saves ~$0.30–0.50 per medium run.
3. **Two-model pipeline** — use `claude-haiku-4-5` or `gemini-2.0-flash` for extraction, then `claude-sonnet-4-6` only for final structuring and validation. Cuts cost by 50–70% with minimal accuracy loss on standard agreements.
4. **Truncate history** — keep only the last N tool results in the message history rather than the full accumulation. Requires careful prompt engineering to avoid losing covenant context.

---

## Integration Notes

Switching from the Anthropic SDK to another provider requires changes in `agent.py`:

```
Files to change:
  agent.py          — SDK import, client init, message format, tool schema format
  tools/__init__.py — tool definition dicts (schema field names differ by provider)
```

The tool *implementations* (`tools/pdf_tools.py`, `tools/validation_tools.py`) and the `schema/` models are provider-agnostic and require no changes.

A unified-API library such as [LiteLLM](https://github.com/BerriAI/litellm) can abstract provider differences and allow A/B testing across models with minimal code changes.
