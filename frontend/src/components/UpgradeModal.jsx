import React from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "./ui/dialog";
import { GameButton } from "./GameButton";
import { useLang } from "../context/LangContext";
import { fmt } from "../i18n";

export default function UpgradeModal({ open, reason, info, onClose }) {
  const { t } = useLang();
  const navigate = useNavigate();
  const isQuota = reason === "quota";
  const body = isQuota
    ? fmt(t("upgrade_quota_body"), { limit: info?.limit ?? 3 })
    : t("upgrade_generation_body");

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="upgrade-modal" className="rounded-3xl border border-border bg-card max-w-md">
        <DialogHeader>
          <div className="w-12 h-12 rounded-2xl bg-primary flex items-center justify-center rotate-3 shadow-[0_4px_0_#E0705A] mb-2">
            <Sparkles size={22} color="#fff" />
          </div>
          <DialogTitle className="font-head font-semibold text-2xl text-fg">
            {isQuota ? t("upgrade_quota_title") : t("upgrade_generation_title")}
          </DialogTitle>
          <DialogDescription className="text-base text-muted-foreground leading-relaxed">{body}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col sm:flex-row gap-3 mt-2">
          <GameButton data-testid="upgrade-modal-cta" className="flex-1" onClick={() => { onClose(); navigate("/pricing"); }}>
            {t("upgrade_cta")}
          </GameButton>
          <GameButton variant="ghost" data-testid="upgrade-modal-close" className="flex-1" onClick={onClose}>
            {t("not_now")}
          </GameButton>
        </div>
      </DialogContent>
    </Dialog>
  );
}
