import React from "react";
import { useLang } from "../context/LangContext";

const STAGE_KEYS = { drafting: "gen_stage_drafting", repairing: "gen_stage_repairing", validating: "gen_stage_validating" };

export default function GenerationProgress({ job }) {
  const { t } = useLang();
  const pct = Math.max(4, Math.min(100, Math.round((job?.progress ?? 0) * (job?.progress <= 1 ? 100 : 1))));
  const stage = STAGE_KEYS[job?.stage] ? t(STAGE_KEYS[job.stage]) : t("gen_stage_queued");
  return (
    <div data-testid="generation-progress" role="status" aria-live="polite" className="card-medkit p-4 mb-6 animate-fade-up">
      <div className="flex items-center justify-between text-sm font-bold text-fg mb-2">
        <span data-testid="generation-stage">{stage}</span>
        <span className="text-muted-foreground">{pct}%</span>
      </div>
      <div className="h-3 rounded-full bg-accent overflow-hidden" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <div className="h-full rounded-full bg-secondary origin-left transition-transform duration-700 ease-out motion-reduce:transition-none" style={{ transform: `scaleX(${pct / 100})` }} />
      </div>
    </div>
  );
}
