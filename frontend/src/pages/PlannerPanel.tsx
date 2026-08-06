import { useEffect, useState } from "react";

import { TransferDiagram, type Geometrie } from "../components/TransferDiagram";
import { Panel, Stat } from "../components/ui";
import * as f from "../format";
import { getJson } from "../api";
import { useRappels } from "../useRappels";

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
  ut_depart?: number;
  periode_synodique?: number;
  date_depart?: { texte: string };
  date_actuelle?: { texte: string };
}

/** Recoupement entre la fusée du moment et ce que le trajet exige. */
interface Confrontation {
  disponible: boolean;
  raison?: string;
  source?: "vab" | "vol";
  vaisseau?: string;
  delta_v_disponible: number;
  delta_v_requis: number;
  marge: number;
  marge_relative: number;
  suffisant: boolean;
  etapes_ignorees: string[];
  etape_bloquante: { titre: string; delta_v: number; restant: number } | null;
  suggestion: string;
  verdict: string;
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
  confrontation: Confrontation | null;
}

const COULEURS: Record<string, string> = {
  ascension: "var(--red)",
  transfert: "var(--cyan)",
  capture: "var(--green)",
  evasion: "var(--amber)",
  descente: "var(--red)",
};

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
  const { rappels, poser } = useRappels();

  // Escales possibles : les engins déjà en orbite autour du corps de départ.
  useEffect(() => {
    getJson<{ cibles?: { nom: string; corps: string }[] }>(
      "/api/planner/cibles",
    ).then((d) => setEscales(d?.cibles ?? []));
  }, []);

  useEffect(() => {
    getJson<{ bodies?: PlannerBody[]; source?: string }>(
      "/api/planner/bodies",
    ).then((d) => {
      if (!d) return;
      setCorps(d.bodies ?? []);
      setSource(d.source ?? "");
    });
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
    getJson<PlanResult>(`/api/planner/plan?${params}`).then(setPlan);
  }, [depart, arrivee, depuisSurface, versSurface, escale]);

  // Une fenêtre déjà suivie ne se repropose pas : le bouton devient un état.
  const dejaRappele = (rappels?.rappels ?? []).some(
    (r) => r.depart === depart && r.arrivee === arrivee,
  );

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

          {/* Le recoupement avec la fusée du moment : c'est ce chiffre-là qui
              dit si le plan est réalisable, pas le total seul. */}
          <ConfrontationBloc c={plan.confrontation} />

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
              <button
                type="button"
                className="planner-rappel"
                disabled={dejaRappele}
                onClick={() =>
                  poser({
                    depart,
                    arrivee,
                    ut_depart: plan.fenetre!.ut_depart ?? 0,
                    periode_synodique: plan.fenetre!.periode_synodique ?? 0,
                  })
                }
              >
                {dejaRappele ? "✓ rappel posé" : "Me le rappeler"}
              </button>
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

/**
 * Le chaînon manquant entre les deux outils : la fusée que tu as face au
 * trajet que tu vises. Le backend a déjà tranché et rédigé le verdict — ici
 * on ne fait que le mettre en forme.
 */
function ConfrontationBloc({ c }: { c: Confrontation | null }) {
  if (!c) return null;

  if (!c.disponible) {
    return <p className="confront-vide">{c.raison}</p>;
  }

  const ton = !c.suffisant ? "manque" : c.marge_relative < 0.1 ? "juste" : "ok";
  const origine =
    c.source === "vab" ? "vaisseau en construction" : "vaisseau en vol";

  return (
    <div className={`confront ${ton}`}>
      <div className="entete">
        <span className="titre">Fusée vs mission</span>
        <span className="origine">
          {c.vaisseau} · {origine}
        </span>
      </div>

      <div className="jauge">
        {/* La barre compare directement les deux réserves : au-delà de 100 %
            du besoin, le dépassement est la marge. */}
        <div
          className="fill"
          style={{
            width: `${Math.min(100, (c.delta_v_disponible / Math.max(c.delta_v_requis, 1)) * 100)}%`,
          }}
        />
      </div>

      <p className="verdict">{c.verdict}</p>

      {c.suggestion && <p className="suggestion">{c.suggestion}</p>}

      {c.etapes_ignorees.length > 0 && (
        <p className="note">
          Déjà accompli, non recompté : {c.etapes_ignorees.join(", ")}.
        </p>
      )}
    </div>
  );
}
