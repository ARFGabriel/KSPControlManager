/** Pages hors vol. Chacune est choisie automatiquement d'après la scène
 *  rapportée par le jeu — il n'y a volontairement aucun sélecteur manuel. */

import { RadioPanel } from "../components/RadioPanel";
import { Panel, Stat } from "../components/ui";
import * as f from "../format";
import type { Telemetry } from "../types";
import { useOverview } from "../useOverview";
import { CrewPanel, FleetPanel, ProgramPanel } from "./FleetPanel";
import { PlannerPanel } from "./PlannerPanel";

/** Centre spatial : vue d'ensemble du programme. */
export function SpaceCenterPage({ t }: { t: Telemetry }) {
  const overview = useOverview(true);

  return (
    <div className="dashboard trois">
      <div className="column">
        <ProgramPanel overview={overview} />
        <Panel title="Horloge">
          <Stat label="Temps universel" value={f.ut(t.ut)} tone="accent" />
          <Stat label="Jour" value={f.jourKerbal(t.ut)} />
        </Panel>
        <CrewPanel overview={overview} />
      </div>

      <div className="column">
        <PlannerPanel />
        <FleetPanel overview={overview} titre="Flotte en vol" grandir />
      </div>

      <div className="column">
        <RadioPanel equipage={false} />
      </div>
    </div>
  );
}

/** Station de suivi : la flotte, en détail. */
export function TrackingPage({ t }: { t: Telemetry }) {
  const overview = useOverview(true);
  const vessels = overview?.vessels ?? [];

  const parCorps = vessels.reduce<Record<string, number>>((acc, v) => {
    acc[v.body] = (acc[v.body] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="dashboard deux">
      <div className="column">
        <FleetPanel overview={overview} titre="Tous les vaisseaux" grandir />
      </div>

      <div className="column">
        <Panel title="Répartition">
          {Object.keys(parCorps).length === 0 ? (
            <div className="empty">Aucun vaisseau à suivre.</div>
          ) : (
            Object.entries(parCorps)
              .sort((a, b) => b[1] - a[1])
              .map(([corps, n]) => <Stat key={corps} label={corps} value={n} />)
          )}
          <div style={{ height: "0.5rem" }} />
          <Stat label="Temps universel" value={f.ut(t.ut)} tone="accent" />
        </Panel>

        <RadioPanel equipage={false} />
      </div>
    </div>
  );
}

/** VAB et SPH : kRPC n'expose aucune API d'éditeur, donc pas de données
 *  sur la fusée en construction tant que le mod émetteur n'existe pas. */
export function EditorPage({ t }: { t: Telemetry }) {
  const atelier = t.game_scene === "editor_sph" ? "hangar (SPH)" : "VAB";

  return (
    <div className="dashboard deux">
      {/* Le planificateur a toute sa place ici : c'est en construisant qu'on
          a besoin de savoir combien de Δv la mission va réclamer. */}
      <div className="column">
        <PlannerPanel />
        <Panel title={`Construction — ${atelier}`}>
          <div className="empty">
            Le Δv par étage pendant la construction demandera d'étendre le mod
            du jeu : kRPC n'expose pas le contenu de l'éditeur.
          </div>
        </Panel>
      </div>

      <div className="column">
        <RadioPanel equipage={false} />
      </div>
    </div>
  );
}

/** Aucun lien avec le jeu, ou scène inconnue. */
export function OfflinePage({ t }: { t: Telemetry | null }) {
  return (
    <div className="dashboard deux">
      <div className="column">
        <Panel title="Liaison" grandir>
          <div className="empty">
            {t?.error || "En attente de la première trame de télémétrie…"}
            <br />
            <br />
            Le tableau de bord suivra automatiquement l'endroit où tu te
            trouves dans le jeu.
          </div>
        </Panel>
      </div>

      <div className="column">
        <RadioPanel equipage={false} />
      </div>
    </div>
  );
}
