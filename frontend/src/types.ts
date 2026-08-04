/** Miroir exact du schema Python (backend/ksp_mc/telemetry/schema.py).
 *  Toute modification la-bas doit etre repercutee ici. */

export interface OrbitInfo {
  body: string;
  apoapsis: number;
  periapsis: number;
  eccentricity: number;
  inclination: number;
  period: number;
  time_to_apoapsis: number;
  time_to_periapsis: number;
  semi_major_axis: number;
}

export interface StageInfo {
  number: number;
  delta_v: number;
  vacuum_delta_v: number;
  twr: number;
  burn_time: number;
  start_mass: number;
  end_mass: number;
}

export interface ResourceInfo {
  name: string;
  amount: number;
  maximum: number;
}

export interface Telemetry {
  connected: boolean;
  source: string;
  error: string | null;
  timestamp: number;
  ut: number;
  met: number;

  vessel_name: string;
  situation: string;
  body: string;
  crew_count: number;

  altitude: number;
  surface_altitude: number;
  speed: number;
  vertical_speed: number;
  g_force: number;
  dynamic_pressure: number;
  mach: number;
  pitch: number;
  heading: number;
  roll: number;
  static_pressure: number;
  atmosphere_density: number;

  throttle: number;
  thrust: number;
  available_thrust: number;
  mass: number;
  dry_mass: number;
  twr: number;
  delta_v: number;
  vacuum_delta_v: number;
  current_stage: number;

  stages: StageInfo[];
  resources: ResourceInfo[];
  orbit: OrbitInfo | null;

  comm_can_communicate: boolean;
  comm_signal_strength: number;
}
