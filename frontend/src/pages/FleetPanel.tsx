import { Panel, Stat } from "../components/ui";
import * as f from "../format";
import type { FleetVessel, Kerbal, Overview } from "../useOverview";

/** Classe CSS de la barre de couleur, selon l'état du vaisseau. */
function ton(situation: string): string {
  if (situation === "orbiting" || situation === "escaping") return "orbiting";
  if (situation === "flying" || situation === "sub_orbital") return "flying";
  return "landed";
}

export function FleetPanel({
  overview,
  titre = "Flotte",
  grandir = false,
}: {
  overview: Overview | null;
  titre?: string;
  grandir?: boolean;
}) {
  const vessels = overview?.vessels ?? [];

  return (
    <Panel title={titre} extra={<span>{vessels.length} vaisseau(x)</span>} grandir={grandir}>
      {!overview?.available && (
        <div className="empty">{overview?.reason ?? "En attente du jeu…"}</div>
      )}

      {overview?.available && vessels.length === 0 && (
        <div className="empty">Aucun vaisseau en jeu.</div>
      )}

      {vessels.map((v: FleetVessel, i: number) => (
        <div key={`${v.name}-${i}`} className={`fleet-item ${ton(v.situation)}`}>
          <div className="nom">
            <b>{v.name}</b>
            <span>{f.situation(v.situation)}</span>
          </div>
          <div className="detail">
            <span>{v.body}</span>
            {v.crew_count > 0 && <span>{v.crew_count} à bord</span>}
            {v.apoapsis > 0 && <span>Ap {f.distance(v.apoapsis)}</span>}
            {v.periapsis > -1e12 && v.apoapsis > 0 && (
              <span>Pe {f.distance(v.periapsis)}</span>
            )}
            {v.met > 0 && <span>{f.met(v.met)}</span>}
          </div>
        </div>
      ))}
    </Panel>
  );
}

export function CrewPanel({ overview }: { overview: Overview | null }) {
  const crew = overview?.crew ?? [];
  const enMission = crew.filter((k) => k.on_mission).length;

  return (
    <Panel title="Équipage" extra={<span>{crew.length} kerbal(s)</span>} grandir>
      {overview?.warnings?.map((w, i) => (
        <div key={i} className="empty" style={{ color: "var(--amber)" }}>
          {w}
        </div>
      ))}

      {crew.length > 0 && (
        <>
          <Stat label="Au centre spatial" value={crew.length - enMission} tone="good" />
          <Stat label="En mission" value={enMission} tone="accent" />
          <div style={{ height: "0.5rem" }} />
          {crew.slice(0, 24).map((k: Kerbal, i: number) => (
            <div key={`${k.name}-${i}`} className="stat">
              <span className="label">{k.name}</span>
              <span className="value" style={{ fontSize: "0.8rem" }}>
                {k.trait || k.type}
                {k.experience > 0 && ` ★${k.experience}`}
                {k.on_mission && (
                  <span style={{ color: "var(--cyan)" }}> · en vol</span>
                )}
              </span>
            </div>
          ))}
        </>
      )}

      {crew.length === 0 && !overview?.warnings?.length && (
        <div className="empty">Aucun kerbal recensé.</div>
      )}
    </Panel>
  );
}

export function ProgramPanel({ overview }: { overview: Overview | null }) {
  const rien = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : f.num(v, 0);

  return (
    <Panel title="Programme">
      <Stat label="Fonds" value={rien(overview?.funds)} tone="good" />
      <Stat label="Science" value={rien(overview?.science)} tone="accent" />
      <Stat label="Réputation" value={rien(overview?.reputation)} />
      {overview?.funds === null && (
        <p className="radio-hint" style={{ marginTop: "0.5rem" }}>
          Partie en mode bac à sable : pas de budget ni de science.
        </p>
      )}
    </Panel>
  );
}
