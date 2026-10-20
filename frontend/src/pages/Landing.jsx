import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";
import { Footer, HeaderRight, Logo } from "../components/Chrome";
import { GameButton } from "../components/GameButton";
import { ClinicScene } from "../components/ClinicScene";
import { PlayCircle, ArrowRight, ArrowDown, MessageCircle, Stethoscope, FlaskConical, ClipboardCheck } from "lucide-react";

const STEPS = [
  { icon: ArrowRight, k: "how_1" },
  { icon: MessageCircle, k: "how_2" },
  { icon: FlaskConical, k: "how_3" },
  { icon: ClipboardCheck, k: "how_4" },
];

const LevelBar = ({ levels, count, t }) => {
  const parts = [["easy", "#3A8F73"], ["moderate", "#E0A23B"], ["hard", "#D9674F"]];
  return (
    <div>
      <div className="flex h-1.5 rounded-full overflow-hidden bg-muted" role="img"
        aria-label={parts.map(([k]) => `${t(`lvl_${k}`)} ${levels?.[k] || 0}`).join(", ")}>
        {parts.map(([k, c]) => (levels?.[k] ? <span key={k} style={{ width: `${(levels[k] / count) * 100}%`, background: c }} /> : null))}
      </div>
      <p className="text-[11px] text-muted-foreground mt-2 tabular-nums">
        {parts.filter(([k]) => levels?.[k]).map(([k]) => `${levels[k]} ${t(`lvl_${k}`).toLowerCase()}`).join(" · ")}
      </p>
    </div>
  );
};

export default function Landing() {
  const { lang, t } = useLang();
  const navigate = useNavigate();
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.listTopics(lang).then((d) => { setTopics(d); setLoading(false); }).catch(() => setLoading(false));
  }, [lang]);

  const total = useMemo(() => topics.reduce((n, x) => n + x.count, 0), [topics]);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-5 sm:px-10 py-4 max-w-6xl mx-auto w-full">
        <Logo onClick={() => navigate("/")} />
        <div className="flex items-center gap-2 sm:gap-3">
          <GameButton variant="ghost" data-testid="demo-link" className="!h-10 !px-3.5 !py-0 !text-sm !hidden sm:!flex items-center gap-2" onClick={() => navigate("/demo")}>
            <PlayCircle size={16} className="text-primary" /> {t("demo")}
          </GameButton>
          <HeaderRight />
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-5 sm:px-10 pb-20">
        {/* hero */}
        <section className="grid lg:grid-cols-12 gap-10 items-center pt-6 sm:pt-12 pb-12 sm:pb-16">
          <div className="lg:col-span-7 animate-fade-up">
            <p className="eyebrow inline-flex items-center gap-2 mb-5 text-primary">
              <Stethoscope size={14} /> {t("tagline")}
            </p>
            <h1 className="text-[2.6rem] sm:text-6xl lg:text-[4.4rem] text-fg leading-[1.02]">
              {lang === "tr" ? "Sanal hastayla" : "Practise with a"}<br />
              <em className="not-italic text-primary">{lang === "tr" ? "klinik pratik." : "virtual patient."}</em>
            </h1>
            <p className="text-base sm:text-lg text-muted-foreground mt-6 leading-relaxed max-w-xl">{t("landing_sub")}</p>
            <div className="flex flex-wrap items-center gap-3 mt-8">
              <GameButton data-testid="hero-browse" className="!px-6 !py-3.5 flex items-center gap-2"
                onClick={() => document.getElementById("topics")?.scrollIntoView({ behavior: "smooth" })}>
                {t("landing_cta")} <ArrowDown size={18} />
              </GameButton>
              <GameButton variant="ghost" className="!px-6 !py-3.5 flex items-center gap-2" onClick={() => navigate("/demo")}>
                <PlayCircle size={18} className="text-primary" /> {t("demo")}
              </GameButton>
            </div>
            <dl className="flex flex-wrap gap-x-10 gap-y-4 mt-10 pt-8 border-t border-border">
              {[[total || "—", "stat_cases"], [topics.length || "—", "stat_topics"], [3, "stat_levels"]].map(([n, k]) => (
                <div key={k}>
                  <dt className="sr-only">{t(k)}</dt>
                  <dd className="font-head text-4xl text-fg leading-none" aria-hidden="true">{n}</dd>
                  <dd className="text-sm text-muted-foreground mt-1.5">{t(k)}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="lg:col-span-5 relative animate-fade-up" style={{ animationDelay: "120ms" }} aria-hidden="true">
            <div className="absolute -inset-3 rounded-[32px] bg-primary/10 rotate-2" />
            <div className="card-medkit relative h-[300px] sm:h-[380px] overflow-hidden bg-accent" style={{ boxShadow: "var(--shadow-lg)" }}>
              <ClinicScene mood="worried" speaking={false} />
            </div>
            <div className="absolute -left-2 sm:-left-6 top-6 bg-white rounded-2xl rounded-bl-md px-4 py-3 text-sm font-medium max-w-[230px] border border-border" style={{ boxShadow: "var(--shadow-md)" }}>
              {lang === "tr" ? "“Geceleri dişim zonkluyor, uyuyamıyorum…”" : "“My tooth throbs at night, I can't sleep…”"}
            </div>
            <div className="absolute -right-2 sm:-right-4 bottom-8 bg-fg text-white rounded-xl px-3.5 py-2 text-xs font-bold flex items-center gap-2" style={{ boxShadow: "var(--shadow-md)" }}>
              <span className="w-2 h-2 rounded-full bg-[#5FD3A6] animate-pulse" /> HR 88 · SpO₂ 99%
            </div>
          </div>
        </section>

        {/* topics */}
        <section id="topics" className="scroll-mt-6">
          <div className="flex items-end justify-between mb-6">
            <div>
              <p className="eyebrow mb-2">01</p>
              <h2 className="text-3xl sm:text-4xl text-fg">{t("choose_topic")}</h2>
            </div>
          </div>
          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton rounded-[20px] h-44" />)}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {topics.map((tp, i) => (
                <button key={tp.id} data-testid={`topic-card-${tp.id}`} onClick={() => navigate(`/topic/${tp.id}`)}
                  className="card-medkit card-lift p-6 text-left animate-fade-up group flex flex-col"
                  style={{ animationDelay: `${i * 40}ms` }}>
                  <div className="flex items-center justify-between mb-5">
                    <span className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl" style={{ background: `${tp.color}22` }} aria-hidden="true">{tp.icon}</span>
                    <span className="text-xs font-bold text-muted-foreground tabular-nums">{tp.count} {t("cases_count")}</span>
                  </div>
                  <h3 className="text-xl text-fg mb-1.5">{tp.name}</h3>
                  <p className="text-sm text-muted-foreground leading-snug flex-1">{tp.blurb}</p>
                  <div className="mt-5"><LevelBar levels={tp.levels} count={tp.count} t={t} /></div>
                  <div className="flex items-center gap-1.5 text-primary font-bold text-sm mt-4 transition-all group-hover:gap-2.5">
                    {t("start")} <ArrowRight size={16} />
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* how it works */}
        <section className="mt-20">
          <p className="eyebrow mb-2">02</p>
          <h2 className="text-3xl sm:text-4xl text-fg mb-8">{t("how_title")}</h2>
          <ol className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {STEPS.map(({ icon: Icon, k }, i) => (
              <li key={k} className="relative card-medkit p-5">
                <span className="font-head text-5xl text-primary/15 absolute right-4 top-2 leading-none" aria-hidden="true">{i + 1}</span>
                <span className="w-10 h-10 rounded-xl bg-primary-soft text-primary flex items-center justify-center mb-4"><Icon size={18} /></span>
                <h3 className="text-lg text-fg mb-1">{t(`${k}_t`)}</h3>
                <p className="text-sm text-muted-foreground leading-snug">{t(`${k}_d`)}</p>
              </li>
            ))}
          </ol>
        </section>
      </main>
      <Footer />
    </div>
  );
}
