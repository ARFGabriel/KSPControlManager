import { useEffect, useState } from "react";

import { Panel, Stat } from "../components/ui";
import * as f from "../format";

interface EtageVab {
  number: number;
  delta_v: number;
  vacuum_delta_v: number;
  twr: number;
  burn_time: number;
  start_mass: number;
  end_mass: number;
}

interface Vaisseau {
  disponible: boolean;
  raison?: string;
  nom: string;
  nombre_pieces: number;
  masse: number;
  masse_seche: number;
  delta_v_total: number;
  delta_v_total_vide: number;
  etages: EtageVab[];
  ressources: { nom: string; quantite: number; masse: number }[];
}

function apiUrl(path: string): string {
  const host = location.port === "5173" ? `${location.hostname}:8000` : location.host;
  return `${location.protocol}//${host}${path}`;
}

export function VabPanel({ atelier }: { atelier: string }) {
  const [nav, setNav] = useState<Vaisseau | null>(null);

  useEffect(() => {
    const charger = () =>
      fetch(apiUrl("/api/vab"))
        .then((r) => r.json())
        .then(setNav)
        .catch(() => undefined);

    charger();
    // Le joueur pose des pièces en continu : on suit d'assez près pour que
    // les chiffres réagissent, sans marteler le backend.
    const timer = window.setInterval(charger, 1500);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <Panel
      title={`Construction — ${atelier}`}
      extra={nav?.disponible ? <span>{nav.nom}</span> : null}
      grandir
    >
      {!nav?.disponible && (
        <div className="empty">
          {nav?.raison ?? "En attente du mod…"}
          <br />
          <br />
          Le mod transmet le vaisseau depuis l'éditeur : kRPC ne donne pas
          accès à ce que tu construis.
        </div>
      )}

      {nav?.disponible && (
        <>
          {/* Deux chiffres, parce qu'ils répondent à deux questions :
              le vide sert à comparer au plan de mission, le niveau de la mer
              dit si la fusée décolle. */}
          <Stat
            label="Δv sous vide"
            value={
              nav.delta_v_total_vide > 0
                ? `${f.num(nav.delta_v_total_vide, 0)} m/s`
                : "aucun étage propulsif"
            }
            tone="big"
          />
          {nav.delta_v_total > 0 && (
            <Stat
              label="Δv au niveau de la mer"
              value={`${f.num(nav.delta_v_total, 0)} m/s`}
            />
          )}
          <Stat label="Masse au décollage" value={`${f.num(nav.masse, 2)} t`} />
          <Stat label="Masse à vide" value={`${f.num(nav.masse_seche, 2)} t`} />
          <Stat label="Pièces" value={nav.nombre_pieces} />

          {nav.etages.length > 0 && (
            <div style={{ marginTop: "0.5rem" }}>
              {nav.etages.map((s) => (
                <div key={s.number} className="stage">
                  <div className="title">
                    <span>Étage {s.number}</span>
                    <span
                      className="tag"
                      style={{ color: s.twr < 1 ? "var(--red)" : "var(--green)" }}
                    >
                      TWR {f.num(s.twr, 2)}
                    </span>
                  </div>
                  <div className="grid">
                    <Stat label="Δv vide" value={`${f.num(s.vacuum_delta_v, 0)} m/s`} />
                    <Stat label="Δv mer" value={`${f.num(s.delta_v, 0)} m/s`} />
                    <Stat label="Combustion" value={f.duration(s.burn_time)} />
                    <Stat label="Masse" value={`${f.num(s.start_mass, 2)} t`} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Le TWR du premier étage décide si la fusée décolle tout court. */}
          {nav.etages.length > 0 && nav.etages[0].twr < 1 && (
            <div className="planner-avert">
              <p>
                Le premier étage a un TWR de {f.num(nav.etages[0].twr, 2)} :
                cette fusée ne quittera pas le pas de tir. Il en faut au moins
                1,2 pour décoller correctement.
              </p>
            </div>
          )}

          {nav.ressources.length > 0 && (
            <div style={{ marginTop: "0.4rem" }}>
              {nav.ressources.map((r) => (
                <Stat
                  key={r.nom}
                  label={f.resourceLabel(r.nom)}
                  value={`${f.num(r.quantite, 0)}`}
                />
              ))}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
