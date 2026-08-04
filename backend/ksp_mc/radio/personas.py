"""Les deux interlocuteurs de la radio.

Le partage des roles est volontairement strict :

  - le SOL voit tout mais ne touche a rien. Il conseille, calcule, alerte.
  - l'EQUIPAGE est le seul a pouvoir agir sur le vaisseau.

Cette separation n'est pas cosmetique. Elle garantit qu'une conversation avec
le centre de controle ne peut jamais, par accident, declencher une action a
bord : le sol ne dispose tout simplement d'aucun outil.
"""

from __future__ import annotations

from ..telemetry.schema import Telemetry

GROUND = "ground"
CREW = "crew"

LABELS = {GROUND: "Kerbal Space Center", CREW: "Equipage"}


_TONE = """\
Tu parles normalement, comme un collegue competent au telephone. Pas de
phraseologie militaire, pas de "Roger" ni de "Over". Des phrases courtes.
Tu peux etre chaleureux, mais tu ne fais pas de bavardage inutile : le pilote
a une fusee a gerer.

Tu reponds en francais. Deux ou trois phrases suffisent presque toujours.
"""

_HONESTY = """\
Regle absolue : tu ne fabriques jamais de chiffre. Toutes les valeurs
numeriques que tu cites doivent venir de la telemetrie ci-dessous ou du
resultat d'une commande. Si une donnee est marquee indisponible, tu dis
qu'elle est indisponible. Si tu ne sais pas, tu le dis.
"""

_GROUND_ROLE = """\
Tu es le centre de controle au sol, au Kerbal Space Center. Tu suis la mission
depuis les ecrans.

Tu n'as aucun moyen d'agir sur le vaisseau : tu ne peux ni allumer un moteur,
ni deployer quoi que ce soit. Si le pilote te demande une action a bord,
tu le renvoies vers l'equipage, qui est joignable sur l'autre canal.

Ton role : lire la telemetrie, expliquer, anticiper. Tu signales ce qui cloche
avant que ce soit un probleme -- un TWR insuffisant, un periapside qui reste
dans l'atmosphere, une reserve de delta-v trop juste pour la suite. Tu peux
faire des calculs d'orbitographie et proposer un plan.
"""

_CREW_ROLE = """\
Tu es l'equipage a bord. C'est toi qui manipules les commandes.

Tu executes ce qu'on te demande via les outils a ta disposition. Tu confirmes
brievement ce que tu as fait, en reprenant le resultat reel de la commande --
pas ce que tu esperais qu'elle fasse.

Avant d'affirmer qu'un equipement est present, verifie avec list_systems.
Beaucoup de vaisseaux n'ont ni panneaux solaires ni parachutes, et annoncer un
deploiement qui n'a pas eu lieu serait pire que de dire qu'il n'y en a pas.

Si une commande echoue, tu le dis franchement avec la raison renvoyee. Tu ne
reessaies pas en boucle.

Tu peux refuser ou temporiser si le moment est manifestement mauvais -- une
acceleration violente, une rentree atmospherique. Dans ce cas tu expliques
pourquoi en une phrase.
"""


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}".replace(",", " ")


def context_block(t: Telemetry | None) -> str:
    """Etat courant du vaisseau, injecte a chaque tour.

    On ne donne que ce qui est reellement mesure : les champs indisponibles
    sont annonces comme tels plutot que remplis de zeros, sinon le modele
    citerait des valeurs fausses en toute confiance.
    """
    if t is None or not t.connected:
        return "TELEMETRIE : aucune liaison avec le jeu."

    if not t.vessel_name:
        return f"TELEMETRIE : pas de vaisseau actif ({t.error or 'scene hors vol'})."

    lines = [
        "TELEMETRIE (instantane) :",
        f"  Vaisseau      : {t.vessel_name}",
        f"  Situation     : {t.situation}, autour de {t.body}",
        f"  Temps mission : {int(t.met // 3600):02d}:{int(t.met % 3600 // 60):02d}:{int(t.met % 60):02d}",
        f"  Equipage      : {t.crew_count} a bord",
        f"  Altitude      : {_fmt(t.altitude, 0)} m ({_fmt(t.surface_altitude, 0)} m sol)",
        f"  Vitesse       : {_fmt(t.orbital_speed)} m/s orbitale, "
        f"{_fmt(t.speed)} m/s surface, {_fmt(t.vertical_speed)} m/s verticale",
        f"  Acceleration  : {_fmt(t.g_force, 2)} g",
        f"  Masse         : {_fmt(t.mass, 2)} t (a vide {_fmt(t.dry_mass, 2)} t)",
        f"  Poussee       : {_fmt(t.thrust)} kN sur {_fmt(t.available_thrust)} kN, "
        f"gaz a {t.throttle * 100:.0f} %, TWR {_fmt(t.twr, 2)}",
        f"  Etage courant : {t.current_stage}",
    ]

    if t.delta_v_available:
        lines.append(f"  Delta-v total : {_fmt(t.delta_v, 0)} m/s")
    else:
        lines.append("  Delta-v total : indisponible (non calcule par le jeu)")

    if t.stages:
        detail = " | ".join(
            f"et.{s.number} {_fmt(s.delta_v, 0)} m/s TWR {_fmt(s.twr, 2)}"
            for s in t.stages
        )
        lines.append(f"  Par etage     : {detail}")

    if t.orbit:
        o = t.orbit
        lines.append(
            f"  Orbite        : Ap {_fmt(o.apoapsis, 0)} m, Pe {_fmt(o.periapsis, 0)} m, "
            f"exc {o.eccentricity:.4f}, inc {_fmt(o.inclination, 2)} deg"
        )

    if t.resources:
        res = ", ".join(
            f"{r.name} {r.amount:.0f}/{r.maximum:.0f}" for r in t.resources
        )
        lines.append(f"  Ressources    : {res}")

    if t.comm_available:
        lines.append(
            f"  Liaison       : {'etablie' if t.comm_can_communicate else 'coupee'}, "
            f"signal {t.comm_signal_strength * 100:.0f} %"
        )
    else:
        lines.append("  Liaison       : CommNet inactif ou pas d'antenne")

    if t.source == "sim":
        lines.append(
            "  ATTENTION     : ces valeurs viennent du SIMULATEUR, le jeu "
            "n'est pas lance. Aucune commande ne pourra etre executee."
        )

    return "\n".join(lines)


def system_prompt(persona: str, telemetry: Telemetry | None) -> str:
    role = _CREW_ROLE if persona == CREW else _GROUND_ROLE
    return "\n".join([role, _TONE, _HONESTY, context_block(telemetry)])
