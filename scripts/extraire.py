r"""Récupère les offres France Travail des métiers suivis et les enregistre dans data/.

Usage :
    .venv\Scripts\python.exe scripts\extraire.py                 # tous les métiers de METIERS
    .venv\Scripts\python.exe scripts\extraire.py --verifier      # teste seulement la connexion
    .venv\Scripts\python.exe scripts\extraire.py --rome D1301    # un seul code, pour essayer

Ce que ça écrit :
    data/brut/<AAAA-MM>/<ROME>.jsonl   une ligne par offre complète (JSON tel que l'API le renvoie),
                                       écrite la première fois qu'on voit l'offre, et de nouveau
                                       si son contenu a changé (une version = une ligne, datée)
    data/actives/<date>.csv            les offres actives ce jour-là : rome, id, date d'actualisation
    data/serie.csv                     une ligne par métier et par jour : total, nouvelles, modifiées

Les identifiants sont lus dans le fichier .env (voir .env.example) ou dans l'environnement
(secrets GitHub Actions). API : https://francetravail.io/data/api/offres-emploi —
150 offres par appel, 1 150 par requête, total réel dans l'en-tête Content-Range.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent
load_dotenv(RACINE / ".env")

# Les métiers suivis : code ROME -> (libellé, groupe, coché par défaut sur la page).
# Choisis pour le master marketing-vente spécialité DCIB (direction commerciale et international
# business) et le parcours management retail et expérience client ; la page permet de cocher/décocher.
METIERS = {
    # Management retail et expérience client
    "D1301": ("Management de magasin de détail", "Retail & expérience client", True),
    "D1302": ("Direction de boutique ou de point de vente", "Retail & expérience client", True),
    "D1509": ("Management du réseau commercial de détail", "Retail & expérience client", True),
    "M1704": ("Management relation clientèle", "Retail & expérience client", True),
    # Direction commerciale et international business
    "M1707": ("Stratégie commerciale", "Direction commerciale & international", True),
    "D1402": ("Relation commerciale grands comptes et entreprises", "Direction commerciale & international", True),
    "H1102": ("Management et ingénierie d'affaires", "Direction commerciale & international", True),
}

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

# On ne collecte que les annonces créées il y a moins de FENETRE_JOURS jours (le site n'en garde pas de plus vieilles).
# L'API plafonne à 1 150 offres par requête : si une fenêtre en contient davantage, on la coupe en deux, et ainsi de suite.
FENETRE_JOURS = 62
PLAFOND = 1150

# Champs qui bougent sans que l'offre change : ignorés pour décider si une offre a été modifiée.
CHAMPS_VOLATILS = {"dateActualisation"}


def obtenir_token():
    # strip() : un espace ou un retour à la ligne copié avec le secret suffit à faire refuser la connexion.
    cid, secret = (os.getenv("FT_CLIENT_ID") or "").strip(), (os.getenv("FT_CLIENT_SECRET") or "").strip()
    if not cid or not secret or cid.startswith("PAR_votre"):
        sys.exit("Identifiants absents : copiez .env.example en .env et remplissez-le.")
    r = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": cid,
        "client_secret": secret,
        "scope": "api_offresdemploiv2 o2dsoffre",
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    if r.status_code != 200:
        # La réponse de France Travail dit pourquoi (jamais les identifiants eux-mêmes).
        try:
            e = r.json()
        except ValueError:
            e = {}
        raison = f"{e.get('error')} — {e.get('error_description') or ''}" if e else r.text[:300]
        conseil = {
            "invalid_client": "identifiant ou secret refusé : vérifiez FT_CLIENT_ID et FT_CLIENT_SECRET "
                              "(pas inversés, copiés en entier, sans espace).",
            "invalid_scope": "l'application francetravail.io n'est pas abonnée à l'API « Offres d'emploi v2 ».",
        }.get(e.get("error"), "vérifiez l'application et ses identifiants sur francetravail.io.")
        message = f"Connexion à France Travail refusée ({r.status_code}) : {raison} → {conseil}"
        if os.getenv("GITHUB_ACTIONS"):              # annotation visible sur la page du run
            print(f"::error title=Token France Travail::{message}")
        sys.exit(message)
    return r.json()["access_token"]


def chercher(token, params, pas=150, maximum=1150):
    """Pagine la recherche ; renvoie (liste d'offres, total annoncé par l'API dans Content-Range)."""
    offres, total, debut = [], None, 0
    while debut < maximum:
        fin = min(debut + pas - 1, maximum - 1)
        r = requests.get(SEARCH_URL, params=dict(params, range=f"{debut}-{fin}"),
                         headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if r.status_code == 204:                     # aucune offre
            break
        if r.status_code not in (200, 206):
            raise RuntimeError(f"{r.status_code} : {r.text[:200]}")
        m = re.search(r"/(\d+)", r.headers.get("Content-Range", ""))   # ex. "offres 0-149/1234"
        if m:
            total = int(m.group(1))
        lot = r.json().get("resultats", [])
        offres.extend(lot)
        if len(lot) < pas or (total is not None and len(offres) >= total):
            break
        debut += pas
        time.sleep(0.3)                              # on reste poli avec l'API
    return offres, total


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def total_fenetre(token, params):
    """Nombre d'offres d'une recherche, lu dans Content-Range d'une requête d'une seule offre."""
    r = requests.get(SEARCH_URL, params=dict(params, range="0-0"),
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code == 204:
        return 0
    if r.status_code not in (200, 206):
        raise RuntimeError(f"{r.status_code} : {r.text[:200]}")
    m = re.search(r"/(\d+)", r.headers.get("Content-Range", ""))
    return int(m.group(1)) if m else len(r.json().get("resultats", []))


def chercher_tout(token, params, debut=None, fin=None, profondeur=0):
    """Toutes les offres créées entre `debut` et `fin`, au-delà du plafond de l'API : une fenêtre qui dépasse
    PLAFOND offres est coupée en deux. Renvoie (liste d'offres sans doublon, nombre de requêtes de découpage)."""
    maintenant = datetime.now(timezone.utc).replace(microsecond=0)
    fin = fin or maintenant
    debut = debut or fin - timedelta(days=FENETRE_JOURS)
    fenetre = dict(params, minCreationDate=_iso(debut), maxCreationDate=_iso(fin))
    total = total_fenetre(token, fenetre)
    if total <= PLAFOND or (fin - debut) <= timedelta(hours=6) or profondeur >= 8:
        offres, _ = chercher(token, fenetre)
        return offres, 1, total
    milieu = debut + (fin - debut) / 2
    a, na, ta = chercher_tout(token, params, debut, milieu.replace(microsecond=0), profondeur + 1)
    b, nb, tb = chercher_tout(token, params, milieu.replace(microsecond=0) + timedelta(seconds=1), fin, profondeur + 1)
    uniques = {o["id"]: o for o in a + b}
    return list(uniques.values()), na + nb + 1, ta + tb


def empreinte(offre):
    """Empreinte du contenu d'une offre, champs volatils exclus : change si l'annonce change."""
    stable = {k: v for k, v in offre.items() if k not in CHAMPS_VOLATILS}
    return hashlib.sha1(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def versions_connues():
    """Toutes les (id, empreinte) déjà enregistrées dans data/brut, pour ne rien écrire deux fois."""
    vues = set()
    for f in (RACINE / "data" / "brut").glob("*/*.jsonl"):
        with f.open(encoding="utf-8") as fh:
            for ligne in fh:
                if ligne.strip():
                    v = json.loads(ligne)
                    vues.add((v["id"], v["empreinte"]))
    return vues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verifier", action="store_true", help="teste seulement la connexion")
    ap.add_argument("--rome", default="", help="un seul code ROME de METIERS, pour essayer")
    args = ap.parse_args()

    token = obtenir_token()
    print("Connexion à l'API France Travail : OK")
    if args.verifier:
        return
    codes = [args.rome] if args.rome else list(METIERS)
    if args.rome and args.rome not in METIERS:
        sys.exit(f"{args.rome} n'est pas dans METIERS (scripts/extraire.py).")

    aujourdhui = f"{date.today():%Y-%m-%d}"
    mois = aujourdhui[:7]
    vues = versions_connues()
    ids_connus = {i for i, _ in vues}
    (RACINE / "data" / "brut" / mois).mkdir(parents=True, exist_ok=True)
    (RACINE / "data" / "actives").mkdir(parents=True, exist_ok=True)

    actives, lignes_serie = [], []
    for code in codes:
        offres, requetes, total = chercher_tout(token, {"codeROME": code})
        nouvelles = modifiees = 0
        with (RACINE / "data" / "brut" / mois / f"{code}.jsonl").open("a", encoding="utf-8") as brut:
            for o in offres:
                e = empreinte(o)
                if (o["id"], e) not in vues:
                    if o["id"] in ids_connus:
                        modifiees += 1
                    else:
                        nouvelles += 1
                        ids_connus.add(o["id"])
                    vues.add((o["id"], e))
                    brut.write(json.dumps({"id": o["id"], "empreinte": e, "vu_le": aujourdhui,
                                           "rome": code, "offre": o}, ensure_ascii=False) + "\n")
                actives.append((code, o["id"], (o.get("dateActualisation") or "")[:10]))
        lignes_serie.append([aujourdhui, code, total if total is not None else len(offres),
                             len(offres), nouvelles, modifiees])
        print(f"{code}  {METIERS[code][0]:<48} {len(offres):5d} offres ({requetes} fenêtre{'s' if requetes > 1 else ''}), {nouvelles:4d} nouvelles, {modifiees:3d} modifiées")
        time.sleep(0.5)

    # Même logique pour les actives du jour : on remplace les codes relancés, on garde les autres.
    fichier_actives = RACINE / "data" / "actives" / f"{aujourdhui}.csv"
    if fichier_actives.exists():
        with fichier_actives.open(encoding="utf-8") as f:
            actives = [tuple(r) for r in list(csv.reader(f))[1:] if r[0] not in codes] + actives
    with fichier_actives.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rome", "id", "date_actualisation"])
        w.writerows(sorted(actives))

    serie = RACINE / "data" / "serie.csv"
    lignes = []
    if serie.exists():
        with serie.open(encoding="utf-8") as f:
            lignes = [r for r in csv.reader(f)][1:]
    # Si on relance le même jour, la ligne du jour est remplacée, pas doublée.
    lignes = [r for r in lignes if not (r[0] == aujourdhui and r[1] in codes)] + lignes_serie
    with serie.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "rome", "total", "recuperees", "nouvelles", "modifiees"])
        w.writerows(sorted(lignes))

    print(f"\n{aujourdhui} : {len(actives)} offres actives sur {len(codes)} métiers — "
          f"{sum(r[4] for r in lignes_serie)} nouvelles versions, {sum(r[5] for r in lignes_serie)} modifiées.")


if __name__ == "__main__":
    main()
