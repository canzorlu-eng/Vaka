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
- Foundation: theme, UI kit, i18n (TR/EN), 4 cases, Landing + Briefing.
- Core sim loop (text): simulation room, phase stepper, vitals, transcript, action dock, patient LLM engine w/ info-gating, exam/test result flow, interactive odontogram.
- Scoring & debrief: 5-dimension deterministic scoring + LLM examiner narrative, full debrief report (score ring, grade, rank, breakdown, history/exam checklists, red flags, test stewardship, dx/tx correctness), copy-summary.
- Voice: Web Speech push-to-talk STT + TTS with graceful text-only fallback.
- Game polish & demo: SVG isometric clinic scene w/ 3 mood states, animated dialogue bubble + Listening pulse, /demo auto-replay.
- **X-ray recognition (Testler phase)**: ordering a radiographic test shows a realistic sample X-ray, multiple-choice "identify the main finding", then correct/incorrect + explanation. Bilingual. Endpoints: `/test` returns spoiler-free xray, `/xray-answer` grades + explains.
- Tested: backend 19/19, frontend full journey 100%.

## Backlog / Remaining (P1/P2)
- P1: Persist X-ray recognition performance into the debrief score/stewardship.
- P1: Richer LLM-based scoring of free-text history (currently keyword checklist).
- P2: More cases; difficulty-scaled rubrics; session resume/history list.
- P2: Full 375px responsive polish pass; dark mode.

## Next Tasks
- Fold X-ray recognition accuracy into Test Stewardship scoring.
- Add per-tooth findings overlay on odontogram from exam results.
