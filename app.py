# ==============================================================================
# ASSISTANT DE RÉVISION — TERMINALE C (Programme camerounais, MINESEC)
# ==============================================================================
# Installation :  pip install -r requirements.txt
# Clé API      :  PowerShell : $env:GEMINI_API_KEY="ta_cle"   |   cmd : set GEMINI_API_KEY=ta_cle
#                 Linux/macOS : export GEMINI_API_KEY="ta_cle"   |   Render : variable d'environnement
# Lancement    :  python app.py
#
# Programme officiel (optionnel mais fortement recommandé) :
#   Place le texte du programme MINESEC de chaque matière dans un dossier
#   "programmes/" à côté de ce fichier, un fichier .txt par matière :
#   programmes/mathematiques.txt, programmes/physique.txt, programmes/chimie.txt,
#   programmes/svt.txt, programmes/informatique.txt, programmes/anglais.txt,
#   programmes/philosophie.txt
#   S'il est présent, il est injecté dans les prompts pour que l'IA reste
#   strictement dans le programme camerounais.
# ==============================================================================

import os
import random
import sys
import time
import tempfile
import unicodedata
from datetime import date, datetime
from pathlib import Path

import gradio as gr
import pandas as pd
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================

# Modèle modifiable sans toucher au code : variable d'environnement GEMINI_MODEL
MODELE = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
# Modèle de secours (optionnel) utilisé si le principal reste surchargé : GEMINI_MODEL_SECOURS
MODELE_SECOURS = os.environ.get("GEMINI_MODEL_SECOURS", "").strip()
NB_ESSAIS = 4                         # essais par modèle en cas de surcharge (503, 429, 500)
MAX_MESSAGES_HISTORIQUE = 20          # limite le coût et la taille du contexte du tuteur
DOSSIER_PROGRAMMES = Path(__file__).parent / "programmes"

if not os.environ.get("GEMINI_API_KEY"):
    sys.exit("❌ Variable d'environnement GEMINI_API_KEY absente. Définis-la avant de lancer l'application.")

client = genai.Client()

LATEX = [
    {"left": "$$", "right": "$$", "display": True},
    {"left": "$", "right": "$", "display": False},
]

# Chapitres indicatifs de Terminale C — À VÉRIFIER ET COMPLÉTER avec le programme
# officiel du MINESEC. L'élève peut aussi taper un chapitre absent de la liste.
CHAPITRES = {
    "Mathématiques": [
        "Nombres complexes", "Arithmétique", "Limites et continuité", "Dérivation",
        "Fonctions logarithme et exponentielle", "Primitives et calcul intégral",
        "Équations différentielles", "Suites numériques", "Probabilités", "Statistiques",
        "Isométries et similitudes planes", "Coniques", "Géométrie dans l'espace",
    ],
    "Physique": [
        "Cinématique et lois de Newton", "Mouvements dans les champs uniformes",
        "Champ de gravitation", "Champ électrique", "Champ magnétique et induction",
        "Oscillateurs mécaniques", "Oscillations électriques", "Ondes et interférences lumineuses",
        "Effet photoélectrique", "Radioactivité et réactions nucléaires",
    ],
    "Chimie": [
        "Alcools", "Amines", "Acides carboxyliques et dérivés", "Acides α-aminés",
        "Cinétique chimique", "Acides et bases, pH", "Dosages acido-basiques",
    ],
    "SVT": [
        "Génétique et hérédité", "Immunologie", "Reproduction humaine",
        "Système nerveux", "Régulation de la glycémie",
    ],
    "Philosophie": [
        "La conscience", "La liberté", "Le travail", "La science", "L'État et la politique",
    ],
    "Informatique": [
        "Algorithmique", "Programmation", "Bases de données", "Réseaux informatiques",
    ],
    "Anglais": [
        "Reading comprehension", "Essay writing", "Grammar: tenses", "Vocabulary by themes",
    ],
}
MATIERES = list(CHAPITRES.keys())
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# ==============================================================================
# 2. SCHÉMAS DE SORTIE STRUCTURÉE
# ==============================================================================

class Exercice(BaseModel):
    enonce: str = Field(description="Énoncé complet de l'exercice, formules en LaTeX entre $...$")
    solution_detaillee: str = Field(description="Corrigé complet, étape par étape, formules en LaTeX")
    bareme: str = Field(description="Barème sur 20 points, détaillé question par question")
    notions_evaluees: list[str] = Field(description="Notions du cours évaluées par l'exercice")


class Seance(BaseModel):
    jour: str = Field(description="Lundi, Mardi, Mercredi, Jeudi, Vendredi, Samedi ou Dimanche")
    debut: str = Field(description="Heure de début, format HH:MM")
    fin: str = Field(description="Heure de fin, format HH:MM")
    matiere: str
    activite: str = Field(description="Activité précise : chapitre à revoir, exercices, sujet de bac...")


class Planning(BaseModel):
    seances: list[Seance]
    conseils: str = Field(description="Conseils de méthode, gestion du stress et du sommeil, en Markdown")

# ==============================================================================
# 3. PROMPTS
# ==============================================================================

def charger_programme(matiere: str) -> str:
    """Renvoie le texte du programme officiel de la matière s'il a été fourni."""
    nom = unicodedata.normalize("NFKD", matiere).encode("ascii", "ignore").decode().lower()
    fichier = DOSSIER_PROGRAMMES / f"{nom}.txt"
    if fichier.exists():
        return fichier.read_text(encoding="utf-8")[:15000]
    return ""


def cadre_programme(matiere: str) -> str:
    programme = charger_programme(matiere)
    if programme:
        return (
            "Voici l'extrait du programme officiel MINESEC de cette matière. "
            "Reste STRICTEMENT dans ce cadre :\n<<<\n" + programme + "\n>>>"
        )
    return (
        "Respecte le programme officiel camerounais de Terminale C (MINESEC). "
        "Si le chapitre demandé ne figure pas à ce programme, signale-le clairement à l'élève."
    )


def systeme_enseignant(matiere: str) -> str:
    langue = (
        "Answer in English, with simple explanations; you may add a short French gloss for difficult words."
        if matiere == "Anglais" else "Réponds en français."
    )
    return f"""
Tu es un enseignant camerounais expérimenté de Terminale C qui prépare ses élèves au Baccalauréat C
(Office du Baccalauréat du Cameroun), selon le programme officiel du MINESEC.
- Sois bienveillant, patient et encourageant, mais rigoureux et exact : n'invente jamais de formule ou de résultat.
- Adapte tes exemples au contexte camerounais quand c'est pertinent (FCFA, villes, situations du quotidien).
- Explique pas à pas en décomposant les notions complexes.
- Écris toutes les formules en LaTeX : $...$ dans le texte et $$...$$ pour les formules isolées.
- Matière actuelle : {matiere}. {langue}
"""


SYSTEME_PLANIFICATEUR = """
Tu es un conseiller pédagogique camerounais expert en organisation des révisions pour le Baccalauréat C.
Au Bac C, les matières scientifiques (Mathématiques, Physique, Chimie) ont les plus forts coefficients.
Tu conçois des plannings réalistes, équilibrés, qui respectent STRICTEMENT les disponibilités de l'élève
(aucune séance hors de ses créneaux ni pendant ses jours de repos), avec des pauses.
"""

# ==============================================================================
# 4. APPELS À GEMINI
# ==============================================================================

def config(system: str, temperature: float = 0.4, schema=None) -> types.GenerateContentConfig:
    kwargs = {"system_instruction": system, "temperature": temperature}
    if schema is not None:
        kwargs["response_mime_type"] = "application/json"
        kwargs["response_schema"] = schema
    return types.GenerateContentConfig(**kwargs)


def message_erreur(e: Exception) -> str:
    """Message clair selon le type d'erreur (au lieu d'un « réessaie » trompeur)."""
    detail = str(e)
    if "404" in detail or "NOT_FOUND" in detail:
        return (f"⚠️ Le modèle « {MODELE} » n'est pas disponible pour ta clé API. "
                "Change de modèle avec la variable d'environnement GEMINI_MODEL.\n\n"
                f"Détail : {detail}")
    if "401" in detail or "403" in detail or "API_KEY" in detail.upper():
        return f"⚠️ Clé API invalide ou non autorisée. Vérifie GEMINI_API_KEY.\n\nDétail : {detail}"
    if "503" in detail or "UNAVAILABLE" in detail or "high demand" in detail:
        return ("⚠️ Les serveurs de Google sont surchargés en ce moment (l'app a déjà réessayé "
                "plusieurs fois). Patiente une minute puis relance.")
    if "429" in detail or "RESOURCE_EXHAUSTED" in detail:
        return "⚠️ Quota d'utilisation de l'API atteint. Patiente quelques minutes puis réessaie."
    return f"⚠️ Le service IA est momentanément indisponible ({detail}). Réessaie dans un instant."


def erreur_temporaire(e: Exception) -> bool:
    """Vrai pour les erreurs passagères qui valent la peine d'un nouvel essai."""
    d = str(e)
    return any(c in d for c in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL", "high demand"))


def modeles_a_essayer() -> list[str]:
    return [MODELE] + ([MODELE_SECOURS] if MODELE_SECOURS and MODELE_SECOURS != MODELE else [])


def avec_reessais(fonction):
    """Appelle fonction(modele) en réessayant (attente 2 s, 4 s, 8 s…) sur les erreurs passagères,
    puis bascule sur le modèle de secours s'il est défini."""
    derniere_erreur = None
    for modele in modeles_a_essayer():
        for essai in range(NB_ESSAIS):
            try:
                return fonction(modele)
            except Exception as e:
                derniere_erreur = e
                if not erreur_temporaire(e):
                    raise
                if essai < NB_ESSAIS - 1:
                    time.sleep(2 ** (essai + 1) + random.random())
    raise derniere_erreur


def flux_gemini(system: str, contents, temperature: float = 0.4):
    """Générateur : renvoie le texte cumulé au fur et à mesure (streaming).
    Réessaie automatiquement si le serveur est surchargé AVANT le premier mot reçu."""
    texte = ""
    derniere_erreur = None
    for modele in modeles_a_essayer():
        for essai in range(NB_ESSAIS):
            try:
                for morceau in client.models.generate_content_stream(
                    model=modele, contents=contents, config=config(system, temperature)
                ):
                    if morceau.text:
                        texte += morceau.text
                        yield texte
                if not texte:
                    yield "Je n'ai pas pu produire de réponse. Reformule ta demande et réessaie."
                return
            except Exception as e:
                derniere_erreur = e
                # Si du texte est déjà affiché, ou si l'erreur n'est pas passagère : on s'arrête.
                if texte or not erreur_temporaire(e):
                    yield texte + "\n\n" + message_erreur(e)
                    return
                if essai < NB_ESSAIS - 1:
                    yield f"⏳ Serveurs IA très sollicités, nouvel essai ({essai + 2}/{NB_ESSAIS})…"
                    time.sleep(2 ** (essai + 1) + random.random())
    yield message_erreur(derniere_erreur)


def appel_structure(system: str, prompt: str, schema, temperature: float = 0.5):
    """Appel non streamé avec sortie JSON validée par Pydantic (avec réessais automatiques)."""
    def appel(modele):
        r = client.models.generate_content(
            model=modele, contents=prompt, config=config(system, temperature, schema)
        )
        if r.parsed is not None:
            return r.parsed
        if not r.text:
            raise ValueError("réponse vide")
        return schema.model_validate_json(r.text)
    return avec_reessais(appel)


def en_contents(messages: list[dict]) -> list[types.Content]:
    """Convertit l'historique stocké (dicts simples) au format attendu par Gemini."""
    return [
        types.Content(role=m["role"], parts=[types.Part(text=m["text"])])
        for m in messages
    ]

# ==============================================================================
# 5. LOGIQUE — COURS, EXERCICE, CORRECTION, TUTEUR
# ==============================================================================

def changer_matiere(matiere):
    return gr.Dropdown(choices=CHAPITRES.get(matiere, []), value=None)


def reinitialiser_session():
    """Nouveau cours : on efface l'exercice, la correction et la conversation."""
    return "", None, "", "", "", [], []


def generer_cours(matiere, chapitre):
    chapitre = (chapitre or "").strip()
    if not chapitre:
        yield "Choisis ou écris le chapitre à réviser.", ""
        return
    prompt = f"""
{cadre_programme(matiere)}

Matière : {matiere}
Chapitre : {chapitre}

Rédige un résumé de cours structuré pour un élève de Terminale C qui prépare le Bac :
1. Les prérequis à maîtriser.
2. Les définitions et propriétés/théorèmes essentiels (avec leurs conditions d'application).
3. Les formules importantes et méthodes types, chacune illustrée par un court exemple résolu.
4. Les erreurs fréquentes au Bac sur ce chapitre.
Ne propose PAS d'exercice : il sera généré séparément.
Termine par une courte phrase d'encouragement.
"""
    texte = ""
    for texte in flux_gemini(systeme_enseignant(matiere), prompt):
        yield texte, ""
    # le cours final est mémorisé pour l'exercice et le tuteur (sauf si c'est un message d'erreur)
    yield texte, ("" if texte.startswith(("⚠️", "⏳")) else texte)


def generer_exercice(matiere, chapitre, difficulte, cours):
    vide = ("", "")
    if not cours:
        return ("⚠️ Génère d'abord le cours du chapitre.", None, *vide)
    prompt = f"""
{cadre_programme(matiere)}

Matière : {matiere} — Chapitre : {chapitre} — Niveau : {difficulte}

Voici le cours que l'élève vient d'étudier :
<<<
{cours}
>>>

Crée UN exercice d'application de type Baccalauréat C camerounais, au niveau « {difficulte} »,
qui vérifie que l'élève a réellement assimilé ce cours (pas une simple application de formule si le niveau
est intermédiaire ou type Bac). Fournis l'énoncé, le corrigé détaillé, un barème sur 20 et les notions évaluées.
"""
    try:
        ex = appel_structure(systeme_enseignant(matiere), prompt, Exercice)
    except Exception as e:
        return (message_erreur(e), None, *vide)

    affichage = (
        f"### 📝 Exercice — niveau {difficulte.lower()}\n\n{ex.enonce}\n\n"
        f"*Notions évaluées : {', '.join(ex.notions_evaluees)}*"
    )
    return affichage, ex.model_dump(), *vide


def corriger_reponse(matiere, reponse, exercice):
    if not exercice:
        yield "⚠️ Génère d'abord un exercice."
        return
    if not (reponse or "").strip():
        yield "Écris ta réponse (même partielle) avant de demander la correction."
        return
    prompt = f"""
Énoncé :
{exercice['enonce']}

Corrigé officiel :
{exercice['solution_detaillee']}

Barème :
{exercice['bareme']}

Réponse de l'élève :
<<<
{reponse}
>>>

Corrige la réponse de l'élève comme un correcteur du Bac, sans complaisance mais avec bienveillance :
1. Une note sur 20 justifiée selon le barème (en gras en première ligne).
2. Ce qui est juste.
3. Chaque erreur ou oubli, expliqué, avec la démarche correcte.
4. Un verdict : notion assimilée, partiellement assimilée ou à retravailler, et quoi revoir en priorité.
Si la réponse est incomplète, note uniquement ce qui a été fait.
"""
    yield from flux_gemini(systeme_enseignant(matiere), prompt, temperature=0.2)


def afficher_solution(exercice):
    if not exercice:
        return "⚠️ Aucun exercice en cours."
    return (
        "### ✅ Corrigé\n\n" + exercice["solution_detaillee"]
        + "\n\n#### Barème\n\n" + exercice["bareme"]
    )


def discuter(matiere, question, chat, memoire, cours, exercice):
    """Tuteur avec mémoire : il voit le cours, l'exercice et toute la conversation."""
    question = (question or "").strip()
    chat = list(chat or [])
    memoire = list(memoire or [])
    if not question:
        yield chat, memoire, ""
        return

    contexte = f"Matière : {matiere}.\nCours que l'élève étudie :\n{cours or '(aucun cours généré pour l’instant)'}"
    if exercice:
        contexte += (
            f"\n\nExercice en cours :\n{exercice['enonce']}\n\n"
            f"Corrigé (ne le donne pas d'emblée : guide l'élève par indices, "
            f"sauf s'il demande explicitement la solution) :\n{exercice['solution_detaillee']}"
        )
    contents = en_contents(
        [{"role": "user", "text": contexte},
         {"role": "model", "text": "Compris, j'accompagne l'élève sur ce cours et cet exercice."}]
        + memoire[-MAX_MESSAGES_HISTORIQUE:]
        + [{"role": "user", "text": question}]
    )

    chat += [{"role": "user", "content": question}, {"role": "assistant", "content": ""}]
    reponse = ""
    for reponse in flux_gemini(systeme_enseignant(matiere), contents):
        chat[-1] = {"role": "assistant", "content": reponse}
        yield chat, memoire, ""

    memoire += [{"role": "user", "text": question}, {"role": "model", "text": reponse}]
    yield chat, memoire, ""

# ==============================================================================
# 6. LOGIQUE — EMPLOI DU TEMPS
# ==============================================================================

def concevoir_emploi_du_temps(creneaux_semaine, creneaux_weekend, jours_repos,
                              date_examen, difficiles, faciles, objectifs):
    sans_resultat = (None, None, None)
    if not (creneaux_semaine or "").strip() and not (creneaux_weekend or "").strip():
        return ("⚠️ Indique au moins tes créneaux libres en semaine ou le week-end.", *sans_resultat)

    info_examen = "Date de l'examen non précisée."
    if (date_examen or "").strip():
        try:
            d = datetime.strptime(date_examen.strip(), "%d/%m/%Y").date()
            jours_restants = (d - date.today()).days
            info_examen = f"Examen le {date_examen} : il reste {jours_restants} jours."
        except ValueError:
            return ("⚠️ Date invalide : utilise le format JJ/MM/AAAA.", *sans_resultat)

    prompt = f"""
Conçois le planning de révision d'UNE semaine type pour un élève de Terminale C (Cameroun).
- Créneaux libres en semaine : {creneaux_semaine or 'aucun'}
- Créneaux libres le week-end : {creneaux_weekend or 'aucun'}
- Jours de repos (aucune séance) : {', '.join(jours_repos) if jours_repos else 'aucun'}
- {info_examen}
- Matières difficiles à renforcer : {', '.join(difficiles) if difficiles else 'non précisé'}
- Matières bien maîtrisées : {', '.join(faciles) if faciles else 'non précisé'}
- Objectifs : {objectifs or 'non précisé'}

Règles :
1. Plus de temps et les créneaux de meilleure concentration pour les matières difficiles et à fort coefficient.
2. Séances de 45 à 90 minutes, avec des pauses ; garde un temps d'entretien pour les matières maîtrisées.
3. Si l'examen approche (moins de 60 jours), privilégie les sujets de Bac et annales.
4. Activité précise pour chaque séance (chapitre, type d'exercice, sujet de bac...).
"""
    try:
        planning = appel_structure(SYSTEME_PLANIFICATEUR, prompt, Planning)
    except Exception as e:
        return (message_erreur(e), *sans_resultat)

    df = pd.DataFrame([s.model_dump() for s in planning.seances])
    if df.empty:
        return ("⚠️ Le planning généré est vide. Précise davantage tes créneaux.", *sans_resultat)
    ordre = {j.lower(): i for i, j in enumerate(JOURS)}
    df["_ordre"] = df["jour"].str.strip().str.lower().map(ordre).fillna(99)
    df = df.sort_values(["_ordre", "debut"]).drop(columns="_ordre")
    df.columns = ["Jour", "Début", "Fin", "Matière", "Activité"]

    chemin_csv = Path(tempfile.gettempdir()) / "planning_revision_terminale_c.csv"
    df.to_csv(chemin_csv, index=False, encoding="utf-8-sig")  # utf-8-sig : accents OK dans Excel

    return "", df, "### 💡 Conseils\n\n" + planning.conseils, str(chemin_csv)

# ==============================================================================
# 7. INTERFACE GRADIO
# ==============================================================================

theme_custom = gr.themes.Soft(primary_hue="indigo", secondary_hue="blue")

with gr.Blocks(title="Assistant Révision Terminale C") as app:

    # États de session (propres à chaque élève connecté)
    cours_state = gr.State("")
    exercice_state = gr.State(None)
    memoire_state = gr.State([])

    gr.Markdown(
        """
        # 🎓 Assistant de Révision — Terminale C
        Révise selon le programme camerounais, entraîne-toi sur des exercices type Bac corrigés,
        pose tes questions à ton tuteur et organise ta semaine.
        > ⚠️ Contenu généré par IA : vérifie toujours avec ton cours et ton enseignant.
        """
    )

    with gr.Tabs():

        # --- ONGLET 1 : COURS, EXERCICE, CORRECTION, TUTEUR ---
        with gr.Tab("📖 Cours & Exercices"):
            gr.Markdown("### 1. Choisis ta matière et ton chapitre")
            with gr.Row():
                matiere_select = gr.Dropdown(choices=MATIERES, value="Mathématiques", label="Matière")
                chapitre_select = gr.Dropdown(
                    choices=CHAPITRES["Mathématiques"], value=None, allow_custom_value=True,
                    label="Chapitre (choisis dans la liste ou écris-le)",
                )
            btn_cours = gr.Button("📚 Générer le résumé du cours", variant="primary")
            output_cours = gr.Markdown(latex_delimiters=LATEX)

            gr.Markdown("---\n### 2. Vérifie que tu as compris")
            with gr.Row():
                difficulte = gr.Radio(
                    ["Application directe", "Intermédiaire", "Type Bac"],
                    value="Intermédiaire", label="Niveau de l'exercice",
                )
                btn_exercice = gr.Button("📝 Générer un exercice", variant="primary")
            output_exercice = gr.Markdown(latex_delimiters=LATEX)
            reponse_eleve = gr.Textbox(
                lines=6, label="Ta réponse",
                placeholder="Rédige ta démarche et tes résultats ici, comme sur ta copie…",
            )
            with gr.Row():
                btn_corriger = gr.Button("✅ Corriger ma réponse", variant="primary")
                btn_solution = gr.Button("👀 Voir le corrigé")
            output_correction = gr.Markdown(latex_delimiters=LATEX)

            gr.Markdown("---\n### 3. 💬 Une question ou un blocage ? Demande à ton tuteur")
            chatbot = gr.Chatbot(label="Ton tuteur IA", latex_delimiters=LATEX, height=420)
            with gr.Row():
                input_question = gr.Textbox(
                    placeholder="Ex : Je ne comprends pas la question 2, peux-tu me donner un indice ?",
                    label="Ta question", scale=5,
                )
                btn_poser = gr.Button("Envoyer", scale=1)

            # Événements
            matiere_select.change(changer_matiere, matiere_select, chapitre_select)

            btn_cours.click(
                reinitialiser_session,
                outputs=[output_exercice, exercice_state, reponse_eleve,
                         output_correction, cours_state, memoire_state, chatbot],
            ).then(
                generer_cours, [matiere_select, chapitre_select], [output_cours, cours_state],
            )

            btn_exercice.click(
                generer_exercice,
                [matiere_select, chapitre_select, difficulte, cours_state],
                [output_exercice, exercice_state, reponse_eleve, output_correction],
            )
            btn_corriger.click(
                corriger_reponse, [matiere_select, reponse_eleve, exercice_state], output_correction,
            )
            btn_solution.click(afficher_solution, exercice_state, output_correction)

            entrees_chat = [matiere_select, input_question, chatbot, memoire_state, cours_state, exercice_state]
            sorties_chat = [chatbot, memoire_state, input_question]
            btn_poser.click(discuter, entrees_chat, sorties_chat)
            input_question.submit(discuter, entrees_chat, sorties_chat)

        # --- ONGLET 2 : EMPLOI DU TEMPS ---
        with gr.Tab("📅 Emploi du Temps"):
            gr.Markdown("### Organise ta semaine de révision")
            with gr.Row():
                with gr.Column():
                    input_semaine = gr.Textbox(
                        label="Créneaux libres en semaine", lines=2,
                        placeholder="Ex : 17h-21h du lundi au vendredi, sauf mercredi 15h-21h",
                    )
                    input_weekend = gr.Textbox(
                        label="Créneaux libres le week-end", lines=2,
                        placeholder="Ex : samedi 8h-12h et 15h-19h, dimanche 14h-18h",
                    )
                    input_repos = gr.CheckboxGroup(JOURS, label="Jours de repos (aucune révision)")
                    input_date = gr.Textbox(label="Date de l'examen (JJ/MM/AAAA)", placeholder="Ex : 10/06/2027")
                with gr.Column():
                    input_difficiles = gr.CheckboxGroup(MATIERES, label="Matières difficiles à renforcer")
                    input_faciles = gr.CheckboxGroup(MATIERES, label="Matières bien maîtrisées")
                    input_objectifs = gr.Textbox(
                        label="Objectifs particuliers", lines=3,
                        placeholder="Ex : préparer le bac blanc de février, finir les complexes cette semaine",
                    )

            btn_planning = gr.Button("🗓️ Générer mon emploi du temps", variant="primary")
            message_planning = gr.Markdown()
            tableau_planning = gr.Dataframe(label="Ton planning de la semaine", interactive=False, wrap=True)
            conseils_planning = gr.Markdown()
            fichier_planning = gr.File(label="Télécharger le planning (CSV, ouvrable dans Excel)")

            btn_planning.click(
                concevoir_emploi_du_temps,
                [input_semaine, input_weekend, input_repos, input_date,
                 input_difficiles, input_faciles, input_objectifs],
                [message_planning, tableau_planning, conseils_planning, fichier_planning],
            )

# ==============================================================================
# 8. LANCEMENT
# ==============================================================================
if __name__ == "__main__":
    # share=True crée un lien public : toute personne qui l'a consomme TON quota d'API.
    # Ne l'active que pour une démo ponctuelle (variable d'environnement PARTAGE=1).
    # Protection par mot de passe (recommandée dès que l'app est accessible hors de ton PC) :
    # définis APP_UTILISATEUR et APP_MOT_DE_PASSE.
    utilisateur = os.environ.get("APP_UTILISATEUR")
    mot_de_passe = os.environ.get("APP_MOT_DE_PASSE")
    # Sur un hébergeur (Render…), la plateforme impose son port via la variable PORT
    port_hebergeur = os.environ.get("PORT")
    app.launch(
        theme=theme_custom,
        server_name="0.0.0.0" if port_hebergeur else None,
        server_port=int(port_hebergeur) if port_hebergeur else None,
        share=os.environ.get("PARTAGE") == "1",
        auth=(utilisateur, mot_de_passe) if utilisateur and mot_de_passe else None,
    )
