import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";
import { Footer, LangToggle, Logo } from "../components/Chrome";
import { GameButton } from "../components/GameButton";
import { PlayCircle, ArrowRight, Stethoscope } from "lucide-react";

const DIFF_COLOR = { easy: "#82C3A6", moderate: "#F0B458", hard: "#E8705B" };
const MOOD_EMOJI = { neutral: "🙂", pain: "😣", anxious: "😰" };

export default function Landing() {
  const { lang, t } = useLang();
  const navigate = useNavigate();
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.listCases(lang).then((d) => { setCases(d); setLoading(false); }).catch(() => setLoading(false));
  }, [lang]);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-5 sm:px-10 py-5 max-w-6xl mx-auto w-full">
        <Logo onClick={() => navigate("/")} />
        <div className="flex items-center gap-3">
          <GameButton variant="secondary" data-testid="demo-link" className="!px-4 !py-2 !text-sm flex items-center gap-2" onClick={() => navigate("/demo")}>
            <PlayCircle size={16} /> {t("demo")}
          </GameButton>
          <LangToggle />
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-5 sm:px-10 pb-16">
        {/* hero */}
        <section className="pt-8 pb-12 max-w-3xl animate-fade-up">
          <div className="inline-flex items-center gap-2 bg-accent text-accent-foreground rounded-full px-4 py-1.5 text-xs font-bold mb-5">
            <Stethoscope size={14} /> {t("tagline")}
          </div>
          <h1 className="font-head font-black text-4xl sm:text-5xl lg:text-6xl text-fg tracking-tight leading-[1.05]">
            {lang === "tr" ? "Sanal hastayla" : "Practice with a"}<br />
            <span className="text-primary">{lang === "tr" ? "klinik pratik." : "virtual patient."}</span>
          </h1>
          <p className="text-base sm:text-lg text-muted-foreground mt-5 leading-relaxed">{t("landing_sub")}</p>
        </section>

        {/* case grid */}
        <h2 className="font-head font-extrabold text-2xl text-fg mb-5">{t("choose_case")}</h2>
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[0, 1, 2, 3].map((i) => <div key={i} className="card-medkit h-52 animate-pulse" />)}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {cases.map((c, i) => (
              <button
                key={c.case_id}
                data-testid={`case-card-${c.case_id}`}
                onClick={() => navigate(`/briefing/${c.case_id}`)}
                className="card-medkit p-6 text-left hover:-translate-y-1 hover:shadow-[0_14px_40px_rgb(0,0,0,0.08)] transition-all animate-fade-up group"
                style={{ animationDelay: `${i * 80}ms` }}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="w-14 h-14 rounded-2xl bg-accent flex items-center justify-center text-3xl">
                    {MOOD_EMOJI[c.mood] || "🙂"}
                  </div>
                  <span
                    className="text-[11px] font-black uppercase tracking-wide px-3 py-1 rounded-full text-white"
                    style={{ background: DIFF_COLOR[c.difficulty] }}
                  >
                    {t(c.difficulty)}
                  </span>
                </div>
                <h3 className="font-head font-extrabold text-xl text-fg mb-1">{c.title}</h3>
                <p className="text-xs text-muted-foreground font-semibold mb-2">{c.patient_name} · {c.age} {t("age").toLowerCase()}</p>
                <p className="text-sm text-fg/80 leading-snug italic">“{c.chief_complaint}”</p>
                <div className="flex items-center gap-1 text-primary font-bold text-sm mt-4 group-hover:gap-2 transition-all">
                  {t("start_case")} <ArrowRight size={16} />
                </div>
              </button>
            ))}
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
}
