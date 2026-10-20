import axios from "axios";
import { toast } from "sonner";
import { STRINGS } from "../i18n";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

// Cookie session (vaka_session, httpOnly) must travel with every request.
axios.defaults.withCredentials = true;

export const loginUrl = (next = "/") => `${API}/auth/google/login?next=${encodeURIComponent(next)}`;

/** Normalised view of an axios error. */
export const errInfo = (e) => {
  const status = e?.response?.status ?? 0;
  const raw = e?.response?.data?.detail;
  const detail = raw && typeof raw === "object" ? raw : null;
  const code = detail?.code || (typeof raw === "string" ? raw : null);
  const retryAfter = Number(e?.response?.headers?.["retry-after"]) || null;
  return { status, detail, code, retryAfter };
};

const currentLang = () => {
  try { return localStorage.getItem("vaka_lang") === "en" ? "en" : "tr"; } catch { return "tr"; }
};

/** Friendly toast for 429 responses. */
export const toastRateLimit = (info) => {
  const s = STRINGS[currentLang()];
  let msg = s.err_rate_limit;
  if (info.code === "daily_ai_budget_reached") msg = s.err_daily_budget;
  else if (info.code === "monthly_ai_budget_reached") msg = s.err_monthly_budget;
  else if (info.code === "too_many_concurrent_ai_requests") msg = s.err_concurrent;
  if (info.retryAfter) msg = `${msg} (${info.retryAfter}${s.seconds_short})`;
  toast.warning(msg);
};

axios.interceptors.response.use(
  (r) => r,
  (e) => {
    const info = errInfo(e);
    const url = e?.config?.url || "";
    if (info.status === 429) {
      toastRateLimit(info);
      e.handled = true;
    } else if (info.status === 401 && url.includes("/sessions")) {
      // Session expired / not signed in: go through login and come back.
      e.handled = true;
      window.location.assign(loginUrl(window.location.pathname));
    }
    return Promise.reject(e);
  }
);

export const newIdempotencyKey = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
      });

const get = (path, params) => axios.get(`${API}${path}`, { params }).then((r) => r.data);
const post = (path, body, config) => axios.post(`${API}${path}`, body, config).then((r) => r.data);

export const api = {
  listTopics: (lang) => get("/topics", { lang }),
  listCases: (lang, topic) => get("/cases", { lang, topic }),
  /** Paginated: resolves {items, total}. */
  listCasesPage: (lang, topic, offset = 0, limit = 50, difficulty) =>
    axios.get(`${API}/cases`, { params: { lang, topic, limit, offset, difficulty } }).then((r) => ({
      items: r.data,
      total: Number(r.headers["x-total-count"]) || r.data.length,
    })),
  caseDetail: (id, lang) => get(`/cases/${id}`, { lang }),
  createSession: (case_id, lang) => post("/sessions", { case_id, lang }),
  getSession: (sid) => get(`/sessions/${sid}`),
  sendMessage: (sid, text) => post(`/sessions/${sid}/message`, { text }),
  runExam: (sid, action_id) => post(`/sessions/${sid}/exam`, { action_id }),
  orderTest: (sid, action_id) => post(`/sessions/${sid}/test`, { action_id }),
  xrayAnswer: (sid, test_id, option_id) => post(`/sessions/${sid}/xray-answer`, { test_id, option_id }),
  commit: (sid, body) => post(`/sessions/${sid}/commit`, body),
  score: (sid) => post(`/sessions/${sid}/score`),
  demo: (lang) => get("/demo", { lang }),
  tts: (text) => post("/tts", { text }),

  // auth / account
  authConfig: () => get("/auth/config"),
  me: () => get("/auth/me"),
  logout: () => post("/auth/logout"),
  listMySessions: (limit = 20, before) => get("/sessions", { limit, before }),
  exportMyData: () => axios.get(`${API}/me/export`, { responseType: "blob" }),
  deleteAccount: () => axios.delete(`${API}/me`, { data: { confirm: "DELETE" } }).then((r) => r.data),

  // AI case generation (async job)
  startGeneration: (topic, lang, idempotencyKey) =>
    post("/cases/generate", { topic, lang }, { headers: { "Idempotency-Key": idempotencyKey } }),
  getJob: (jobId) => get(`/jobs/${jobId}`),

  // billing
  billingPlans: () => get("/billing/plans"),
  subscription: () => get("/billing/subscription"),
  checkout: (body) => post("/billing/checkout", body),
  cancelSubscription: () => post("/billing/cancel"),
};
