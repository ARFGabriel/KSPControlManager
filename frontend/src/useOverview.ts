import { useEffect, useState } from "react";

export interface FleetVessel {
  name: string;
  type: string;
  situation: string;
  body: string;
  crew_count: number;
  met: number;
  apoapsis: number;
  periapsis: number;
  inclination: number;
  period: number;
}

export interface Kerbal {
  name: string;
  type: string;
  trait: string;
  experience: number;
  courage: number;
  stupidity: number;
  on_mission: boolean;
}

export interface Overview {
  available: boolean;
  reason?: string;
  ut: number;
  funds: number | null;
  science: number | null;
  reputation: number | null;
  vessels: FleetVessel[];
  crew: Kerbal[];
  warnings: string[];
}

function apiUrl(path: string): string {
  const host = location.port === "5173" ? `${location.hostname}:8000` : location.host;
  return `${location.protocol}//${host}${path}`;
}

/**
 * Interroge la vue d'ensemble à basse fréquence.
 * Ces données coûtent cher à lire côté jeu et ne bougent qu'à l'échelle de
 * la minute : inutile de les rafraîchir au rythme de la télémétrie.
 */
export function useOverview(actif: boolean, periodeMs = 4000): Overview | null {
  const [overview, setOverview] = useState<Overview | null>(null);

  useEffect(() => {
    if (!actif) return;
    let arrete = false;

    const charger = async () => {
      try {
        const reponse = await fetch(apiUrl("/api/overview"));
        if (!arrete) setOverview(await reponse.json());
      } catch {
        /* backend momentanément absent : on retentera au prochain tour */
      }
    };

    charger();
    const timer = window.setInterval(charger, periodeMs);
    return () => {
      arrete = true;
      window.clearInterval(timer);
    };
  }, [actif, periodeMs]);

  return overview;
}
