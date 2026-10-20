# Vaka: Product Requirements for Automated Testing

Vaka is a bilingual (Turkish default, English) web app where dental students practise clinical reasoning with an
AI-driven virtual patient. Live app: https://vaka-z1na.onrender.com . It is an educational tool, not a clinical decision aid.

## Personas
- **Visitor** (not signed in): browses topics and cases, plays the scripted demo, reads pricing and legal pages.
- **Student** (signed in with Google): starts case sessions, talks to the patient, examines, orders tests, commits a diagnosis and
  treatment, receives a scored debrief. Free plan: 3 sessions per month.
- **Admin / Pro**: unlimited-ish quotas (60 sessions per month) and AI-generated cases.

## Product map (routes)
| Route | Purpose | Needs sign-in |
|---|---|---|
| `/` | Landing: hero, stats (139 cases / 11 specialties / 3 levels), topic grid, "how it works" | no |
| `/topic/:id` | Case list for a specialty, difficulty filter, "load more" | no |
| `/briefing/:caseId` | Patient card, vitals, scoring dimensions, Start button | viewing no, starting yes |
| `/sim/:sessionId` | The encounter (5 phases) | yes |
| `/debrief/:sessionId` | Scored report | yes |
| `/demo` | Scripted replay of a case with a patient conversation | no |
| `/pricing` | Free vs Pro, monthly/yearly, USD/TRY | no |
| `/account` | Profile, usage, history, data export, account deletion | yes |
| `/legal/terms`, `/legal/privacy`, `/legal/refund` | Draft legal pages | no |
| `/api/health`, `/api/ready`, `/api/topics`, `/api/topics/:id/cases` | Public API | no |

## Acceptance criteria

### Landing and navigation
1. The landing page shows the headline "Sanal hastayla klinik pratik." in Turkish and "Practise with a virtual patient." after switching language with the TR | EN toggle; the choice persists after reload.
2. Exactly 11 topic cards are shown (Endodonti, Periodontoloji, Ağız Diş ve Çene Cerrahisi, Ağız Patolojisi ve Oral Tıp, Restoratif Diş Tedavisi, Protetik Diş Tedavisi, Pedodonti, Ortodonti, Travma ve Acil, Sistemik Hastalıklar ve İlaçlar, Orofasiyal Ağrı ve TMD). Their case counts sum to 139. Each card shows a difficulty distribution bar.
3. Clicking a topic card opens `/topic/<id>`; the "Konulara Dön" link returns to `/`.
4. "Konulara göz at" scrolls to the topic grid. The Demo button opens `/demo`.

### Topic page
5. The header shows the topic name and blurb. Filter tabs are Tümü / Kolay / Orta / Zor, each with a count; selecting one filters the cards to that difficulty only and the Tümü count equals the topic total.
6. Every case card shows title, patient name and age, a quoted chief complaint and a difficulty badge. Clicking opens `/briefing/<caseId>`.
7. When a topic has more cases than the page size, "Daha fazla göster" (load more) appends further cases without duplicates.

### Briefing and sign-in gate
8. The briefing shows the patient (name, age, sex, setting), chief complaint, four vitals (BP, HR, temperature, SpO₂) and five scoring dimensions worth 25, 20, 15, 25 and 15 points (100 total).
9. As a visitor the primary button reads "Başlamak için giriş yap" and redirects to Google sign-in; as a signed-in student it reads "Başla" and opens a simulation.

### Simulation (signed in)
10. A phase stepper shows 5 phases: Anamnez, Klinik Muayene, Testler, Tanı, Tedavi Planı. The "Sonraki aşama" button on the right names the next phase and moves to it; on the last phase it is absent.
11. In the Anamnez phase an empty chat offers suggested questions; clicking one sends it as a student message and a patient reply appears within about 30 seconds.
12. Typing a question and pressing Enter or the send button appends the student message and then a patient reply. Empty input cannot be sent.
13. In Klinik Muayene, exam action buttons add a result card to the transcript and mark the button done; the progress panel (desktop) updates counts such as 1/5.
14. In Testler, ordering a test adds a result card and an indicated / not indicated badge.
15. In Tanı and Tedavi Planı the student selects exactly one option per phase; the selection is highlighted.
16. "Görüşmeyi Bitir" ends the encounter and opens the debrief.

### Debrief
17. The debrief shows a total score out of 100 with a grade, a per-dimension breakdown whose maxima are 25/20/15/25/15, the chosen vs correct diagnosis and treatment, red flags and checklists. "Özeti Kopyala" copies a text summary; "Tekrar Dene" starts the case again.

### Demo (no sign-in)
18. `/demo` plays a scripted encounter: messages appear progressively, "Baştan Oynat" restarts, and no sign-in is required.

### Pricing
19. The yearly option shows $108 struck through and $90 emphasised with a savings badge; the monthly option shows $9. A USD / TRY switch changes the currency. The Free card lists 3 sessions per month.
20. While billing is not yet connected the Pro button is disabled or labelled unavailable; no payment form is ever shown.

### Access control and API
21. `GET /api/health` returns 200 `{"status":"ok"}`; `GET /api/ready` returns 200 with `database: true` and `cache: true`.
22. `GET /api/topics` returns 11 topics, each with `count` and `levels.easy|moderate|hard`; counts sum to 139.
23. Protected endpoints (`POST /api/sessions`, `GET /api/account/export`) return 401 without a session; unknown case ids return 404.
24. Responses carry `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY`.

### Responsive layout
25. At 375 px and 768 px widths there is no horizontal scrolling on any public page; on narrow screens the simulation shows a compact stepper ("Anamnez 1 / 5") instead of five circles.

## Safe-testing rules (important)
- **Never** click "Hesabı Sil" / delete account, and do not export data. These are destructive or privacy-relevant.
- Do not generate AI cases ("Yapay zeka ile yeni vaka"), and keep real AI conversations short (at most 3 patient messages per test): every reply costs money.
- Do not attempt checkout or subscription actions.
- Use only the dedicated test Google account for sign-in.
