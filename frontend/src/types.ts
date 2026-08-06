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

export interface Guidage {
  phase: string;
  consigne: string;
  noeud: boolean;
  noeud_delta_v: number;
  noeud_temps: number;
  noeud_duree: number;
  noeud_allumage: number;
  ecart_attitude: number;
  circularisation_dv: number;
  circularisation_duree: number;
  assiette_cible: number;
  assiette_ecart: number;
  alertes: string[];
}

export interface Telemetry {
  connected: boolean;
  source: string;
  error: string | null;
  timestamp: number;
  ut: number;
  met: number;
  game_scene: string;

  vessel_name: string;
  situation: string;
  body: string;
  crew_count: number;

  altitude: number;
  surface_altitude: number;
  speed: number;
  orbital_speed: number;
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
  delta_v_available: boolean;
  current_stage: number;

  specific_impulse: number;
  stages: StageInfo[];
  resources: ResourceInfo[];
  orbit: OrbitInfo | null;
  guidage: Guidage | null;

  comm_available: boolean;
  comm_can_communicate: boolean;
  comm_signal_strength: number;
}
