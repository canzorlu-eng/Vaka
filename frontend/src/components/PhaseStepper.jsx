import React from "react";
import { PHASES } from "../i18n";
import { useLang } from "../context/LangContext";
import { Check } from "lucide-react";

export const PhaseStepper = ({ current, onJump }) => {
  const { t } = useLang();
  const curIdx = PHASES.findIndex((p) => p.id === current);
  return (
    <div data-testid="phase-stepper" className="flex items-center justify-between w-full overflow-x-auto scroll-soft gap-1 py-1">
      {PHASES.map((p, i) => {
        const done = i < curIdx;
        const active = i === curIdx;
        const color = active ? "var(--primary)" : done ? "var(--secondary)" : "#E3DED6";
        return (
          <React.Fragment key={p.id}>
            <button
              data-testid={`phase-step-${p.id}`}
              onClick={() => onJump && onJump(p.id, i)}
              className="flex flex-col items-center gap-1 min-w-[64px] group"
            >
              <div
                className="w-9 h-9 rounded-full flex items-center justify-center font-head font-black text-sm text-white transition-transform group-hover:scale-110"
                style={{ background: color, boxShadow: active ? "0 0 0 4px rgba(255,147,123,0.25)" : "none" }}
              >
                {done ? <Check size={18} strokeWidth={3} /> : i + 1}
              </div>
              <span className={`text-[11px] font-semibold whitespace-nowrap ${active ? "text-primary" : "text-muted-foreground"}`}>
                {t(p.key)}
              </span>
            </button>
            {i < PHASES.length - 1 && (
              <div className="flex-1 h-1 rounded-full min-w-[10px]" style={{ background: i < curIdx ? "var(--secondary)" : "#E3DED6" }} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
};
