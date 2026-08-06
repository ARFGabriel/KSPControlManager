import { NodePlanner } from "./NodePlanner";
import { Panel, Stat } from "./ui";
import * as f from "../format";
import type { Guidage } from "../types";

const PHASES: Record<string, string> = {
  "au sol": "Au sol",
  ascension: "Ascension",
  satellisation: "Satellisation",
  "en orbite": "En orbite",
  rentree: "Rentrée",
  amarre: "Amarré",
};

/** L'écart d'attitude mérite une jauge : c'est la seule grandeur qu'on
 *  corrige en continu au manche. */
function EcartAttitude({ degres }: { degres: number }) {
  const borne = Math.min(Math.abs(degres), 90);
  const teinte =
    borne < 5 ? "var(--green)" : borne < 20 ? "var(--amber)" : "var(--red)";

  return (
    <div className="nav-ecart">
      <div className="head">
        <span>Écart de direction</span>
        <span style={{ color: teinte }}>{f.num(degres, 1)}°</span>
      </div>
      <div className="track">
        <div className="fill" style={{ width: `${(borne / 90) * 100}%`, background: teinte }} />
      </div>
    </div>
  );
}

export function NavigationPanel({ g }: { g: Guidage | null }) {
  if (!g) {
    return (
      <Panel title="Navigation">
        <div className="empty">Pas de guidage disponible.</div>
      </Panel>
    );
  }

  const allumageProche = g.noeud && g.noeud_allumage <= 10;

  return (
    <Panel
      title="Navigation"
      extra={<span>{PHASES[g.phase] ?? g.phase}</span>}
      grandir
    >
      <p className={`nav-consigne ${allumageProche ? "urgent" : ""}`}>
        {g.consigne || "—"}
      </p>

      {g.noeud && (
        <>
          <Stat
            label="Δv de la manœuvre"
            value={`${f.num(g.noeud_delta_v, 0)} m/s`}
            tone="big"
          />
          <Stat label="Nœud dans" value={f.duration(g.noeud_temps)} tone="accent" />
          <Stat
            label="Allumage dans"
            value={g.noeud_allumage > 0 ? f.duration(g.noeud_allumage) : "maintenant"}
            tone={allumageProche ? "alert" : ""}
          />
          <Stat label="Durée de poussée" value={f.duration(g.noeud_duree)} />
          <EcartAttitude degres={g.ecart_attitude} />
        </>
      )}

      {!g.noeud && g.phase === "ascension" && (
        <>
          <Stat
            label="Assiette à tenir"
            value={`${f.num(g.assiette_cible, 0)}°`}
            tone="big"
          />
          <Stat
            label="Écart d'assiette"
            value={`${g.assiette_ecart > 0 ? "+" : ""}${f.num(g.assiette_ecart, 1)}°`}
            tone={Math.abs(g.assiette_ecart) < 3 ? "good" : "alert"}
          />
        </>
      )}

      {g.circularisation_dv > 0 && (
        <>
          <Stat
            label="Circularisation"
            value={`${f.num(g.circularisation_dv, 0)} m/s`}
            tone={g.noeud ? "" : "big"}
          />
          {g.circularisation_duree > 0 && (
            <Stat
              label="Durée de la poussée"
              value={f.duration(g.circularisation_duree)}
            />
          )}
        </>
      )}

      <NodePlanner noeudExistant={g.noeud} />

      {g.alertes.length > 0 && (
        <div className="planner-avert" style={{ borderLeftColor: "var(--red)" }}>
          {g.alertes.map((a, i) => (
            <p key={i} style={{ color: "var(--red)" }}>
              {a}
            </p>
          ))}
        </div>
      )}
    </Panel>
  );
}
