import React from "react";
import { useLang } from "../context/LangContext";

export const ListeningDots = () => (
  <span className="inline-flex items-center gap-1 ml-1">
    <span className="w-1.5 h-1.5 rounded-full bg-primary dot-1" />
    <span className="w-1.5 h-1.5 rounded-full bg-primary dot-2" />
    <span className="w-1.5 h-1.5 rounded-full bg-primary dot-3" />
  </span>
);

// Floating dialogue bubble that shows the patient's latest utterance or a live state.
export const DialogueBubble = ({ text, listening, thinking }) => {
  const { t } = useLang();
  return (
    <div
      data-testid="dialogue-bubble"
      className="animate-bubble card-medkit px-5 py-3 max-w-[280px] relative"
      style={{ borderColor: "#FFD8CC" }}
    >
      {listening ? (
        <div className="flex items-center text-sm font-semibold text-primary">
          {t("listening")} <ListeningDots />
        </div>
      ) : thinking ? (
        <div className="flex items-center text-sm font-semibold text-muted-foreground">
          {t("thinking")} <ListeningDots />
        </div>
      ) : (
        <p className="text-sm text-fg font-medium leading-snug">{text}</p>
      )}
      {/* tail */}
      <div
        className="absolute -bottom-2 left-8 w-4 h-4 rotate-45 bg-white border-b border-r"
        style={{ borderColor: "#FFD8CC" }}
      />
    </div>
  );
};
