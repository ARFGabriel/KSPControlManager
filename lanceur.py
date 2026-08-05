"""Lanceur de KSP Mission Control.

Un seul processus qui fait tout :
  - demarre le backend,
  - attend que Kerbal Space Program soit lance,
  - ouvre une vraie fenetre Windows (pas un onglet de navigateur),
  - la referme quand tu quittes le jeu.

Usage :
    lanceur.py             attend que KSP demarre
    lanceur.py --maintenant  ouvre tout de suite (utile avec le simulateur)

La fenetre s'ouvre par defaut sur ton ecran secondaire s'il y en a un, pour
se placer d'emblee a cote du jeu.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE / "backend"))

import psutil  # noqa: E402
import uvicorn  # noqa: E402
import webview  # noqa: E402

from ksp_mc.config import settings  # noqa: E402

PROCESSUS_KSP = {"ksp_x64.exe", "ksp.exe", "ksp_x64"}
URL = f"http://{settings.host}:{settings.port}"

TITRE = "KSP Mission Control"


# ----------------------------------------------------------------------
# Backend
# ----------------------------------------------------------------------
def demarrer_backend() -> uvicorn.Server:
    """Lance uvicorn dans un thread. La fenetre doit rester sur le thread
    principal : c'est une exigence de pywebview sous Windows.

    On renvoie le serveur pour pouvoir l'arreter proprement a la fermeture :
    sans cela, la boucle de telemetrie continue de tourner pendant que
    l'interpreteur se demonte, et lache une trace d'erreur inutile.
    """
    config = uvicorn.Config(
        "ksp_mc.app:app",
        host=settings.host,
        port=settings.port,
        log_level="warning",
    )
    serveur = uvicorn.Server(config)
    threading.Thread(target=serveur.run, daemon=True, name="backend").start()
    return serveur


def attendre_backend(timeout: float = 30.0) -> bool:
    """Attend que le serveur reponde avant d'ouvrir la fenetre, sinon on
    afficherait une page d'erreur au demarrage."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            with urllib.request.urlopen(f"{URL}/api/health", timeout=2):
                return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.4)
    return False


# ----------------------------------------------------------------------
# Detection du jeu
# ----------------------------------------------------------------------
def ksp_tourne() -> bool:
    for proc in psutil.process_iter(["name"]):
        nom = (proc.info.get("name") or "").lower()
        if nom in PROCESSUS_KSP:
            return True
    return False


def attendre_ksp() -> None:
    print("  En attente du lancement de Kerbal Space Program...")
    print("  (Ctrl+C pour abandonner)")
    while not ksp_tourne():
        time.sleep(2.0)
    print("  KSP detecte.")


def surveiller_fermeture(fenetre) -> None:
    """Ferme la fenetre quand le jeu se termine.

    Deux precautions :

    - on n'arme la surveillance qu'apres avoir VU le jeu tourner. Sans cela,
      un demarrage avec --maintenant (jeu pas encore lance) refermait la
      fenetre six secondes plus tard, le veilleur prenant l'absence initiale
      pour une fermeture.
    - on exige plusieurs absences consecutives : KSP disparait brievement de
      la liste des processus lors de certains changements de scene lourds.
    """
    while not ksp_tourne():
        time.sleep(2.0)

    absences = 0
    while True:
        time.sleep(2.0)
        if ksp_tourne():
            absences = 0
            continue
        absences += 1
        if absences >= 3:  # environ 6 secondes d'absence continue
            print("  KSP s'est ferme, fermeture du centre de controle.")
            try:
                fenetre.destroy()
            except Exception:
                pass
            return


# ----------------------------------------------------------------------
# Fenetre
# ----------------------------------------------------------------------
def choisir_ecran():
    """Renvoie l'ecran secondaire s'il existe, sinon None (ecran principal).

    Le tableau de bord est concu pour vivre a cote du jeu, pas devant.
    """
    try:
        ecrans = webview.screens
    except Exception:
        return None
    if not ecrans or len(ecrans) < 2:
        return None
    # Le premier ecran renvoye par pywebview est le principal.
    return ecrans[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=TITRE)
    parser.add_argument(
        "--maintenant",
        action="store_true",
        help="ouvrir sans attendre que KSP soit lance",
    )
    args = parser.parse_args()

    print()
    print("  ================================================")
    print("    KSP MISSION CONTROL")
    print("  ================================================")
    print()

    serveur = demarrer_backend()
    if not attendre_backend():
        print("  Le backend n'a pas demarre. Verifie backend/.env et les")
        print("  dependances (pip install -r backend/requirements.txt).")
        return 1
    print(f"  Backend pret sur {URL}")

    if not args.maintenant and not ksp_tourne():
        attendre_ksp()

    ecran = choisir_ecran()
    if ecran is not None:
        largeur = int(ecran.width * 0.9)
        hauteur = int(ecran.height * 0.9)
        print(f"  Ouverture sur l'ecran secondaire ({ecran.width}x{ecran.height}).")
    else:
        largeur, hauteur = 1600, 900
        print("  Un seul ecran detecte, ouverture en fenetre.")

    fenetre = webview.create_window(
        TITRE,
        URL,
        width=largeur,
        height=hauteur,
        resizable=True,
        min_size=(900, 600),
        background_color="#07090c",
        screen=ecran,
    )

    threading.Thread(
        target=surveiller_fermeture, args=(fenetre,), daemon=True, name="veille-ksp"
    ).start()

    # Bloque jusqu'a la fermeture de la fenetre.
    webview.start()

    # Arret propre du backend : on laisse la boucle de telemetrie se terminer
    # avant de rendre la main.
    serveur.should_exit = True
    time.sleep(0.6)
    print("  Centre de controle ferme.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Interrompu.")
        sys.exit(0)
