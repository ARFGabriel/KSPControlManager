/** Schéma du transfert : orbites, position des corps, ellipse de transfert.
 *
 *  On montre trois instants sur le même dessin — maintenant, le départ, et
 *  l'arrivée. Un schéma limité à l'instant présent n'apprendrait rien : tout
 *  l'intérêt est de voir où seront les corps quand on partira.
 */

export interface Geometrie {
  parent: string;
  depart: string;
  arrivee: string;
  rayon_depart: number;
  rayon_arrivee: number;
  maintenant: { depart: number; arrivee: number };
  au_depart: { depart: number; arrivee: number };
  a_l_arrivee: { vaisseau: number; arrivee: number };
  duree_transfert: number;
}

const T = 340; // côté du dessin, en unités de viewBox

/** Les angles du jeu tournent dans le sens trigonométrique ; l'axe y de SVG
 *  descend, donc on inverse pour garder le même sens de rotation à l'écran. */
function point(angleDeg: number, rayon: number, echelle: number, c: number) {
  const a = (angleDeg * Math.PI) / 180;
  return [c + Math.cos(a) * rayon * echelle, c - Math.sin(a) * rayon * echelle];
}

export function TransferDiagram({ g }: { g: Geometrie }) {
  const c = T / 2;
  const rMax = Math.max(g.rayon_depart, g.rayon_arrivee);
  const echelle = (T / 2 - 26) / rMax;

  const r1 = g.rayon_depart * echelle;
  const r2 = g.rayon_arrivee * echelle;

  // Ellipse de transfert : un foyer sur l'astre, périapside et apoapside sur
  // les deux orbites. Le grand axe est porté par la ligne de départ.
  const aEll = (r1 + r2) / 2;
  const bEll = Math.sqrt(r1 * r2);
  const angleDepart = g.au_depart.depart;
  // Décalage du centre de l'ellipse par rapport au foyer.
  const decalage = Math.abs(r1 - r2) / 2;
  const interne = g.rayon_depart < g.rayon_arrivee;
  const sens = interne ? -1 : 1;
  const [cx, cy] = point(angleDepart, (sens * decalage) / echelle, echelle, c);

  const [pDepartNow] = [point(g.maintenant.depart, g.rayon_depart, echelle, c)];
  const [pArriveeNow] = [point(g.maintenant.arrivee, g.rayon_arrivee, echelle, c)];
  const pDepart = point(angleDepart, g.rayon_depart, echelle, c);
  const pArrivee = point(g.a_l_arrivee.arrivee, g.rayon_arrivee, echelle, c);

  return (
    <svg
      viewBox={`0 0 ${T} ${T}`}
      width="100%"
      preserveAspectRatio="xMidYMid meet"
      style={{ display: "block", maxHeight: "17rem" }}
    >
      {/* Orbites */}
      <circle cx={c} cy={c} r={r1} fill="none" stroke="var(--border)" strokeWidth={1} />
      <circle cx={c} cy={c} r={r2} fill="none" stroke="var(--border)" strokeWidth={1} />

      {/* Trajectoire de transfert */}
      <ellipse
        cx={cx}
        cy={cy}
        rx={aEll}
        ry={bEll}
        transform={`rotate(${-angleDepart} ${cx} ${cy})`}
        fill="none"
        stroke="var(--amber)"
        strokeWidth={1.6}
        strokeDasharray="5 3"
      />

      {/* Astre central */}
      <circle cx={c} cy={c} r={7} fill="#3a2f10" stroke="var(--amber)" />
      <text x={c} y={c + 20} textAnchor="middle" fill="var(--dim)" fontSize={9}>
        {g.parent}
      </text>

      {/* Positions actuelles, en retrait */}
      <circle cx={pDepartNow[0]} cy={pDepartNow[1]} r={3.5} fill="var(--dim)" />
      <circle cx={pArriveeNow[0]} cy={pArriveeNow[1]} r={3.5} fill="var(--dim)" />
      <text
        x={pArriveeNow[0]}
        y={pArriveeNow[1] - 7}
        textAnchor="middle"
        fill="var(--dim)"
        fontSize={8}
      >
        aujourd'hui
      </text>

      {/* Depart */}
      <line
        x1={c}
        y1={c}
        x2={pDepart[0]}
        y2={pDepart[1]}
        stroke="var(--cyan)"
        strokeWidth={0.8}
        opacity={0.4}
      />
      <circle cx={pDepart[0]} cy={pDepart[1]} r={5} fill="var(--cyan)" />
      <text
        x={pDepart[0]}
        y={pDepart[1] - 9}
        textAnchor="middle"
        fill="var(--cyan)"
        fontSize={9}
      >
        {g.depart}
      </text>

      {/* Arrivee */}
      <line
        x1={c}
        y1={c}
        x2={pArrivee[0]}
        y2={pArrivee[1]}
        stroke="var(--green)"
        strokeWidth={0.8}
        opacity={0.4}
      />
      <circle cx={pArrivee[0]} cy={pArrivee[1]} r={5} fill="var(--green)" />
      <text
        x={pArrivee[0]}
        y={pArrivee[1] - 9}
        textAnchor="middle"
        fill="var(--green)"
        fontSize={9}
      >
        {g.arrivee}
      </text>
    </svg>
  );
}
