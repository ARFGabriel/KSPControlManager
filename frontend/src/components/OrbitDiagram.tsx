/** Vue schematique de l'orbite : le corps, l'ellipse, et la position courante.
 *
 *  Le rayon du corps n'est pas transmis directement par le backend, mais il se
 *  deduit : rayon = rayon d'apoapside - altitude d'apoapside.
 */

import type { OrbitInfo } from "../types";

const W = 320;
const H = 260;

export function OrbitDiagram({
  orbit,
  altitude,
}: {
  orbit: OrbitInfo;
  altitude: number;
}) {
  const { eccentricity: e, semi_major_axis: a, apoapsis } = orbit;

  const bodyRadius = a > 0 && e < 1 ? a * (1 + e) - apoapsis : 0;

  if (!(a > 0) || e >= 1 || !(bodyRadius > 0)) {
    return (
      <div className="empty">
        Trajectoire non elliptique
        <br />
        (au sol, ou en trajectoire de fuite)
      </div>
    );
  }

  const b = a * Math.sqrt(1 - e * e);
  const rApo = a * (1 + e);

  // Echelle : l'apoapside occupe 85 % de la demi-largeur disponible.
  const scale = (Math.min(W, H) / 2) * 0.85 / rApo;

  const cx = W / 2;
  const cy = H / 2;
  // Le corps occupe un foyer ; le centre de l'ellipse est decale de a*e.
  const ellipseCx = cx + a * e * scale;

  // Position du vaisseau : anomalie vraie deduite du rayon courant.
  const r = bodyRadius + altitude;
  let nu = 0;
  if (e > 1e-6) {
    const cosNu = Math.max(-1, Math.min(1, (a * (1 - e * e) / r - 1) / e));
    nu = Math.acos(cosNu);
    // On monte vers l'apoapside si elle arrive avant le periapside.
    if (orbit.time_to_apoapsis > orbit.time_to_periapsis) nu = -nu;
  }
  // Periapside dessine a gauche (x negatif depuis le foyer).
  const vx = cx - r * Math.cos(nu) * scale;
  const vy = cy + r * Math.sin(nu) * scale;

  const bodyPx = Math.max(4, bodyRadius * scale);
  const apoPx = cx - rApo * scale;
  const perPx = cx + a * (1 - e) * scale;

  return (
    // La hauteur est bornée : sans cela le diagramme s'étire avec la largeur
    // de la colonne et pousse les chiffres hors du panneau.
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      preserveAspectRatio="xMidYMid meet"
      style={{ display: "block", maxHeight: "13rem" }}
    >
      <ellipse
        cx={ellipseCx}
        cy={cy}
        rx={a * scale}
        ry={b * scale}
        fill="none"
        stroke="var(--cyan)"
        strokeWidth={1.4}
        strokeDasharray="4 3"
        opacity={0.75}
      />

      <circle cx={cx} cy={cy} r={bodyPx} fill="#16324a" stroke="#2d5878" />
      <text x={cx} y={cy + 4} textAnchor="middle" fill="var(--dim)" fontSize={10}>
        {orbit.body}
      </text>

      {/* Apoapside a gauche, periapside a droite */}
      <circle cx={apoPx} cy={cy} r={3} fill="var(--amber)" />
      <text x={apoPx} y={cy - 9} textAnchor="middle" fill="var(--amber)" fontSize={9}>
        Ap
      </text>
      <circle cx={perPx} cy={cy} r={3} fill="var(--green)" />
      <text x={perPx} y={cy - 9} textAnchor="middle" fill="var(--green)" fontSize={9}>
        Pe
      </text>

      <circle cx={vx} cy={vy} r={4.5} fill="var(--amber)" stroke="#000" strokeWidth={1} />
    </svg>
  );
}
