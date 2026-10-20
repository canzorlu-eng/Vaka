import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Check, ShieldCheck, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { useLang } from "../context/LangContext";
import { useAuth } from "../context/AuthContext";
import { Footer, HeaderRight, Logo } from "../components/Chrome";
import { GameButton } from "../components/GameButton";
import CheckoutModal from "../components/CheckoutModal";
import { derivePrices, formatMoney } from "../lib/money";
import { fmt } from "../i18n";

const FREE_FEATURES = ["pr_free_f1", "pr_free_f2", "pr_free_f3"];
const PRO_FEATURES = ["pr_pro_f1", "pr_pro_f2", "pr_pro_f3", "pr_pro_f4"];

const Feature = ({ text }) => (
  <li className="flex items-start gap-2.5 text-sm text-fg">
    <span className="mt-0.5 w-5 h-5 shrink-0 rounded-full bg-secondary/25 text-secondary flex items-center justify-center"><Check size={13} strokeWidth={3.5} /></span>
    <span>{text}</span>
  </li>
);

export default function Pricing() {
  const { lang, t } = useLang();
  const navigate = useNavigate();
  const { isAuthed, plan, login } = useAuth();
  const [data, setData] = useState(null);
  const [comingSoon, setComingSoon] = useState(false);
  const [interval, setIntervalSel] = useState("year");
  const [currency, setCurrency] = useState("USD"); // list price is USD; Turkish-issued cards are charged in TRY (toggle)
  const [checkoutOpen, setCheckoutOpen] = useState(false);


  useEffect(() => {
    api.billingPlans().then(setData).catch(() => setComingSoon(true));
  }, []);

  const p = useMemo(() => derivePrices(data, currency), [data, currency]);
  const money = (n) => formatMoney(n, currency, lang);
  const yearly = interval === "year";
  const planId = yearly ? "pro_yearly" : "pro_monthly";
  const isPro = plan === "pro";

  const onCta = () => {
    if (!isAuthed) { login("/pricing"); return; }
    setCheckoutOpen(true);
  };

  const summary = `Pro · ${yearly ? t("pr_yearly") : t("pr_monthly")} · ${money(yearly ? p.yearly : p.monthly)}`;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-5 sm:px-10 py-5 max-w-6xl mx-auto w-full">
        <Logo onClick={() => navigate("/")} />
        <HeaderRight />
      </header>

      <main className="flex-1 max-w-5xl mx-auto w-full px-5 sm:px-10 pb-16">
        <section className="text-center max-w-2xl mx-auto pt-4 pb-8 animate-fade-up">
          <h1 className="font-head font-semibold text-4xl sm:text-5xl text-fg tracking-tight leading-[1.05]">{t("pr_title")}</h1>
          <p className="text-muted-foreground mt-4 text-base sm:text-lg">{t("pr_sub")}</p>
        </section>

        {comingSoon && (
          <div role="status" data-testid="pricing-coming-soon" className="card-medkit bg-accent/60 px-5 py-3 text-center text-sm font-bold text-accent-foreground mb-6">
            {t("pr_coming_soon")}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-center gap-4 mb-8">
          <div role="group" aria-label={t("pr_billing")} className="inline-flex rounded-full border border-border bg-white p-1">
            {[["month", "pr_monthly"], ["year", "pr_yearly"]].map(([v, k]) => (
              <button key={v} type="button" data-testid={`pricing-toggle-${v === "year" ? "yearly" : "monthly"}`} aria-pressed={interval === v} onClick={() => setIntervalSel(v)}
                className={`px-5 py-1.5 rounded-full text-sm font-extrabold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${interval === v ? "bg-primary text-white" : "text-fg hover:text-primary"}`}>
                {t(k)}
                {v === "year" && <span className={`ml-2 text-[10px] font-black px-1.5 py-0.5 rounded-full ${interval === v ? "bg-white/25" : "bg-secondary/25 text-secondary"}`}>-{p.savePct}%</span>}
              </button>
            ))}
          </div>
          <div role="group" aria-label={t("currency")} className="inline-flex gap-1">
            {["USD", "TRY"].map((c) => (
              <button key={c} type="button" data-testid={`pricing-currency-${c.toLowerCase()}`} aria-pressed={currency === c} onClick={() => setCurrency(c)}
                className={`px-3 py-1 rounded-full text-xs font-extrabold border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${currency === c ? "border-primary text-primary bg-white" : "border-border text-muted-foreground hover:border-primary"}`}>{c}</button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-6 items-stretch">
          {/* Free */}
          <section aria-labelledby="plan-free" className="md:col-span-2 card-medkit p-7 flex flex-col animate-fade-up">
            <h2 id="plan-free" className="font-head font-semibold text-xl text-fg">{t("plan_free")}</h2>
            <div className="mt-3 flex items-baseline gap-1">
              <span className="font-head font-semibold text-5xl text-fg">{money(0)}</span>
            </div>
            <p className="text-sm text-muted-foreground mt-1 mb-5">{t("pr_free_tag")}</p>
            <ul className="space-y-3 mb-7">{FREE_FEATURES.map((k) => <Feature key={k} text={t(k)} />)}</ul>
            <GameButton variant="ghost" data-testid="pricing-free-cta" className="mt-auto w-full"
              onClick={() => (isAuthed ? navigate("/") : login("/"))}>
              {isAuthed && !isPro ? t("pr_current") : t("pr_free_cta")}
            </GameButton>
          </section>

          {/* Pro */}
          <section aria-labelledby="plan-pro" className="md:col-span-3 card-medkit p-7 flex flex-col relative border-primary shadow-[0_18px_50px_rgb(255,147,123,0.22)] md:-translate-y-2 animate-fade-up">
            <span className="absolute -top-3.5 left-7 inline-flex items-center gap-1 bg-primary text-white text-[11px] font-black uppercase tracking-wide px-3 py-1 rounded-full rotate-[-2deg] shadow-[0_3px_0_#E0705A]">
              <Sparkles size={12} /> {t("pr_popular")}
            </span>
            <h2 id="plan-pro" className="font-head font-semibold text-xl text-fg">{t("plan_pro")}</h2>

            {yearly ? (
              <div data-testid="pricing-yearly-block">
                <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <s data-testid="pricing-yearly-list-price" className="line-through text-muted-foreground text-xl font-bold decoration-2" aria-label={`${t("pr_was")} ${money(p.list)}`}>{money(p.list)}</s>
                  <span data-testid="pricing-yearly-price" className="font-head font-semibold text-6xl text-primary leading-none">{money(p.yearly)}</span>
                  <span className="text-muted-foreground font-bold">{t("pr_per_year")}</span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span data-testid="pricing-save-badge" className="inline-flex bg-secondary text-white text-xs font-black px-3 py-1 rounded-full">
                    {fmt(t("pr_save"), { amount: money(p.save), pct: p.savePct })}
                  </span>
                  <span className="inline-flex bg-accent text-accent-foreground text-xs font-black px-3 py-1 rounded-full">{t("pr_months_free")}</span>
                </div>
                <p data-testid="pricing-yearly-permonth" className="text-sm text-muted-foreground mt-2 font-semibold">
                  {fmt(t("pr_per_month_billed_yearly"), { amount: formatMoney(p.yearlyPerMonth, currency, lang) })}
                </p>
              </div>
            ) : (
              <div data-testid="pricing-monthly-block" className="mt-3 flex items-baseline gap-1">
                <span data-testid="pricing-monthly-price" className="font-head font-semibold text-6xl text-fg leading-none">{money(p.monthly)}</span>
                <span className="text-muted-foreground font-bold">{t("pr_per_month")}</span>
              </div>
            )}

            <p className="text-xs text-muted-foreground mt-3 mb-5">{currency === "TRY" ? t("pr_currency_try") : t("pr_currency_usd")}</p>
            <ul className="space-y-3 mb-7">{PRO_FEATURES.map((k) => <Feature key={k} text={t(k)} />)}</ul>
            <GameButton data-testid="pricing-pro-cta" className="mt-auto w-full !py-4 !text-lg" disabled={comingSoon || isPro} onClick={onCta}>
              {comingSoon ? t("pr_cta_soon") : isPro ? t("pr_current") : isAuthed ? t("pr_cta_upgrade") : t("pr_cta_signin")}
            </GameButton>
            {isPro && <Link to="/account" className="text-center text-sm font-bold text-primary mt-3 hover:underline">{t("my_account")}</Link>}
          </section>
        </div>

        <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground mt-8 font-semibold">
          <ShieldCheck size={16} className="text-secondary" /> {t("pr_secure")}
        </p>

        <section aria-labelledby="faq-h" className="mt-14 max-w-3xl mx-auto">
          <h2 id="faq-h" className="font-head font-semibold text-2xl text-fg mb-4">{t("faq_title")}</h2>
          <div className="space-y-3">
            {[1, 2, 3, 4].map((n) => (
              <details key={n} data-testid={`faq-${n}`} className="card-medkit px-5 py-4 group">
                <summary className="font-head font-semibold text-fg cursor-pointer list-none flex justify-between items-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
                  {t(`faq_q${n}`)}
                  <span className="text-primary text-xl transition-transform group-open:rotate-45 motion-reduce:transition-none" aria-hidden="true">+</span>
                </summary>
                <p className="text-sm text-muted-foreground mt-3 leading-relaxed">
                  {t(`faq_a${n}`)}{" "}
                  {n === 3 && <Link to="/legal/refund" className="text-primary font-bold hover:underline">{t("legal_refund")}</Link>}
                </p>
              </details>
            ))}
          </div>
        </section>
      </main>

      <CheckoutModal open={checkoutOpen} onClose={() => setCheckoutOpen(false)} planId={planId}
        currency={currency} onCurrencyChange={setCurrency} summary={summary}
        onUnavailable={() => setComingSoon(true)} />
      <Footer />
    </div>
  );
}
