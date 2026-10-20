"""End-to-end cost probe: runs a REAL practice run through the actual API (in-process) and reports what each step
cost, taken from the llm_usage ledger the app itself writes. Spends real money on the configured API keys
(typically a few cents per scenario).

Usage (dev services from docker-compose.dev.yml must be up):
  DATABASE_URL=postgresql://vaka:vaka@localhost:55432/vaka REDIS_URL=redis://localhost:56379/0 \
  SECRET_KEY=$(python -c 'import secrets;print(secrets.token_urlsafe(48))') AUTO_MIGRATE=true \
  .venv/bin/python scripts/cost_probe.py --models gemini-3.5-flash-lite,gemini-3.6-flash [--no-generation] [--no-tts]

Scenarios per model:
  authored  - a student works through a built-in case: chat (12 questions) -> exam -> tests -> diagnosis -> scoring,
              with natural TTS for every patient reply.
  generated - the same, but the case is first created by the AI generation job (what a Pro "new case" costs).
"""
import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from config import settings  # noqa: E402

QUESTIONS_TR = [
    "Merhaba, bugün sizi buraya getiren şikayet nedir?",
    "Ağrınız ne zaman başladı, kaç gündür var?",
    "Ağrıyı nasıl tarif edersiniz? Zonklayıcı mı, keskin mi?",
    "Geceleri ağrı sizi uyandırıyor mu?",
    "Soğuk ya da sıcak bir şey içince ağrı oluyor mu, ne kadar sürüyor?",
    "Ağrı başka bir yere, mesela kulağınıza yayılıyor mu?",
    "Ağrı kesici aldınız mı, işe yaradı mı?",
    "Bu dişe daha önce bir tedavi yapıldı mı?",
    "Yüzünüzde şişlik veya ateşiniz var mı?",
    "Çiğnerken ağrıyor mu?",
    "Düzenli kullandığınız bir ilaç veya alerjiniz var mı?",
    "Diş fırçalama ve diş ipi alışkanlığınız nasıl?",
]


async def usage_since(conn, user_id, since_id):
    rows = await conn.fetch(
        """SELECT kind, count(*) AS calls, sum(input_tokens) AS in_tok, sum(output_tokens) AS out_tok, sum(chars) AS chars,
                  sum(cost_usd) AS usd, sum(latency_ms) AS ms
           FROM llm_usage WHERE user_id = $1 AND id > $2 GROUP BY kind ORDER BY kind""", user_id, since_id)
    return [dict(r) for r in rows]


async def run_session(client, case_id, questions, with_tts, label, user):
    h = {"Origin": settings.public_base_url}
    t0 = time.perf_counter()
    r = await client.post("/api/sessions", json={"case_id": case_id, "lang": "tr"}, headers=h)
    r.raise_for_status()
    s = r.json()
    sid, case = s["id"], s["case"]
    replies = []
    for q in questions:
        r = await client.post(f"/api/sessions/{sid}/message", json={"text": q}, headers=h)
        r.raise_for_status()
        replies.append(r.json()["reply"])
    if with_tts:
        for text in replies:
            r = await client.post("/api/tts", json={"text": text}, headers=h)
            r.raise_for_status()
    for a in case["exam_actions"][:4]:
        (await client.post(f"/api/sessions/{sid}/exam", json={"action_id": a["id"]}, headers=h)).raise_for_status()
    for t in case["tests"][:3]:
        r = await client.post(f"/api/sessions/{sid}/test", json={"action_id": t["id"]}, headers=h)
        r.raise_for_status()
    # diagnosis/treatment: pick via the stored case (correct options)
    import catalogue
    full = await catalogue.get_case(case_id, user)
    dx = next(d["id"] for d in full["diagnosis_options"] if d["correct"])
    tx = next(d["id"] for d in full["treatment_options"] if d["correct"])
    (await client.post(f"/api/sessions/{sid}/commit", json={"diagnosis_id": dx, "treatment_id": tx}, headers=h)).raise_for_status()
    r = await client.post(f"/api/sessions/{sid}/score", headers=h)
    r.raise_for_status()
    rep = r.json()
    return {"label": label, "wall_s": round(time.perf_counter() - t0, 1), "score": rep["total"], "replies": len(replies),
            "avg_reply_chars": round(sum(map(len, replies)) / max(1, len(replies)))}


async def scenario(app, conn, user, token, model, with_gen, with_tts):
    object.__setattr__(settings, "gemini_model", model)
    out = {"model": model, "steps": {}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=settings.public_base_url,
                                 cookies={"vaka_session": token}, timeout=300) as client:
        base = await conn.fetchval("SELECT COALESCE(max(id), 0) FROM llm_usage")
        res = await run_session(client, "acute-pulpitis", QUESTIONS_TR, with_tts, "authored", user)
        authored = await usage_since(conn, user["id"], base)
        out["authored"] = {"run": res, "usage": authored, "total_usd": round(sum(float(x["usd"]) for x in authored), 5)}
        if with_gen:
            mark = await conn.fetchval("SELECT COALESCE(max(id), 0) FROM llm_usage")
            t0 = time.perf_counter()
            key = uuid.uuid4().hex
            r = await client.post("/api/cases/generate", json={"topic": "restorative", "lang": "tr"},
                                  headers={"Origin": settings.public_base_url, "Idempotency-Key": key})
            r.raise_for_status()
            job = r.json()
            while job["status"] not in ("completed", "failed") and time.perf_counter() - t0 < 300:
                await asyncio.sleep(2)
                job = (await client.get(f"/api/jobs/{job['job_id']}")).json()
            gen_s = round(time.perf_counter() - t0, 1)
            gen_usage = await usage_since(conn, user["id"], mark)
            out["generation"] = {"status": job["status"], "wall_s": gen_s, "attempts": job["attempts"], "usage": gen_usage,
                                 "total_usd": round(sum(float(x["usd"]) for x in gen_usage), 5)}
            if job["status"] == "completed":
                mark2 = await conn.fetchval("SELECT COALESCE(max(id), 0) FROM llm_usage")
                res2 = await run_session(client, job["result"]["case_id"], QUESTIONS_TR[:8], with_tts, "generated-case play", user)
                play = await usage_since(conn, user["id"], mark2)
                out["generated_play"] = {"run": res2, "usage": play, "total_usd": round(sum(float(x["usd"]) for x in play), 5)}
                out["generated_total_usd"] = round(out["generation"]["total_usd"] + out["generated_play"]["total_usd"], 5)
    return out


async def main(models, with_gen, with_tts):
    import db
    import server
    async with server.app.router.lifespan_context(server.app):
        import repo
        from auth import _hash_token
        sub = "probe-" + uuid.uuid4().hex[:10]
        user = await repo.upsert_google_user(sub, f"{sub}@probe.invalid", True, "Cost Probe", None, [f"{sub}@probe.invalid"])
        token = uuid.uuid4().hex + uuid.uuid4().hex
        await repo.create_auth_session(_hash_token(token), user["id"], 1, "cost-probe")
        results = []
        async with db.pool().acquire() as conn:
            for m in models:
                print(f"\n=== model {m} ===", flush=True)
                results.append(await scenario(server.app, conn, user, token, m, with_gen, with_tts))
        await repo.delete_user(user["id"])
    return results


def render(results):
    lines = []
    for r in results:
        lines.append(f"\n## {r['model']}")
        for key, title in (("authored", "Authored case (one full run)"), ("generation", "AI case generation"),
                           ("generated_play", "Playing the generated case")):
            if key not in r:
                continue
            blk = r[key]
            lines.append(f"\n### {title} — ${blk['total_usd']:.4f}" + (f"  ({blk.get('wall_s', blk.get('run', {}).get('wall_s'))}s wall)"))
            lines.append("| step | calls | in tok | out tok (incl. thinking) | chars | USD | latency/call |")
            lines.append("|---|---|---|---|---|---|---|")
            for u in blk["usage"]:
                calls = int(u["calls"])
                lines.append(f"| {u['kind']} | {calls} | {int(u['in_tok'] or 0)} | {int(u['out_tok'] or 0)} | {int(u['chars'] or 0)} | "
                             f"{float(u['usd']):.4f} | {int((u['ms'] or 0) / calls)} ms |")
        if "generated_total_usd" in r:
            lines.append(f"\n**New AI case + playing it: ${r['generated_total_usd']:.4f}**")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=settings.gemini_model)
    ap.add_argument("--no-generation", action="store_true")
    ap.add_argument("--no-tts", action="store_true")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out" / "cost_probe.json"))
    a = ap.parse_args()
    if not settings.gemini_api_key:
        sys.exit("GEMINI_API_KEY is not configured")
    res = asyncio.run(main([m.strip() for m in a.models.split(",")], not a.no_generation, not a.no_tts))
    Path(a.out).write_text(json.dumps(res, indent=1, default=str))
    print(render(res))
