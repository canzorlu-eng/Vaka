import React from "react";
import { useLang } from "../context/LangContext";

export const Footer = () => {
  const { t } = useLang();
  return (
    <footer
      data-testid="footer-disclaimer"
      className="w-full py-5 px-4 text-center text-xs sm:text-sm text-muted-foreground border-t-2 border-border mt-auto"
    >
      <span className="inline-flex items-center gap-2 font-medium">
        <span className="text-primary">⚕</span>
        {t("disclaimer")}
      </span>
    </footer>
  );
};

export const LangToggle = () => {
  const { lang, toggle } = useLang();
  return (
    <button
      data-testid="lang-toggle"
      onClick={toggle}
      className="game-btn px-4 py-2 text-sm bg-white flex items-center gap-1"
      style={{ "--shadow-btn": "#EAE2D8", color: "var(--fg)" }}
    >
      <span className={lang === "tr" ? "text-primary font-black" : "opacity-50"}>TR</span>
      <span className="opacity-30">/</span>
      <span className={lang === "en" ? "text-primary font-black" : "opacity-50"}>EN</span>
    </button>
  );
};

export const Logo = ({ onClick }) => (
  <div
    data-testid="logo"
    onClick={onClick}
    className="flex items-center gap-2 cursor-pointer select-none"
  >
    <div className="w-11 h-11 rounded-2xl bg-primary flex items-center justify-center shadow-[0_4px_0_#E0705A] rotate-3">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path d="M12 4v16M4 12h16" stroke="#fff" strokeWidth="3.5" strokeLinecap="round" />
      </svg>
    </div>
    <div className="leading-none">
      <div className="font-head font-black text-2xl text-fg">Vaka</div>
      <div className="text-[10px] font-semibold text-secondary tracking-wide -mt-0.5">MEDKIT+</div>
    </div>
  </div>
);
