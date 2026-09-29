r"""Lit les offres actives du jour (data/actives/<date>.csv), retrouve leur dernière version dans
data/brut, et écrit data/resume.json : le fichier que la page index.html affiche.

Usage :
    .venv\Scripts\python.exe scripts\resumer.py

C'est ici que la donnée brute est retravaillée :
  - salaire : libellé texte -> minimum et maximum annuels bruts ;
  - outils cités dans l'intitulé + la description (grille OUTILS, à adapter à votre métier) ;
  - position sur la carte : latitude/longitude de l'API quand elle les donne, sinon le centre
    de la commune (geo.api.gouv.fr, mis en cache dans data/geo/), sinon la ville principale
    du département ; les offres « France » n'ont pas de point.
  - niveau de poste déduit de l'intitulé (assistant / chargé / responsable / directeur / autre),
    nature du contrat (apprentissage, professionnalisation, salarié, non salarié) et libellés
    lisibles des codes de contrat (clé « contrats » du résumé).
  - exigences : exp_exige, exp_ans (années, 0 = débutant accepté), qualification, formation
    (niveau le plus élevé demandé), secteur, temps (plein/partiel), postes.
La page recalcule ensuite tous les comptages côté navigateur, selon les métiers cochés.
"""
import csv
import json
import re
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))
from extraire import METIERS  # noqa: E402  (la liste des métiers vit dans un seul fichier)

# Les outils et compétences que l'on cherche dans les annonces : c'est VOTRE grille, adaptez-la.
# Chaque entrée : libellé affiché -> variantes cherchées (mot entier, insensible à la casse).
OUTILS = {
    # Retail et expérience client
    "Gestion d'équipe / management": ["management d'équipe", "manager une équipe", "encadrement d'équipe",
                                      "encadrer une équipe", "animation d'équipe", "animer une équipe"],
    "Merchandising / VM": ["merchandising", "visual merchandising", "mise en rayon", "implantation", "vitrine"],
    "Gestion de stock / inventaire": ["gestion des stocks", "gestion de stock", "stocks", "inventaire", "inventaires"],
    "Suivi de KPI / tableaux de bord": ["kpi", "indicateurs", "tableau de bord", "tableaux de bord", "reporting"],
    "Chiffre d'affaires / objectifs": ["chiffre d'affaires", "objectifs de vente", "marge", "rentabilité", "panier moyen"],
    "Expérience / satisfaction client": ["expérience client", "satisfaction client", "nps", "fidélisation",
                                         "parcours client", "voix du client"],
    "Omnicanal / e-commerce": ["omnicanal", "omnicanalité", "cross-canal", "e-commerce", "click and collect", "drive"],
    "Recrutement / formation": ["recrutement", "recruter", "formation des équipes", "former les équipes", "onboarding"],
    "Multi-sites / réseau": ["multi-sites", "multisites", "réseau de magasins", "réseau de points de vente",
                             "franchise", "franchisés", "franchisé"],
    "Service client / SAV": ["service client", "relation client", "sav", "réclamations"],
    # Direction commerciale et international business
    "Stratégie commerciale": ["stratégie commerciale", "plan d'action commercial", "business plan", "budget"],
    "Grands comptes / KAM": ["grands comptes", "grand compte", "key account", "kam", "comptes clés"],
    "Développement de portefeuille": ["développement du portefeuille", "prospection", "conquête", "business development"],
    "Négociation": ["négociation", "négocier", "negotiation"],
    "Réponse à appels d'offres": ["appel d'offres", "appels d'offres", "tender", "tenders"],
    "Import / export": ["export", "import", "incoterm", "incoterms", "douane", "douanes", "international"],
    "Salons / événements": ["salon", "salons", "foire", "foires", "événement", "événements"],
    # Outils
    "CRM / Salesforce": ["crm", "salesforce", "hubspot", "dynamics"],
    "ERP / SAP": ["erp", "sap", "oracle", "sage", "cegid"],
    "Excel": ["excel"],
    "Power BI / Qlik": ["power bi", "powerbi", "qlik", "tableau software"],
    "LinkedIn": ["linkedin"],
    # Langues
    "Anglais": ["anglais", "english", "toeic", "toefl", "bilingue"],
    "Allemand": ["allemand", "german", "deutsch"],
    "Espagnol": ["espagnol", "spanish", "español"],
    "Italien": ["italien", "italian"],
    "Portugais": ["portugais", "portuguese"],
    "Chinois": ["chinois", "mandarin", "chinese"],
    "Arabe": ["arabe", "arabic"],
    "Déplacements": ["déplacements", "déplacements à l'étranger", "déplacements internationaux",
                     "voyages à l'étranger", "mobilité internationale", "mobilité géographique"],
}
REGEX_OUTILS = {nom: re.compile(r"(?<![\w-])(" + "|".join(re.escape(v) for v in variantes) + r")(?![\w-])")
                for nom, variantes in OUTILS.items()}

GEO = "https://geo.api.gouv.fr"

# Niveau du poste, lu dans l'intitulé : l'ordre compte (un « directeur marketing » n'est pas
# un « chargé »). Première expression qui correspond, en minuscules.
NIVEAUX = [
    ("directeur", r"directeur|directrice|\bhead of\b|\bcso\b|\bcpo\b|\bvp\b|export director|sales director"),
    ("responsable", r"responsable|gérant|gérante|store manager|area manager|manager|\bchef|\bcheffe|\blead\b|\bhead\b|key account|\bkam\b"),
    ("assistant", r"assistant|alternan|apprenti|stagiaire|\bstage\b|junior"),
    ("charge", r"charg[ée]|consultant|analyste|analyst|spécialiste|specialist|traffic|community"
                r"|expert|technicien|conseiller|animateur|référenceur|rédacteur|designer"
                r"|développeur|business developer|ingénieur|gestionnaire|coordinateur|superviseur"
                r"|commercial|attaché|acheteu|approvisionneu|déclarant|agent|affréteu|négociat"
                r"|sales|buyer|\badv\b"),
]
REGEX_NIVEAUX = [(cle, re.compile(motif, re.IGNORECASE)) for cle, motif in NIVEAUX]
NIVEAUX_LIBELLES = [
    ["assistant", "Assistant·e / junior"],
    ["charge", "Chargé·e"],
    ["responsable", "Responsable"],
    ["directeur", "Directeur·rice"],
    ["autre", "Autre"],
]

# Codes de type de contrat de l'API -> libellé court lisible par un étudiant.
CONTRATS = {
    "CDI": "CDI",
    "CDD": "CDD",
    "MIS": "Intérim",
    "SAI": "Saisonnier",
    "FRA": "Franchise",
    "LIB": "Profession libérale",
    "CCE": "Profession commerciale",
    "DDI": "CDI de chantier",
    "DIN": "CDI intérimaire",
    "TTI": "Intérim",
    "CDS": "CDD senior",
    "REP": "Reprise d'entreprise",
}

NATURES = [
    ("apprentissage", "apprentissage"),
    ("professionnalisation", "professionnalisation"),
    ("non salarié", "non_salarie"),
    ("contrat travail", "salarie"),
]

# Niveau de formation demandé : du plus faible au plus élevé (l'ordre sert aussi à l'affichage).
FORMATIONS = ["< Bac", "Bac", "Bac+2", "Bac+3/4", "Bac+5"]


def niveau(intitule):
    """'Directeur marketing' -> 'directeur' ; 'Chargé de com' -> 'charge' ; sinon 'autre'."""
    t = intitule or ""
    for cle, rx in REGEX_NIVEAUX:
        if rx.search(t):
            return cle
    return "autre"


def contrat_libelle(code):
    """Code de contrat de l'API -> libellé court ; les codes inconnus restent identifiables."""
    return CONTRATS.get(code) or f"Autre ({code})"


def nature(o):
    """natureContrat -> 'apprentissage' | 'professionnalisation' | 'salarie' | 'non_salarie' | 'autre'."""
    lib = (o.get("natureContrat") or "").lower()
    if not lib:
        return "autre"
    for motif, cle in NATURES:
        if motif in lib:
            return cle
    return "autre"


def exp_ans(lib):
    """'Débutant accepté'/'0 An(s)' -> 0, '6 Mois' -> 0.5, '5 An(s)' -> 5, 'Expérience exigée' -> None."""
    l = (lib or "").lower()
    if not l:
        return None
    if "débutant" in l or "debutant" in l:
        return 0
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(an|mois)", l)
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    n = n if m.group(2) == "an" else n / 12
    return int(n) if n == int(n) else round(n, 2)


def formation(o):
    """Niveau de formation le plus élevé demandé par l'offre, ou None si rien n'est indiqué."""
    meilleur = None
    for f in o.get("formations") or []:
        l = (f.get("niveauLibelle") or "").lower()
        if not l:
            continue
        if "bac+5" in l or "bac + 5" in l:
            n = "Bac+5"
        elif "bac+3" in l or "bac+4" in l or "bac + 3" in l or "bac + 4" in l:
            n = "Bac+3/4"
        elif "bac+2" in l or "bac + 2" in l:
            n = "Bac+2"
        elif "bac" in l:
            n = "Bac"
        else:
            n = "< Bac"
        if meilleur is None or FORMATIONS.index(n) > FORMATIONS.index(meilleur):
            meilleur = n
    return meilleur


def temps_travail(o):
    """'Temps plein' -> 'plein', 'Temps partiel' -> 'partiel', sinon None."""
    l = (o.get("dureeTravailLibelleConverti") or "").lower()
    return "plein" if "plein" in l else ("partiel" if "partiel" in l else None)


# En-tête normalisé des libellés de salaire de France Travail :
# « Annuel de 32000.0 Euros à 38000.0 Euros », « Mensuel de 486.0 Euros sur 12 mois »,
# « Horaire de 12.31 Euros - 13ème mois + primes »…
MOTIF_SALAIRE = re.compile(
    r"^(annuel|mensuel|horaire)\s+de\s+(\d+(?:[.,]\d+)?)\s*euros"
    r"(?:\s*à\s*(\d+(?:[.,]\d+)?)\s*euros)?",
    re.IGNORECASE,
)
MULTIPLICATEUR = {"annuel": 1, "mensuel": 12, "horaire": 1607}
# Fenêtre de vraisemblance, en brut annuel. En dessous : l'employeur a saisi des
# milliers d'euros dans la case « annuel » (« Annuel de 32.0 Euros à 38.0 Euros »).
# Au dessus : il a saisi un salaire annuel dans la case « mensuel ». Le plancher
# laisse passer les apprentis (27 % du SMIC = 5 832 € par an).
SALAIRE_MIN, SALAIRE_MAX = 4000, 250000


def salaire_min_max(lib):
    """'Annuel de 32000.0 Euros à 38000.0 Euros' -> (32000, 38000) ; mensuel x12, horaire x1607.

    On ne lit que cet en-tête : le commentaire libre qui suit un « - » répète ou
    brouille les chiffres (« De 30 à 35 k€ par an », « 13ème mois », « 35h hebdo »),
    et « sur 12 mois » n'est pas un montant. Lire tous les nombres du libellé
    obligeait à écarter les petites valeurs, ce qui effaçait les vrais salaires
    d'apprenti (486 €/mois = 27 % du SMIC).
    """
    if not lib:
        return None, None
    m = MOTIF_SALAIRE.match(lib.strip())
    if not m:
        return None, None
    mult = MULTIPLICATEUR[m.group(1).lower()]
    vals = [float(x.replace(",", ".")) * mult for x in (m.group(2), m.group(3)) if x]
    vals = [v for v in vals if SALAIRE_MIN <= v <= SALAIRE_MAX]
    return (round(min(vals)), round(max(vals))) if vals else (None, None)


def departement(lieu):
    cp = lieu.get("codePostal") or ""
    if cp[:2].isdigit() and cp != "99999":
        return "2A" if cp[:2] == "20" and cp < "20200" else ("2B" if cp[:2] == "20" else cp[:2])
    m = re.match(r"\s*(\d{2}|2A|2B)\s*-", lieu.get("libelle") or "")
    return m.group(1) if m else ""


class Geocodeur:
    """Centre des communes et villes principales des départements, via geo.api.gouv.fr, avec cache."""

    def __init__(self):
        self.dossier = RACINE / "data" / "geo"
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.communes = self._lire("communes.json")
        self.departements = self._lire("departements.json")
        self.appels = 0

    def _lire(self, nom):
        f = self.dossier / nom
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    def _get(self, url):
        self.appels += 1
        time.sleep(0.05)
        try:
            r = requests.get(url, timeout=15)
            return r.json() if r.status_code == 200 else None
        except requests.RequestException:
            return None

    def commune(self, code):
        if code not in self.communes:
            d = self._get(f"{GEO}/communes/{code}?fields=centre")
            self.communes[code] = d["centre"]["coordinates"][::-1] if d and d.get("centre") else None
        return self.communes[code]

    def departement(self, code):
        if code not in self.departements:
            d = self._get(f"{GEO}/communes?codeDepartement={code}&fields=centre&boost=population&limit=1")
            self.departements[code] = d[0]["centre"]["coordinates"][::-1] if d else None
        return self.departements[code]

    def position(self, lieu):
        """(lat, lon, précision) ; précision = 'offre', 'commune', 'departement' ou None."""
        if lieu.get("latitude") and lieu.get("longitude"):
            return lieu["latitude"], lieu["longitude"], "offre"
        if lieu.get("commune"):
            p = self.commune(lieu["commune"])
            if p:
                return p[0], p[1], "commune"
        dep = departement(lieu)
        if dep:
            p = self.departement(dep)
            if p:
                return p[0], p[1], "departement"
        return None, None, None

    def sauver(self):
        (self.dossier / "communes.json").write_text(json.dumps(self.communes), encoding="utf-8")
        (self.dossier / "departements.json").write_text(json.dumps(self.departements), encoding="utf-8")


# ---------------------------------------------------------------------------
# Ce qu'on garde dans le résumé (les règles du groupe : annonces récentes, propres, uniques).
# ---------------------------------------------------------------------------
AGE_MAX_JOURS = 60            # publiée il y a moins de 2 mois
EXIGER_ENTREPRISE = True      # pas d'annonce sans nom d'employeur
EXIGER_SALAIRE = True         # pas d'annonce sans salaire lisible (smin renseigné)

# Écoles et organismes de formation : leurs annonces recrutent des étudiants, pas des salariés.
# Testé sur le nom de l'employeur, puis sur le secteur d'activité.
ECOLES_NOM = re.compile(
    r"\bformations?\b|\bécoles?\b|\becoles?\b|\biscod\b|\binstitut\b|\bcampus\b|\bacad[ée]mie\b|"
    r"\bacademy\b|\buniversit|\bcfa\b|\bcfp\b|\bcnam\b|\bgreta\b|\bstudi\b|\bbusiness school\b|"
    r"\bigs\b|\besgci\b|\binseec\b|\besc\b|\bpigier\b|\bcned\b|\baftec\b|\bgroupe es\b|\bwebschool\b",
    re.IGNORECASE)
ECOLES_SECTEUR = re.compile(r"enseignement|formation continue|formation profession|écoles? de|autres enseignements",
                            re.IGNORECASE)


def est_ecole(entreprise, secteur):
    return bool(ECOLES_NOM.search(entreprise or "") or ECOLES_SECTEUR.search(secteur or ""))


def famille_contrat(o):
    """Les cinq types de contrat gardés : cdi, cdd, mis (intérim), alt (alternance), indep (freelance).
    L'alternance l'emporte sur le CDI/CDD qui la porte ; les autres contrats (franchise, reprise…) sortent."""
    c, nat = o.get("typeContrat") or "", nature(o)
    if o.get("alternance") or nat in ("apprentissage", "professionnalisation"):
        return "alt"
    if c in ("MIS", "TTI", "DIN"):
        return "mis"
    if c in ("LIB", "CCE") or nat == "non_salarie" and c != "FRA":
        return "indep"
    if c in ("CDI", "DDI"):
        return "cdi"
    if c in ("CDD", "CDS", "SAI"):
        return "cdd"
    return None


def cle_doublon(o):
    """Une même annonce republiée (même employeur, même intitulé, même département)."""
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", (t or "").lower().replace("é", "e").replace("è", "e")).strip()
    intitule = re.sub(r"\b(h ?/ ?f|f ?/ ?h|h|f)\b", " ", norm(o["intitule"]))
    return (norm(o["entreprise"]), " ".join(intitule.split()), o["dep"] or norm(o["lieu"]))


def nettoyer(offres, jour):
    """Applique les règles ci-dessus, une par une et dans cet ordre.

    Renvoie (offres gardées, décompte de ce qui est retiré et pourquoi, trace) ; la trace est la suite
    [libellé, offres restantes, offres retirées] que la page affiche avant tout graphique."""
    limite = date.fromisoformat(jour) - timedelta(days=AGE_MAX_JOURS)

    def recente(o):
        try:
            return date.fromisoformat(o["date"]) >= limite
        except (TypeError, ValueError):
            return False

    etapes = [
        ("Moins de 2 mois", "plus de 2 mois", recente),
        ("Avec un nom d'employeur", "sans nom d'entreprise", lambda o: not EXIGER_ENTREPRISE or bool(o["entreprise"])),
        ("Hors écoles et organismes de formation", "école ou organisme de formation", lambda o: not est_ecole(o["entreprise"], o["secteur"])),
        ("Avec un salaire lisible", "sans salaire", lambda o: not EXIGER_SALAIRE or o["smin"] is not None),
        ("CDI, CDD, intérim, alternance ou freelance", "contrat hors CDI/CDD/intérim/alternance/freelance", lambda o: bool(o["famille"])),
    ]
    retires, trace, restantes = {}, [["Offres au départ", len(offres), 0]], offres
    for libelle, raison, garde in etapes:
        suivantes = [o for o in restantes if garde(o)]
        retires[raison] = len(restantes) - len(suivantes)
        trace.append([libelle, len(suivantes), len(restantes) - len(suivantes)])
        restantes = suivantes
    # Doublons : on garde la plus récente de chaque groupe.
    uniques = {}
    for o in sorted(restantes, key=lambda x: x["date"] or "", reverse=True):
        uniques.setdefault(cle_doublon(o), o)
    retires["doublon"] = len(restantes) - len(uniques)
    trace.append(["Sans doublon", len(uniques), len(restantes) - len(uniques)])
    return list(uniques.values()), retires, trace


# ---------------------------------------------------------------------------
# Offres d'Adzuna, relevées à la main dans le navigateur (data/externes/adzuna.csv).
# ---------------------------------------------------------------------------
MOTIF_SALAIRE_ADZUNA = re.compile(
    r"(?:(a partir de)\s*)?(\d[\d.,\s]*)\s*(k)?\s*€?\s*(?:-|à)?\s*(?:(\d[\d.,\s]*)\s*(k)?\s*€)?", re.IGNORECASE)


def salaire_adzuna(lib):
    """'40 - 50 K€ BRUT ANNUEL' -> (40000, 50000) ; '2400.00€ - 2500.00€ MOIS' -> x12 ; 'A PARTIR DE 32 K€' -> (32000, None)."""
    t = (lib or "").lower().replace("\u202f", " ").replace("\xa0", " ")
    mois = "mois" in t
    nombres = re.findall(r"(\d[\d\s]*(?:[.,]\d+)?)\s*(k)?\s*€?", re.split(r"\bbrut\b|\bpar\b|\bmois\b", t)[0])
    vals = []
    for n, k in nombres:
        try:
            v = float(n.replace(" ", "").replace(",", "."))
        except ValueError:
            continue
        v = v * 1000 if (k or v < 1000) else v
        vals.append(v * 12 if mois else v)
    vals = [round(v) for v in vals if SALAIRE_MIN <= v <= SALAIRE_MAX]
    if not vals:
        return None, None
    return (vals[0], None) if "a partir" in t or "à partir" in t or len(vals) == 1 else (min(vals), max(vals))


def lire_adzuna(geo, jour):
    """Les offres Adzuna au même format que celles de France Travail.

    Adzuna ne donne ni date précise (seulement « publiée il y a moins de 30 jours ») ni contrat sur la page
    de résultats : la date est posée au milieu de la fenêtre (jour - 15) et un contrat non lu est supposé CDI ;
    les deux sont signalés par `date_approx` et `contrat_suppose`."""
    fichier = RACINE / "data" / "externes" / "adzuna.csv"
    if not fichier.exists():
        return []
    offres = []
    approx = (date.fromisoformat(jour) - timedelta(days=15)).isoformat()
    with fichier.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            smin, smax = salaire_adzuna(r["salaire"])
            m = re.search(r"\b(\d{2}[0-9AB]\d{2})\b", r["lieu"] or "")
            insee = m.group(1) if m else None
            pos = geo.commune(insee) if insee else None
            dep = insee[:2] if insee else ""
            contrat = (r["contrat"] or "").upper()
            famille = {"CDD": "cdd", "INTÉRIM": "mis", "INTERIM": "mis", "ALTERNANCE": "alt"}.get(contrat, "cdi")
            offres.append({
                "id": "adz-" + r["id"], "rome": r["rome"], "intitule": r["intitule"], "entreprise": r["entreprise"] or None,
                "lieu": r["lieu"], "dep": dep,
                "lat": pos[0] if pos else None, "lon": pos[1] if pos else None, "prec": "commune" if pos else None,
                "contrat": contrat or None, "famille": famille, "source": "Adzuna",
                "date_approx": True, "contrat_suppose": not contrat,
                "experience": None, "alternance": famille == "alt", "salaire": r["salaire"], "smin": smin, "smax": smax,
                "date": approx, "vu_le": r["recupere_le"], "url": "https://www.adzuna.fr/details/" + r["id"],
                "outils": [nom for nom, rx in REGEX_OUTILS.items() if rx.search((r["intitule"] or "").lower())],
                "teletravail": False, "competences": [], "niveau": niveau(r["intitule"]), "nature": "salarie",
                "exp_exige": None, "exp_ans": None, "qualification": None, "formation": None, "secteur": None,
                "temps": None, "postes": 1,
            })
    return offres


def main():
    jours = sorted((RACINE / "data" / "actives").glob("*.csv"))
    if not jours:
        raise SystemExit("Aucune extraction : lancez d'abord scripts/extraire.py")
    jour = jours[-1].stem
    with jours[-1].open(encoding="utf-8") as f:
        # Seuls les métiers suivis comptent : un ancien code encore dans le fichier du jour est ignoré.
        actives = [(r["rome"], r["id"]) for r in csv.DictReader(f) if r["rome"] in METIERS]
    ids_actifs = {i for _, i in actives}

    # Dernière version connue de chaque offre active (les fichiers sont lus dans l'ordre des mois).
    versions = {}
    for f in sorted((RACINE / "data" / "brut").glob("*/*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            for ligne in fh:
                if ligne.strip():
                    v = json.loads(ligne)
                    if v["id"] in ids_actifs:
                        versions[v["id"]] = v
    nb_versions = sum(1 for f in (RACINE / "data" / "brut").glob("*/*.jsonl")
                      for l in f.open(encoding="utf-8") if l.strip())

    geo = Geocodeur()
    offres = []
    for rome, oid in actives:
        v = versions.get(oid)
        if not v:
            continue
        o = v["offre"]
        lieu = o.get("lieuTravail") or {}
        texte = (o.get("intitule") or "") + " " + (o.get("description") or "")
        t = texte.lower()
        smin, smax = salaire_min_max((o.get("salaire") or {}).get("libelle"))
        lat, lon, precision = geo.position(lieu)
        offres.append({
            "id": oid,
            "rome": rome,
            "intitule": o.get("intitule"),
            "entreprise": (o.get("entreprise") or {}).get("nom"),
            "lieu": lieu.get("libelle"),
            "dep": departement(lieu),
            "lat": lat, "lon": lon, "prec": precision,
            "contrat": o.get("typeContrat"),
            "famille": famille_contrat(o),
            "source": "France Travail",
            "experience": o.get("experienceLibelle"),
            "alternance": bool(o.get("alternance")),
            "salaire": (o.get("salaire") or {}).get("libelle"),
            "smin": smin, "smax": smax,
            "date": (o.get("dateCreation") or "")[:10],
            "vu_le": v["vu_le"],
            "url": (o.get("origineOffre") or {}).get("urlOrigine"),
            "outils": [nom for nom, rx in REGEX_OUTILS.items() if rx.search(t)],
            "teletravail": "télétravail" in t,
            "competences": [c.get("libelle") for c in o.get("competences") or [] if c.get("libelle")],
            "niveau": niveau(o.get("intitule")),
            "nature": nature(o),
            "exp_exige": o.get("experienceExige") or None,
            "exp_ans": exp_ans(o.get("experienceLibelle")),
            "qualification": o.get("qualificationLibelle") or None,
            "formation": formation(o),
            "secteur": o.get("secteurActiviteLibelle") or None,
            "temps": temps_travail(o),
            "postes": int(o.get("nombrePostes") or 1),
        })
    offres += lire_adzuna(geo, jour)
    geo.sauver()
    offres, retires, trace = nettoyer(offres, jour)

    # Série : par jour et par métier
    serie = defaultdict(dict)
    with (RACINE / "data" / "serie.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["rome"] in METIERS:
                serie[r["date"]][r["rome"]] = int(r["total"])

    resume = {
        "date": jour,
        "source": "France Travail — API Offres d'emploi v2, complété par Adzuna",
        "requete": "une requête codeROME par métier, France entière",
        "metiers": [{"code": c, "libelle": l, "groupe": g, "coche": k,
                     "actives": sum(1 for o in offres if o["rome"] == c)}
                    for c, (l, g, k) in METIERS.items()],
        "outils": list(OUTILS),
        "contrats": {"cdi": "CDI", "cdd": "CDD", "mis": "Intérim", "alt": "Alternance", "indep": "Freelance"},
        "retires": retires,
        "trace": trace,
        "niveaux": NIVEAUX_LIBELLES,
        "formations": FORMATIONS,
        "versions_conservees": nb_versions,
        "sans_position": sum(1 for o in offres if o["lat"] is None),
        "serie": [{"date": d, "par_metier": m} for d, m in sorted(serie.items())],
        "offres": offres,
    }
    sortie = RACINE / "data" / "resume.json"
    sortie.write_text(json.dumps(resume, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    prec = defaultdict(int)
    for o in offres:
        prec[o["prec"]] += 1
    print(f"Écrit : {sortie.relative_to(RACINE)} — {len(offres)} offres actives du {jour}, "
          f"{sortie.stat().st_size // 1024} Ko")
    print("Retirées :", ", ".join(f"{k} {v}" for k, v in sorted(retires.items(), key=lambda kv: -kv[1])))
    print(f"Positions : {dict(prec)} ({geo.appels} appels geo.api.gouv.fr)")
    avec = [o for o in offres if o["smin"] is not None]
    part = 100 * len(avec) // len(offres) if offres else 0
    print(f"Salaire affiché par {len(avec)} offres sur {len(offres)} ({part} %)")


if __name__ == "__main__":
    main()
