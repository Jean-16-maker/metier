r"""Compte les offres actives (France entière) de métiers candidats, sans rien écrire dans data/.

Sert à choisir les métiers suivis avant de modifier METIERS (scripts/extraire.py).
Pour chaque code : total annoncé par l'API, part « débutant accepté » (experienceExige = D)
et part en alternance (alternance, apprentissage ou professionnalisation), calculées sur les
offres récupérées (1 150 au plus : au-delà, c'est un échantillon).

Usage :
    .venv\Scripts\python.exe scripts\compter.py
Dans GitHub Actions (workflow « comptage »), le tableau s'affiche dans le résumé du run.
"""
import os
import sys
import time

from extraire import chercher, obtenir_token

# Groupe -> [(métier, code ROME, correspondance)]. Codes vérifiés dans l'arborescence ROME 4.0 du 15/06/2026.
CANDIDATS = {
    "Commerce international B2B": [
        ("Commercial export", "D1433", "exacte"),
        ("Business developer / resp. développement commercial", "M1707", "exacte"),
        ("Ingénieur d'affaires BtoB (cadre technico-commercial)", "D1420", "exacte"),
        ("Commercial grands comptes et entreprises", "D1402", "exacte"),
        ("Responsable grands comptes / Key Account Manager", "D1444", "exacte"),
        ("Responsable de zone internationale", "D1414", "exacte"),
        ("Chef de produit (dont assistant chef de marché)", "M1703", "exacte"),
        ("Acheteur", "M1101", "exacte"),
    ],
    "Retail management": [
        ("Directeur / resp. adjoint de magasin de grande distribution", "D1504", "exacte"),
        ("Responsable / adjoint de boutique (commerce de détail)", "D1302", "exacte"),
        ("Manager de rayon produits alimentaires", "D1502", "exacte"),
        ("Manager de rayon produits non alimentaires", "D1503", "exacte"),
        ("Manager de rayon produits frais", "D1513", "exacte"),
        ("Chef de secteur distribution", "D1517", "exacte"),
        ("Chef de secteur magasin", "D1510", "exacte"),
        ("Category manager (CATMAN)", "M1720", "exacte"),
        ("Merchandiser / visual merchandiser", "D1506", "exacte"),
        ("Responsable merchandising", "D1516", "alternative"),
    ],
    "Expérience client": [
        ("Chargé de relation client", "D1415", "exacte"),
        ("Responsable service clients (CRM, fidélisation)", "M1704", "approchante"),
        ("Responsable / chargé e-commerce", "E1113", "approchante"),
        ("Chef de projet web", "M1886", "alternative"),
    ],
    "Assistants (pour décider)": [
        ("Assistant import-export", "D1429", "exacte"),
        ("Assistant administration des ventes", "D1409", "exacte"),
        ("Assistant achat", "D1431", "exacte"),
        ("Assistant commercial", "D1401", "exacte"),
    ],
}

SEUIL = 30


def est_alternance(o):
    nature = (o.get("natureContrat") or "").lower()
    return bool(o.get("alternance")) or "apprentissage" in nature or "professionnalisation" in nature


def pct(n, d):
    return f"{round(100 * n / d)} %" if d else "—"


def main():
    token = obtenir_token()
    lignes = ["| Groupe | Métier | Code | Offres actives | Débutant accepté | Alternance | Remarque |",
              "|---|---|---|--:|--:|--:|---|"]
    for groupe, metiers in CANDIDATS.items():
        for nom, code, corresp in metiers:
            offres, total = chercher(token, {"codeROME": code})
            total = total if total is not None else len(offres)
            n = len(offres)
            deb = sum(1 for o in offres if o.get("experienceExige") == "D")
            alt = sum(1 for o in offres if est_alternance(o))
            remarques = []
            if corresp != "exacte":
                remarques.append(f"correspondance {corresp}")
            if total < SEUIL:
                remarques.append(f"< {SEUIL} offres")
            if n < total:
                remarques.append(f"parts sur {n} offres")
            lignes.append(f"| {groupe} | {nom} | {code} | {total} | {pct(deb, n)} | {pct(alt, n)} | {', '.join(remarques)} |")
            print(lignes[-1], flush=True)
            time.sleep(0.5)
    tableau = "\n".join(lignes)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("## Comptage des métiers candidats\n\n" + tableau + "\n")
    if os.getenv("GITHUB_ACTIONS"):
        # Une seule annotation (GitHub en garde 10 par étape), lignes séparées par %0A :
        # lisible sur la page du run, et via l'API publique.
        print("::notice title=Comptage::" + "%0A".join(lignes[2:]))
    print("\n" + tableau)


if __name__ == "__main__":
    sys.exit(main())
