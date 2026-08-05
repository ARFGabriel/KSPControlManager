import { AttitudeIndicator } from "../components/AttitudeIndicator";
import { OrbitDiagram } from "../components/OrbitDiagram";
import { RadioPanel } from "../components/RadioPanel";
import { Bar, Panel, Stat } from "../components/ui";
import * as f from "../format";
import type { Telemetry } from "../types";

export function FlightPage({ t }: { t: Telemetry }) {
  return (
    <div className="dashboard trois">
      {/* ---------------- Pilotage ---------------- */}
      <div className="column">
        <Panel title="Attitude">
          <AttitudeIndicator pitch={t.pitch} heading={t.heading} roll={t.roll} />
          <div style={{ marginTop: "0.6rem" }}>
            <Stat label="Assiette" value={`${f.num(t.pitch, 1)}°`} />
            <Stat label="Cap" value={`${f.num(t.heading, 1)}°`} />
            <Stat label="Roulis" value={`${f.num(t.roll, 1)}°`} />
          </div>
        </Panel>

        <Panel title="Vol" grandir>
          <Stat label="Altitude" value={f.distance(t.altitude)} tone="big" />
          <Stat label="Vitesse orbitale" value={f.speed(t.orbital_speed)} tone="big" />
          <Stat label="Vitesse surface" value={f.speed(t.speed)} />
          <Stat label="Sol" value={f.distance(t.surface_altitude)} />
          <Stat
            label="Vitesse verticale"
            value={`${f.num(t.vertical_speed, 1)} m/s`}
            tone={t.vertical_speed < -10 ? "alert" : ""}
          />
          <Stat
            label="Accélération"
            value={`${f.num(t.g_force, 2)} g`}
            tone={t.g_force > 5 ? "alert" : ""}
          />
          <Stat label="Mach" value={f.num(t.mach, 2)} />
          <Stat
            label="Pression dyn."
            value={f.pressure(t.dynamic_pressure)}
            tone={t.dynamic_pressure > 40000 ? "alert" : ""}
          />
          <Stat label="Pression stat." value={f.pressure(t.static_pressure)} />
        </Panel>
      </div>

      {/* ---------------- Orbite et radio ---------------- */}
      <div className="column">
        <Panel title="Orbite" extra={<span>{t.body}</span>}>
          {t.orbit ? (
            <>
              <OrbitDiagram orbit={t.orbit} altitude={t.altitude} />
              <div style={{ marginTop: "0.6rem" }}>
                <Stat label="Apoapside" value={f.distance(t.orbit.apoapsis)} tone="accent" />
                <Stat
                  label="Périapside"
                  value={f.distance(t.orbit.periapsis)}
                  tone={t.orbit.periapsis < 70000 ? "alert" : "good"}
                />
                <Stat label="Temps → Ap" value={f.duration(t.orbit.time_to_apoapsis)} />
                <Stat label="Temps → Pe" value={f.duration(t.orbit.time_to_periapsis)} />
                <Stat label="Excentricité" value={f.num(t.orbit.eccentricity, 4)} />
                <Stat label="Inclinaison" value={`${f.num(t.orbit.inclination, 2)}°`} />
              </div>
            </>
          ) : (
            <div className="empty">Pas de données orbitales</div>
          )}
        </Panel>

        <RadioPanel />
      </div>

      {/* ---------------- Propulsion ---------------- */}
      <div className="column">
        <Panel title="Propulsion">
          <Bar
            label="Poussée"
            amount={t.throttle}
            maximum={1}
            color="var(--green)"
            text={`${Math.round(t.throttle * 100)} %`}
          />
          <Stat label="Poussée" value={`${f.num(t.thrust, 1)} kN`} />
          <Stat label="Disponible" value={`${f.num(t.available_thrust, 1)} kN`} />
          <Stat label="TWR" value={f.num(t.twr, 2)} tone={t.twr < 1 ? "alert" : "good"} />
          <Stat label="Masse" value={`${f.num(t.mass, 2)} t`} />
          <Stat
            label="Δv total"
            value={t.delta_v_available ? `${f.num(t.delta_v, 0)} m/s` : "indisponible"}
            tone={t.delta_v_available ? "big" : ""}
          />
        </Panel>

        <Panel title="Ressources">
          {t.resources.length > 0 ? (
            t.resources.map((r) => (
              <Bar
                key={r.name}
                label={f.resourceLabel(r.name)}
                amount={r.amount}
                maximum={r.maximum}
                color={r.name === "ElectricCharge" ? "var(--amber)" : "var(--cyan)"}
                text={`${f.num(r.amount, 0)} / ${f.num(r.maximum, 0)}`}
              />
            ))
          ) : (
            <div className="empty">Aucune ressource détectée</div>
          )}
        </Panel>

        <Panel title="Étages" extra={<span>actuel : {t.current_stage}</span>} grandir>
          {t.stages.length > 0 ? (
            t.stages.map((s) => (
              <div
                key={s.number}
                className={`stage ${s.number === t.current_stage ? "current" : ""}`}
              >
                <div className="title">
                  <span>Étage {s.number}</span>
                  {s.number === t.current_stage && <span className="tag">actif</span>}
                </div>
                <div className="grid">
                  <Stat label="Δv" value={`${f.num(s.delta_v, 0)} m/s`} />
                  <Stat label="TWR" value={f.num(s.twr, 2)} />
                  <Stat label="Combustion" value={f.duration(s.burn_time)} />
                  <Stat label="Masse" value={`${f.num(s.start_mass, 2)} t`} />
                </div>
              </div>
            ))
          ) : (
            <div className="empty">Aucun étage avec propulsion</div>
          )}
        </Panel>
      </div>
    </div>
  );
}
