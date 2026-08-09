import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";
import { Footer, LangToggle, Logo } from "../components/Chrome";
import { GameButton } from "../components/GameButton";
import { Check, X, RotateCcw, Home, Copy, AlertTriangle, FlaskConical, ClipboardList } from "lucide-react";

const GRADE_COLOR = { A: "#82C3A6", B: "#5AA0C3", C: "#F0B458", D: "#E89A5B", F: "#E8705B" };

export default function Debrief() {
  const { sid } = useParams();
  const { lang, t } = useLang();
  const navigate = useNavigate();
  const [r, setR] = useState(null);
  const [caseId, setCaseId] = useState(null);

  useEffect(() => {
    api.getSession(sid).then((s) => {
      setCaseId(s.case_id);
      if (s.report) setR(s.report);
      else api.score(sid).then(setR);
    }).catch(() => navigate("/"));
  }, [sid, navigate]);

  const copySummary = () => {
    if (!r) return;
    const lines = [
      `Vaka — ${r.case_title}`,
      `${t("total_score")}: ${r.total}/100  (${r.grade} · ${r.rank})`,
      "",
      t("breakdown") + ":",
      ...r.dimensions.map((d) => `  - ${d.label}: ${d.score}/${d.max}`),
      "",
      `${t("your_diagnosis")}: ${r.diagnosis.chosen || t("none_selected")} (${r.diagnosis.is_correct ? t("correct") : t("incorrect")})`,
      `${t("correct_diagnosis")}: ${r.diagnosis.correct}`,
      `${t("your_treatment")}: ${r.treatment.chosen || t("none_selected")} (${r.treatment.is_correct ? t("correct") : t("incorrect")})`,
      `${t("correct_treatment")}: ${r.treatment.correct}`,
      "",
      t("examiner_narrative") + ": " + r.narrative,
    ];
    navigator.clipboard.writeText(lines.join("\n"));
    toast.success(t("copied"));
  };

  if (!r) return <div className="min-h-screen flex flex-col items-center justify-center gap-3 text-muted-foreground">
    <div className="flex gap-1"><span className="w-2.5 h-2.5 rounded-full bg-primary dot-1" /><span className="w-2.5 h-2.5 rounded-full bg-primary dot-2" /><span className="w-2.5 h-2.5 rounded-full bg-primary dot-3" /></div>
    {t("debrief")}…
  </div>;

  const pct = r.total;
  const gc = GRADE_COLOR[r.grade] || "#E8705B";

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-5 sm:px-10 py-5 max-w-6xl mx-auto w-full">
        <Logo onClick={() => navigate("/")} />
        <LangToggle />
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-5 sm:px-10 pb-14">
        <div className="inline-block bg-accent text-accent-foreground rounded-full px-4 py-1.5 text-xs font-bold mb-2">{t("debrief")}</div>
        <h1 className="font-head font-black text-3xl sm:text-4xl text-fg mb-6">{r.case_title}</h1>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* score column */}
          <aside className="lg:col-span-4 flex flex-col gap-6">
            <div className="card-medkit p-7 text-center animate-pop">
              <ScoreRing pct={pct} color={gc} />
              <div className="mt-4 inline-flex items-center gap-2">
                <span className="font-head font-black text-2xl" style={{ color: gc }}>{r.grade}</span>
                <span className="text-sm font-bold text-fg">· {r.rank}</span>
              </div>
              <p className="text-xs text-muted-foreground font-semibold mt-1">{t("total_score")}</p>
            </div>

            {/* dimensions */}
            <div className="card-medkit p-6">
              <h3 className="font-head font-extrabold text-lg mb-4">{t("breakdown")}</h3>
              <div className="space-y-4">
                {r.dimensions.map((d) => (
                  <div key={d.id} data-testid={`dim-${d.id}`}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-semibold text-fg">{d.label}</span>
                      <span className="font-head font-extrabold text-muted-foreground">{d.score}/{d.max}</span>
                    </div>
                    <div className="h-2.5 rounded-full bg-accent overflow-hidden">
                      <div className="h-full rounded-full transition-all" style={{ width: `${d.pct}%`, background: gc }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <GameButton data-testid="retry-btn" onClick={() => navigate(`/briefing/${caseId}`)} className="w-full flex items-center justify-center gap-2">
                <RotateCcw size={18} /> {t("retry")}
              </GameButton>
              <div className="flex gap-3">
                <GameButton variant="ghost" data-testid="copy-summary-btn" onClick={copySummary} className="flex-1 flex items-center justify-center gap-2 !text-sm">
                  <Copy size={16} /> {t("copy_summary")}
                </GameButton>
                <GameButton variant="accent" data-testid="home-btn" onClick={() => navigate("/")} className="flex-1 flex items-center justify-center gap-2 !text-sm">
                  <Home size={16} /> {t("back")}
                </GameButton>
              </div>
            </div>
          </aside>

          {/* detail column */}
          <div className="lg:col-span-8 flex flex-col gap-6">
            {/* narrative */}
            <div className="card-medkit p-6 bg-accent/40">
              <h3 className="font-head font-extrabold text-lg mb-2 flex items-center gap-2"><ClipboardList size={18} className="text-primary" />{t("examiner_narrative")}</h3>
              <p className="text-fg font-medium leading-relaxed">{r.narrative}</p>
            </div>

            {/* dx / tx */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <DiagCard title={t("your_diagnosis")} chosen={r.diagnosis.chosen} correct={r.diagnosis.correct} ok={r.diagnosis.is_correct}
                correctLabel={t("correct_diagnosis")} none={t("none_selected")} okLabel={t("correct")} badLabel={t("incorrect")} />
              <DiagCard title={t("your_treatment")} chosen={r.treatment.chosen} correct={r.treatment.correct} ok={r.treatment.is_correct}
                correctLabel={t("correct_treatment")} none={t("none_selected")} okLabel={t("correct")} badLabel={t("incorrect")} />
            </div>

            {/* red flags */}
            {r.red_flags.length > 0 && (
              <div className="card-medkit p-6">
                <h3 className="font-head font-extrabold text-lg mb-3 flex items-center gap-2"><AlertTriangle size={18} className="text-[#E8705B]" />{t("red_flags")}</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {r.red_flags.map((f, i) => (
                    <div key={i} data-testid={`redflag-${i}`} className={`flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium ${f.caught ? "bg-secondary/15 text-secondary" : "bg-[#E8705B]/12 text-[#E8705B]"}`}>
                      {f.caught ? <Check size={16} /> : <X size={16} />} {f.label}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* checklists */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Checklist title={t("history_checklist")} items={r.history_checklist.map((h) => ({ label: h.label, ok: h.asked }))} okLabel={t("asked")} noLabel={t("missed")} />
              <Checklist title={t("exam_checklist")} items={r.exam_checklist.map((e) => ({ label: e.label, ok: e.done }))} okLabel={t("done")} noLabel={t("missed")} />
            </div>

            {/* test stewardship */}
            <div className="card-medkit p-6">
              <h3 className="font-head font-extrabold text-lg mb-3 flex items-center gap-2"><FlaskConical size={18} className="text-secondary" />{t("test_stewardship")}</h3>
              <TestGroup label={t("correct_tests")} items={r.test_stewardship.ordered_indicated} tone="ok" />
              <TestGroup label={t("missed_tests")} items={r.test_stewardship.missed_indicated} tone="warn" />
              <TestGroup label={t("over_tests")} items={r.test_stewardship.over_ordered} tone="bad" />
            </div>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

function ScoreRing({ pct, color }) {
  const R = 54, C = 2 * Math.PI * R;
  const off = C - (pct / 100) * C;
  return (
    <div className="relative w-40 h-40 mx-auto">
      <svg viewBox="0 0 128 128" className="w-full h-full -rotate-90">
        <circle cx="64" cy="64" r={R} fill="none" stroke="#F0E7DB" strokeWidth="12" />
        <circle cx="64" cy="64" r={R} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={off} style={{ transition: "stroke-dashoffset 1s ease" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span data-testid="total-score" className="font-head font-black text-4xl text-fg">{pct}</span>
        <span className="text-xs text-muted-foreground font-bold">/ 100</span>
      </div>
    </div>
  );
}

function DiagCard({ title, chosen, correct, ok, correctLabel, none, okLabel, badLabel }) {
  return (
    <div className="card-medkit p-5">
      <div className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-1">{title}</div>
      <div className="flex items-center gap-2 mb-2">
        <span className={`w-6 h-6 rounded-full flex items-center justify-center text-white ${ok ? "bg-secondary" : "bg-[#E8705B]"}`}>
          {ok ? <Check size={14} /> : <X size={14} />}
        </span>
        <span className="font-head font-bold text-fg text-sm">{chosen || none}</span>
      </div>
      <span className={`text-xs font-bold ${ok ? "text-secondary" : "text-[#E8705B]"}`}>{ok ? okLabel : badLabel}</span>
      {!ok && <p className="text-xs text-muted-foreground mt-1">{correctLabel}: <span className="font-semibold text-fg">{correct}</span></p>}
    </div>
  );
}

function Checklist({ title, items, okLabel, noLabel }) {
  return (
    <div className="card-medkit p-5">
      <h3 className="font-head font-extrabold text-base mb-3">{title}</h3>
      <div className="space-y-2">
        {items.map((it, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <span className={`w-5 h-5 rounded-full flex items-center justify-center text-white shrink-0 ${it.ok ? "bg-secondary" : "bg-border"}`}>
              {it.ok ? <Check size={12} /> : <X size={12} />}
            </span>
            <span className={`font-medium ${it.ok ? "text-fg" : "text-muted-foreground line-through"}`}>{it.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TestGroup({ label, items, tone }) {
  if (!items || items.length === 0) return null;
  const color = tone === "ok" ? "#82C3A6" : tone === "warn" ? "#F0B458" : "#E8705B";
  return (
    <div className="mb-3 last:mb-0">
      <div className="text-xs font-bold mb-1" style={{ color }}>{label}</div>
      <div className="flex flex-wrap gap-2">
        {items.map((it, i) => (
          <span key={i} className="text-xs font-semibold px-3 py-1 rounded-full" style={{ background: `${color}22`, color }}>{it}</span>
        ))}
      </div>
    </div>
  );
}
