"""Contrat commun a toutes les sources de telemetrie.

L'interet d'avoir une abstraction ici est concret : le dashboard se developpe
et se teste entierement contre le simulateur, sans lancer KSP. Le jour ou on
branche le vrai jeu, rien ne change en aval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .schema import Telemetry


class TelemetrySource(ABC):
    """Source d'echantillons de telemetrie."""

    name: str = "none"

    @abstractmethod
    def connect(self) -> None:
        """Etablit la liaison. Doit lever une exception si elle echoue."""

    @abstractmethod
    def sample(self) -> Telemetry:
        """Renvoie l'etat courant. Ne doit jamais lever : en cas de probleme,
        renvoyer un Telemetry avec connected=False et le champ error rempli."""

    @abstractmethod
    def close(self) -> None:
        """Libere les ressources (streams, socket)."""


def safe(fn, default=None):
    """Lit une valeur kRPC en absorbant les erreurs.

    Beaucoup de proprietes kRPC levent legitimement selon le contexte : le
    delta-v n'existe pas sur un kerbal en EVA, l'orbite n'a pas de periapsis
    utile au sol, un etage de decouplage n'a pas de TWR. On veut un dashboard
    qui affiche des tirets, pas un backend qui tombe.
    """
    try:
        value = fn()
        return default if value is None else value
    except Exception:
        return default
