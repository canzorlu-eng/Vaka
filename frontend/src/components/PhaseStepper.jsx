import React from "react";
import { PHASES } from "../i18n";
import { useLang } from "../context/LangContext";
import { Check } from "lucide-react";

export const PhaseStepper = ({ current, onJump }) => {
  const { t } = useLang();
  const curIdx = PHASES.findIndex((p) => p.id === current);
  return (
    <>
    {/* compact variant for narrow screens */}
    <div data-testid="phase-stepper-compact" className="sm:hidden w-full">
      <div className="flex items-center justify-between mb-1.5 text-xs">
        <span className="font-bold text-primary">{t(PHASES[curIdx]?.key)}</span>
        <span className="font-semibold text-muted-foreground tabular-nums">{curIdx + 1} / {PHASES.length}</span>
      </div>
      <div className="flex gap-1.5" role="list">
        {PHASES.map((p, i) => (
          <button key={p.id} type="button" role="listitem" aria-label={t(p.key)} aria-current={i === curIdx ? "step" : undefined}
            onClick={() => onJump && onJump(p.id, i)} className="flex-1 py-2 group">
            <span className="block h-1.5 rounded-full transition-colors"
              style={{ background: i < curIdx ? "var(--secondary)" : i === curIdx ? "var(--primary)" : "var(--border)" }} />
          </button>
        ))}
      </div>
    </div>
    <div data-testid="phase-stepper" className="hidden sm:flex items-center justify-between w-full overflow-x-auto scroll-soft gap-1 py-1">
      {PHASES.map((p, i) => {
        const done = i < curIdx;
        const active = i === curIdx;
        const bg = active ? "var(--primary)" : done ? "var(--secondary)" : "#fff";
        const fg = active || done ? "#fff" : "var(--muted-fg)";
        return (
          <React.Fragment key={p.id}>
            <button
              data-testid={`phase-step-${p.id}`}
              onClick={() => onJump && onJump(p.id, i)}
              className="flex flex-col items-center gap-1 min-w-[64px] group"
            >
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center font-semibold text-sm transition-transform group-hover:scale-110"
                style={{ background: bg, color: fg, border: active || done ? "1px solid transparent" : "1.5px solid var(--border)", boxShadow: active ? "0 0 0 4px rgba(15,107,99,0.18)" : "none" }}
              >
                {done ? <Check size={18} strokeWidth={3} /> : i + 1}
              </div>
              <span className={`text-[11px] font-bold whitespace-nowrap ${active ? "text-primary" : "text-muted-foreground"}`}>
                {t(p.key)}
              </span>
            </button>
            {i < PHASES.length - 1 && (
              <div className="flex-1 h-1 rounded-full min-w-[10px]" style={{ background: i < curIdx ? "var(--secondary)" : "var(--border)" }} />
            )}
          </React.Fragment>
        );
      })}
    </div>
    </>
  );
};
