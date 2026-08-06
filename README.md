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

Double-clique **`demarrer.bat`**. Il attend que Kerbal Space Program soit
lancé, puis ouvre une **fenêtre native** (pas un onglet de navigateur) sur
l'écran secondaire s'il y en a un.

**La fenêtre reste ouverte en permanence.** Elle ne se ferme pas quand tu
quittes KSP : elle affiche « en attente du jeu » et se rebranche seule à la
partie suivante. Un seul lancement couvre donc toutes tes sessions de jeu.

Pour ne plus y penser du tout, `installer-au-demarrage.bat` place un raccourci
dans le démarrage de Windows. Pour annuler, supprimer le raccourci depuis
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`.

Options :

```bash
demarrer.bat --maintenant        REM ouvrir sans attendre KSP (simulateur)
demarrer.bat --fermer-avec-jeu   REM ancien comportement : fermer avec le jeu
```

Lancer `demarrer.bat` une seconde fois ne casse rien : il détecte l'instance
déjà en place et n'y touche pas.

> **Note pour le développement :** le port 8000 appartient à cette fenêtre.
> Tout backend de test doit tourner sur un autre port (`BACKEND_PORT=8010`),
> sinon il vole le port et la fenêtre se retrouve sans serveur.

### Installation, une seule fois

```bash
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Puis renseigne `GEMINI_API_KEY` dans `backend\.env`.

### Développement du dashboard

Rechargement à chaud sur <http://localhost:5173> :

```bash
cd frontend
npm run dev
```

Pour que la fenêtre native voie tes changements, il faut recompiler :

```bash
cd frontend
npm run build
```

## Pages selon la scène de jeu

Le tableau de bord suit **automatiquement** l'endroit où tu te trouves, sans
sélecteur manuel : c'est la scène rapportée par le jeu qui décide.

| Scène | Page |
|---|---|
| `flight` | Vol : attitude, orbite, propulsion, étages, radio |
| `space_center` | Programme, équipage, flotte en vol |
| `tracking_station` | Toute la flotte et sa répartition |
| `editor_vab` / `editor_sph` | Construction (données limitées, voir plus bas) |

La mise en page tient **toujours dans la fenêtre** : aucun défilement de page,
quelle que soit la résolution. La taille de base du texte suit la hauteur de
la fenêtre. Seul le journal radio défile, ce qui est normal pour une
conversation.

**Limite connue :** kRPC ne distingue que ces cinq scènes. Le centre de
recherche, le contrôle de mission et l'administration sont des interfaces
ouvertes *par-dessus* le centre spatial, pas des scènes : impossible de les
détecter. De même, kRPC n'expose aucune API d'éditeur : c'est le mod du jeu
qui pousse le contenu du VAB vers `POST /api/vab`, sans quoi cette page
resterait vide.

## Ce que le tableau de bord surveille pour toi

Cinq mécanismes qui répondent à des pannes réellement vécues, plutôt qu'à des
chiffres qu'il faudrait penser à aller lire.

### Fusée vs mission

Le VAB connaît le Δv de la fusée, le planificateur celui qu'exige le trajet.
Le backend confronte les deux (`mission.py`) et le planificateur affiche le
verdict :

> 3 900 m/s disponibles, 5 088 nécessaires pour Duna — il manque 1 188 m/s.
> La réserve s'épuise à l'étape « Injection Kerbin vers Duna ».

Le cumul étape par étape dit *où* la réserve s'épuise, pas seulement de
combien. Le Δv manquant est aussi traduit en tonnes d'ergols à ajouter sur
l'étage supérieur — une borne basse, qui ignore la masse des réservoirs.

La source est le vaisseau en construction tant que l'éditeur émet, sinon le
vaisseau en vol. Dans ce second cas, l'ascension n'est décomptée que si le
vaisseau est réellement en orbite : à mi-montée, il en a payé une part
inconnue, et le plan complet reste la seule mesure honnête.

### Veille de bord

`telemetry/veille.py` observe la suite des échantillons plutôt qu'un seuil
instantané. Une batterie à 40 % n'est ni bonne ni mauvaise ; ce qui compte est
de savoir si elle se vide, et en combien de temps.

- **Réserve électrique** : flux mesuré par régression sur 30 secondes de jeu,
  puis projection — « batterie vide dans 4 minutes ». Le temps de référence
  est le temps universel du jeu, jamais l'horloge du PC : sous accélération
  temporelle, un flux calculé sur l'horloge murale serait faux d'un facteur
  cent.
- **Périapside** : alerte quand l'orbite passe sous l'atmosphère, et quand
  elle y descend par freinage atmosphérique. Aucune alerte moteur allumé —
  c'est ce qui distingue une désorbitation voulue d'une dégradation subie.

Les alertes critiques remontent dans un bandeau sous la barre supérieure,
visible quelle que soit la scène.

### Rappels de fenêtre de tir

Un bouton « Me le rappeler » sur la fenêtre calculée pose une note sur le
calendrier du jeu (`rappels.py`, persistée dans `backend/donnees/`). Le
bandeau la ressort quand la date approche. Une fenêtre manquée est reportée à
sa prochaine période synodique plutôt que de rester un rappel mort.

### Science non transmise

`science.py` liste les expériences dont les données dorment à bord du vaisseau
actif, avec ce qu'elles valent transmises par radio *et* rapportées au sol —
l'écart est souvent la raison pour laquelle une mission rapporte moins que
prévu. Le panneau ne s'affiche que s'il y a quelque chose à signaler.

Limite : kRPC ne donne accès aux pièces que du vaisseau chargé. Les sondes
lointaines ne sont pas inspectées.

## Mode simulateur

`KSP_MC_SOURCE=auto` (par défaut) : le backend cherche KSP, et s'il ne le
trouve pas il démarre un **simulateur de vol** — vraie dynamique du point
matériel, traînée atmosphérique, largage d'étages, éléments orbitaux calculés
depuis le vecteur d'état. Dès que KSP est lancé, il bascule tout seul sur le
jeu sans qu'on ait à redémarrer quoi que ce soit.

Valeurs possibles : `auto`, `krpc` (jeu uniquement), `sim` (simulateur forcé).

## La radio

Deux interlocuteurs, aux pouvoirs volontairement différents :

- **Le sol** (Kerbal Space Center) voit toute la télémétrie mais ne dispose
  d'**aucun outil**. Il conseille, calcule, alerte. Il lui est structurellement
  impossible de déclencher une action à bord.
- **L'équipage** est le seul à pouvoir agir : pilotage, systèmes de bord,
  science, étagement.

Les commandes irréversibles (`activate_stage`, `deploy_parachutes`) ne partent
jamais sans confirmation explicite du pilote : la conversation se met en pause
et attend.

Le fournisseur de modèle est configurable (`LLM_PROVIDER`). Gemini est actif,
Claude est écrit et prêt. La liste des modèles acceptés par ta clé est
disponible sur `/api/radio/models`.

## Calcul du Δv par étage

kRPC 0.6.0 n'arrive pas à lire le Δv par étage sur KSP 1.12.5 : toutes les
propriétés de `Stage` lèvent une erreur alors que le jeu affiche les chiffres.
Le backend le recalcule donc lui-même, par simulation de la consommation
(`telemetry/deltav.py`).

Validé contre l'affichage du jeu sur un lanceur à propulseurs latéraux :
écart nul sur les deux étages propulsifs principaux, 0,6 % sur le total.
Les coiffes ne sont pas encore modélisées, d'où ~5 % d'écart sur l'étage
supérieur. L'asparagus staging avec conduites de carburant n'est pas géré.

## Sécurité des clés API

Aucune clé n'est écrite dans le code. Le backend les lit depuis `backend/.env`,
et le mod depuis `GameData/AIAssistant/apikey.txt`. Ces deux fichiers sont
ignorés par git. **`backend/.env.example` est versionné : n'y mets jamais de
vraie clé.**

## État d'avancement

- [x] Mod kRPC installé dans KSP 1.12.5
- [x] Couche télémétrie (kRPC + simulateur)
- [x] Dashboard temps réel
- [x] Calcul du Δv par étage
- [x] Radio : sol et équipage, avec exécution de commandes
- [x] Planificateur de mission (fenêtres de tir, transferts, itinéraires)
- [x] Aide à la construction dans le VAB (le mod émet, le backend calcule)
- [x] Aide à la navigation : consignes, manœuvres, circularisation
- [x] Recoupement fusée / mission, veille de bord, rappels de fenêtre
- [ ] Veille et science validées sur un vol réel dans KSP
- [ ] Commandes validées sur un vol réel
- [ ] Radio vocale
- [ ] Pilote automatique
