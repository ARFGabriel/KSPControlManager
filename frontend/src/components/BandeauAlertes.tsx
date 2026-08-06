import type { Rappel } from "../useRappels";
import type { Telemetry } from "../types";

/**
 * Bandeau d'alertes, sous la barre supérieure.
 *
 * Il existe parce que les deux informations qu'il porte ne peuvent pas
 * attendre qu'on ouvre le bon panneau : une batterie qui se vide et une
 * fenêtre de tir qui arrive sont des échéances, pas des mesures. Elles
 * doivent donc suivre le joueur d'une scène à l'autre.
 *
 * Rien n'est affiché quand tout va bien : un bandeau permanent finirait par
 * ne plus être lu.
 */
export function BandeauAlertes({
  t,
  rappels,
  onRetirer,
}: {
  t: Telemetry | null;
  rappels: Rappel[];
  onRetirer: (id: string) => void;
}) {
  const alertes = t?.veille?.alertes ?? [];
  if (alertes.length === 0 && rappels.length === 0) return null;

  return (
    <div className="bandeau">
      {alertes.map((a, i) => (
        <div key={`veille-${i}`} className="alerte danger">
          <span className="pastille" />
          {a}
        </div>
      ))}

      {rappels.map((r) => (
        <div key={r.id} className={`alerte ${r.imminent ? "urgent" : "info"}`}>
          <span className="pastille" />
          {r.message}
          <button
            type="button"
            className="fermer"
            title="Ne plus rappeler cette fenêtre"
            onClick={() => onRetirer(r.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
