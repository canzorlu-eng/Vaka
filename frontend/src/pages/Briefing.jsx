import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";
import { Footer, LangToggle, Logo } from "../components/Chrome";
import { GameButton } from "../components/GameButton";
import { VitalsStrip } from "../components/VitalsStrip";
import { ClinicScene } from "../components/ClinicScene";
import { ArrowLeft, MapPin, User, Play } from "lucide-react";

const DIMS = [
  { key: "phase_anamnez", w: 25, c: "#FF937B" },
  { key: "phase_muayene", w: 20, c: "#82C3A6" },
  { key: "phase_testler", w: 15, c: "#F0B458" },
  { key: "phase_tani", w: 25, c: "#5AA0C3" },
  { key: "phase_tedavi", w: 15, c: "#C08BD9" },
];

export default function Briefing() {
  const { lang, t } = useLang();
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [c, setC] = useState(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    api.caseDetail(caseId, lang).then(setC).catch(() => navigate("/"));
  }, [caseId, lang, navigate]);

  const start = async () => {
    setStarting(true);
    try {
      const s = await api.createSession(caseId, lang);
      navigate(`/sim/${s.id}`);
    } catch (e) { setStarting(false); }
  };

  if (!c) return <div className="min-h-screen flex items-center justify-center text-muted-foreground">…</div>;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-5 sm:px-10 py-5 max-w-6xl mx-auto w-full">
        <Logo onClick={() => navigate("/")} />
        <LangToggle />
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-5 sm:px-10 pb-14">
        <button data-testid="briefing-back" onClick={() => navigate("/")} className="flex items-center gap-1 text-sm font-bold text-muted-foreground hover:text-primary mb-5">
          <ArrowLeft size={16} /> {t("back_to_cases")}
        </button>

        <div className="inline-block bg-accent text-accent-foreground rounded-full px-4 py-1.5 text-xs font-bold mb-3">{t("briefing")}</div>
        <h1 className="font-head font-black text-3xl sm:text-4xl text-fg mb-8">{c.title}</h1>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 animate-fade-up">
          {/* patient card */}
          <div className="lg:col-span-3 card-medkit overflow-hidden">
            <div className="h-56 bg-accent relative">
              <ClinicScene mood={c.patient.avatar_mood} />
            </div>
            <div className="p-6">
              <div className="flex items-center gap-2 text-primary font-bold text-sm mb-1"><User size={16} /> {t("patient")}</div>
              <h2 className="font-head font-extrabold text-2xl text-fg">{c.patient.name}</h2>
              <p className="text-sm text-muted-foreground font-semibold mb-4">{c.patient.age} {t("age").toLowerCase()} · {c.patient.sex}</p>

              <div className="bg-accent/60 rounded-2xl p-4 mb-4">
                <div className="text-xs font-bold text-accent-foreground uppercase tracking-wide mb-1">{t("chief_complaint")}</div>
                <p className="text-fg font-medium italic">“{c.chief_complaint}”</p>
              </div>

              <div className="flex items-center gap-2 text-sm text-muted-foreground mb-4"><MapPin size={15} className="text-secondary" /> {c.patient.setting}</div>
              <VitalsStrip vitals={c.vitals} />
            </div>
          </div>

          {/* scoring dims + start */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            <div className="card-medkit p-6">
              <h3 className="font-head font-extrabold text-lg text-fg mb-4">{t("scoring_dims")}</h3>
              <div className="space-y-3">
                {DIMS.map((d) => (
                  <div key={d.key} className="flex items-center gap-3">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ background: d.c }} />
                    <span className="flex-1 text-sm font-semibold text-fg">{t(d.key)}</span>
                    <span className="text-sm font-head font-extrabold text-muted-foreground">{d.w} pt</span>
                  </div>
                ))}
              </div>
            </div>
            <GameButton data-testid="start-case-btn" onClick={start} disabled={starting} className="w-full flex items-center justify-center gap-2 !py-4 !text-lg">
              <Play size={20} fill="#fff" /> {starting ? "…" : t("start")}
            </GameButton>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}
