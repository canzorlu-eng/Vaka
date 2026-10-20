import { useCallback, useEffect, useRef, useState } from "react";
import { api, errInfo, newIdempotencyKey } from "../lib/api";

const STORAGE_KEY = "vaka_gen_job";
const POLL_MS = 2000;
const MAX_WAIT_MS = 4 * 60 * 1000;
const POST_RETRIES = 2;

const store = {
  read() { try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null"); } catch { return null; } },
  write(v) { try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  clear() { try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* storage unavailable */ } },
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Drives the async case-generation job: start (idempotent), poll, resume after reload.
 * callbacks: onCompleted(result), onError({kind, info}) where kind is
 * "upgrade_required" | "quota" | "unavailable" | "failed" | "timeout" | "auth".
 */
export function useGenerationJob({ topic, lang, onCompleted, onError }) {
  const [job, setJob] = useState(null); // {job_id,status,progress,stage}
  const alive = useRef(true);
  const runId = useRef(0);
  const cb = useRef({ onCompleted, onError });
  cb.current = { onCompleted, onError };

  useEffect(() => { alive.current = true; return () => { alive.current = false; runId.current += 1; }; }, []);

  const poll = useCallback(async (jobId) => {
    const my = ++runId.current;
    const started = Date.now();
    const live = () => alive.current && runId.current === my;
    while (live()) {
      let j;
      try {
        j = await api.getJob(jobId);
      } catch (e) {
        const info = errInfo(e);
        if (info.status === 404 || info.status === 401) {
          store.clear(); if (live()) setJob(null);
          cb.current.onError?.({ kind: info.status === 401 ? "auth" : "failed", info });
          return;
        }
        j = null; // transient: keep polling until timeout
      }
      if (!live()) return;
      if (j) {
        setJob(j);
        if (j.status === "completed") { store.clear(); setJob(null); cb.current.onCompleted?.(j.result); return; }
        if (j.status === "failed") { store.clear(); setJob(null); cb.current.onError?.({ kind: "failed", info: { detail: j.error } }); return; }
      }
      if (Date.now() - started > MAX_WAIT_MS) {
        store.clear(); setJob(null); cb.current.onError?.({ kind: "timeout" }); return;
      }
      await sleep(POLL_MS);
    }
  }, []);

  // Resume an in-flight job after reload.
  useEffect(() => {
    const saved = store.read();
    if (saved?.jobId && saved.topic === topic) {
      setJob({ job_id: saved.jobId, status: "queued", progress: 0, stage: null });
      poll(saved.jobId);
    }
  }, [topic, poll]);

  const start = useCallback(async () => {
    const key = newIdempotencyKey(); // one key per click, reused for retries
    setJob({ job_id: null, status: "queued", progress: 0, stage: null });
    let lastErr;
    for (let attempt = 0; attempt <= POST_RETRIES; attempt += 1) {
      try {
        const j = await api.startGeneration(topic, lang, key);
        store.write({ jobId: j.job_id, topic });
        setJob(j);
        if (j.status === "completed") { store.clear(); setJob(null); cb.current.onCompleted?.(j.result); return; }
        poll(j.job_id);
        return;
      } catch (e) {
        lastErr = e;
        const info = errInfo(e);
        if (info.status !== 0 && info.status < 500) break; // 4xx: don't retry
        if (info.status === 503) break;
        await sleep(1000 * (attempt + 1));
      }
    }
    setJob(null);
    const info = errInfo(lastErr);
    let kind = "failed";
    if (info.status === 401) kind = "auth";
    else if (info.status === 402) kind = info.code === "upgrade_required" ? "upgrade_required" : "quota";
    else if (info.status === 503) kind = "unavailable";
    else if (info.status === 429) kind = "handled";
    cb.current.onError?.({ kind, info });
  }, [topic, lang, poll]);

  return { job, running: !!job, start };
}
