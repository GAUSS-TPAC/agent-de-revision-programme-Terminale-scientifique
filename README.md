# Assistant de révision — Terminale C (MINESEC Cameroun)

![Python](https://img.shields.io/badge/Python-3776ab)
![Gradio](https://img.shields.io/badge/UI-Gradio-f97316)
![Gemini](https://img.shields.io/badge/AI-Gemini-4285f4)

Un assistant de révision par IA pour les élèves de **Terminale C** du programme camerounais (MINESEC). Interface web Gradio, propulsée par Gemini : l'élève choisit une matière et un chapitre, révise, pose des questions à un tuteur, et s'entraîne.

## Fonctionnalités

- Couvre les matières de Terminale C : mathématiques, physique, chimie, SVT, informatique, anglais, philosophie.
- **Tuteur conversationnel** avec historique limité (coût et contexte maîtrisés).
- Rendu **LaTeX** des formules (`$...$` et `$$...$$`).
- **Cadrage sur le programme officiel** : déposez le texte du programme MINESEC dans `programmes/<matiere>.txt` et il est injecté dans les prompts pour que l'IA reste dans le programme.
- Robuste aux surcharges de l'API : plusieurs essais et un **modèle de secours** optionnel.

## Démarrage

```bash
git clone https://github.com/GAUSS-TPAC/agent-de-revision-programme-Terminale-scientifique.git
cd agent-de-revision-programme-Terminale-scientifique
pip install -r requirements.txt
export GEMINI_API_KEY="votre_cle"     # Windows : set GEMINI_API_KEY=...
python app.py
```

Gradio ouvre l'interface dans le navigateur.

## Configuration (variables d'environnement)

| Variable | Rôle | Défaut |
|---|---|---|
| `GEMINI_API_KEY` | Clé API Gemini (obligatoire) | — |
| `GEMINI_MODEL` | Modèle principal | `gemini-3.8-flash` |
| `GEMINI_MODEL_SECOURS` | Modèle de repli si surcharge | (vide) |

Déployable sur Render (définir les variables d'environnement dans le service).

## Programme officiel (recommandé)

Créez un dossier `programmes/` à côté de `app.py`, un `.txt` par matière :
`mathematiques.txt`, `physique.txt`, `chimie.txt`, `svt.txt`, `informatique.txt`, `anglais.txt`, `philosophie.txt`. Présent, il recentre l'IA sur le programme camerounais.

## Licence

MIT.
