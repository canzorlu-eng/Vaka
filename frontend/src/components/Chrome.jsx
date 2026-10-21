import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { LogOut, User, Sparkles } from "lucide-react";
import { useLang } from "../context/LangContext";
import { useAuth } from "../context/AuthContext";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "./ui/dropdown-menu";

export const Footer = () => {
  const { t } = useLang();
  return (
    <footer
      data-testid="footer-disclaimer"
      className="w-full py-5 px-4 text-center text-xs sm:text-sm text-muted-foreground border-t border-border mt-auto bg-white/40"
    >
      <span className="inline-flex items-center gap-2 font-medium">
        <span className="text-primary">⚕</span>
        {t("disclaimer")}
      </span>
      <nav aria-label={t("legal")} className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 font-semibold">
        {[["/pricing", "nav_pricing"], ["/legal/terms", "legal_terms"], ["/legal/privacy", "legal_privacy"], ["/legal/refund", "legal_refund"]].map(([to, key]) => (
          <Link key={to} to={to} data-testid={`footer-link-${to.split("/").pop()}`}
            className="hover:text-primary underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded">
            {t(key)}
          </Link>
        ))}
      </nav>
    </footer>
  );
};

export const LangToggle = () => {
  const { lang, toggle } = useLang();
  return (
    <button
      data-testid="lang-toggle"
      onClick={toggle}
      aria-label="Language / Dil"
      className="game-btn h-10 px-3 text-xs bg-white flex items-center gap-1.5 tracking-wide"
      style={{ color: "var(--fg)", borderColor: "var(--border)" }}
    >
      <span className={lang === "tr" ? "text-primary font-extrabold" : "opacity-45"}>TR</span>
      <span className="opacity-25">|</span>
      <span className={lang === "en" ? "text-primary font-extrabold" : "opacity-45"}>EN</span>
    </button>
  );
};

export const Logo = ({ onClick }) => (
  <button
    type="button"
    data-testid="logo"
    onClick={onClick}
    aria-label="Vaka"
    className="flex items-center gap-2.5 select-none rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
  >
    <span className="w-10 h-10 rounded-xl flex items-center justify-center bg-primary shadow-[0_4px_12px_-4px_rgba(15,107,99,0.6)]">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 5v14M5 12h14" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </span>
    <span className="font-head font-semibold text-[1.7rem] leading-none text-fg tracking-tight">Vaka</span>
  </button>
);

export const GoogleG = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
    <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
  </svg>
);

export const LoginButton = ({ next, className = "", label }) => {
  const { t } = useLang();
  const { login } = useAuth();
  return (
    <button
      type="button"
      data-testid="login-btn"
      onClick={() => login(next)}
      className={`game-btn inline-flex items-center gap-2.5 bg-white px-4 py-2.5 text-sm text-fg ${className}`}
      style={{ borderColor: "var(--border)" }}
    >
      <GoogleG />
      <span>{label || t("sign_in_google")}</span>
    </button>
  );
};

export const PlanBadge = ({ plan }) => {
  const { t } = useLang();
  return (
    <span
      data-testid="plan-badge"
      className={`text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-md ${plan === "pro" ? "bg-primary text-white" : "bg-accent text-accent-foreground"}`}
    >
      {plan === "pro" ? t("plan_pro") : t("plan_free")}
    </span>
  );
};

export const AuthControl = () => {
  const { t } = useLang();
  const { user, plan, loading, logout } = useAuth();
  const navigate = useNavigate();
  if (loading) return <div className="w-10 h-10 rounded-xl skeleton" aria-hidden="true" />;
  if (!user) return <LoginButton />;
  const initial = (user.name || user.email || "?").trim().charAt(0).toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        data-testid="user-menu-trigger"
        aria-label={t("account_menu")}
        className="flex items-center gap-2 h-10 rounded-xl border border-border bg-white pl-1 pr-2.5 shadow-sm transition hover:border-primary/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {user.picture ? (
          <img src={user.picture} alt="" width={32} height={32} referrerPolicy="no-referrer" className="w-8 h-8 rounded-lg object-cover" />
        ) : (
          <span className="w-8 h-8 rounded-lg bg-primary text-white font-head font-semibold flex items-center justify-center">{initial}</span>
        )}
        <PlanBadge plan={plan} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" collisionPadding={12} className="w-[min(16rem,calc(100vw-1.5rem))] rounded-2xl border border-border bg-popover p-1.5 shadow-lg">
        <DropdownMenuLabel className="font-normal">
          <div className="font-head font-semibold text-fg truncate" data-testid="user-menu-name">{user.name || user.email}</div>
          <div className="text-xs text-muted-foreground truncate">{user.email}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem data-testid="menu-account" className="gap-2 font-semibold cursor-pointer" onSelect={() => navigate("/account")}>
          <User size={16} /> {t("my_account")}
        </DropdownMenuItem>
        <DropdownMenuItem data-testid="menu-pricing" className="gap-2 font-semibold cursor-pointer" onSelect={() => navigate("/pricing")}>
          <Sparkles size={16} /> {t("nav_pricing")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem data-testid="logout-btn" className="gap-2 font-semibold cursor-pointer" onSelect={logout}>
          <LogOut size={16} /> {t("sign_out")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export const HeaderRight = () => (
  <div className="flex items-center gap-2 sm:gap-3">
    <AuthControl />
    <LangToggle />
  </div>
);
