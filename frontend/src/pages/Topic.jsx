import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";
import { Footer, HeaderRight, Logo } from "../components/Chrome";
import { GameButton } from "../components/GameButton";
import { useAuth } from "../context/AuthContext";
import { useGenerationJob } from "../hooks/useGenerationJob";
import GenerationProgress from "../components/GenerationProgress";
import { ArrowLeft, ArrowRight, Sparkles } from "lucide-react";

const PAGE_SIZE = 50;

const DIFF_COLOR = { easy: ["#1F7A5C", "#E3F3EC"], moderate: ["#8A5A00", "#FBF0D6"], hard: ["#B24A35", "#FBE9E4"] };
const MOOD_EMOJI = { neutral: "🙂", pain: "😣", anxious: "😰" };
const LEVELS = ["easy", "moderate", "hard"];

export default function Topic() {
  const { lang, t } = useLang();
  const { topicId } = useParams();
  const navigate = useNavigate();
  const { isAuthed, login, refresh, handleGateError } = useAuth();
  const [topic, setTopic] = useState(null);
  const [cases, setCases] = useState([]);
  const [total, setTotal] = useState(0);
  const [level, setLevel] = useState("all");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const difficulty = level === "all" ? undefined : level;

  const reload = useCallback(async () => {
    const page = await api.listCasesPage(lang, topicId, 0, PAGE_SIZE, difficulty);
    setCases(page.items);
    setTotal(page.total);
  }, [lang, topicId, difficulty]);

  useEffect(() => {
    setLoading(true);
    Promise.all([api.listTopics(lang), api.listCasesPage(lang, topicId, 0, PAGE_SIZE, difficulty)])
      .then(([topics, page]) => {
        const found = topics.find((x) => x.id === topicId);
        if (!found) { navigate("/"); return; }
        setTopic(found);
        setCases(page.items);
        setTotal(page.total);
        setLoading(false);
      })
      .catch(() => navigate("/"));
  }, [lang, topicId, difficulty, navigate]);

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const page = await api.listCasesPage(lang, topicId, cases.length, PAGE_SIZE, difficulty);
      setCases((prev) => [...prev, ...page.items]);
      setTotal(page.total);
    } catch (e) {
      toast.error(t("err_generic"));
    } finally {
      setLoadingMore(false);
    }
  };

  const { job, running, start } = useGenerationJob({
    topic: topicId,
    lang,
    onCompleted: async (result) => {
      try { await reload(); } catch (e) { /* list refresh is best-effort */ }
      refresh();
      toast.success(`✨ ${result?.title || t("gen_done")}`);
    },
    onError: ({ kind, info }) => {
      if (kind === "handled") return;
      if (kind === "auth") { login(`/topic/${topicId}`); return; }
      if (kind === "upgrade_required") { handleGateError({ response: { status: 402, data: { detail: { code: "upgrade_required" } } } }); return; }
      if (kind === "quota") { toast.error(t("gen_quota")); return; }
      if (kind === "unavailable") { toast.error(t("gen_unavailable")); return; }
      if (kind === "timeout") { toast.error(t("gen_timeout")); return; }
      toast.error(info?.detail && typeof info.detail === "string" ? `${t("gen_failed")} (${info.detail})` : t("gen_failed"));
    },
  });

  const generate = () => {
    if (!isAuthed) { login(`/topic/${topicId}`); return; }
    start();
  };

  const visible = cases;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-5 sm:px-10 py-5 max-w-6xl mx-auto w-full">
        <Logo onClick={() => navigate("/")} />
        <HeaderRight />
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-5 sm:px-10 pb-16">
        <button data-testid="topic-back" onClick={() => navigate("/")}
          className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground hover:text-primary mb-6 transition-colors">
          <ArrowLeft size={16} /> {t("back_to_topics")}
        </button>

        {topic && (
          <section className="mb-8 animate-fade-up">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center text-4xl shrink-0" style={{ background: `${topic.color}33` }}>{topic.icon}</div>
              <div>
                <h1 className="font-head font-semibold text-3xl sm:text-4xl text-fg tracking-tight">{topic.name}</h1>
                <p className="text-muted-foreground mt-1">{topic.blurb}</p>
              </div>
            </div>
          </section>
        )}

        <div className="flex items-center justify-between flex-wrap gap-3 mb-5">
          <div className="flex items-center gap-2 flex-wrap" role="tablist" aria-label={t("difficulty")}>
            {["all", ...LEVELS].map((l) => (
              <button key={l} role="tab" aria-selected={level === l} data-testid={`level-${l}`} onClick={() => setLevel(l)}
                className={`px-4 py-2 rounded-xl text-sm font-bold border transition-colors ${level === l ? "bg-fg text-white border-fg" : "bg-white border-border text-fg hover:border-primary"}`}>
                {l === "all" ? t("all_levels") : t(l)}
                {topic && <span className="ml-1.5 opacity-70">{l === "all" ? topic.count : topic.levels?.[l]}</span>}
              </button>
            ))}
          </div>
          <GameButton variant="secondary" data-testid="generate-case-btn" onClick={generate} disabled={running}
            className="!px-5 !py-2.5 !text-sm flex items-center gap-2">
            <Sparkles size={16} className={running ? "animate-spin motion-reduce:animate-none" : ""} />
            {running ? t("generating") : t("generate_case")}
          </GameButton>
        </div>
        {running && <GenerationProgress job={job} />}

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton rounded-[20px] h-52" />)}
          </div>
        ) : visible.length === 0 ? (
          <p className="text-muted-foreground py-10">{t("no_cases")}</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {visible.map((c, i) => (
              <button key={c.case_id} data-testid={`case-card-${c.case_id}`} onClick={() => navigate(`/briefing/${c.case_id}`)}
                className="card-medkit p-6 text-left card-lift animate-fade-up group"
                style={{ animationDelay: `${Math.min(i, 8) * 60}ms` }}>
                <div className="flex items-start justify-between mb-3">
                  <div className="w-12 h-12 rounded-xl bg-accent flex items-center justify-center text-2xl">{MOOD_EMOJI[c.mood] || "🙂"}</div>
                  <div className="flex items-center gap-2">
                    {c.generated && (
                      <span className="text-[11px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded-md bg-primary-soft text-primary flex items-center gap-1">
                        <Sparkles size={11} /> {t("ai_case")}
                      </span>
                    )}
                    <span className="text-[11px] font-extrabold uppercase tracking-wider px-2.5 py-1 rounded-md" style={{ color: DIFF_COLOR[c.difficulty][0], background: DIFF_COLOR[c.difficulty][1] }}>
                      {t(c.difficulty)}
                    </span>
                  </div>
                </div>
                <h3 className="font-head font-semibold text-xl text-fg mb-1">{c.title}</h3>
                <p className="text-xs text-muted-foreground font-semibold mb-2">{c.patient_name} · {c.age} {t("age").toLowerCase()}</p>
                <p className="text-sm text-fg/80 leading-snug italic">“{c.chief_complaint}”</p>
                <div className="flex items-center gap-1 text-primary font-bold text-sm mt-4 group-hover:gap-2 transition-all">
                  {t("start_case")} <ArrowRight size={16} />
                </div>
              </button>
            ))}
          </div>
        )}
        {!loading && cases.length < total && (
          <div className="flex justify-center mt-8">
            <GameButton variant="ghost" data-testid="load-more-cases" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? "…" : t("load_more")}
            </GameButton>
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
}
