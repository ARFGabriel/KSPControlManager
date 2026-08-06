"""Veille de bord : ce qui va manquer, et quand.

Ce module ne lit rien lui-meme. Il regarde passer les echantillons de
telemetrie et en tire des tendances -- ce qu'un seuil instantane ne peut pas
faire. Une batterie a 40 % n'est ni bonne ni mauvaise ; ce qui compte, c'est de
savoir si elle se vide, et en combien de temps.

Deux surveillances :

  - la **reserve electrique** : on mesure le flux reel par regression sur les
    dernieres secondes de jeu, puis on projette. C'est la panne qui transforme
    une sonde en debris, et elle ne previent jamais d'elle-meme ;
  - la **periapside** : une orbite dont le point bas descend sous l'atmosphere
    finira par rentrer, parfois des dizaines de minutes plus tard. On le dit
    tant qu'il reste du temps pour reagir.

Le temps de reference est le **temps universel du jeu**, jamais l'horloge du
PC : sous acceleration temporelle, une batterie se vide en quelques secondes
reelles, et un flux calcule sur l'horloge murale serait faux d'un facteur cent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Fenetre d'observation, en secondes de jeu. Assez longue pour lisser le bruit
# de la consommation (une antenne qui emet, un panneau qui passe a l'ombre),
# assez courte pour reagir a un changement de regime.
FENETRE_UT = 30.0

# Garde-fou memoire : a 10 Hz sans acceleration, 30 s de jeu font 300 points.
MAX_POINTS = 400

# En dessous, on previent : cinq minutes de jeu suffisent a rentrer la
# batterie dans le vert (orienter les panneaux, couper un consommateur), et
# pas beaucoup plus.
SEUIL_CRITIQUE_S = 300.0

# Une periapside ne bouge pas d'elle-meme en conique patchee : toute derive
# vient d'une poussee ou du frottement de l'air. En dessous de ce seuil, c'est
# du bruit de mesure.
DERIVE_MINIMALE = 0.5      # m par seconde de jeu

# Au-dela, la rentree est trop lointaine pour meriter une alerte : le joueur
# aura change dix fois de vaisseau d'ici la. Un jour kerbal.
HORIZON_DERIVE_S = 6 * 3600


@dataclass
class ReserveElectrique:
    suivie: bool = False
    charge: float = 0.0
    maximum: float = 0.0
    fraction: float = 0.0
    flux: float = 0.0                  # unites par seconde de jeu, < 0 = decharge
    secondes_restantes: float = -1.0   # -1 : pas de fin previsible
    secondes_plein: float = -1.0       # -1 : pas de recharge en cours
    message: str = ""
    critique: bool = False


@dataclass
class Periapside:
    surveillee: bool = False
    altitude: float = 0.0
    plancher: float = 0.0              # atmosphere, ou le sol s'il n'y en a pas
    derive: float = 0.0                # m par seconde de jeu, < 0 = descend
    sous_le_plancher: bool = False
    temps_avant: float = 0.0           # s avant le passage sous le plancher
    message: str = ""
    critique: bool = False


@dataclass
class Veille:
    electrique: ReserveElectrique = field(default_factory=ReserveElectrique)
    periapside: Periapside = field(default_factory=Periapside)
    alertes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# Briques de calcul
# ----------------------------------------------------------------------
def pente(points: list[tuple[float, float]]) -> float:
    """Variation par unite de temps, par moindres carres.

    Une simple difference entre le premier et le dernier point suffirait en
    theorie, mais les quantites du jeu sont bruitees et arrivent par paquets :
    deux echantillons mal choisis donnent un flux aberrant. La regression
    utilise toute la fenetre.
    """
    n = len(points)
    if n < 2:
        return 0.0

    t_moyen = math.fsum(t for t, _ in points) / n
    v_moyen = math.fsum(v for _, v in points) / n

    covariance = math.fsum((t - t_moyen) * (v - v_moyen) for t, v in points)
    variance = math.fsum((t - t_moyen) ** 2 for t, _ in points)
    if variance <= 0:
        return 0.0
    return covariance / variance


def _fr(valeur: float, decimales: int = 2) -> str:
    """Nombre a la francaise : virgule decimale, comme partout ailleurs dans
    l'interface."""
    return f"{valeur:.{decimales}f}".replace(".", ",")


def _fini(valeur, defaut: float = 0.0) -> float:
    """Un vaisseau au sol renvoie NaN pour son apoapside, et NaN n'est pas du
    JSON valide : il casserait la trame entiere, pas seulement ce champ."""
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return defaut
    return nombre if math.isfinite(nombre) else defaut


class _Serie:
    """Historique d'une grandeur, borne en duree de jeu et en nombre."""

    def __init__(self) -> None:
        self.points: list[tuple[float, float]] = []

    def vider(self) -> None:
        self.points.clear()

    def ajouter(self, ut: float, valeur: float) -> None:
        self.points.append((ut, valeur))
        limite = ut - FENETRE_UT
        # On coupe par la duree d'abord, par le nombre ensuite : sous forte
        # acceleration temporelle, trois points peuvent couvrir la fenetre.
        self.points = [p for p in self.points if p[0] >= limite][-MAX_POINTS:]

    @property
    def duree(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return self.points[-1][0] - self.points[0][0]

    def exploitable(self, duree_minimale: float = 2.0) -> bool:
        return len(self.points) >= 3 and self.duree >= duree_minimale

    def pente(self) -> float:
        return pente(self.points)


# ----------------------------------------------------------------------
# Surveillance
# ----------------------------------------------------------------------
class Veilleur:
    """Garde la memoire des echantillons precedents pour un vaisseau donne.

    Toute rupture de continuite -- changement de vaisseau, retour a une
    sauvegarde, changement de corps -- remet les series a zero : melanger deux
    histoires donnerait une pente inventee.
    """

    def __init__(self) -> None:
        self._reference: tuple[str, str, str] | None = None
        self._dernier_ut = 0.0
        self._electrique = _Serie()
        self._periapside = _Serie()

    def reinitialiser(self) -> None:
        self._reference = None
        self._dernier_ut = 0.0
        self._electrique.vider()
        self._periapside.vider()

    # ------------------------------------------------------------------
    def observer(self, t) -> Veille:
        """Met a jour les series et renvoie l'etat de la veille."""
        veille = Veille()

        if not getattr(t, "connected", False) or not getattr(t, "vessel_name", ""):
            self.reinitialiser()
            return veille

        ut = _fini(getattr(t, "ut", 0.0))
        reference = (t.source, t.vessel_name, t.body)

        # Un rechargement de sauvegarde fait reculer l'horloge du jeu : les
        # anciens points n'ont plus rien a voir avec la situation presente.
        if reference != self._reference or ut < self._dernier_ut:
            self._electrique.vider()
            self._periapside.vider()
        self._reference = reference
        self._dernier_ut = ut

        veille.electrique = self._suivre_electrique(t, ut)
        veille.periapside = self._suivre_periapside(t, ut)

        for etat in (veille.electrique, veille.periapside):
            if etat.critique and etat.message:
                veille.alertes.append(etat.message)

        return veille

    # ------------------------------------------------------------------
    def _suivre_electrique(self, t, ut: float) -> ReserveElectrique:
        source = next(
            (r for r in getattr(t, "resources", []) or []
             if getattr(r, "name", "") == "ElectricCharge"),
            None,
        )
        if source is None:
            self._electrique.vider()
            return ReserveElectrique()

        charge = _fini(source.amount)
        maximum = _fini(source.maximum)
        if maximum <= 0:
            self._electrique.vider()
            return ReserveElectrique()

        self._electrique.ajouter(ut, charge)

        etat = ReserveElectrique(
            suivie=True,
            charge=charge,
            maximum=maximum,
            fraction=charge / maximum,
        )

        # La panne a deja eu lieu : une projection n'a plus rien a annoncer,
        # et « reserve stable a 0 % » serait la pire facon de le dire.
        if charge <= 0:
            etat.critique = True
            etat.message = (
                "Batterie vide : plus de contrôle d'attitude ni de "
                "transmission tant qu'elle ne se recharge pas."
            )
            return etat

        if not self._electrique.exploitable():
            etat.message = "Réserve électrique en cours d'observation."
            return etat

        etat.flux = self._electrique.pente()

        # Seuil de bruit : un flux qui ne consomme pas 1 % de la batterie en
        # une heure de jeu ne merite pas d'echeance. Annoncer une date
        # la-dessus serait du bruit deguise en information.
        if abs(etat.flux) < 1e-3 or abs(etat.flux) * 3600 < maximum * 0.01:
            etat.message = (
                f"Réserve stable à {etat.fraction * 100:.0f} % "
                f"({charge:.0f} / {maximum:.0f})."
            )
            return etat

        if etat.flux < 0:
            etat.secondes_restantes = charge / -etat.flux
            etat.critique = etat.secondes_restantes <= SEUIL_CRITIQUE_S
            etat.message = (
                f"Batterie vide dans {duree_lisible(etat.secondes_restantes)} "
                f"au rythme actuel ({_fr(etat.flux)} u/s)."
            )
        elif charge < maximum:
            etat.secondes_plein = (maximum - charge) / etat.flux
            etat.message = (
                f"Recharge en cours (+{_fr(etat.flux)} u/s), pleine dans "
                f"{duree_lisible(etat.secondes_plein)}."
            )
        else:
            etat.message = "Batterie pleine."

        return etat

    # ------------------------------------------------------------------
    def _suivre_periapside(self, t, ut: float) -> Periapside:
        orbite = getattr(t, "orbit", None)
        if orbite is None:
            self._periapside.vider()
            return Periapside()

        atmosphere = _fini(getattr(t, "atmosphere_depth", 0.0))
        altitude = _fini(getattr(t, "altitude", 0.0))
        periapside = _fini(getattr(orbite, "periapsis", 0.0))

        # La surveillance n'a de sens qu'une fois hors de l'air : pendant
        # l'ascension, la periapside est evidemment sous le sol, et le
        # rappeler a chaque seconde noierait les vraies alertes.
        au_sol = t.situation in ("pre_launch", "landed", "splashed", "docked")
        if au_sol or altitude <= atmosphere:
            self._periapside.vider()
            return Periapside()

        self._periapside.ajouter(ut, periapside)

        etat = Periapside(
            surveillee=True,
            altitude=periapside,
            plancher=atmosphere,
        )

        # Une poussee en cours explique la derive : c'est le pilote qui agit,
        # pas une degradation subie. On mesure quand meme, on n'alerte pas --
        # c'est ce qui distingue une desorbitation voulue d'un freinage
        # atmospherique qu'on n'a pas vu venir.
        pousse = _fini(getattr(t, "thrust", 0.0)) > 0.01
        if self._periapside.exploitable():
            etat.derive = self._periapside.pente()

        temps_pe = _fini(getattr(orbite, "time_to_periapsis", 0.0))

        if periapside < 0:
            etat.sous_le_plancher = True
            etat.temps_avant = temps_pe
            etat.critique = not pousse
            etat.message = (
                f"Trajectoire d'impact : la périapside est "
                f"{-periapside / 1000:.0f} km sous le sol, contact dans "
                f"{duree_lisible(temps_pe)}."
            )
            return etat

        if periapside < atmosphere:
            etat.sous_le_plancher = True
            etat.temps_avant = temps_pe
            etat.critique = not pousse
            etat.message = (
                f"L'orbite plonge dans l'atmosphère : périapside à "
                f"{periapside / 1000:.0f} km pour un plafond d'air à "
                f"{atmosphere / 1000:.0f} km. Rentrée dans "
                f"{duree_lisible(temps_pe)}."
            )
            return etat

        # Orbite encore saine, mais qui se degrade : c'est le cas du freinage
        # atmospherique involontaire, ou d'un vaisseau qui rase l'air a chaque
        # passage. La chute se compte en metres par seconde de jeu.
        if etat.derive < -DERIVE_MINIMALE:
            etat.temps_avant = (periapside - atmosphere) / -etat.derive
            if etat.temps_avant <= HORIZON_DERIVE_S:
                etat.critique = not pousse
                etat.message = (
                    f"La périapside descend de {-etat.derive:.0f} m/s : elle "
                    f"passera sous l'atmosphère dans "
                    f"{duree_lisible(etat.temps_avant)}."
                )
                return etat

        etat.message = f"Périapside stable à {periapside / 1000:.0f} km."
        return etat


def duree_lisible(secondes: float) -> str:
    """Duree parlee : « 4 minutes », plutot que « 247 s »."""
    if not math.isfinite(secondes) or secondes < 0:
        return "—"
    if secondes < 90:
        return f"{secondes:.0f} s"
    if secondes < 3600:
        return f"{secondes / 60:.0f} minutes"
    if secondes < 6 * 3600:
        return f"{_fr(secondes / 3600, 1)} h"
    jours = secondes / (6 * 3600)
    return f"{_fr(jours, 1)} jours" if jours < 100 else "très longtemps"


veilleur = Veilleur()
