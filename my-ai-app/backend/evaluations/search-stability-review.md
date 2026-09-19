# Search stability — 2026-09-11

Changes: unified rule-based search gate; fixed invalid Asia/Ha_Noi timezone to Asia/Ho_Chi_Minh; bounded two-attempt/10-second search requests; validated response schema and providers; deduplicated usable HTTP(S) results; separate publication/retrieval dates; filtered dated stale/future results for current queries; search metadata on both chat API paths; frontend source-count/unavailable/outdated status without URLs in speech.

Validation: 215 backend tests and 42 frontend tests passed. Tests cover 403/503/timeouts, malformed results, duplicates, unknown dates, stale-only results, exact currency/TFT wording, and metadata on both regular/streaming API routes. Final frontend build and lint also passed; the existing Live2D chunk-size advisory remains.

Live check: scripts/verify_search.py routed both sample questions to search, but both returned connection_error after two attempts (about 164–168 ms). The raw report is search-verification.json. Docker daemon was found stopped; Docker Desktop was started and docker ps confirmed searxng-searxng-1 listening on port 8080 plus searxng-redis-1 running. The subsequent HTTP verification was rejected by the user, so source retrieval after restart is not verified. Do not interpret a running container as proof of successful search.

Limits: unknown publication dates cannot establish freshness; the generative answer still needs to interpret snippets correctly. Full page reading/cross-source factual verification is outside this chat-path change. No visual browser test or live final-answer evaluation was performed. Docker remains a separate runtime prerequisite.
