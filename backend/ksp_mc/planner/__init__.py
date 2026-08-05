"""Planification de mission : budgets delta-v, transferts, fenetres de tir."""

from .bodies import Body, BodyCatalog, load
from .transfer import Transfer, calculer

__all__ = ["Body", "BodyCatalog", "load", "Transfer", "calculer", "catalogue"]

_catalogue: BodyCatalog | None = None


def catalogue(conn=None, forcer: bool = False) -> BodyCatalog:
    """Catalogue courant, relu depuis le jeu des qu'une connexion existe.

    On garde le resultat en memoire : ces donnees ne changent pas en cours de
    partie, et les relire demanderait une dizaine d'appels par corps.
    """
    global _catalogue

    if _catalogue is None or forcer:
        _catalogue = load(conn)
    elif conn is not None and _catalogue.source != "jeu":
        # Le jeu vient de se connecter : on remplace les valeurs approximatives.
        _catalogue = load(conn)

    return _catalogue
