import { useEffect, useState } from "react";

import { Panel, Stat } from "../components/ui";
import * as f from "../format";
import { apiUrl } from "../api";

interface Cible {
  nom: string;
  corps: string;
  apoapside: number;
  periapside: number;
  inclinaison: number;
  excentricite: number;
  equipage: number;
  situation: string;
}

interface EtapeRdv {
  titre: string;
  delta_v: number;
  detail: string;
}

interface PlanRdv {
  possible: boolean;
  raison?: string;
  cible: string;
  corps: string;
  depuis_altitude: number;
  vers_altitude: number;
  delta_v_plan: number;
  delta_v_transfert: number;
  delta_v_total: number;
  inclinaison_relative: number;
  duree_transfert: number;
  attente_phase: number;
  angle_actuel: number | null;
  angle_vise: number;
  etapes: EtapeRdv[];
  avertissements: string[];
}

export function RendezvousPanel() {
  const [cibles, setCibles] = useState<Cible[]>([]);
  const [disponible, setDisponible] = useState(true);
  const [raison, setRaison] = useState("");
  const [cible, setCible] = useState("");
  const [chasseur, setChasseur] = useState("");
  const [altitude, setAltitude] = useState(100);
  const [plan, setPlan] = useState<PlanRdv | null>(null);

  useEffect(() => {
    fetch(apiUrl("/api/planner/cibles"))
      .then((r) => r.json())
      .then((d) => {
        setCibles(d.cibles ?? []);
        setDisponible(d.disponible ?? false);
        setRaison(d.raison ?? "");
        if (d.cibles?.length && !cible) setCible(d.cibles[0].nom);
      })
      .catch(() => setDisponible(false));
    // On ne recharge pas en boucle : la flotte bouge lentement.
  }, []);

  useEffect(() => {
    if (!cible) return;
    const params = new URLSearchParams({ cible });
    if (chasseur) params.set("chasseur", chasseur);
    else params.set("chasseur_altitude", String(altitude * 1000));

    fetch(apiUrl(`/api/planner/rendezvous?${params}`))
      .then((r) => r.json())
      .then(setPlan)
      .catch(() => setPlan(null));
  }, [cible, chasseur, altitude]);

  const autres = cibles.filter((c) => c.nom !== cible);

  return (
    <Panel title="Rendez-vous" grandir>
      {!disponible && <div className="empty">{raison || "Jeu non connecté."}</div>}

      {disponible && cibles.length === 0 && (
        <div className="empty">
          Aucun engin en orbite.
          <br />
          Mets un vaisseau en orbite pour pouvoir planifier un rendez-vous.
        </div>
      )}

      {disponible && cibles.length > 0 && (
        <>
          <div className="planner-form">
            <label>
              Cible
              <select value={cible} onChange={(e) => setCible(e.target.value)}>
                {cibles.map((c) => (
                  <option key={c.nom} value={c.nom}>
                    {c.nom}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Depuis
              <select value={chasseur} onChange={(e) => setChasseur(e.target.value)}>
                <option value="">une orbite au choix</option>
                {autres.map((c) => (
                  <option key={c.nom} value={c.nom}>
                    {c.nom}
                  </option>
                ))}
              </select>
            </label>

            {!chasseur && (
              <label>
                Altitude
                <select
                  value={altitude}
                  onChange={(e) => setAltitude(Number(e.target.value))}
                >
                  {[80, 100, 120, 150, 200].map((km) => (
                    <option key={km} value={km}>
                      {km} km
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {plan && !plan.possible && <div className="empty">{plan.raison}</div>}

          {plan?.possible && (
            <>
              <Stat
                label="Δv du rendez-vous"
                value={`${f.num(plan.delta_v_total, 1)} m/s`}
                tone="big"
              />
              <Stat
                label="Écart de plan"
                value={`${f.num(plan.inclinaison_relative, 2)}°`}
                tone={plan.inclinaison_relative > 1 ? "alert" : "good"}
              />
              <Stat
                label="Durée du transfert"
                value={f.duration(plan.duree_transfert)}
              />
              {plan.attente_phase > 0 && (
                <Stat
                  label="Attente avant la poussée"
                  value={f.duration(plan.attente_phase)}
                  tone="accent"
                />
              )}

              <div className="planner-etapes">
                {plan.etapes.map((e, i) => (
                  <div key={i} className="planner-etape">
                    <span className="puce" style={{ background: "var(--cyan)" }} />
                    <div className="corps">
                      <div className="ligne">
                        <span className="titre">{e.titre}</span>
                        <span className="dv">{f.num(e.delta_v, 1)} m/s</span>
                      </div>
                      <div className="detail">{e.detail}</div>
                    </div>
                  </div>
                ))}
              </div>

              {plan.avertissements.length > 0 && (
                <div className="planner-avert">
                  {plan.avertissements.map((a, i) => (
                    <p key={i}>{a}</p>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </Panel>
  );
}
