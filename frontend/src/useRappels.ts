import { useCallback, useEffect, useState } from "react";

import { apiUrl, getJson } from "./api";

export interface Rappel {
  id: string;
  depart: string;
  arrivee: string;
  ut_depart: number;
  periode_synodique: number;
  date_depart: { texte: string };
  /** Secondes de jeu avant la fenêtre ; négatif si elle est passée. */
  attente: number;
  attente_texte: string;
  proche: boolean;
  imminent: boolean;
  passee: boolean;
  renouvele?: boolean;
  message: string;
}

export interface Rappels {
  date_actuelle: string;
  rappels: Rappel[];
  a_signaler: Rappel[];
}

/** Une fenêtre de tir se compte en jours de jeu : la relire toutes les dix
 *  secondes suffit largement, même sous accélération temporelle. */
const PERIODE_MS = 10_000;

export function useRappels() {
  const [rappels, setRappels] = useState<Rappels | null>(null);

  const recharger = useCallback(async () => {
    const data = await getJson<Rappels>("/api/rappels");
    if (data) setRappels(data);
  }, []);

  useEffect(() => {
    recharger();
    const timer = window.setInterval(recharger, PERIODE_MS);
    return () => window.clearInterval(timer);
  }, [recharger]);

  const poser = useCallback(
    async (r: {
      depart: string;
      arrivee: string;
      ut_depart: number;
      periode_synodique?: number;
    }) => {
      try {
        await fetch(apiUrl("/api/rappels"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(r),
        });
      } catch {
        /* Le rappel n'est pas posé ; la prochaine relecture le dira. */
      }
      await recharger();
    },
    [recharger],
  );

  const retirer = useCallback(
    async (id: string) => {
      try {
        await fetch(apiUrl(`/api/rappels/${id}`), { method: "DELETE" });
      } catch {
        /* idem */
      }
      await recharger();
    },
    [recharger],
  );

  return { rappels, poser, retirer, recharger };
}
