"""Itineraires multi-etapes entre deux corps quelconques du systeme.

Le systeme est un arbre : une etoile, des planetes, des lunes. Aller d'un
corps a un autre revient a remonter l'arbre jusqu'a l'ancetre commun, faire un
transfert a ce niveau, puis redescendre.

    Kerbin -> Laythe :  Kerbin --(transfert autour du Soleil)--> Jool
                        Jool   --(descente vers sa lune)-------> Laythe

    Mun -> Duna :       Mun    --(evasion vers le systeme Kerbin)--> Kerbin
                        Kerbin --(transfert autour du Soleil)------> Duna

Chaque etape a son propre cout, et ils ne s'additionnent pas naivement : une
evasion depuis une lune ne coute pas la meme chose qu'une ejection depuis une
orbite basse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .bodies import Body, BodyCatalog
from .transfer import delta_v_ejection, hohmann

# Delta-v empirique pour passer de la surface a une orbite basse, pertes
# comprises (gravite, trainee, braquage). Ces valeurs viennent des cartes de
# delta-v de la communaute : elles ne se calculent pas proprement, car elles
# dependent du profil d'ascension et de la forme du lanceur.
SURFACE_VERS_ORBITE: dict[str, float] = {
    "Kerbin": 3400, "Mun": 580, "Minmus": 180,
    "Eve": 8000, "Gilly": 30,
    "Duna": 1450, "Ike": 390,
    "Moho": 870, "Dres": 430, "Eeloo": 620,
    "Laythe": 2900, "Vall": 860, "Tylo": 2270, "Bop": 220, "Pol": 130,
}


@dataclass
class Etape:
    """Une etape du plan de vol."""

    genre: str        # "ascension" | "evasion" | "transfert" | "capture" | "descente"
    titre: str
    delta_v: float
    depuis: str = ""
    vers: str = ""
    duree: float = 0.0            # s, 0 si instantane a l'echelle du plan
    angle_de_phase: float | None = None
    periode_synodique: float = 0.0
    detail: str = ""
    approximatif: bool = False    # chiffre empirique plutot que calcule


@dataclass
class Plan:
    depart: str
    arrivee: str
    profil: str                   # "orbite" | "surface"
    etapes: list[Etape] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    itineraire: list[str] = field(default_factory=list)

    @property
    def delta_v_total(self) -> float:
        return math.fsum(e.delta_v for e in self.etapes)

    @property
    def duree_totale(self) -> float:
        return math.fsum(e.duree for e in self.etapes)


# ----------------------------------------------------------------------
# Structure de l'arbre
# ----------------------------------------------------------------------
def ancetres(catalog: BodyCatalog, nom: str) -> list[str]:
    """Chaine depuis le corps jusqu'a l'etoile, incluse."""
    chaine: list[str] = []
    courant = catalog.get(nom)
    vus: set[str] = set()
    while courant is not None and courant.name not in vus:
        vus.add(courant.name)
        chaine.append(courant.name)
        courant = catalog.parent_of(courant)
    return chaine


def itineraire(catalog: BodyCatalog, depart: str, arrivee: str) -> list[str] | None:
    """Suite de corps traversee, ancetre commun compris s'il faut y passer."""
    if depart == arrivee:
        return None

    haut = ancetres(catalog, depart)
    bas = ancetres(catalog, arrivee)
    if not haut or not bas:
        return None

    commun = next((n for n in haut if n in bas), None)
    if commun is None:
        return None

    # Montee : du depart jusqu'a l'enfant direct de l'ancetre commun.
    montee = haut[: haut.index(commun)]
    # Descente : de l'enfant direct de l'ancetre commun jusqu'a l'arrivee.
    descente = list(reversed(bas[: bas.index(commun)]))

    if not montee:
        # On part de l'ancetre commun lui-meme (Kerbin -> Mun, Jool -> Laythe).
        return [commun] + descente
    if not descente:
        # On arrive sur l'ancetre commun (Mun -> Kerbin).
        return montee + [commun]
    return montee + descente


# ----------------------------------------------------------------------
# Construction du plan
# ----------------------------------------------------------------------
def construire(
    catalog: BodyCatalog,
    depart: str,
    arrivee: str,
    depuis_surface: bool = False,
    vers_surface: bool = False,
    parking_depart: float | None = None,
    parking_arrivee: float | None = None,
) -> Plan | None:
    chemin = itineraire(catalog, depart, arrivee)
    if chemin is None:
        return None

    corps_depart = catalog.get(depart)
    corps_arrivee = catalog.get(arrivee)
    if corps_depart is None or corps_arrivee is None:
        return None

    alt_depart = (
        parking_depart if parking_depart is not None else corps_depart.low_orbit()
    )
    alt_arrivee = (
        parking_arrivee if parking_arrivee is not None else corps_arrivee.low_orbit()
    )

    plan = Plan(
        depart=depart,
        arrivee=arrivee,
        profil="surface" if vers_surface else "orbite",
        itineraire=chemin,
    )

    # --- Decollage ---
    if depuis_surface:
        cout = SURFACE_VERS_ORBITE.get(depart)
        if cout is None:
            plan.avertissements.append(
                f"Pas de valeur d'ascension connue pour {depart} : le "
                f"decollage n'est pas compte."
            )
        else:
            plan.etapes.append(
                Etape(
                    genre="ascension",
                    titre=f"Decollage depuis {depart}",
                    delta_v=cout,
                    depuis=depart,
                    vers=f"orbite basse de {depart}",
                    detail=f"jusqu'a environ {alt_depart / 1000:.0f} km",
                    approximatif=True,
                )
            )

    # --- Enchainement des etapes intermediaires ---
    # Vrai quand la capture precedente nous a laisses sur une ellipse qui
    # atteint deja la lune visee : il n'y a alors plus d'injection a payer.
    deja_en_route = False

    for i in range(len(chemin) - 1):
        a = catalog.get(chemin[i])
        b = catalog.get(chemin[i + 1])
        if a is None or b is None:
            continue

        premiere = i == 0
        derniere = i == len(chemin) - 2

        alt_a = alt_depart if premiere else a.low_orbit()
        alt_b = alt_arrivee if derniere else b.low_orbit()

        # Si l'etape suivante descend vers une lune de b, on ne se capture pas
        # en orbite basse : on vise une ellipse dont l'apoapside touche deja
        # l'orbite de cette lune. C'est ce que fait tout joueur, et l'ecart est
        # enorme -- sur Jool, 1100 m/s au lieu de 2950.
        lune_suivante = None
        if not derniere:
            candidate = catalog.get(chemin[i + 2])
            if candidate is not None and candidate.parent == b.name:
                lune_suivante = candidate

        if b.parent == a.name:
            _descente(catalog, plan, a, b, alt_a, alt_b, deja_en_route)
            deja_en_route = False
        elif a.parent == b.name:
            _evasion(catalog, plan, a, b, alt_a)
        elif a.parent == b.parent and a.parent:
            _transfert_freres(catalog, plan, a, b, alt_a, alt_b, premiere, lune_suivante)
            deja_en_route = lune_suivante is not None
        else:
            plan.avertissements.append(
                f"Etape {a.name} vers {b.name} non modelisee."
            )

    # --- Atterrissage ---
    if vers_surface:
        cout = SURFACE_VERS_ORBITE.get(arrivee)
        if cout is None:
            plan.avertissements.append(
                f"Pas de valeur d'atterrissage connue pour {arrivee}."
            )
        elif corps_arrivee.has_atmosphere:
            # Sur un corps avec atmosphere, la seule poussee vraiment
            # necessaire est la desorbitation : abaisser le periapside dans
            # l'air. Elle se calcule, contrairement au reste de la descente.
            dv_desorbitation = _desorbitation(corps_arrivee, alt_arrivee)
            plan.etapes.append(
                Etape(
                    genre="descente",
                    titre=f"Desorbitation vers {arrivee}",
                    delta_v=dv_desorbitation,
                    depuis=f"orbite basse de {arrivee}",
                    vers=arrivee,
                    detail=(
                        "l'atmosphere fait le freinage ; le posé final dépend "
                        "des parachutes et du vaisseau, non compté ici"
                    ),
                )
            )
            if corps_arrivee.atmosphere < 60_000:
                plan.avertissements.append(
                    f"L'atmosphere de {arrivee} est mince : les parachutes seuls "
                    f"ne suffisent generalement pas, prevoir plusieurs centaines "
                    f"de m/s pour le posé."
                )
        else:
            plan.etapes.append(
                Etape(
                    genre="descente",
                    titre=f"Atterrissage sur {arrivee}",
                    delta_v=cout,
                    depuis=f"orbite basse de {arrivee}",
                    vers=arrivee,
                    detail="sans atmosphere : freinage entierement propulsif",
                    approximatif=True,
                )
            )

    _avertir(catalog, plan, chemin)
    return plan


def _transfert_freres(
    catalog, plan, a: Body, b: Body, alt_a, alt_b, premiere, lune_suivante=None
) -> None:
    """Transfert entre deux corps de meme parent.

    `lune_suivante` change la nature de la capture : au lieu de se satelliser
    en orbite basse, on vise une ellipse qui atteint deja cette lune.
    """
    parent = catalog.parent_of(a)
    if parent is None:
        return

    v_inf_dep, v_inf_arr, duree = hohmann(parent.mu, a.orbit_radius, b.orbit_radius)
    from .transfer import angle_de_phase, periode_synodique

    dv_ejection = delta_v_ejection(a, alt_a, v_inf_dep)
    plan.etapes.append(
        Etape(
            genre="transfert",
            titre=f"Injection {a.name} vers {b.name}",
            delta_v=dv_ejection,
            depuis=a.name,
            vers=b.name,
            duree=duree,
            angle_de_phase=angle_de_phase(parent.mu, a.orbit_radius, b.orbit_radius),
            periode_synodique=periode_synodique(
                parent.mu, a.orbit_radius, b.orbit_radius
            ),
            detail=f"depuis une orbite a {alt_a / 1000:.0f} km",
        )
    )
    if lune_suivante is None:
        plan.etapes.append(
            Etape(
                genre="capture",
                titre=f"Capture autour de {b.name}",
                delta_v=delta_v_ejection(b, alt_b, v_inf_arr),
                depuis=b.name,
                vers=b.name,
                detail=f"vers une orbite a {alt_b / 1000:.0f} km",
            )
        )
        return

    # Capture sur une ellipse : periapside bas pour profiter de l'effet
    # Oberth, apoapside deja a hauteur de la lune visee.
    rp = b.radius + alt_b
    ra = lune_suivante.orbit_radius
    a_ellipse = (rp + ra) / 2.0
    v_hyperbolique = math.sqrt(v_inf_arr ** 2 + 2.0 * b.mu / rp)
    v_ellipse = math.sqrt(b.mu * (2.0 / rp - 1.0 / a_ellipse))

    plan.etapes.append(
        Etape(
            genre="capture",
            titre=f"Capture elliptique autour de {b.name}",
            delta_v=v_hyperbolique - v_ellipse,
            depuis=b.name,
            vers=lune_suivante.name,
            detail=(
                f"periapside {alt_b / 1000:.0f} km, apoapside a hauteur de "
                f"{lune_suivante.name} : bien moins cher qu'une orbite basse"
            ),
        )
    )


def _descente(
    catalog, plan, parent: Body, lune: Body, alt_parent, alt_lune, deja_en_route=False
) -> None:
    """Du corps central vers l'une de ses lunes."""
    r1 = parent.radius + alt_parent
    v_inf_dep, v_inf_arr, duree = hohmann(parent.mu, r1, lune.orbit_radius)
    from .transfer import angle_de_phase, periode_synodique

    if deja_en_route:
        # L'ellipse de capture atteint deja cette lune : la vitesse residuelle
        # a la rencontre se calcule depuis l'apoapside de cette ellipse.
        ra = lune.orbit_radius
        a_ellipse = (r1 + ra) / 2.0
        v_ellipse_apo = math.sqrt(parent.mu * (2.0 / ra - 1.0 / a_ellipse))
        v_lune = math.sqrt(parent.mu / ra)
        v_inf_arr = abs(v_lune - v_ellipse_apo)
    else:
        plan.etapes.append(
            Etape(
                genre="transfert",
                titre=f"Injection vers {lune.name}",
                delta_v=v_inf_dep,
                depuis=parent.name,
                vers=lune.name,
                duree=duree,
                angle_de_phase=angle_de_phase(parent.mu, r1, lune.orbit_radius),
                periode_synodique=periode_synodique(parent.mu, r1, lune.orbit_radius),
                detail=(
                    f"depuis une orbite a {alt_parent / 1000:.0f} km autour de "
                    f"{parent.name}"
                ),
            )
        )
    plan.etapes.append(
        Etape(
            genre="capture",
            titre=f"Capture autour de {lune.name}",
            delta_v=delta_v_ejection(lune, alt_lune, v_inf_arr),
            depuis=lune.name,
            vers=lune.name,
            detail=f"vers une orbite a {alt_lune / 1000:.0f} km",
        )
    )


def _evasion(catalog, plan, lune: Body, parent: Body, alt_lune) -> None:
    """Quitter une lune pour se retrouver en orbite autour de son parent.

    On vise tout juste la vitesse de liberation : le vaisseau sort de la
    sphere d'influence avec une vitesse residuelle quasi nulle, donc sur une
    orbite proche de celle de la lune autour du parent.
    """
    r = lune.radius + alt_lune
    v_circulaire = math.sqrt(lune.mu / r)
    v_liberation = math.sqrt(2.0 * lune.mu / r)

    plan.etapes.append(
        Etape(
            genre="evasion",
            titre=f"Evasion de {lune.name}",
            delta_v=v_liberation - v_circulaire,
            depuis=lune.name,
            vers=parent.name,
            detail=(
                f"depuis une orbite a {alt_lune / 1000:.0f} km, on ressort sur "
                f"l'orbite de {lune.name} autour de {parent.name}"
            ),
        )
    )


def _desorbitation(corps: Body, altitude: float) -> float:
    """Cout pour abaisser le periapside au coeur de l'atmosphere.

    On vise un periapside a mi-hauteur de l'atmosphere : assez bas pour que le
    freinage soit franc, assez haut pour ne pas exploser en entree.
    """
    r_orbite = corps.radius + altitude
    r_cible = corps.radius + corps.atmosphere * 0.25
    if r_cible >= r_orbite:
        return 0.0

    a_ellipse = (r_orbite + r_cible) / 2.0
    v_circulaire = math.sqrt(corps.mu / r_orbite)
    v_ellipse = math.sqrt(corps.mu * (2.0 / r_orbite - 1.0 / a_ellipse))
    return v_circulaire - v_ellipse


def _avertir(catalog, plan: Plan, chemin: list[str]) -> None:
    for nom in chemin:
        corps = catalog.get(nom)
        if corps is None or corps.parent is None:
            continue
        if corps.inclination >= 1.0:
            plan.avertissements.append(
                f"L'orbite de {nom} est inclinee de {corps.inclination:.1f}° : "
                f"prevoir un changement de plan, non compte ici."
            )
        if corps.eccentricity >= 0.05:
            plan.avertissements.append(
                f"L'orbite de {nom} est excentrique (e = {corps.eccentricity:.2f}) : "
                f"le cout varie selon le moment de l'annee."
            )

    arrivee = catalog.get(plan.arrivee)
    if arrivee is not None and arrivee.has_atmosphere and plan.profil == "orbite":
        plan.avertissements.append(
            f"{plan.arrivee} a une atmosphere : un aerofreinage peut supprimer "
            f"l'essentiel du cout de capture."
        )
