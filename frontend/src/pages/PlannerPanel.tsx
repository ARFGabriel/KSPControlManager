import { useEffect, useState } from "react";

import { Panel, Stat } from "../components/ui";
import * as f from "../format";

interface PlannerBody {
  name: string;
  parent: string | null;
  low_orbit: number;
  inclination: number;
  eccentricity: number;
}

interface Burn {
  label: string;
  delta_v: number;
  note: string;
}

interface TransferResult {
  possible: boolean;
  raison?: string;
  source?: string;
  delta_v_ejection: number;
  delta_v_capture: number;
  delta_v_total: number;
  duree_transfert: number;
  angle_de_phase: number;
  periode_synodique: number;
  parking_depart: number;
  parking_arrivee: number;
  burns: Burn[];
  avertissements: string[];
}

function apiUrl(path: string): string {
  const host = location.port === "5173" ? `${location.hostname}:8000` : location.host;
  return `${location.protocol}//${host}${path}`;
}

/** Destinations atteignables depuis un corps : ses frères et ses lunes. */
function destinations(corps: PlannerBody[], depart: string): PlannerBody[] {
  const source = corps.find((b) => b.name === depart);
  if (!source) return [];
  return corps.filter(
    (b) =>
      b.name !== depart &&
      ((source.parent && b.parent === source.parent) || b.parent === depart)
  );
}

export function PlannerPanel() {
  const [corps, setCorps] = useState<PlannerBody[]>([]);
  const [source, setSource] = useState("");
  const [depart, setDepart] = useState("Kerbin");
  const [arrivee, setArrivee] = useState("Mun");
  const [parking, setParking] = useState(100);
  const [plan, setPlan] = useState<TransferResult | null>(null);

  useEffect(() => {
    fetch(apiUrl("/api/planner/bodies"))
      .then((r) => r.json())
      .then((d) => {
        setCorps(d.bodies ?? []);
        setSource(d.source ?? "");
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!depart || !arrivee) return;
    const params = new URLSearchParams({
      depart,
      arrivee,
      parking_depart: String(parking * 1000),
    });
    fetch(apiUrl(`/api/planner/transfer?${params}`))
      .then((r) => r.json())
      .then(setPlan)
      .catch(() => setPlan(null));
  }, [depart, arrivee, parking]);

  const cibles = destinations(corps, depart);

  // Si la destination courante n'est plus atteignable, on prend la première.
  useEffect(() => {
    if (cibles.length && !cibles.some((c) => c.name === arrivee)) {
      setArrivee(cibles[0].name);
    }
  }, [cibles, arrivee]);

  return (
    <Panel
      title="Planificateur"
      extra={<span>{source === "jeu" ? "données du jeu" : source}</span>}
      grandir
    >
      <div className="planner-form">
        <label>
          Départ
          <select value={depart} onChange={(e) => setDepart(e.target.value)}>
            {corps
              .filter((b) => b.parent)
              .map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name}
                </option>
              ))}
          </select>
        </label>

        <label>
          Destination
          <select value={arrivee} onChange={(e) => setArrivee(e.target.value)}>
            {cibles.map((b) => (
              <option key={b.name} value={b.name}>
                {b.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Orbite de départ
          <select value={parking} onChange={(e) => setParking(Number(e.target.value))}>
            {[80, 100, 150, 200, 300].map((km) => (
              <option key={km} value={km}>
                {km} km
              </option>
            ))}
          </select>
        </label>
      </div>

      {plan && !plan.possible && <div className="empty">{plan.raison}</div>}

      {plan?.possible && (
        <>
          <Stat
            label="Δv total nécessaire"
            value={`${f.num(plan.delta_v_total, 0)} m/s`}
            tone="big"
          />
          {plan.burns.map((b, i) => (
            <Stat
              key={i}
              label={b.label}
              value={`${f.num(b.delta_v, 0)} m/s`}
              tone={i === 0 ? "accent" : ""}
            />
          ))}

          <div style={{ height: "0.4rem" }} />
          <Stat
            label="Angle de phase au départ"
            value={`${f.num(plan.angle_de_phase, 2)}°`}
            tone="good"
          />
          <Stat label="Durée du trajet" value={f.joursKerbals(plan.duree_transfert)} />
          <Stat
            label="Fenêtre de tir tous les"
            value={
              isFinite(plan.periode_synodique)
                ? f.joursKerbals(plan.periode_synodique)
                : "—"
            }
          />

          {plan.avertissements.length > 0 && (
            <div className="planner-avert">
              {plan.avertissements.map((a, i) => (
                <p key={i}>{a}</p>
              ))}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
