"""Calcul du delta-v par etage, par simulation de la consommation.

Pourquoi ce module existe : kRPC 0.6.0 expose bien `Stage.delta_v`, mais sur
KSP 1.12.5 toutes les proprietes d'etage levent "Delta-v has not been
calculated for this vessel yet", alors meme que `Vessel.delta_v` repond
correctement dans la meme session. Le jeu, lui, affiche le detail. On le
recalcule donc a partir des pieces.

Pourquoi une simulation plutot qu'une formule : sur un lanceur a propulseurs
lateraux, deux moteurs brulent simultanement dans des reservoirs differents et
les carcasses vides sont larguees en cours de route. Une difference de masse
entre etages attribuerait la masse jetee a du carburant consomme. Il faut donc
integrer la consommation dans le temps, puis larguer.

Simplification assumee : on suppose le crossfeed total pour les ergols
liquides (tous les reservoirs presents alimentent tous les moteurs liquides).
C'est exact pour un empilement classique et pour des propulseurs lateraux
standard. Ca ne modelise pas l'asparagus staging avec conduites de carburant,
ou le resultat serait optimiste.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .schema import StageInfo

G0 = 9.80665
DT = 0.05          # pas d'integration, s
MAX_BURN_S = 3600  # garde-fou : un etage ne brule jamais plus d'une heure


@dataclass
class EngineInfo:
    stage: int
    max_thrust: float           # N, a la pression courante
    max_vacuum_thrust: float    # N
    isp: float                  # s, a la pression courante
    vacuum_isp: float           # s
    propellants: dict[str, float]  # nom -> ratio en unites
    solid: bool = False         # un moteur a poudre ne puise que chez lui


@dataclass
class PartInfo:
    index: int
    dry_mass: float                       # kg
    stage: int                            # etage d'allumage (-1 = jamais)
    decouple_stage: int                   # etage de largage (-1 = jamais)
    resources: dict[str, float] = field(default_factory=dict)  # nom -> unites
    engine: EngineInfo | None = None


def compute_stages(
    parts: list[PartInfo],
    densities: dict[str, float],   # nom -> kg par unite
    current_stage: int,
    vacuum: bool = False,
) -> list[StageInfo]:
    """Renvoie un StageInfo par etage, du plus haut numero au plus bas."""

    by_index = {p.index: p for p in parts}
    present = {p.index for p in parts}
    # Etat mutable des ergols : on le vide au fil de la simulation.
    tanks: dict[int, dict[str, float]] = {
        p.index: dict(p.resources) for p in parts
    }

    def mass_of(indices) -> float:
        total = 0.0
        for i in indices:
            total += by_index[i].dry_mass
            for name, units in tanks[i].items():
                total += units * densities.get(name, 0.0)
        return total

    results: list[StageInfo] = []

    # Borne haute : le plus grand numero d'etage reellement porte par une
    # piece, jamais au-dela de l'etage courant.
    #
    # Au pas de tir, current_stage vaut un de plus que le plus haut etage
    # existant (4 pour des pieces numerotees 3 a 0) : partir de current_stage-1
    # fonctionnait donc par coincidence. Mais une fois tout largue,
    # current_stage tombe a 0 et cette meme formule donne une plage vide : le
    # dernier etage, celui qui brule encore, devenait incalculable.
    highest = max((p.stage for p in parts), default=-1)
    start = min(current_stage, highest)

    for stage in range(start, -1, -1):
        # Largage : les pieces dont le decouple_stage vaut cet etage partent
        # au moment ou l'etage s'active, donc avant la combustion.
        present = {i for i in present if by_index[i].decouple_stage != stage}
        if not present:
            break

        start_mass = mass_of(present)

        # Moteurs actifs : allumes a cet etage ou plus haut, et encore attaches.
        engines = [
            by_index[i]
            for i in present
            if by_index[i].engine is not None and by_index[i].stage >= stage
        ]

        dv, burn_time, thrust_sum, mdot_sum = _burn(
            engines, present, tanks, by_index, densities, mass_of, vacuum
        )

        end_mass = mass_of(present)
        eff_isp = thrust_sum / (mdot_sum * G0) if mdot_sum > 0 else 0.0

        # TWR au demarrage de l'etage, au niveau de la mer de Kerbin.
        twr = thrust_sum / (start_mass * G0) if start_mass > 0 else 0.0

        results.append(
            StageInfo(
                number=stage,
                delta_v=dv,
                vacuum_delta_v=dv if vacuum else 0.0,
                twr=twr,
                burn_time=burn_time,
                start_mass=start_mass / 1000.0,
                end_mass=end_mass / 1000.0,
            )
        )

    return results


def _burn(engines, present, tanks, by_index, densities, mass_of, vacuum):
    """Integre la combustion d'un etage jusqu'a la PREMIERE extinction.

    C'est le point cle du calcul. Un etage ne s'arrete pas quand tous ses
    moteurs sont a sec, mais des que l'un d'eux s'eteint : c'est ce qui
    declenche le largage. Sur un lanceur a propulseurs lateraux, les
    propulseurs a poudre s'eteignent bien avant le moteur central, et celui-ci
    poursuit sa combustion dans l'etage suivant. Attendre l'extinction generale
    ferait bruler a l'etage 3 du carburant qui appartient a l'etage 2.

    Renvoie (delta_v, duree, poussee initiale, debit massique initial).
    """
    dv = 0.0
    elapsed = 0.0
    thrust0 = 0.0
    mdot0 = 0.0
    watch: set[int] | None = None

    steps = 0
    max_steps = int(MAX_BURN_S / DT)

    while steps < max_steps:
        steps += 1
        thrust = 0.0
        mdot_total = 0.0
        draws: list[tuple[EngineInfo, int, float]] = []

        for part in engines:
            eng = part.engine
            th = eng.max_vacuum_thrust if vacuum else eng.max_thrust
            isp = eng.vacuum_isp if vacuum else eng.isp
            if th <= 0 or isp <= 0:
                continue
            if not _has_propellant(eng, part.index, present, tanks, by_index):
                continue
            mdot = th / (isp * G0)
            thrust += th
            mdot_total += mdot
            draws.append((eng, part.index, mdot))

        firing = {owner for _, owner, _ in draws}

        if watch is None:
            # Premier pas : on retient qui allume, ce sont eux qu'on surveille.
            if not firing:
                break
            watch = firing
            thrust0, mdot0 = thrust, mdot_total
        elif watch - firing:
            # Un moteur du lot initial vient de s'eteindre : fin de l'etage.
            break

        if not draws:
            break

        mass = mass_of(present)
        if mass <= 0:
            break

        dv += (thrust / mass) * DT
        for eng, owner, mdot in draws:
            _consume(eng, owner, mdot * DT, present, tanks, by_index, densities)
        elapsed += DT

    return dv, elapsed, thrust0, mdot0


def _sources(eng: EngineInfo, owner: int, resource: str, present, tanks, by_index):
    """Reservoirs ou ce moteur peut reellement puiser cet ergol.

    Un decoupleur bloque le crossfeed : un moteur ne pompe que dans les
    reservoirs qui seront largues en meme temps que lui. On approxime donc le
    groupe d'alimentation par le decouple_stage commun.

    Sans cette restriction, le moteur principal viderait les reservoirs de
    l'etage superieur : mesure a l'appui, il brulait 93 s au lieu de 70.
    """
    if eng.solid:
        # La poudre n'est pas transferable : le propulseur brule la sienne.
        return [owner] if tanks.get(owner, {}).get(resource, 0.0) > 0 else []

    group = by_index[owner].decouple_stage
    return [
        i
        for i in present
        if by_index[i].decouple_stage == group and tanks[i].get(resource, 0.0) > 0
    ]


def _has_propellant(eng, owner, present, tanks, by_index) -> bool:
    for resource in eng.propellants:
        if not _sources(eng, owner, resource, present, tanks, by_index):
            return False
    return True


def _consume(eng, owner, mass_kg, present, tanks, by_index, densities) -> None:
    """Retire `mass_kg` d'ergols, repartis selon le melange du moteur."""
    # Part massique de chaque ergol dans le melange.
    weights = {
        name: ratio * densities.get(name, 0.0)
        for name, ratio in eng.propellants.items()
    }
    total = sum(weights.values())
    if total <= 0:
        return

    for name, weight in weights.items():
        density = densities.get(name, 0.0)
        if density <= 0:
            continue
        units_needed = (mass_kg * weight / total) / density
        sources = _sources(eng, owner, name, present, tanks, by_index)
        if not sources:
            continue
        # Vidange proportionnelle au contenu, pour eviter qu'un reservoir se
        # vide seul alors que les autres sont pleins.
        available = sum(tanks[i][name] for i in sources)
        if available <= 0:
            continue
        drawn = min(units_needed, available)
        for i in sources:
            share = tanks[i][name] / available
            tanks[i][name] = max(0.0, tanks[i][name] - drawn * share)


def snapshot(vessel, pressure_atm: float = 1.0) -> tuple[list[PartInfo], dict[str, float]]:
    """Photographie les pieces du vaisseau dans nos structures.

    `pressure_atm` sert a choisir l'Isp : KSP affiche par defaut les valeurs au
    niveau de la mer, on fait pareil pour pouvoir comparer.
    """
    parts: list[PartInfo] = []
    densities: dict[str, float] = {}

    for index, part in enumerate(vessel.parts.all):
        resources: dict[str, float] = {}
        for res in part.resources.all:
            try:
                if res.amount > 0:
                    resources[res.name] = res.amount
                    densities.setdefault(res.name, res.density)
            except Exception:
                continue

        engine_info = None
        engine = part.engine
        if engine is not None:
            try:
                names = list(engine.propellant_names)
                ratios = _ratios(engine, names)
                # Le limiteur de poussee regle dans le VAB n'est PAS pris en
                # compte par max_thrust, malgre ce que suggere la doc kRPC.
                # Mesure a l'appui : un RE-M3 limite a 73,5 % annonce 1380 kN
                # alors que le jeu compte 1014 kN. Sans cette correction, on
                # sur-estime la poussee, donc le debit, donc on brule trop
                # d'ergols et toutes les masses des etages suivants derivent.
                limit = _thrust_limit(engine)
                engine_info = EngineInfo(
                    stage=part.stage,
                    max_thrust=engine.max_thrust * limit,
                    max_vacuum_thrust=engine.max_vacuum_thrust * limit,
                    isp=engine.specific_impulse,
                    vacuum_isp=engine.vacuum_specific_impulse,
                    propellants=ratios,
                    solid="SolidFuel" in names,
                )
            except Exception:
                engine_info = None

        parts.append(
            PartInfo(
                index=index,
                dry_mass=part.dry_mass,
                stage=part.stage,
                decouple_stage=part.decouple_stage,
                resources=resources,
                engine=engine_info,
            )
        )

    return parts, densities


def _thrust_limit(engine) -> float:
    """Limiteur de poussee, ramene dans [0, 1].

    kRPC l'expose en pourcentage sur certaines versions et en fraction sur
    d'autres ; on normalise pour ne pas dependre de cette variation.
    """
    try:
        value = float(engine.thrust_limit)
    except Exception:
        return 1.0
    if value > 1.0:
        value /= 100.0
    return max(0.0, min(1.0, value))


def _ratios(engine, names: list[str]) -> dict[str, float]:
    """Melange du moteur. On lit les ratios exposes par kRPC, avec un repli
    sur un melange equilibre si l'API ne les fournit pas."""
    try:
        return {p.name: p.ratio for p in engine.propellants}
    except Exception:
        return {name: 1.0 for name in names}


def total_delta_v(stages: list[StageInfo]) -> float:
    return math.fsum(s.delta_v for s in stages)
