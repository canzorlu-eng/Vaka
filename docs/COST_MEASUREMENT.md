# AI cost of one end-to-end run (measured 2026-10-20)

Measured with `backend/scripts/cost_probe.py`: a real run through the real API (in-process), costs taken from the
`llm_usage` ledger the app itself writes. Prices: Gemini `gemini-3.5-flash-lite` $0.30 in / $2.50 out per 1M tokens
(ai.google.dev/gemini-api/docs/pricing, read 2026-10-20); OpenAI `tts-1` $15 per 1M characters (third-party mirrors,
openai.com returned 403 - verify). Re-run the probe after any model/price change.

## Result (model `gemini-3.5-flash-lite`, voice `tts-1`)

| Scenario | Cost | Wall time |
|---|---|---|
| Practice run on an authored case: 12 questions, 12 voiced patient replies, 4 exams, 3 tests, diagnosis, scoring + feedback | **$0.0152** | 40 s |
| Same run **without** server voice (browser voice, free plan) | **$0.0028** | ~20 s |
| AI-generated case (one generation job) | **$0.0035** | 10 s |
| Playing a generated case (8 questions, voiced) | $0.0137 | 40 s |
| **New AI case + playing it** | **$0.0172** | |

Breakdown of the $0.0152 run: chat $0.0024 (12 calls, 5.9k input / 0.25k output tokens, ~1.1 s each), coverage $0.0001,
narrative $0.0003, **TTS $0.0124 (82 %)** for 824 characters.

## Models that were NOT usable with the current key
- `gemini-3.8-flash`: works but "thinks" ~350 tokens per reply -> ~12 s latency per patient reply and ~8x the chat cost.
  Unsuitable for a conversational simulator unless `GEMINI_THINKING_BUDGET=0`.
- `gemini-3.6-flash`, `gemini-3.5-flash`: 429 RESOURCE_EXHAUSTED (the key is on the free tier with exhausted quota).
  `gemini-3.5-flash` is not on the public price list at all, so its cost cannot be tracked reliably.
- 3.6/3.8 Flash prices double on 2027-01-01 ($1.50 in / $7.50 out).
- IMPORTANT: free-tier Gemini data may be used to improve Google products. Enable billing (paid tier) before real users.

## Margin model
- COGS per Pro user at the full quota (60 sessions + 10 generations, all voiced): 60 x 0.0152 + 10 x 0.0035 = **~$0.95 / month**
  vs $9 revenue (before payment-provider fees, which are not public for iyzico subscriptions - ask them).
- Break-even sessions per month at $9: ~590 (the plan cap is 60). Yearly plan ($90 = $7.50/month) is still ~85 % gross margin at full use.
- Free user (3 sessions, no server voice): ~$0.008 / month.
- Worst-case abuse is bounded by guard rails: per-user daily cap ($0.25 free / $1.50 pro), monthly cap ($0.15 / $4.00),
  40 messages per session, rate limits, per-user concurrency of 2 AI calls, 60-session monthly quota, global daily alert ($20).

## Levers if you want to lower cost
1. Voice is the cost driver. Options: keep it Pro-only (current), voice only for the first N replies, or a cheaper provider
   (Gemini TTS 3.8 Flash-Lite is ~$0.008 for the same audio today but doubles in 2027; gpt-4o-mini-tts ~$0.014).
2. A stronger model only for rare, quality-critical work: `GEMINI_MODEL_GENERATION` / `GEMINI_MODEL_SCORING`
   (chat stays on the fast model). Measure with the probe first.
3. Do not add caching for chat: replies are unique. TTS audio is cached in Redis by content for 7 days (hits only on repeated text).
