import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";
import { PHASES } from "../i18n";
import { useSpeech } from "../hooks/useSpeech";
import { Footer, HeaderRight, Logo } from "../components/Chrome";
import { GameButton } from "../components/GameButton";
import { PhaseStepper } from "../components/PhaseStepper";
import { VitalsStrip } from "../components/VitalsStrip";
import { ClinicScene } from "../components/ClinicScene";
import { DialogueBubble } from "../components/DialogueBubble";
import { Odontogram } from "../components/Odontogram";
import {
  Send, Mic, Volume2, VolumeX, FlaskConical, Stethoscope,
  ClipboardCheck, Pill as PillIcon, DoorOpen, Check, X, CircleDot, ScanLine, Lightbulb, ArrowRight,
} from "lucide-react";

export default function Simulation() {
  const { sid } = useParams();
  const { lang, t } = useLang();
  const navigate = useNavigate();
  const speech = useSpeech(lang);

  const [session, setSession] = useState(null);
  const [caseData, setCaseData] = useState(null);
  const [phase, setPhase] = useState("anamnez");
  const [transcript, setTranscript] = useState([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [bubble, setBubble] = useState("");
  const [mood, setMood] = useState("neutral");
  const [tooth, setTooth] = useState(null);
  const [highlighted, setHighlighted] = useState([]);
  const [toothMarkers, setToothMarkers] = useState({});
  const [examsDone, setExamsDone] = useState([]);
  const [testsDone, setTestsDone] = useState([]);
  const [dx, setDx] = useState(null);
  const [tx, setTx] = useState(null);
  const [voiceOn, setVoiceOn] = useState(true);
  const [ending, setEnding] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    api.getSession(sid).then((s) => {
      setSession(s);
      setCaseData(s.case);
      setMood(s.case.patient.avatar_mood);
      setBubble(s.case.chief_complaint);
      setTranscript(s.transcript.map((m) => ({ role: m.role, text: m.text })));
      setExamsDone(s.exams_done || []);
      setTestsDone(s.tests_ordered || []);
      setDx(s.diagnosis_id || null);
      setTx(s.treatment_id || null);
    }).catch(() => navigate("/"));
  }, [sid, navigate]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [transcript, thinking]);

  const push = (entry) => setTranscript((prev) => [...prev, entry]);

  const speakPatient = async (text) => {
    if (!voiceOn || !text) return;
    try {
      const res = await api.tts(text);
      if (res && res.audio) { speech.playBase64(res.audio); return; }
    } catch (e) {}
    speech.speak(text); // graceful fallback to browser voice
  };

  const sendQuestion = async (text) => {
    const q = (text ?? input).trim();
    if (!q || thinking) return;
    setInput("");
    push({ role: "student", text: q });
    setThinking(true);
    try {
      const res = await api.sendMessage(sid, q);
      push({ role: "patient", text: res.reply });
      setBubble(res.reply);
      if (res.mood) setMood(res.mood);
      speakPatient(res.reply);
    } catch (e) {
      toast.error("Error");
    } finally {
      setThinking(false);
    }
  };

  const doExam = async (a) => {
    try {
      const res = await api.runExam(sid, a.id);
      setExamsDone((prev) => prev.includes(a.id) ? prev : [...prev, a.id]);
      if (res.tooth) {
        setTooth(res.tooth);
        setHighlighted((p) => p.includes(res.tooth) ? p : [...p, res.tooth]);
        setToothMarkers((p) => ({ ...p, [res.tooth]: res.severity || "finding" }));
      }
      push({ role: "exam", label: res.label, text: res.result });
    } catch (e) { toast.error("Error"); }
  };

  const doTest = async (tst) => {
    try {
      const res = await api.orderTest(sid, tst.id);
      setTestsDone((prev) => prev.includes(tst.id) ? prev : [...prev, tst.id]);
      if (res.xray) {
        push({ role: "xray", testId: tst.id, label: res.label, indicated: res.indicated,
               result: res.result, image: res.xray.image, question: res.xray.question, options: res.xray.options });
      } else {
        push({ role: "test", label: res.label, text: res.result, indicated: res.indicated });
      }
    } catch (e) { toast.error("Error"); }
  };

  const commitDx = async (id) => {
    setDx(id);
    await api.commit(sid, { diagnosis_id: id });
    toast.success(t("diagnosis_committed"));
  };
  const commitTx = async (id) => {
    setTx(id);
    await api.commit(sid, { treatment_id: id });
    toast.success(t("treatment_committed"));
  };

  const endEncounter = async () => {
    setEnding(true);
    try {
      await api.score(sid);
      navigate(`/debrief/${sid}`);
    } catch (e) { toast.error("Error"); setEnding(false); }
  };

  const micPress = () => {
    if (!speech.sttSupported) { toast.error(t("voice_unavailable")); return; }
    if (speech.listening) { speech.stopListening(); return; }
    speech.startListening((txt) => { setInput(txt); sendQuestion(txt); });
  };

  if (!caseData) return <div className="min-h-screen flex items-center justify-center text-muted-foreground">…</div>;

  const nextPhase = PHASES[PHASES.findIndex((p) => p.id === phase) + 1] || null;

  return (
    <div className="min-h-screen flex flex-col">
      {/* top bar */}
      <header className="px-4 sm:px-8 py-3 border-b border-border bg-bg/80 backdrop-blur sticky top-0 z-20">
        <div className="max-w-7xl mx-auto w-full flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            <Logo onClick={() => navigate("/")} />
            <div className="order-3 md:order-none w-full md:w-auto overflow-x-auto scroll-soft">
              <VitalsStrip vitals={caseData.vitals} />
            </div>
            <HeaderRight />
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-5">
            <div className="flex-1 min-w-0 w-full">
              <PhaseStepper current={phase} onJump={(id) => setPhase(id)} />
            </div>
            {nextPhase && (
              <button
                data-testid="next-phase-btn"
                onClick={() => setPhase(nextPhase.id)}
                aria-label={`${t("next_phase_hint")}: ${t(nextPhase.key)}`}
                className="game-btn shrink-0 w-full sm:w-auto justify-between pl-4 pr-3 py-2 flex items-center gap-3 text-left"
                style={{ background: "var(--primary)", color: "#fff", "--shadow-btn": "#E0705A" }}
              >
                <span className="flex flex-col leading-tight">
                  <span className="text-[10px] font-bold uppercase tracking-wider opacity-80">{t("next_phase_hint")}</span>
                  <span className="text-sm font-black whitespace-nowrap">{t(nextPhase.key)}</span>
                </span>
                <ArrowRight size={20} strokeWidth={3} />
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-8 py-5 grid grid-cols-1 lg:grid-cols-12 gap-5 content-start">
        {/* left: clinic scene */}
        <section className="lg:col-span-5 flex flex-col gap-4">
          <div className="card-medkit relative h-[220px] sm:h-[360px] overflow-hidden bg-accent">
            <ClinicScene mood={mood} speaking={thinking} />
            <div className="absolute top-4 left-4 z-10">
              <DialogueBubble text={bubble} listening={speech.listening} thinking={thinking} />
            </div>
            <div className="absolute bottom-3 right-3 bg-white/90 rounded-full px-3 py-1 text-xs font-bold text-fg border border-border">
              {caseData.patient.name}
            </div>
          </div>
          {phase === "muayene" && (
            <div>
              <p className="text-xs font-bold text-muted-foreground mb-2">{t("select_tooth")}</p>
              <Odontogram selected={tooth} highlighted={highlighted} markers={toothMarkers} onSelect={setTooth} />
            </div>
          )}
          <ProgressPanel t={t} caseData={caseData} examsDone={examsDone} testsDone={testsDone} dx={dx} tx={tx} transcript={transcript} />
        </section>

        {/* right: transcript + input */}
        <section className="lg:col-span-7 flex flex-col card-medkit overflow-hidden">
          <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-soft p-4 sm:p-5 space-y-3 min-h-[280px] max-h-[52vh]">
            <div className="text-center text-xs text-muted-foreground font-semibold py-2">— {caseData.patient.name} · {caseData.patient.setting} —</div>
            {transcript.map((m, i) => <TranscriptItem key={i} m={m} t={t} sid={sid} patientName={caseData.patient.name} />)}
            {phase === "anamnez" && !thinking && !transcript.some((m) => m.role === "student") && (
              <div className="pt-4" data-testid="starter-questions">
                <p className="eyebrow mb-3 text-center">{t("starters_title")}</p>
                <div className="flex flex-wrap justify-center gap-2">
                  {t("starters").map((q) => (
                    <button key={q} type="button" className="chip" onClick={() => sendQuestion(q)}>{q}</button>
                  ))}
                </div>
              </div>
            )}
            {thinking && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <div className="w-2 h-2 rounded-full bg-primary dot-1" />
                <div className="w-2 h-2 rounded-full bg-primary dot-2" />
                <div className="w-2 h-2 rounded-full bg-primary dot-3" />
              </div>
            )}
          </div>

          {/* input row */}
          <div className="border-t border-border p-3 flex items-center gap-2">
            <button data-testid="voice-toggle" onClick={() => setVoiceOn((v) => !v)} title="TTS"
              className="w-11 h-11 rounded-xl flex items-center justify-center border border-border bg-white shrink-0" style={{ color: voiceOn ? "var(--secondary)" : "var(--muted-foreground)" }}>
              {voiceOn ? <Volume2 size={18} /> : <VolumeX size={18} />}
            </button>
            <input
              data-testid="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendQuestion()}
              placeholder={t("type_question")}
              className="flex-1 bg-white rounded-xl px-4 py-3 text-sm outline-none border border-border focus:ring-2 focus:ring-primary/25 focus:border-primary"
            />
            <button data-testid="push-to-talk-btn" onClick={micPress}
              className="w-11 h-11 rounded-xl flex items-center justify-center text-white shrink-0 game-btn"
              style={{ background: speech.listening ? "var(--coral)" : "var(--secondary)" }}
              title={t("push_to_talk")}>
              <Mic size={18} className={speech.listening ? "animate-pulse" : ""} />
            </button>
            <GameButton data-testid="send-btn" onClick={() => sendQuestion()} disabled={!input.trim() || thinking} className="!px-4 !py-3 shrink-0">
              <Send size={18} />
            </GameButton>
          </div>
        </section>
      </main>

      {/* ACTION DOCK */}
      <div className="sticky bottom-0 z-20 bg-bg/90 backdrop-blur border-t border-border">
        <div className="max-w-7xl mx-auto w-full px-4 sm:px-8 py-3">
          <ActionDock
            phase={phase} caseData={caseData} t={t}
            examsDone={examsDone} testsDone={testsDone} dx={dx} tx={tx}
            onExam={doExam} onTest={doTest} onDx={commitDx} onTx={commitTx}
            onEnd={endEncounter} ending={ending}
          />
        </div>
      </div>
      <Footer />
    </div>
  );
}

function TranscriptItem({ m, t, sid, patientName }) {
  if (m.role === "student") {
    return (
      <div className="flex justify-end animate-pop">
        <div className="bg-primary text-white rounded-2xl rounded-br-md px-4 py-2.5 max-w-[80%] text-sm font-medium shadow-sm">{m.text}</div>
      </div>
    );
  }
  if (m.role === "patient") {
    return (
      <div className="flex justify-start animate-pop">
        <div className="bg-accent text-accent-foreground rounded-2xl rounded-bl-md px-4 py-2.5 max-w-[80%] text-sm font-medium">{m.text}</div>
      </div>
    );
  }
  if (m.role === "xray") {
    return <XrayCard m={m} t={t} sid={sid} />;
  }
  // exam / test result card
  const isTest = m.role === "test";
  return (
    <div className="animate-pop">
      <div className="mx-auto max-w-[92%] bg-white border border-border rounded-2xl p-3">
        <div className="flex items-center gap-2 mb-1">
          {isTest ? <FlaskConical size={15} className="text-secondary" /> : <Stethoscope size={15} className="text-primary" />}
          <span className="text-xs font-black uppercase tracking-wide text-muted-foreground">{m.label}</span>
          {isTest && (
            <span className={`ml-auto text-[10px] font-bold px-2 py-0.5 rounded-full ${m.indicated ? "bg-secondary/20 text-secondary" : "bg-[#E8705B]/15 text-[#E8705B]"}`}>
              {m.indicated ? t("indicated") : t("not_indicated")}
            </span>
          )}
        </div>
        <p className="text-sm text-fg font-medium">{m.text}</p>
      </div>
    </div>
  );
}

function XrayCard({ m, t, sid }) {
  const [chosen, setChosen] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const answer = async (optId) => {
    if (result || loading) return;
    setChosen(optId);
    setLoading(true);
    try {
      const res = await api.xrayAnswer(sid, m.testId, optId);
      setResult(res);
    } catch (e) {
      setChosen(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="animate-pop">
      <div className="mx-auto max-w-[96%] bg-white border border-border rounded-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-accent/40">
          <ScanLine size={15} className="text-secondary" />
          <span className="text-xs font-black uppercase tracking-wide text-muted-foreground">{m.label}</span>
          <span className={`ml-auto text-[10px] font-bold px-2 py-0.5 rounded-full ${m.indicated ? "bg-secondary/20 text-secondary" : "bg-[#E8705B]/15 text-[#E8705B]"}`}>
            {m.indicated ? t("indicated") : t("not_indicated")}
          </span>
        </div>

        {/* X-ray viewer */}
        <div className="bg-[#111214] p-3 flex justify-center">
          <img
            data-testid={`xray-image-${m.testId}`}
            src={m.image}
            alt={t("radiograph")}
            className="max-h-64 rounded-lg object-contain"
            style={{ boxShadow: "0 0 24px rgba(130,195,166,0.25)" }}
          />
        </div>

        <div className="p-3">
          <p className="text-sm font-head font-semibold text-fg mb-2 flex items-center gap-1.5">
            <span className="text-primary">◎</span> {m.question || t("identify_finding")}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {m.options.map((o) => {
              const isChosen = chosen === o.id;
              const isCorrectOpt = result && result.correct_option_id === o.id;
              let cls = "bg-white border-border text-fg hover:border-primary/50";
              if (result) {
                if (isCorrectOpt) cls = "bg-secondary/15 border-secondary text-secondary";
                else if (isChosen) cls = "bg-[#E8705B]/12 border-[#E8705B] text-[#E8705B]";
                else cls = "bg-white border-border text-muted-foreground opacity-70";
              } else if (isChosen) {
                cls = "bg-primary/10 border-primary text-primary";
              }
              return (
                <button
                  key={o.id}
                  data-testid={`xray-opt-${m.testId}-${o.id}`}
                  disabled={!!result || loading}
                  onClick={() => answer(o.id)}
                  className={`text-left text-sm font-semibold px-3 py-2.5 rounded-xl border transition-all flex items-center gap-2 ${cls}`}
                >
                  {result && isCorrectOpt && <Check size={15} className="shrink-0" />}
                  {result && isChosen && !isCorrectOpt && <X size={15} className="shrink-0" />}
                  <span>{o.label}</span>
                </button>
              );
            })}
          </div>

          {result && (
            <div data-testid={`xray-explanation-${m.testId}`} className="mt-3 rounded-xl bg-accent/50 border border-border p-3 animate-fade-up">
              <div className={`text-xs font-black uppercase tracking-wide mb-1 flex items-center gap-1.5 ${result.correct ? "text-secondary" : "text-[#E8705B]"}`}>
                {result.correct ? <><Check size={14} />{t("correct")}</> : <><X size={14} />{t("incorrect")}</>}
                {!result.correct && <span className="text-muted-foreground normal-case font-semibold">· {t("correct_answer")}: {result.correct_label}</span>}
              </div>
              <div className="flex items-start gap-2">
                <Lightbulb size={16} className="text-[#F0B458] mt-0.5 shrink-0" />
                <p className="text-sm text-fg font-medium leading-snug">{result.explanation}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ActionDock({ phase, caseData, t, examsDone, testsDone, dx, tx, onExam, onTest, onDx, onTx, onEnd, ending }) {
  const Pill = ({ icon: Icon, label, active, done, onClick, testid, danger }) => (
    <button
      data-testid={testid}
      onClick={onClick}
      className="game-btn px-4 py-2.5 text-sm flex items-center gap-2 whitespace-nowrap"
      style={{
        background: active ? "var(--primary)" : done ? "var(--secondary)" : "#fff",
        color: active || done ? "#fff" : (danger ? "#E8705B" : "var(--fg)"),
        "--shadow-btn": active ? "#E0705A" : done ? "#5FA184" : "#EAE2D8",
      }}
    >
      <Icon size={16} /> {label} {done && <Check size={14} />}
    </button>
  );

  return (
    <div>
      {phase === "anamnez" && (
        <div className="text-sm text-muted-foreground font-semibold flex items-center gap-2">
          <CircleDot size={16} className="text-primary" />
          {t("phase_anamnez")}: {t("type_question")}
        </div>
      )}

      {phase === "muayene" && (
        <div className="flex items-center gap-2 overflow-x-auto scroll-soft pb-1">
          <span className="text-xs font-black uppercase text-muted-foreground shrink-0">{t("exam_actions")}</span>
          {caseData.exam_actions.map((a) => (
            <Pill key={a.id} testid={`exam-${a.id}`} icon={Stethoscope} label={a.label} done={examsDone.includes(a.id)} onClick={() => onExam(a)} />
          ))}
        </div>
      )}

      {phase === "testler" && (
        <div className="flex items-center gap-2 overflow-x-auto scroll-soft pb-1">
          <span className="text-xs font-black uppercase text-muted-foreground shrink-0">{t("order_tests")}</span>
          {caseData.tests.map((tst) => (
            <Pill key={tst.id} testid={`test-${tst.id}`} icon={FlaskConical} label={tst.label} done={testsDone.includes(tst.id)} onClick={() => onTest(tst)} />
          ))}
        </div>
      )}

      {phase === "tani" && (
        <div className="flex items-center gap-2 overflow-x-auto scroll-soft pb-1">
          <span className="text-xs font-black uppercase text-muted-foreground shrink-0 flex items-center gap-1"><ClipboardCheck size={14} />{t("choose_diagnosis")}</span>
          {caseData.diagnosis_options.map((d) => (
            <Pill key={d.id} testid={`dx-${d.id}`} icon={ClipboardCheck} label={d.label} active={dx === d.id} onClick={() => onDx(d.id)} />
          ))}
        </div>
      )}

      {phase === "tedavi" && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 overflow-x-auto scroll-soft pb-1 flex-1 min-w-0">
            <span className="text-xs font-black uppercase text-muted-foreground shrink-0 flex items-center gap-1"><PillIcon size={14} />{t("choose_treatment")}</span>
            {caseData.treatment_options.map((tr) => (
              <Pill key={tr.id} testid={`tx-${tr.id}`} icon={PillIcon} label={tr.label} active={tx === tr.id} onClick={() => onTx(tr.id)} />
            ))}
          </div>
          <GameButton data-testid="end-encounter-btn" variant="danger" onClick={onEnd} disabled={ending} className="flex items-center gap-2 shrink-0">
            <DoorOpen size={18} /> {ending ? "…" : t("end_encounter")}
          </GameButton>
        </div>
      )}

      {phase !== "tedavi" && (
        <div className="flex justify-end mt-2">
          <GameButton data-testid="end-encounter-btn" variant="ghost" onClick={onEnd} disabled={ending} style={{ color: "var(--coral)" }} className="flex items-center gap-2 !px-4 !py-2 !text-sm">
            <DoorOpen size={16} /> {ending ? "…" : t("end_encounter")}
          </GameButton>
        </div>
      )}
    </div>
  );
}


function ProgressPanel({ t, caseData, examsDone, testsDone, dx, tx, transcript }) {
  const rows = [
    ["progress_exam", examsDone.length, caseData.exam_actions.length],
    ["progress_tests", testsDone.length, caseData.tests.length],
    ["progress_dx", dx ? 1 : 0, 1],
    ["progress_tx", tx ? 1 : 0, 1],
  ];
  const findings = transcript.filter((m) => m.role === "exam" || m.role === "test");
  return (
    <div className="card-medkit p-5 hidden lg:block" data-testid="progress-panel">
      <p className="eyebrow mb-3">{t("progress_title")}</p>
      <ul className="space-y-2.5">
        {rows.map(([k, n, total]) => (
          <li key={k} className="flex items-center gap-3 text-sm">
            <span className="w-24 font-semibold text-fg">{t(k)}</span>
            <span className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={n}>
              <span className="block h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${(n / total) * 100}%` }} />
            </span>
            <span className="w-10 text-right text-xs font-bold text-muted-foreground tabular-nums">{n}/{total}</span>
          </li>
        ))}
      </ul>
      <p className="eyebrow mt-5 mb-2">{t("findings_title")}</p>
      {findings.length === 0 ? (
        <p className="text-sm text-muted-foreground leading-snug">{t("findings_empty")}</p>
      ) : (
        <ul className="space-y-1.5 max-h-40 overflow-y-auto scroll-soft pr-1">
          {findings.map((f, i) => (
            <li key={i} className="text-sm leading-snug"><span className="font-bold text-fg">{f.label}:</span> <span className="text-muted-foreground">{f.text}</span></li>
          ))}
        </ul>
      )}
    </div>
  );
}
