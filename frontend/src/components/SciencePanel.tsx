import { useEffect, useState } from "react";

import { Panel, Stat } from "./ui";
import * as f from "../format";
import { getJson } from "../api";

interface Experience {
  piece: string;
  sujet: string;
  biome: string;
  quantite: number;
  science: number;
  transmission: number;
  reutilisable: boolean;
  inoperante: boolean;
}

interface Inventaire {
  disponible: boolean;
  raison?: string;
  experiences: Experience[];
  nombre: number;
  science: number;
  transmission: number;
  perte_transmission: number;
  message: string;
}

/** Une expérience ne se déclenche pas dix fois par seconde : trois secondes
 *  suffisent, et la lecture coûte plusieurs appels par pièce. */
const PERIODE_MS = 3000;

/**
 * Science embarquée non transmise.
 *
 * Le panneau ne s'affiche que lorsqu'il y a vraiment des données à bord : le
 * reste du temps, il ne prendrait de la place que pour dire « rien ».
 */
export function SciencePanel() {
  const [inv, setInv] = useState<Inventaire | null>(null);

  useEffect(() => {
    const charger = async () => {
      const data = await getJson<Inventaire>("/api/science");
      if (data) setInv(data);
    };
    charger();
    const timer = window.setInterval(charger, PERIODE_MS);
    return () => window.clearInterval(timer);
  }, []);

  if (!inv?.disponible || inv.experiences.length === 0) return null;

  return (
    <Panel
      title="Science à bord"
      extra={<span>{f.num(inv.science, 1)} pts</span>}
    >
      <p className="science-message">{inv.message}</p>

      {inv.perte_transmission > 0.5 && (
        <Stat
          label="Si transmis par radio"
          value={`${f.num(inv.transmission, 1)} pts`}
          tone="alert"
        />
      )}

      <div className="science-liste">
        {inv.experiences.map((e, i) => (
          <div key={i} className="science-ligne">
            <div className="haut">
              <span className="sujet">{e.sujet}</span>
              <span className="valeur">{f.num(e.science, 1)}</span>
            </div>
            <div className="bas">
              {e.piece}
              {e.biome ? ` — ${e.biome}` : ""}
              {/* Une expérience non réutilisable est perdue si on la relance
                  sans avoir récupéré ses données : ça se dit. */}
              {!e.reutilisable && <span className="unique"> · usage unique</span>}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
