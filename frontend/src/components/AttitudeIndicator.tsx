/** Horizon artificiel facon navball : assiette, roulis et cap. */

const SIZE = 240;
const C = SIZE / 2;
const R = 100;
const PX_PER_DEG = 2.0;

export function AttitudeIndicator({
  pitch,
  heading,
  roll,
}: {
  pitch: number;
  heading: number;
  roll: number;
}) {
  // L'assiette est bornee a l'affichage pour que le ciel ne disparaisse pas
  // completement lors d'un vol vertical (typique d'un decollage).
  const shift = Math.max(-90, Math.min(90, pitch)) * PX_PER_DEG;

  const ladder = [];
  for (let p = -60; p <= 60; p += 10) {
    if (p === 0) continue;
    const y = C - p * PX_PER_DEG;
    const half = p % 30 === 0 ? 34 : 18;
    ladder.push(
      <g key={p}>
        <line
          x1={C - half}
          y1={y}
          x2={C + half}
          y2={y}
          stroke="rgba(255,255,255,0.55)"
          strokeWidth={1}
        />
        {p % 30 === 0 && (
          <text
            x={C + half + 5}
            y={y + 3.5}
            fill="rgba(255,255,255,0.65)"
            fontSize={9}
          >
            {p > 0 ? `+${p}` : p}
          </text>
        )}
      </g>
    );
  }

  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width="100%" style={{ display: "block" }}>
      <defs>
        <clipPath id="ball">
          <circle cx={C} cy={C} r={R} />
        </clipPath>
      </defs>

      <g clipPath="url(#ball)">
        <g transform={`rotate(${-roll} ${C} ${C}) translate(0 ${shift})`}>
          <rect x={C - 400} y={C - 800} width={800} height={800} fill="#1b3a55" />
          <rect x={C - 400} y={C} width={800} height={800} fill="#4a3520" />
          <line
            x1={C - 400}
            y1={C}
            x2={C + 400}
            y2={C}
            stroke="#e8eef2"
            strokeWidth={2}
          />
          {ladder}
        </g>
      </g>

      {/* Index de roulis, fixes par rapport au vaisseau */}
      <circle cx={C} cy={C} r={R} fill="none" stroke="var(--border)" strokeWidth={2} />
      <polygon
        points={`${C},${C - R + 4} ${C - 7},${C - R + 16} ${C + 7},${C - R + 16}`}
        fill="var(--amber)"
      />

      {/* Symbole du vaisseau */}
      <g stroke="var(--amber)" strokeWidth={2.5} fill="none">
        <line x1={C - 42} y1={C} x2={C - 14} y2={C} />
        <line x1={C + 14} y1={C} x2={C + 42} y2={C} />
        <circle cx={C} cy={C} r={3} fill="var(--amber)" />
      </g>

      {/* Cap */}
      <rect
        x={C - 34}
        y={SIZE - 26}
        width={68}
        height={20}
        fill="var(--panel-2)"
        stroke="var(--border)"
      />
      <text
        x={C}
        y={SIZE - 11}
        textAnchor="middle"
        fill="var(--cyan)"
        fontSize={13}
      >
        {heading.toFixed(0).padStart(3, "0")}°
      </text>
    </svg>
  );
}
