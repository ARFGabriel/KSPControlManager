import { BandeauAlertes } from "./components/BandeauAlertes";
import { Badge } from "./components/ui";
import * as f from "./format";
import { FlightPage } from "./pages/FlightPage";
import {
  EditorPage,
  OfflinePage,
  SpaceCenterPage,
  TrackingPage,
} from "./pages/SimplePages";
import type { Telemetry } from "./types";
import { useRappels } from "./useRappels";
import { useTelemetry } from "./useTelemetry";

/** Libellé de la scène, affiché en haut. */
const SCENES: Record<string, string> = {
  flight: "Vol",
  space_center: "Centre spatial",
  tracking_station: "Station de suivi",
  editor_vab: "VAB",
  editor_sph: "Hangar",
  main_menu: "Menu principal",
};

export default function App() {
  const { telemetry, online } = useTelemetry();
  // Les rappels de fenêtre de tir vivent ici, et non dans le planificateur :
  // une fenêtre qui approche doit se signaler quelle que soit la scène où
  // l'on se trouve, y compris en plein vol.
  const { rappels, retirer } = useRappels();

  return (
    <div className="app">
      <TopBar telemetry={telemetry} online={online} />

      {!online && (
        <div className="banner">
          Backend injoignable. Le tableau de bord se rebranchera tout seul dès
          qu'il répondra.
        </div>
      )}

      <BandeauAlertes
        t={telemetry}
        rappels={rappels?.a_signaler ?? []}
        onRetirer={retirer}
      />

      {choisirPage(telemetry)}
    </div>
  );
}

/**
 * Le routage suit la scène rapportée par le jeu. Il n'y a volontairement
 * aucun sélecteur manuel : le tableau de bord doit refléter où l'on est,
 * pas demander où l'on veut aller.
 */
function choisirPage(t: Telemetry | null) {
  if (!t || !t.connected) return <OfflinePage t={t} />;

  switch (t.game_scene) {
    case "flight":
      // La scène de vol peut être active pendant le chargement du vaisseau :
      // on n'affiche le tableau de bord que lorsqu'il y a vraiment quelqu'un.
      return t.vessel_name ? <FlightPage t={t} /> : <OfflinePage t={t} />;
    case "space_center":
      return <SpaceCenterPage t={t} />;
    case "tracking_station":
      return <TrackingPage t={t} />;
    case "editor_vab":
    case "editor_sph":
      return <EditorPage t={t} />;
    default:
      return <OfflinePage t={t} />;
  }
}

function TopBar({
  telemetry,
  online,
}: {
  telemetry: Telemetry | null;
  online: boolean;
}) {
  const t = telemetry;
  const signal = t ? Math.round(t.comm_signal_strength * 100) : 0;
  const enVol = t?.game_scene === "flight" && !!t.vessel_name;

  return (
    <div className="topbar">
      <span className="vessel">
        {enVol ? t!.vessel_name : "KSP MISSION CONTROL"}
      </span>

      <span className="scene">
        {SCENES[t?.game_scene ?? ""] ?? (t?.connected ? "—" : "hors ligne")}
      </span>

      {enVol && (
        <>
          <span style={{ color: "var(--dim)" }}>{f.situation(t!.situation)}</span>
          <span className="met">{f.met(t!.met)}</span>
        </>
      )}

      <span className="spacer" />

      {enVol && t!.crew_count > 0 && (
        <Badge tone="info">
          {t!.crew_count} kerbal{t!.crew_count > 1 ? "s" : ""}
        </Badge>
      )}

      {enVol &&
        (t!.comm_available ? (
          <Badge tone={t!.comm_can_communicate ? (signal > 30 ? "ok" : "warn") : "bad"}>
            {t!.comm_can_communicate ? `Liaison ${signal} %` : "Pas de liaison"}
          </Badge>
        ) : (
          <Badge tone="info">CommNet inactif</Badge>
        ))}

      <Badge tone={t?.source === "krpc" ? "ok" : t?.source === "sim" ? "warn" : "bad"}>
        {t?.source === "krpc"
          ? "KSP en direct"
          : t?.source === "sim"
            ? "Simulateur"
            : "Aucune source"}
      </Badge>

      <Badge tone={online ? "ok" : "bad"}>{online ? "Liaison MC" : "Hors ligne"}</Badge>
    </div>
  );
}
