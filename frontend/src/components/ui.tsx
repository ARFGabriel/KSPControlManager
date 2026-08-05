import type { ReactNode } from "react";

export function Panel({
  title,
  extra,
  children,
  className = "",
  grandir = false,
}: {
  title: string;
  extra?: ReactNode;
  children: ReactNode;
  /** Classes supplémentaires, par ex. "radio" pour un corps en flex. */
  className?: string;
  /** Le panneau absorbe la hauteur restante de sa colonne. */
  grandir?: boolean;
}) {
  return (
    <section className={`panel ${grandir ? "grandir" : ""} ${className}`.trim()}>
      <header>
        <span>{title}</span>
        {extra}
      </header>
      <div className="body">{children}</div>
    </section>
  );
}

type StatTone = "" | "big" | "accent" | "good" | "alert";

export function Stat({
  label,
  value,
  unit,
  tone = "",
}: {
  label: string;
  value: string | number;
  unit?: string;
  tone?: StatTone;
}) {
  return (
    <div className={`stat ${tone}`}>
      <span className="label">{label}</span>
      <span className="value">
        {value}
        {unit ? <span style={{ color: "var(--dim)", fontSize: 12 }}> {unit}</span> : null}
      </span>
    </div>
  );
}

export function Bar({
  label,
  amount,
  maximum,
  color = "var(--cyan)",
  text,
}: {
  label: string;
  amount: number;
  maximum: number;
  color?: string;
  text?: string;
}) {
  const ratio = maximum > 0 ? Math.max(0, Math.min(1, amount / maximum)) : 0;
  // En dessous de 15 % la barre passe au rouge : on veut voir venir la panne
  // seche sans avoir a lire les chiffres.
  const fill = ratio < 0.15 ? "var(--red)" : color;
  return (
    <div className="bar">
      <div className="head">
        <span>{label}</span>
        <span className="amount">{text ?? `${Math.round(ratio * 100)} %`}</span>
      </div>
      <div className="track">
        <div className="fill" style={{ width: `${ratio * 100}%`, background: fill }} />
      </div>
    </div>
  );
}

export function Badge({
  tone,
  children,
}: {
  tone: "ok" | "warn" | "bad" | "info";
  children: ReactNode;
}) {
  return (
    <span className={`badge ${tone}`}>
      <span className="dot" />
      {children}
    </span>
  );
}
