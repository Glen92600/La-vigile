#!/usr/bin/env python3
"""
Auto-réparation des conflits Git.

Lancé AVANT generer_site.py dans l'automate horaire. Si un Fetch/Pull a laissé
des marqueurs de conflit (<<<<<<<, =======, >>>>>>>) dans les fichiers suivis,
ce script les nettoie tout seul pour que le site ne reste jamais bloqué.

- articles_db.json : on fusionne les deux versions (sans perdre d'article).
- site/index.html  : on garde une version valide, et on demande au générateur
                     de régénérer la page même s'il n'y a aucun nouvel article
                     (sinon main() s'arrête tôt et laisse la page cassée).

Si une réparation a eu lieu, on écrit VIGIE_FORCE_HTML=1 dans $GITHUB_ENV
afin de forcer la régénération du HTML.
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "articles_db.json")
HTML_PATH = os.path.join(BASE, "site", "index.html")

MARQUEURS = ("<<<<<<<", "=======", ">>>>>>>")


def a_des_conflits(texte: str) -> bool:
    return any(m in texte for m in ("<<<<<<<", ">>>>>>>"))


def _extraire_cote(texte: str, cote: str) -> str:
    """Reconstruit une version du fichier en gardant 'ours' (HEAD) ou 'theirs'."""
    lignes = texte.splitlines(keepends=True)
    sortie = []
    etat = "normal"  # normal | ours | theirs
    for ligne in lignes:
        nu = ligne.lstrip()
        if nu.startswith("<<<<<<<"):
            etat = "ours"
            continue
        if nu.startswith("=======") and etat in ("ours", "theirs"):
            etat = "theirs"
            continue
        if nu.startswith(">>>>>>>"):
            etat = "normal"
            continue
        if etat == "normal":
            sortie.append(ligne)
        elif etat == cote:
            sortie.append(ligne)
    return "".join(sortie)


def reparer_db() -> bool:
    """Nettoie articles_db.json en fusionnant les deux côtés. Retourne True si réparé."""
    if not os.path.exists(DB_PATH):
        return False
    with open(DB_PATH, "r", encoding="utf-8") as f:
        texte = f.read()
    if not a_des_conflits(texte):
        return False

    print("[reparation] Conflit détecté dans articles_db.json — fusion en cours...")
    listes = []
    for cote in ("ours", "theirs"):
        try:
            data = json.loads(_extraire_cote(texte, cote))
            if isinstance(data, list):
                listes.append(data)
        except Exception:
            pass

    fusion = {}
    for data in listes:
        for art in data:
            lien = art.get("lien")
            if not lien:
                continue
            # On garde la fiche la plus complète si doublon
            if lien not in fusion or len(json.dumps(art)) > len(json.dumps(fusion[lien])):
                fusion[lien] = art

    articles = sorted(fusion.values(), key=lambda a: a.get("date", ""), reverse=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"[reparation] articles_db.json réparé : {len(articles)} articles conservés.")
    return True


def reparer_html() -> bool:
    """Nettoie site/index.html (garde le côté HEAD). Retourne True si réparé."""
    if not os.path.exists(HTML_PATH):
        return False
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        texte = f.read()
    if not a_des_conflits(texte):
        return False

    print("[reparation] Conflit détecté dans site/index.html — nettoyage...")
    propre = _extraire_cote(texte, "ours")
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(propre)
    print("[reparation] site/index.html nettoyé (sera régénéré proprement).")
    return True


def main():
    repare = False
    repare |= reparer_db()
    repare |= reparer_html()

    if repare:
        # Forcer la régénération du HTML même sans nouvel article.
        env = os.environ.get("GITHUB_ENV")
        if env:
            with open(env, "a", encoding="utf-8") as f:
                f.write("VIGIE_FORCE_HTML=1\n")
        print("[reparation] Réparation effectuée — régénération forcée du site.")
    else:
        print("[reparation] Aucun conflit — rien à réparer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
