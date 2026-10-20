export const DEFAULT_PRICES = { monthlyUsd: 9, yearlyUsd: 90, listYearlyUsd: 108, monthlyTry: 399, yearlyTry: 3990 };

export const formatMoney = (amount, currency, lang) => {
  const locale = lang === "tr" ? "tr-TR" : "en-US";
  const whole = Number.isInteger(amount);
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: whole ? 0 : 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
};

/** Derive display prices for a currency from the /billing/plans payload (with fallbacks). */
export const derivePrices = (data, currency) => {
  const plans = data?.plans || [];
  const m = plans.find((p) => p.id === "pro_monthly");
  const y = plans.find((p) => p.id === "pro_yearly");
  const d = DEFAULT_PRICES;
  const usd = currency === "USD";
  const monthly = usd ? (m?.usd ?? d.monthlyUsd) : (m?.try ?? d.monthlyTry);
  const yearly = usd ? (y?.usd ?? d.yearlyUsd) : (y?.try ?? d.yearlyTry);
  const list = usd ? (data?.list_price_yearly_usd ?? d.listYearlyUsd) : monthly * 12;
  const save = Math.max(0, list - yearly);
  return {
    monthly,
    yearly,
    list,
    save,
    savePct: list > 0 ? Math.round((save / list) * 100) : 0,
    yearlyPerMonth: Math.round((yearly / 12) * 100) / 100,
  };
};
