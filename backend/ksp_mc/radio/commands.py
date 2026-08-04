"""Registre des commandes que l'equipage peut executer a bord.

Chaque commande est declaree une seule fois ici : sa description sert a la
fois de documentation pour le modele de langage et de contrat d'execution.
Ajouter une capacite a l'equipage revient a ajouter une entree dans ce
fichier, rien d'autre.

Les noms d'API utilises ont ete verifies sur le jeu reel (KSP 1.12.5,
kRPC 0.6.0) : controles de pilotage, collections de pieces, membres de
SASMode. Deux familles n'ont pas pu l'etre faute de pieces correspondantes a
bord du vaisseau de test : les experiences scientifiques et les parachutes.
Elles sont ecrites de façon defensive et signalees comme telles.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .llm import ToolSpec

# Membres exacts releves sur le jeu.
SAS_MODES = [
    "stability_assist", "prograde", "retrograde", "normal", "anti_normal",
    "radial", "anti_radial", "target", "anti_target", "maneuver",
]
SPEED_MODES = ["orbit", "surface", "target"]


@dataclass
class Command:
    name: str
    description: str
    handler: Callable[..., str]
    parameters: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    # Une commande irreversible ne part jamais sans accord explicite : un
    # largage d'etage mal interprete coute la mission.
    irreversible: bool = False
    # Verifiee sur le jeu reel ou non. Sert a nuancer les messages d'erreur.
    verified: bool = True

    def to_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
            },
        )


REGISTRY: dict[str, Command] = {}


def command(**kwargs):
    def decorate(fn):
        cmd = Command(name=fn.__name__, handler=fn, **kwargs)
        REGISTRY[cmd.name] = cmd
        return fn
    return decorate


# ======================================================================
# Pilotage
# ======================================================================

@command(
    description="Regle la manette des gaz, en pourcentage de 0 a 100.",
    parameters={"percent": {"type": "number",
                            "description": "0 = coupe, 100 = plein gaz"}},
    required=["percent"],
)
def set_throttle(conn, vessel, percent: float) -> str:
    value = max(0.0, min(100.0, float(percent)))
    vessel.control.throttle = value / 100.0
    return f"Manette des gaz a {value:.0f} %."


@command(
    description="Active ou coupe le pilote automatique de stabilisation (SAS).",
    parameters={"enabled": {"type": "boolean"}},
    required=["enabled"],
)
def set_sas(conn, vessel, enabled: bool) -> str:
    vessel.control.sas = bool(enabled)
    return "SAS active." if enabled else "SAS coupe."


@command(
    description=(
        "Oriente le vaisseau selon un mode SAS. Le SAS doit etre actif ; "
        "il est allume automatiquement si besoin."
    ),
    parameters={"mode": {"type": "string", "enum": SAS_MODES}},
    required=["mode"],
)
def set_sas_mode(conn, vessel, mode: str) -> str:
    if mode not in SAS_MODES:
        return f"Mode inconnu : {mode}. Modes possibles : {', '.join(SAS_MODES)}."
    vessel.control.sas = True
    try:
        vessel.control.sas_mode = getattr(conn.space_center.SASMode, mode)
    except Exception as exc:
        # Typiquement : pas de cible selectionnee, ou pas de noeud de manoeuvre.
        return f"Impossible de passer en {mode} : {exc}"
    return f"Orientation {mode} engagee."


@command(
    description="Active ou coupe le RCS (petits propulseurs d'attitude).",
    parameters={"enabled": {"type": "boolean"}},
    required=["enabled"],
)
def set_rcs(conn, vessel, enabled: bool) -> str:
    vessel.control.rcs = bool(enabled)
    return "RCS actif." if enabled else "RCS coupe."


# ======================================================================
# Systemes de bord
# ======================================================================

def _set_deployable(items, deployed: bool, singular: str, plural: str) -> str:
    """Deplie ou replie une collection de pieces deployables.

    Les pieces fixes exposent `deployed` en lecture seule : ecrire dessus
    echoue. On teste donc `deployable` avant d'agir, et on distingue dans le
    compte-rendu ce qui a bouge de ce qui est fixe.
    """
    if not items:
        return f"Aucun {singular} a bord."

    moved = fixed = failed = 0
    for item in items:
        try:
            if not item.deployable:
                fixed += 1
                continue
            item.deployed = bool(deployed)
            moved += 1
        except Exception:
            failed += 1

    action = "deploye" if deployed else "replie"
    parts = [f"{moved} {plural if moved > 1 else singular} {action}{'s' if moved > 1 else ''}"]
    if fixed:
        parts.append(f"{fixed} fixe{'s' if fixed > 1 else ''} (non deployable)")
    if failed:
        parts.append(f"{failed} en echec")
    return ", ".join(parts) + "."


@command(
    description="Deploie ou replie les panneaux solaires.",
    parameters={"deployed": {"type": "boolean"}},
    required=["deployed"],
)
def set_solar_panels(conn, vessel, deployed: bool) -> str:
    return _set_deployable(vessel.parts.solar_panels, deployed,
                           "panneau solaire", "panneaux solaires")


@command(
    description="Deploie ou replie les antennes de communication.",
    parameters={"deployed": {"type": "boolean"}},
    required=["deployed"],
)
def set_antennas(conn, vessel, deployed: bool) -> str:
    return _set_deployable(vessel.parts.antennas, deployed, "antenne", "antennes")


@command(
    description="Deploie ou replie les radiateurs.",
    parameters={"deployed": {"type": "boolean"}},
    required=["deployed"],
)
def set_radiators(conn, vessel, deployed: bool) -> str:
    return _set_deployable(vessel.parts.radiators, deployed, "radiateur", "radiateurs")


@command(
    description="Sort ou rentre le train d'atterrissage.",
    parameters={"deployed": {"type": "boolean"}},
    required=["deployed"],
)
def set_landing_gear(conn, vessel, deployed: bool) -> str:
    vessel.control.gear = bool(deployed)
    return "Train sorti." if deployed else "Train rentre."


@command(
    description="Allume ou eteint les feux exterieurs.",
    parameters={"on": {"type": "boolean"}},
    required=["on"],
)
def set_lights(conn, vessel, on: bool) -> str:
    vessel.control.lights = bool(on)
    return "Feux allumes." if on else "Feux eteints."


@command(
    description="Serre ou desserre les freins.",
    parameters={"on": {"type": "boolean"}},
    required=["on"],
)
def set_brakes(conn, vessel, on: bool) -> str:
    vessel.control.brakes = bool(on)
    return "Freins serres." if on else "Freins desserres."


@command(
    description=(
        "Active ou desactive un groupe d'actions personnalise, numerote de "
        "1 a 9. C'est le moyen de declencher ce que le pilote a lui-meme "
        "configure dans le VAB."
    ),
    parameters={
        "group": {"type": "integer", "description": "Numero du groupe, 1 a 9"},
        "enabled": {"type": "boolean"},
    },
    required=["group", "enabled"],
)
def set_action_group(conn, vessel, group: int, enabled: bool) -> str:
    number = int(group)
    if not 1 <= number <= 9:
        return "Les groupes d'actions vont de 1 a 9."
    vessel.control.set_action_group(number, bool(enabled))
    return f"Groupe d'actions {number} {'active' if enabled else 'desactive'}."


# ======================================================================
# Science
# ======================================================================

@command(
    description="Declenche toutes les experiences scientifiques disponibles.",
    verified=False,
)
def run_experiments(conn, vessel) -> str:
    experiments = vessel.parts.experiments
    if not experiments:
        return "Aucun instrument scientifique a bord."

    done = busy = failed = 0
    for exp in experiments:
        try:
            if not exp.available or exp.has_data:
                busy += 1
                continue
            exp.run()
            done += 1
        except Exception:
            failed += 1

    if done == 0 and busy and not failed:
        return f"Les {busy} instruments ont deja leurs donnees."
    report = f"{done} experience(s) declenchee(s)"
    if busy:
        report += f", {busy} deja utilisee(s)"
    if failed:
        report += f", {failed} en echec"
    return report + "."


@command(
    description="Transmet par radio les donnees scientifiques collectees.",
    verified=False,
)
def transmit_science(conn, vessel) -> str:
    experiments = vessel.parts.experiments
    if not experiments:
        return "Aucun instrument scientifique a bord."

    sent = failed = 0
    for exp in experiments:
        try:
            if not exp.has_data:
                continue
            exp.transmit()
            sent += 1
        except Exception:
            failed += 1

    if sent == 0 and failed == 0:
        return "Rien a transmettre, aucune donnee en memoire."
    report = f"{sent} lot(s) de donnees transmis"
    if failed:
        report += f", {failed} en echec"
    return report + "."


# ======================================================================
# Etagement et decouplage : IRREVERSIBLE
# ======================================================================

@command(
    description=(
        "Declenche l'etage suivant : allumage des moteurs de l'etage et "
        "largage de ce qui doit l'etre. Action definitive."
    ),
    irreversible=True,
)
def activate_stage(conn, vessel) -> str:
    before = vessel.control.current_stage
    vessel.control.activate_next_stage()
    after = vessel.control.current_stage
    return f"Etage declenche : passage de {before} a {after}."


@command(
    description="Ouvre les parachutes. Action definitive.",
    irreversible=True,
    verified=False,
)
def deploy_parachutes(conn, vessel) -> str:
    chutes = vessel.parts.parachutes
    if not chutes:
        return "Aucun parachute a bord."

    opened = failed = 0
    for chute in chutes:
        try:
            chute.deploy()
            opened += 1
        except Exception:
            failed += 1
    report = f"{opened} parachute(s) ouvert(s)"
    if failed:
        report += f", {failed} en echec"
    return report + "."


# ======================================================================
# Lecture seule
# ======================================================================

@command(
    description=(
        "Inventaire de ce qui est reellement installe a bord : panneaux, "
        "antennes, radiateurs, parachutes, instruments, moteurs. A utiliser "
        "avant d'affirmer qu'un equipement existe."
    ),
)
def list_systems(conn, vessel) -> str:
    parts = vessel.parts
    inventory = {
        "panneaux solaires": len(parts.solar_panels),
        "antennes": len(parts.antennas),
        "radiateurs": len(parts.radiators),
        "parachutes": len(parts.parachutes),
        "instruments scientifiques": len(parts.experiments),
        "moteurs": len(parts.engines),
        "decoupleurs": len(parts.decouplers),
    }
    present = [f"{n} {label}" for label, n in inventory.items() if n]
    absent = [label for label, n in inventory.items() if not n]

    report = "A bord : " + (", ".join(present) if present else "rien de notable")
    if absent:
        report += ". Absents : " + ", ".join(absent)
    return report + "."


# ======================================================================

def specs(include_irreversible: bool = True) -> list[ToolSpec]:
    return [
        c.to_spec()
        for c in REGISTRY.values()
        if include_irreversible or not c.irreversible
    ]


def get(name: str) -> Command | None:
    return REGISTRY.get(name)
