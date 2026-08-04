/** Mise en forme des grandeurs, dans les conventions du jeu. */

/** Temps de mission au format T+HH:MM:SS (ou avec les jours si besoin). */
export function met(seconds: number): string {
  if (!isFinite(seconds)) return "T+--:--:--";
  const sign = seconds < 0 ? "-" : "+";
  let s = Math.floor(Math.abs(seconds));
  const days = Math.floor(s / 21600); // une journee kerbale = 6 h
  s -= days * 21600;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  const base = `${pad(h)}:${pad(m)}:${pad(sec)}`;
  return days > 0 ? `T${sign}${days}j ${base}` : `T${sign}${base}`;
}

/** Duree courte, pour un temps restant. */
export function duration(seconds: number): string {
  if (!isFinite(seconds) || seconds <= 0) return "--:--";
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

/** Distance : metres en dessous de 10 km, kilometres au-dela. */
export function distance(meters: number): string {
  if (!isFinite(meters)) return "--";
  const abs = Math.abs(meters);
  if (abs >= 1e9) return `${(meters / 1e9).toFixed(3)} Gm`;
  if (abs >= 1e6) return `${(meters / 1e6).toFixed(3)} Mm`;
  if (abs >= 10_000) return `${(meters / 1000).toFixed(2)} km`;
  return `${meters.toFixed(0)} m`;
}

/** Vitesse : toujours en m/s, comme le jeu. */
export function speed(mps: number): string {
  if (!isFinite(mps)) return "--";
  return `${num(mps, Math.abs(mps) < 100 ? 1 : 0)} m/s`;
}

export function num(value: number, digits = 1): string {
  if (!isFinite(value)) return "--";
  return value.toLocaleString("fr-FR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Pression : Pa en dessous de 1 kPa, kPa au-dela. */
export function pressure(pa: number): string {
  if (!isFinite(pa)) return "--";
  return pa >= 1000 ? `${(pa / 1000).toFixed(1)} kPa` : `${pa.toFixed(0)} Pa`;
}

const SITUATIONS: Record<string, string> = {
  pre_launch: "Sur le pas de tir",
  landed: "Au sol",
  splashed: "Amerri",
  flying: "En vol",
  sub_orbital: "Suborbital",
  orbiting: "En orbite",
  escaping: "Trajectoire de fuite",
  docked: "Amarré",
};

export function situation(key: string): string {
  return SITUATIONS[key] ?? (key || "—");
}

const RESOURCES: Record<string, string> = {
  LiquidFuel: "Carburant",
  Oxidizer: "Comburant",
  MonoPropellant: "Monergol",
  ElectricCharge: "Électricité",
  SolidFuel: "Poudre",
  XenonGas: "Xénon",
  Ablator: "Ablateur",
  IntakeAir: "Air admis",
  Ore: "Minerai",
};

export function resourceLabel(name: string): string {
  return RESOURCES[name] ?? name;
}
