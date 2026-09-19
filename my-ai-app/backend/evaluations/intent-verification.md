# Contextual intent routing — 2026-09-11

Validation: 195 backend unit/integration tests passed. Cases include current TFT questions, opinions, emotional sharing, memory/action routing, contextual follow-ups, duplicate current-turn removal, scoped history, malformed/low-confidence model output, rejected assistant references, timeouts, and Ollama request parameters.

Read-only Ollama probe results are preserved in intent-verification.json. Clear intents used rules in 0–1 ms. The ambiguous model path took about 5–8 seconds; the Obsidian follow-up timed out and the TFT follow-up used the contextual fallback. Missing referent was classified as clarification by the model. After this probe, a tested fallback was added for explicitly named products such as Obsidian, so its final fallback now selects web search rather than clarification. That final addition was unit-tested, not re-probed with Ollama.

No browser interaction or full final-answer model evaluation was performed. These checks establish routing behaviour, not perfect semantic intent recognition or factual answer correctness. Multiple intents, quotations, negations and multiword product names remain limited by the fast-path rules. The classifier does not replace existing tool authorization or memory retrieval.
