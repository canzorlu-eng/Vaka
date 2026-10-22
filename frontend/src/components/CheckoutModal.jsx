import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { GameButton } from "./GameButton";
import { useLang } from "../context/LangContext";
import { api, errInfo } from "../lib/api";

const EMPTY = { name: "", surname: "", gsm_number: "", identity_number: "", address: "", city: "", country: "", zip_code: "" };

const Field = ({ id, label, value, onChange, type = "text", autoComplete, required = true, hint, ...rest }) => (
  <div>
    <label htmlFor={id} className="block text-xs font-bold text-fg mb-1">{label}{required && <span aria-hidden="true"> *</span>}</label>
    <input id={id} data-testid={`checkout-${id}`} type={type} value={value} onChange={onChange} required={required}
      autoComplete={autoComplete} aria-describedby={hint ? `${id}-hint` : undefined}
      className="w-full rounded-xl border border-border bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/40" {...rest} />
    {hint && <p id={`${id}-hint`} className="text-[11px] text-muted-foreground mt-1">{hint}</p>}
  </div>
);

export default function CheckoutModal({ open, onClose, planId, currency, onCurrencyChange, summary, onUnavailable }) {
  const { t } = useLang();
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const isTry = currency === "TRY";

  useEffect(() => { if (!open) setBusy(false); }, [open]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const customer = { ...form };
      if (!isTry) delete customer.identity_number;
      const res = await api.checkout({ plan: planId, currency, customer });
      // Our own pay page (iyzico's embedded subscription form under a page-scoped CSP).
      if (typeof res?.checkout_url === "string" && res.checkout_url.startsWith("/api/billing/pay/")) {
        window.location.assign(res.checkout_url);
        return;
      }
      throw new Error("empty checkout response");
    } catch (err) {
      setBusy(false);
      if (err.handled) return;
      const info = errInfo(err);
      if (info.status === 404 || info.status === 503) { onUnavailable?.(); onClose(); return; }
      toast.error(t("checkout_failed"));
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="checkout-modal" className="rounded-3xl border border-border bg-card max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-head font-semibold text-2xl text-fg">{t("checkout_title")}</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">{summary}</DialogDescription>
        </DialogHeader>
      <form onSubmit={submit} className="space-y-3" aria-label={t("checkout_title")}>
          <fieldset className="flex items-center gap-2" aria-label={t("currency")}>
            {["TRY", "USD"].map((c) => (
              <button key={c} type="button" data-testid={`checkout-currency-${c.toLowerCase()}`} aria-pressed={currency === c} onClick={() => onCurrencyChange(c)}
                className={`px-4 py-1 rounded-full text-sm font-bold border ${currency === c ? "bg-primary text-white border-primary" : "bg-white border-border hover:border-primary"}`}>{c}</button>
            ))}
          </fieldset>
          <div className="grid grid-cols-2 gap-3">
            <Field id="name" label={t("co_name")} value={form.name} onChange={set("name")} autoComplete="given-name" />
            <Field id="surname" label={t("co_surname")} value={form.surname} onChange={set("surname")} autoComplete="family-name" />
          </div>
          <Field id="gsm_number" label={t("co_phone")} type="tel" value={form.gsm_number} onChange={set("gsm_number")} autoComplete="tel" placeholder="+905xxxxxxxxx" />
          {isTry && (
            <Field id="identity_number" label={t("co_identity")} value={form.identity_number} onChange={set("identity_number")}
              inputMode="numeric" pattern="[0-9]{11}" maxLength={11} hint={t("co_identity_hint")} autoComplete="off" />
          )}
          <Field id="address" label={t("co_address")} value={form.address} onChange={set("address")} autoComplete="street-address" />
          <div className="grid grid-cols-3 gap-3">
            <Field id="city" label={t("co_city")} value={form.city} onChange={set("city")} autoComplete="address-level2" />
            <Field id="country" label={t("co_country")} value={form.country} onChange={set("country")} autoComplete="country-name" />
            <Field id="zip_code" label={t("co_zip")} value={form.zip_code} onChange={set("zip_code")} autoComplete="postal-code" />
          </div>
          <p className="text-xs text-muted-foreground">{t("co_privacy_note")}</p>
          <GameButton type="submit" data-testid="checkout-submit" className="w-full" disabled={busy}>
            {busy ? "…" : t("co_continue")}
          </GameButton>
        </form>
      </DialogContent>
    </Dialog>
  );
}
