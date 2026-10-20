import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errInfo, loginUrl } from "../lib/api";
import { useLang } from "./LangContext";
import UpgradeModal from "../components/UpgradeModal";

const AuthContext = createContext(null);

const ANON = { user: null, plan: "free", limits: null, used: null };

export const AuthProvider = ({ children }) => {
  const { t } = useLang();
  const location = useLocation();
  const navigate = useNavigate();
  const [state, setState] = useState(ANON);
  const [loading, setLoading] = useState(true);
  const [upgrade, setUpgrade] = useState({ open: false, reason: "quota", info: null });

  const refresh = useCallback(async () => {
    try {
      const d = await api.me();
      if (d?.authenticated) {
        setState({ user: d.user, plan: d.plan || "free", limits: d.limits || null, used: d.used || null });
      } else {
        setState(ANON);
      }
    } catch (e) {
      setState(ANON);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Handle redirect-back flags from the OAuth round trip (?login=failed|unverified).
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const flag = params.get("login");
    if (!flag) return;
    toast.error(flag === "unverified" ? t("login_unverified") : t("login_failed"));
    params.delete("login");
    const qs = params.toString();
    navigate({ pathname: location.pathname, search: qs ? `?${qs}` : "" }, { replace: true });
  }, [location.search, location.pathname, navigate, t]);

  const login = useCallback((next) => {
    const target = next || `${window.location.pathname}${window.location.search}`;
    window.location.assign(loginUrl(target));
  }, []);

  const logout = useCallback(async () => {
    try { await api.logout(); } catch (e) { /* ignore: cookie may already be gone */ }
    setState(ANON);
    await refresh();
    navigate("/");
  }, [navigate, refresh]);

  const showUpgrade = useCallback((reason, info = null) => setUpgrade({ open: true, reason, info }), []);
  const closeUpgrade = useCallback(() => setUpgrade((u) => ({ ...u, open: false })), []);

  /** Shared handler for 401 / 402 on gated actions. Returns true if it consumed the error. */
  const handleGateError = useCallback((e, next) => {
    const info = errInfo(e);
    if (info.status === 401) { login(next); return true; }
    if (info.status === 402) {
      showUpgrade(info.code === "upgrade_required" ? "upgrade_required" : "quota", info.detail);
      return true;
    }
    return false;
  }, [login, showUpgrade]);

  const value = useMemo(
    () => ({ ...state, isAuthed: !!state.user, loading, login, logout, refresh, showUpgrade, handleGateError }),
    [state, loading, login, logout, refresh, showUpgrade, handleGateError]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
      <UpgradeModal open={upgrade.open} reason={upgrade.reason} info={upgrade.info} onClose={closeUpgrade} />
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
