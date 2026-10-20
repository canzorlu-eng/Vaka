import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";
import { Footer, HeaderRight, Logo } from "../components/Chrome";
import { GameButton } from "../components/GameButton";
import { VitalsStrip } from "../components/VitalsStrip";
import { ClinicScene } from "../components/ClinicScene";
import { DialogueBubble } from "../components/DialogueBubble";
import { RotateCcw, ArrowLeft, PlayCircle, Stethoscope, FlaskConical, ClipboardCheck } from "lucide-react";

export default function Demo() {
  const { lang, t } = useLang();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [steps, setSteps] = useState([]);
  const [idx, setIdx] = useState(0);
  const [bubble, setBubble] = useState("");
  const [thinking, setThinking] = useState(false);
  const [mood, setMood] = useState("pain");
  const scrollRef = useRef(null);
  const timers = useRef([]);

  const buildSteps = (d) => {
    const s = [];
    d.script.forEach((m) => s.push({ type: m.role, text: m.text }));
    d.exams.forEach((e) => s.push({ type: "exam", label: e.label, text: e.result }));
    d.tests.forEach((tst) => s.push({ type: "test", label: tst.label, text: tst.result }));
    s.push({ type: "dx", label: t("commit_diagnosis"), text: d.diagnosis });
    s.push({ type: "tx", label: t("commit_treatment"), text: d.treatment });
    return s;
  };

  useEffect(() => {
    api.demo(lang).then((d) => {
      setData(d);
      setMood(d.case.patient.avatar_mood);
      setBubble(d.case.chief_complaint);
      setSteps(buildSteps(d));
      setIdx(0);
    });
    // eslint-disable-next-line
  }, [lang]);

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };

  useEffect(() => {
    if (!steps.length) return;
    clearTimers();
    setIdx(0);
    let played = 0;
    const play = () => {
      if (played >= steps.length) return;
      const step = steps[played];
      if (step.type === "patient") { setThinking(true); }
      const tm = setTimeout(() => {
        setThinking(false);
        setIdx(played + 1);
        if (step.type === "patient") setBubble(step.text);
        played += 1;
        play();
      }, step.type === "patient" ? 1400 : 1100);
      timers.current.push(tm);
    };
    play();
    return clearTimers;
    // eslint-disable-next-line
  }, [steps]);

  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; }, [idx, thinking]);

  const replay = () => { setSteps((s) => [...s]); };

  if (!data) return <div className="min-h-screen flex items-center justify-center text-muted-foreground">…</div>;
  const visible = steps.slice(0, idx);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-5 sm:px-10 py-4 max-w-6xl mx-auto w-full">
        <Logo onClick={() => navigate("/")} />
        <div className="flex items-center gap-3">
          <span className="hidden sm:inline-flex items-center gap-1.5 bg-primary-soft text-primary rounded-lg px-3 py-1.5 text-xs font-bold">
            <PlayCircle size={14} /> {t("demo_mode")}
          </span>
          <HeaderRight />
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-5 sm:px-10 pb-10">
        <button onClick={() => navigate("/")} className="flex items-center gap-1 text-sm font-bold text-muted-foreground hover:text-primary mb-4">
          <ArrowLeft size={16} /> {t("back_to_cases")}
        </button>

        <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
          <h1 className="font-head font-semibold text-2xl sm:text-3xl text-fg">{data.case.title}</h1>
          <VitalsStrip vitals={data.case.vitals} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
          <section className="lg:col-span-5">
            <div className="card-medkit relative h-[320px] overflow-hidden bg-accent">
              <ClinicScene mood={mood} speaking={thinking} />
              <div className="absolute top-4 left-4 z-10">
                <DialogueBubble text={bubble} thinking={thinking} />
              </div>
              <div className="absolute bottom-3 right-3 bg-white/90 rounded-full px-3 py-1 text-xs font-bold text-fg border border-border">{data.case.patient.name}</div>
            </div>
            <GameButton data-testid="demo-replay-btn" variant="secondary" onClick={replay} className="w-full mt-4 flex items-center justify-center gap-2">
              <RotateCcw size={18} /> {t("demo_replay")}
            </GameButton>
          </section>

          <section className="lg:col-span-7 card-medkit p-4 sm:p-5">
            <div ref={scrollRef} className="overflow-y-auto scroll-soft space-y-3 h-[360px]">
              <div className="text-center text-xs text-muted-foreground font-semibold py-1">{t("demo_playing")}</div>
              {visible.map((m, i) => <DemoItem key={i} m={m} t={t} />)}
              {thinking && <div className="flex gap-1"><span className="w-2 h-2 rounded-full bg-primary dot-1" /><span className="w-2 h-2 rounded-full bg-primary dot-2" /><span className="w-2 h-2 rounded-full bg-primary dot-3" /></div>}
            </div>
          </section>
        </div>
      </main>
      <Footer />
    </div>
  );
}

function DemoItem({ m, t }) {
  if (m.type === "student") return <div className="flex justify-end animate-pop"><div className="bg-primary text-white rounded-2xl rounded-br-md px-4 py-2.5 max-w-[80%] text-sm font-medium">{m.text}</div></div>;
  if (m.type === "patient") return <div className="flex justify-start animate-pop"><div className="bg-accent text-accent-foreground rounded-2xl rounded-bl-md px-4 py-2.5 max-w-[80%] text-sm font-medium">{m.text}</div></div>;
  const icons = { exam: Stethoscope, test: FlaskConical, dx: ClipboardCheck, tx: ClipboardCheck };
  const Icon = icons[m.type] || Stethoscope;
  const color = m.type === "test" ? "#82C3A6" : (m.type === "dx" || m.type === "tx") ? "#5AA0C3" : "#FF937B";
  return (
    <div className="animate-pop"><div className="mx-auto max-w-[92%] bg-white border border-border rounded-2xl p-3">
      <div className="flex items-center gap-2 mb-1"><Icon size={15} style={{ color }} /><span className="text-xs font-black uppercase tracking-wide text-muted-foreground">{m.label}</span></div>
      <p className="text-sm text-fg font-medium">{m.text}</p>
    </div></div>
  );
}
