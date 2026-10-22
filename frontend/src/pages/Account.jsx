import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Download, Trash2, CheckCircle2, XCircle } from "lucide-react";
import { api, errInfo } from "../lib/api";
import { useLang } from "../context/LangContext";
import { useAuth } from "../context/AuthContext";
import { Footer, HeaderRight, Logo, LoginButton, PlanBadge } from "../components/Chrome";
import { GameButton } from "../components/GameButton";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "../components/ui/alert-dialog";
import { fmt } from "../i18n";

const PAGE = 20;
const CHECKOUT_BANNERS = { success: "acc_checkout_success", refunded: "acc_checkout_refunded", failed: "acc_checkout_failed" };

const Meter = ({ id, label, used, limit }) => {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const hot = pct >= 100;
  return (
    <div data-testid={`meter-${id}`}>
      <div className="flex justify-between text-sm font-bold text-fg mb-1.5">
        <span>{label}</span>
        <span className={hot ? "text-primary" : "text-muted-foreground"}>{used ?? 0} / {limit ?? "—"}</span>
      </div>
      <div className="h-3 rounded-full bg-accent overflow-hidden" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={limit || 0} aria-valuenow={used || 0}>
        <div className={`h-full origin-left rounded-full transition-transform duration-500 motion-reduce:transition-none ${hot ? "bg-primary" : "bg-secondary"}`} style={{ transform: `scaleX(${pct / 100})` }} />
      </div>
    </div>
  );
};

const Card = ({ title, children, testid, tone }) => (
  <section data-testid={testid} aria-label={title} className={`card-medkit p-6 ${tone === "danger" ? "border-[#E8705B]/50" : ""}`}>
    <h2 className="font-head font-semibold text-lg text-fg mb-4">{title}</h2>
    {children}
  </section>
);

const fmtDate = (iso, lang) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString(lang === "tr" ? "tr-TR" : "en-US", { year: "numeric", month: "long", day: "numeric" });
};

export default function Account() {
  const { lang, t } = useLang();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { user, plan, limits, used, loading, refresh, logout } = useAuth();
  const [sub, setSub] = useState(null);
  const [billingUp, setBillingUp] = useState(true);
  const [history, setHistory] = useState({ items: [], next: null, loaded: false });
  const [moreBusy, setMoreBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteText, setDeleteText] = useState("");
  const [busy, setBusy] = useState(false);
  const checkout = params.get("checkout");

  const loadSub = useCallback(async () => {
    try { setSub(await api.subscription()); setBillingUp(true); } catch (e) { setBillingUp(false); }
  }, []);

  useEffect(() => { if (user) loadSub(); }, [user, loadSub]);

  // After returning from the payment page the webhook may lag: re-check shortly.
  useEffect(() => {
    if (checkout !== "success") return undefined;
    refresh();
    const id = setTimeout(() => { refresh(); loadSub(); }, 4000);
    return () => clearTimeout(id);
  }, [checkout, refresh, loadSub]);

  useEffect(() => {
    if (!user) return;
    api.listMySessions(PAGE).then((d) => setHistory({ items: d.items || [], next: d.next_before ?? null, loaded: true }))
      .catch(() => setHistory((h) => ({ ...h, loaded: true })));
  }, [user]);

  const loadMore = async () => {
    setMoreBusy(true);
    try {
      const d = await api.listMySessions(PAGE, history.next);
      setHistory((h) => ({ items: [...h.items, ...(d.items || [])], next: d.next_before ?? null, loaded: true }));
    } catch (e) { toast.error(t("err_generic")); } finally { setMoreBusy(false); }
  };

  const dismissBanner = () => { const p = new URLSearchParams(params); p.delete("checkout"); setParams(p, { replace: true }); };

  const cancel = async () => {
    setBusy(true);
    try {
      await api.cancelSubscription();
      toast.success(t("acc_cancel_ok"));
      setConfirmCancel(false);
      await loadSub();
    } catch (e) { if (!e.handled) toast.error(t("err_generic")); } finally { setBusy(false); }
  };

  const exportData = async () => {
    try {
      const r = await api.exportMyData();
      const url = URL.createObjectURL(new Blob([r.data], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url; a.download = "vaka-my-data.json";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { if (!e.handled) toast.error(t("err_generic")); }
  };

  const deleteAccount = async () => {
    setBusy(true);
    try {
      await api.deleteAccount();
      toast.success(t("acc_delete_ok"));
      setConfirmDelete(false);
      await logout();
    } catch (e) {
      const info = errInfo(e);
      if (info.status === 409 && info.code === "active_subscription") toast.error(t("acc_delete_blocked"));
      else if (!e.handled) toast.error(t("err_generic"));
    } finally { setBusy(false); }
  };

  const header = (
    <header className="flex items-center justify-between px-5 sm:px-10 py-5 max-w-6xl mx-auto w-full">
      <Logo onClick={() => navigate("/")} />
      <HeaderRight />
    </header>
  );

  if (loading) return <div className="min-h-screen flex items-center justify-center text-muted-foreground">…</div>;

  if (!user) {
    return (
      <div className="min-h-screen flex flex-col">
        {header}
        <main className="flex-1 max-w-md mx-auto w-full px-5 py-16 text-center">
          <h1 className="font-head font-semibold text-3xl text-fg mb-3">{t("my_account")}</h1>
          <p className="text-muted-foreground mb-6">{t("acc_login_required")}</p>
          <LoginButton next="/account" className="mx-auto" />
        </main>
        <Footer />
      </div>
    );
  }

  const subActive = sub && ["active", "past_due"].includes(sub.status);
  const subStatusLabel = sub ? t(`sub_${sub.status}`) : "";

  return (
    <div className="min-h-screen flex flex-col">
      {header}
      <main className="flex-1 max-w-4xl mx-auto w-full px-5 sm:px-10 pb-16 space-y-6">
        <h1 className="font-head font-semibold text-3xl sm:text-4xl text-fg tracking-tight animate-fade-up">{t("my_account")}</h1>

        {checkout && (
          <div role="status" data-testid={`checkout-banner-${checkout}`}
            className={`card-medkit px-5 py-4 flex items-start gap-3 ${checkout === "failed" ? "bg-[#E8705B]/10" : "bg-secondary/15"}`}>
            {checkout === "failed" ? <XCircle className="text-[#E8705B] shrink-0" /> : <CheckCircle2 className="text-secondary shrink-0" />}
            <p className="flex-1 text-sm font-semibold text-fg">{t(CHECKOUT_BANNERS[checkout] || "acc_checkout_failed")}</p>
            <button type="button" onClick={dismissBanner} className="text-xs font-bold text-muted-foreground hover:text-primary" aria-label={t("close")}>✕</button>
          </div>
        )}

        <Card title={t("acc_profile")} testid="account-profile">
          <div className="flex items-center gap-4">
            {user.picture ? (
              <img src={user.picture} alt="" width={64} height={64} referrerPolicy="no-referrer" className="w-16 h-16 rounded-2xl object-cover" />
            ) : (
              <div className="w-16 h-16 rounded-2xl bg-primary text-white font-head font-semibold text-2xl flex items-center justify-center">{(user.name || user.email || "?").charAt(0).toUpperCase()}</div>
            )}
            <div className="min-w-0">
              <div className="font-head font-semibold text-xl text-fg truncate" data-testid="account-name">{user.name}</div>
              <div className="text-sm text-muted-foreground truncate" data-testid="account-email">{user.email}</div>
            </div>
            <div className="ml-auto"><PlanBadge plan={plan} /></div>
          </div>
        </Card>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card title={t("acc_usage")} testid="account-usage">
            <div className="space-y-5">
              <Meter id="sessions" label={t("acc_sessions_month")} used={used?.sessions_this_month} limit={limits?.sessions_per_month} />
              <Meter id="generations" label={t("acc_generations_month")} used={used?.generations_this_month} limit={limits?.generations_per_month} />
            </div>
            {plan !== "pro" && <Link to="/pricing" data-testid="account-upgrade-link" className="inline-block mt-5 text-sm font-extrabold text-primary hover:underline">{t("upgrade_cta")} →</Link>}
          </Card>

          <Card title={t("acc_subscription")} testid="account-subscription">
            {!billingUp ? (
              <p className="text-sm text-muted-foreground">{t("pr_coming_soon")}</p>
            ) : !sub || sub.status === "none" ? (
              <div>
                <p className="text-sm text-muted-foreground mb-4">{t("acc_no_sub")}</p>
                <GameButton data-testid="account-go-pricing" className="!text-sm !px-5 !py-2.5" onClick={() => navigate("/pricing")}>{t("nav_pricing")}</GameButton>
              </div>
            ) : (
              <div className="space-y-3 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">{t("acc_status")}</span><b data-testid="sub-status">{subStatusLabel}</b></div>
                <div className="flex justify-between"><span className="text-muted-foreground">{t("acc_plan")}</span><b>{sub.plan === "pro_yearly" ? `Pro · ${t("pr_yearly")}` : sub.plan === "pro_monthly" ? `Pro · ${t("pr_monthly")}` : "Pro"}</b></div>
                <div className="flex justify-between"><span className="text-muted-foreground">{sub.cancel_at_period_end ? t("acc_ends_on") : t("acc_renews_on")}</span><b>{fmtDate(sub.current_period_end, lang)}</b></div>
                {sub.cancel_at_period_end && <p className="text-xs text-muted-foreground">{fmt(t("acc_cancel_note"), { date: fmtDate(sub.current_period_end, lang) })}</p>}
                {subActive && !sub.cancel_at_period_end && (
                  <GameButton variant="ghost" data-testid="cancel-subscription-btn" className="!text-sm !px-5 !py-2.5 mt-1" onClick={() => setConfirmCancel(true)}>{t("acc_cancel_btn")}</GameButton>
                )}
              </div>
            )}
          </Card>
        </div>

        <Card title={t("acc_history")} testid="account-history">
          {!history.loaded ? <div className="h-16 rounded-2xl bg-accent animate-pulse" /> : history.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("acc_no_history")}</p>
          ) : (
            <ul className="divide-y-2 divide-border">
              {history.items.map((s) => (
                <li key={s.id}>
                  <Link to={s.ended ? `/debrief/${s.id}` : `/sim/${s.id}`} data-testid={`history-item-${s.id}`}
                    className="flex items-center gap-3 py-3 hover:bg-accent/40 -mx-2 px-2 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                    <div className="min-w-0 flex-1">
                      <div className="font-bold text-fg truncate">{s.case_title || s.case_id}</div>
                      <div className="text-xs text-muted-foreground">{fmtDate(s.created_at, lang)} · {(s.lang || "").toUpperCase()}</div>
                    </div>
                    {s.ended && s.grade ? (
                      <span data-testid="history-grade" className="text-xs font-black px-3 py-1 rounded-full bg-secondary text-white">{s.grade}{s.total != null ? ` · ${Math.round(s.total)}` : ""}</span>
                    ) : null}
                    <span className={`text-[11px] font-black uppercase px-2.5 py-1 rounded-full ${s.ended ? "bg-accent text-accent-foreground" : "bg-primary text-white"}`}>{s.ended ? t("acc_report") : t("acc_continue")}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {history.next != null && (
            <div className="flex justify-center mt-4">
              <GameButton variant="ghost" data-testid="history-load-more" className="!text-sm !px-5 !py-2.5" onClick={loadMore} disabled={moreBusy}>{moreBusy ? "…" : t("load_more")}</GameButton>
            </div>
          )}
        </Card>

        <Card title={t("acc_data")} testid="account-data">
          <p className="text-sm text-muted-foreground mb-4">{t("acc_data_desc")}</p>
          <GameButton variant="ghost" data-testid="export-data-btn" className="!text-sm !px-5 !py-2.5 inline-flex items-center gap-2" onClick={exportData}>
            <Download size={16} /> {t("acc_export")}
          </GameButton>
        </Card>

        <Card title={t("acc_danger")} testid="account-danger" tone="danger">
          <p className="text-sm text-muted-foreground mb-4">{t("acc_delete_desc")}</p>
          <GameButton variant="danger" data-testid="delete-account-btn" className="!text-sm !px-5 !py-2.5 inline-flex items-center gap-2" onClick={() => { setDeleteText(""); setConfirmDelete(true); }}>
            <Trash2 size={16} /> {t("acc_delete_btn")}
          </GameButton>
        </Card>
      </main>

      <AlertDialog open={confirmCancel} onOpenChange={setConfirmCancel}>
        <AlertDialogContent data-testid="cancel-dialog" className="rounded-3xl border border-border">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-head font-semibold">{t("acc_cancel_title")}</AlertDialogTitle>
            <AlertDialogDescription>{fmt(t("acc_cancel_desc"), { date: fmtDate(sub?.current_period_end, lang) })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="cancel-dialog-keep">{t("acc_keep")}</AlertDialogCancel>
            <AlertDialogAction data-testid="cancel-dialog-confirm" disabled={busy} onClick={(e) => { e.preventDefault(); cancel(); }}>{t("acc_cancel_confirm")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent data-testid="delete-dialog" className="rounded-3xl border border-border">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-head font-semibold">{t("acc_delete_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("acc_delete_explain")}</AlertDialogDescription>
          </AlertDialogHeader>
          <div>
            <label htmlFor="delete-confirm" className="block text-xs font-bold mb-1">{t("acc_delete_type")}</label>
            <input id="delete-confirm" data-testid="delete-confirm-input" value={deleteText} onChange={(e) => setDeleteText(e.target.value)} autoComplete="off"
              className="w-full rounded-xl border border-border bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:border-primary" />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction data-testid="delete-confirm-btn" disabled={deleteText !== "DELETE" || busy} onClick={(e) => { e.preventDefault(); deleteAccount(); }}>{t("acc_delete_btn")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <Footer />
    </div>
  );
}
