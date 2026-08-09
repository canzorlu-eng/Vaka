# Vaka — Voice-Based Virtual Patient Simulator (PRD)

## Problem Statement
Bilingual (Turkish default / English) web app where dental students run a full clinical encounter with an AI-driven virtual patient across 5 phases (Anamnez → Klinik Muayene → Testler → Tanı → Tedavi Planı), then receive an examiner-style, rubric-scored debrief. Warm, playful "medkit+" pastel game aesthetic. Includes a hands-off /demo replay.

## Architecture
- Frontend: React (JS/JSX), Tailwind, custom medkit+ UI kit, SVG clinic scene + odontogram, react-router, sonner toasts, Web Speech API (STT/TTS).
- Backend: FastAPI, all `/api`-prefixed. Patient dialogue + scoring engines server-side.
- DB: MongoDB (sessions, reports). Cases seeded in code (`cases_seed.py`).
- AI: Gemini (`gemini-3-flash-preview`) via EMERGENT_LLM_KEY — in-character patient (info-gated) + examiner narrative, with deterministic scoring fallback.
- Auth: none (anonymous sessions).

## User Personas
- Dental students (primary): practice clinical reasoning safely/repeatably.
- Educators / judges: view the /demo replay.

## Core Requirements (static)
- 4 seeded cases, TR/EN toggle everywhere, footer disclaimer on every page.
- Landing → Briefing → Simulation (chat + exams + tests + commit dx/tx) → Debrief → Retry.
- Info-gating: patient reveals a fact only when the topic is asked.
- Deterministic scoring so debrief never crashes.

## Implemented (2026-06)
- Foundation, core sim loop, scoring & debrief, voice, game polish & /demo (see below).
- **Voice upgraded to natural OpenAI TTS** (`tts-1`, voice `coral`) via EMERGENT_LLM_KEY; browser Web Speech kept as graceful fallback and for push-to-talk STT.
- **X-ray recognition** in Testler with a vetted shared library (`xray_library.py`, 10 radiographs) reused by authored + generated cases.
- **X-ray reading scored**: Test Stewardship blends test-ordering (60%) + X-ray reading accuracy (40%); debrief shows an X-ray Reading sub-section (correct/incorrect/unanswered + score).
- **Two radiographs per case** for multi-finding practice.
- **Tooth Findings Map**: exam results drop coloured markers (finding/normal/neutral) on the matching odontogram tooth.
- **10 authored cases** + **LLM 'Generate new case'** button (landing) creating fresh cases on demand, X-rays chosen from the library, stored in Mongo (`generated_cases`) and loaded on startup.
- Tested: iteration_1 (MVP) 19/19 backend + full frontend; iteration_2 (new features) 11/11 backend + full frontend. No open bugs.

## Backlog / Remaining (P1/P2)
- P1: Richer LLM-based scoring of free-text history (currently keyword checklist).
- P2: Persist a student's session history / leaderboard; difficulty-scaled rubrics.
- P2: Full 375px responsive polish pass; dark mode.

## Next Tasks
- Fold X-ray recognition accuracy into Test Stewardship scoring.
- Add per-tooth findings overlay on odontogram from exam results.
