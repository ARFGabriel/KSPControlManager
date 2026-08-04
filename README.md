# KSP Mission Control

Un centre de contrôle externe pour Kerbal Space Program 1.12.5 : planification
de mission, aide à la construction, télémétrie en direct sur un deuxième écran,
radio avec le sol et l'équipage, et pilotage automatique.

## Architecture

```
KSP (mod kRPC)  ──réseau──►  Backend Python  ──WebSocket──►  Dashboard React
                             (télémétrie, calculs
                              orbitaux, radio, pilote)
```

Le choix structurant : toute l'intelligence vit **hors du jeu**, en Python.
Le mod dans `mod/` ne sert qu'à l'affichage in-game. C'est bien plus simple à
développer et à déboguer qu'un mod Unity, et ça permet de travailler sans
lancer KSP grâce au simulateur intégré.

## Arborescence

| Dossier | Rôle |
|---|---|
| `backend/` | Serveur Python : télémétrie, API REST, flux WebSocket |
| `backend/ksp_mc/telemetry/` | Sources de données : `krpc_source` (le jeu) et `sim_source` (simulateur) |
| `frontend/` | Dashboard React + TypeScript |
| `mod/` | Le mod C# in-game (fenêtre d'assistance dans le VAB) |

## Démarrage

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe run.py
```

Le serveur écoute sur <http://127.0.0.1:8000>.

### 2. Dashboard

En développement (rechargement à chaud) :

```bash
cd frontend
npm install
npm run dev
```

puis <http://localhost:5173>.

Pour l'usage normal, on compile une fois et le backend sert tout :

```bash
cd frontend
npm run build
```

puis simplement <http://127.0.0.1:8000>.

## Mode simulateur

`KSP_MC_SOURCE=auto` (par défaut) : le backend cherche KSP, et s'il ne le
trouve pas il démarre un **simulateur de vol** — vraie dynamique du point
matériel, traînée atmosphérique, largage d'étages, éléments orbitaux calculés
depuis le vecteur d'état. Dès que KSP est lancé, il bascule tout seul sur le
jeu sans qu'on ait à redémarrer quoi que ce soit.

Valeurs possibles : `auto`, `krpc` (jeu uniquement), `sim` (simulateur forcé).

## Sécurité des clés API

Aucune clé n'est écrite dans le code. Le backend les lit depuis `backend/.env`,
et le mod depuis `GameData/AIAssistant/apikey.txt`. Ces deux fichiers sont
ignorés par git.

## État d'avancement

- [x] Couche télémétrie (kRPC + simulateur)
- [x] Dashboard temps réel V1
- [ ] Mod kRPC installé dans KSP
- [ ] Radio : sol et équipage, avec exécution de commandes
- [ ] Planificateur de mission (fenêtres de tir, transferts)
- [ ] Aide à la construction dans le VAB
- [ ] Pilote automatique
