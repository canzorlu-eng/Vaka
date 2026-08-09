import React from "react";
import { Heart, Activity, Thermometer, Droplet } from "lucide-react";
import { useLang } from "../context/LangContext";

export const VitalsStrip = ({ vitals }) => {
  const { t } = useLang();
  if (!vitals) return null;
  const items = [
    { icon: Activity, label: "BP", value: vitals.bp, color: "#FF937B" },
    { icon: Heart, label: "HR", value: `${vitals.hr}`, color: "#E8705B" },
    { icon: Thermometer, label: "T°", value: vitals.temp, color: "#82C3A6" },
    { icon: Droplet, label: "SpO₂", value: vitals.spo2, color: "#5AA0C3" },
  ];
  return (
    <div data-testid="vitals-strip" className="flex items-center gap-2 flex-wrap">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-2 bg-white rounded-full px-3 py-1.5 border-2 border-border">
          <it.icon size={15} style={{ color: it.color }} strokeWidth={2.5} />
          <span className="text-[11px] text-muted-foreground font-semibold">{it.label}</span>
          <span className="text-sm font-head font-extrabold text-fg">{it.value}</span>
        </div>
      ))}
    </div>
  );
};
