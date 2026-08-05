import { useEffect, useState } from "react";

import { TransferDiagram, type Geometrie } from "../components/TransferDiagram";
import { Panel, Stat } from "../components/ui";
import * as f from "../format";

interface PlannerBody {
  name: string;
  parent: string | null;
  low_orbit: number;
}

interface Etape {
  genre: string;
  titre: string;
  delta_v: number;
  depuis: string;
  vers: string;
  duree: number;
  angle_de_phase: number | null;
  periode_synodique: number;
  detail: string;
  approximatif: boolean;
}

interface Fenetre {
  recurrente?: boolean;
  angle_actuel?: number;
  angle_vise?: number;
  attente?: number;
  note?: string;
  date_depart?: { texte: string };
  date_actuelle?: { texte: string };
}

interface PlanResult {
  possible: boolean;
  raison?: string;
  source?: string;
  itineraire: string[];
  etapes: Etape[];
  avertissements: string[];
  delta_v_total: number;
  duree_totale: number;
  fenetre: Fenetre | null;
  geometrie: Geometrie | null;
}

const COULEURS: Record<string, string> = {
  ascension: "var(--red)",
  transfert: "var(--cyan)",
  capture: "var(--green)",
  evasion: "var(--amber)",
  descente: "var(--red)",
};

function apiUrl(path: string): string {
  const host = location.port === "5173" ? `${location.hostname}:8000` : location.host;
  return `${location.protocol}//${host}${path}`;
}

export function PlannerPanel() {
  const [corps, setCorps] = useState<PlannerBody[]>([]);
  const [source, setSource] = useState("");
  const [depart, setDepart] = useState("Kerbin");
  const [arrivee, setArrivee] = useState("Duna");
  const [depuisSurface, setDepuisSurface] = useState(true);
  const [versSurface, setVersSurface] = useState(false);
  const [escale, setEscale] = useState("");
  const [escales, setEscales] = useState<{ nom: string; corps: string }[]>([]);
  const [plan, setPlan] = useState<PlanResult | null>(null);

  // Escales possibles : les engins déjà en orbite autour du corps de départ.
  useEffect(() => {
    fetch(apiUrl("/api/planner/cibles"))
      .then((r) => r.json())
      .then((d) => setEscales(d.cibles ?? []))
      .catch(() => setEscales([]));
  }, []);

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
    if (!depart || !arrivee || depart === arrivee) return;
    const params = new URLSearchParams({
      depart,
      arrivee,
      depuis_surface: String(depuisSurface),
      vers_surface: String(versSurface),
    });
    if (escale) params.set("escale", escale);
    fetch(apiUrl(`/api/planner/plan?${params}`))
      .then((r) => r.json())
      .then(setPlan)
      .catch(() => setPlan(null));
  }, [depart, arrivee, depuisSurface, versSurface, escale]);

  // Toute destination du système est atteignable : l'itinéraire se charge
  // d'enchaîner les étapes intermédiaires.
  const destinations = corps.filter((b) => b.parent && b.name !== depart);

  // Une escale n'a de sens que sur un engin déjà en orbite du corps de départ.
  const escalesPossibles = escales.filter((e) => e.corps === depart);

  return (
    <Panel
      title="Planificateur de mission"
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
            {destinations.map((b) => (
              <option key={b.name} value={b.name}>
                {b.name}
              </option>
            ))}
          </select>
        </label>

        {escalesPossibles.length > 0 && (
          <label>
            Escale
            <select value={escale} onChange={(e) => setEscale(e.target.value)}>
              <option value="">aucune</option>
              {escalesPossibles.map((e) => (
                <option key={e.nom} value={e.nom}>
                  {e.nom}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="planner-options">
        <label>
          <input
            type="checkbox"
            checked={depuisSurface}
            onChange={(e) => setDepuisSurface(e.target.checked)}
          />
          Décoller du sol
        </label>
        <label>
          <input
            type="checkbox"
            checked={versSurface}
            onChange={(e) => setVersSurface(e.target.checked)}
          />
          Se poser à l'arrivée
        </label>
      </div>

      {plan && !plan.possible && <div className="empty">{plan.raison}</div>}

      {plan?.possible && (
        <>
          <div className="planner-route">
            {plan.itineraire.map((corpsNom, i) => (
              <span key={i}>
                {i > 0 && <span className="fleche"> → </span>}
                {corpsNom}
              </span>
            ))}
          </div>

          {plan.geometrie && <TransferDiagram g={plan.geometrie} />}

          <Stat
            label="Δv total de la mission"
            value={`${f.num(plan.delta_v_total, 0)} m/s`}
            tone="big"
          />

          {/* Fenêtre de tir : uniquement quand le jeu fournit les positions. */}
          {plan.fenetre?.date_depart && (
            <div className="planner-fenetre">
              <div className="titre">Prochaine fenêtre de tir</div>
              <div className="date">{plan.fenetre.date_depart.texte}</div>
              <div className="sous">
                dans {f.joursKerbals(plan.fenetre.attente ?? 0)} · angle de
                phase {f.num(plan.fenetre.angle_actuel ?? 0, 1)}° →{" "}
                {f.num(plan.fenetre.angle_vise ?? 0, 1)}°
              </div>
            </div>
          )}

          {plan.fenetre?.recurrente && (
            <div className="planner-fenetre">
              <div className="titre">Fenêtre de tir</div>
              <div className="sous">{plan.fenetre.note}</div>
            </div>
          )}

          <div className="planner-etapes">
            {plan.etapes.map((e, i) => (
              <div key={i} className="planner-etape">
                <span
                  className="puce"
                  style={{ background: COULEURS[e.genre] ?? "var(--dim)" }}
                />
                <div className="corps">
                  <div className="ligne">
                    <span className="titre">{e.titre}</span>
                    <span className="dv">
                      {f.num(e.delta_v, 0)} m/s
                      {e.approximatif && <span className="approx"> ≈</span>}
                    </span>
                  </div>
                  {e.detail && <div className="detail">{e.detail}</div>}
                  {e.duree > 0 && (
                    <div className="detail">
                      trajet : {f.joursKerbals(e.duree)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {plan.duree_totale > 0 && (
            <Stat
              label="Durée totale du voyage"
              value={f.joursKerbals(plan.duree_totale)}
              tone="accent"
            />
          )}

          {plan.avertissements.length > 0 && (
            <div className="planner-avert">
              {plan.avertissements.map((a, i) => (
                <p key={i}>{a}</p>
              ))}
            </div>
          )}

          <p className="radio-hint" style={{ marginTop: "0.5rem" }}>
            ≈ : valeur empirique, dépendante du vaisseau et du profil de vol.
          </p>
        </>
      )}
    </Panel>
  );
}
