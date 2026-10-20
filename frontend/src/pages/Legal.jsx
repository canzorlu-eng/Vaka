import React from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { useLang } from "../context/LangContext";
import { Footer, HeaderRight, Logo } from "../components/Chrome";
import { LEGAL } from "../content/legal";

const DOCS = ["terms", "privacy", "refund"];

export default function Legal() {
  const { lang, t } = useLang();
  const { doc } = useParams();
  const navigate = useNavigate();
  if (!DOCS.includes(doc)) return <Navigate to="/legal/terms" replace />;
  const content = LEGAL[lang][doc];

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-5 sm:px-10 py-5 max-w-6xl mx-auto w-full">
        <Logo onClick={() => navigate("/")} />
        <HeaderRight />
      </header>
      <main className="flex-1 max-w-3xl mx-auto w-full px-5 sm:px-10 pb-16">
        <div role="note" data-testid="legal-draft-banner" className="flex items-start gap-3 rounded-2xl border border-[#F0B458] bg-[#F0B458]/15 px-4 py-3 mb-6 text-sm font-bold text-fg">
          <AlertTriangle size={18} className="shrink-0 mt-0.5 text-[#B9801F]" /> {LEGAL[lang].banner}
        </div>
        <nav aria-label={t("legal")} className="flex flex-wrap gap-2 mb-6">
          {DOCS.map((d) => (
            <Link key={d} to={`/legal/${d}`} data-testid={`legal-tab-${d}`} aria-current={d === doc ? "page" : undefined}
              className={`px-4 py-1.5 rounded-full text-sm font-bold border ${d === doc ? "bg-primary text-white border-primary" : "bg-white border-border hover:border-primary"}`}>
              {t(`legal_${d}`)}
            </Link>
          ))}
        </nav>
        <article data-testid={`legal-${doc}`} className="card-medkit p-6 sm:p-8">
          <h1 className="font-head font-semibold text-3xl text-fg mb-1">{content.title}</h1>
          <p className="text-xs text-muted-foreground mb-6">{LEGAL[lang].updated}</p>
          {content.sections.map((s) => (
            <section key={s.h} className="mb-5">
              <h2 className="font-head font-semibold text-lg text-fg mb-2">{s.h}</h2>
              {(s.p || []).map((para) => <p key={para} className="text-sm text-fg/85 leading-relaxed mb-2">{para}</p>)}
              {s.ul && <ul className="list-disc pl-5 space-y-1 text-sm text-fg/85">{s.ul.map((li) => <li key={li}>{li}</li>)}</ul>}
            </section>
          ))}
        </article>
      </main>
      <Footer />
    </div>
  );
}
