"use client";
import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";
import { useTranslations } from "next-intl";
import type { Stage } from "../lib/check-stream";

const stages = ["scoring", "scoringNext", "scoringPatterns"] as const;
export function StatusTicker({ stage }: { stage: Stage }) {
  const t = useTranslations("home");
  const reduce = useReducedMotion();
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (reduce || stage !== "scoring") return;
    const timer = window.setInterval(() => setStep((n) => (n + 1) % stages.length), 1600);
    return () => window.clearInterval(timer);
  }, [reduce, stage]);
  // Only announce stage changes. Rotating copy is decorative for screen readers.
  return <p className="status" role="status"><span className="sr-only">{t(stage)}</span>
    <span aria-hidden="true">{t(reduce ? "loading" : stage === "scoring" ? stages[step] : stage)}</span></p>;
}
