import React, { createContext, useContext, useState, useCallback } from "react";
import { STRINGS } from "../i18n";

const LangContext = createContext(null);

export const LangProvider = ({ children }) => {
  const [lang, setLang] = useState(() => localStorage.getItem("vaka_lang") || "tr");
  const toggle = useCallback(() => {
    setLang((prev) => {
      const next = prev === "tr" ? "en" : "tr";
      localStorage.setItem("vaka_lang", next);
      return next;
    });
  }, []);
  const t = useCallback((key) => STRINGS[lang][key] || key, [lang]);
  return <LangContext.Provider value={{ lang, setLang, toggle, t }}>{children}</LangContext.Provider>;
};

export const useLang = () => {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used within LangProvider");
  return ctx;
};
