import { useEffect, useState } from "react";

import * as f from "../format";
import { apiUrl } from "../api";

interface Cible {
  nom: string;
  genre: string;
}

interface Resultat {
  possible: boolean;
  raison?: string;
  pose?: boolean;
  cible?: string;
  delta_v?: number;
  attente?: number;
  duree_transfert?: number;
  angle_actuel?: number;
  angle_vise?: number;
  altitude_cible?: number;
}

/**
 * Pose de nœud de manœuvre depuis le tableau de bord.
 *
 * Le calcul se fait toujours en simulation d'abord : on montre ce qu'on va
 * écrire avant de l'écrire. Modifier la partie du joueur reste une action
 * délibérée, jamais un effet de bord d'un affichage.
 */
export function NodePlanner({ noeudExistant }: { noeudExistant: boolean }) {
  const [cibles, setCibles] = useState<Cible[]>([]);
  const [cible, setCible] = useState("");
  const [resultat, setResultat] = useState<Resultat | null>(null);
  const [occupe, setOccupe] = useState(false);

  useEffect(() => {
    fetch(apiUrl("/api/noeud/cibles"))
      .then((r) => r.json())
      .then((d) => {
        setCibles(d.cibles ?? []);
        if (d.cibles?.length && !cible) setCible(d.cibles[0].nom);
      })
      .catch(() => undefined);
  }, []);

  const appeler = async (simuler: boolean) => {
    if (!cible) return;
    setOccupe(true);
    try {
      const params = new URLSearchParams({ cible, simuler: String(simuler) });
      const r = await fetch(apiUrl(`/api/noeud/poser?${params}`), { method: "POST" });
      setResultat(await r.json());
    } catch {
      setResultat({ possible: false, raison: "Le backend n'a pas répondu." });
    } finally {
      setOccupe(false);
    }
  };

  const effacer = async () => {
    setOccupe(true);
    try {
      await fetch(apiUrl("/api/noeud/effacer"), { method: "POST" });
      setResultat(null);
    } finally {
      setOccupe(false);
    }
  };

  if (cibles.length === 0) return null;

  return (
    <div className="node-planner">
      <div className="tete">Poser une manœuvre</div>

      <div className="ligne">
        <select value={cible} onChange={(e) => setCible(e.target.value)}>
          {cibles.map((c) => (
            <option key={c.nom} value={c.nom}>
              {c.nom}
              {c.genre === "vaisseau" ? " (vaisseau)" : ""}
            </option>
          ))}
        </select>
        <button onClick={() => appeler(true)} disabled={occupe}>
          Calculer
        </button>
      </div>

      {resultat && !resultat.possible && (
        <p className="raison">{resultat.raison}</p>
      )}

      {resultat?.possible && (
        <>
          <div className="apercu">
            <span>Δv</span>
            <b>{f.num(resultat.delta_v ?? 0, 1)} m/s</b>
            <span>dans</span>
            <b>{f.duration(resultat.attente ?? 0)}</b>
            <span>trajet</span>
            <b>{f.duration(resultat.duree_transfert ?? 0)}</b>
          </div>

          {resultat.pose ? (
            <p className="succes">
              Nœud posé dans la partie. Il apparaît sur ta carte.
            </p>
          ) : (
            <div className="ligne">
              <button className="poser" onClick={() => appeler(false)} disabled={occupe}>
                Écrire dans le jeu
              </button>
            </div>
          )}
        </>
      )}

      {(noeudExistant || resultat?.pose) && (
        <div className="ligne">
          <button onClick={effacer} disabled={occupe}>
            Effacer les nœuds
          </button>
        </div>
      )}
    </div>
  );
}
