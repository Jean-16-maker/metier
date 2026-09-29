# Le marché de mon métier — les métiers du commerce international

Une veille quotidienne des offres d'emploi du commerce international : export,
import, développement commercial, achats, transit et douane. Chaque matin, une
Action GitHub interroge l'API France Travail, enregistre les offres du jour et
publie les chiffres sur GitHub Pages.

Adapté du dépôt de démonstration
[VincentFavarin/metier](https://github.com/VincentFavarin/metier) (métiers du
marketing, IAE Clermont Auvergne) : même chaîne API → données → Action planifiée
→ pages, autres métiers, autre grille d'outils.

| Page | |
|---|---|
| `index.html` | les filtres, les chiffres, la carte de France |
| `salaires.html` | fourchettes par niveau, métier, contrat, territoire |
| `exigences.html` | expérience, diplôme, outils, langues, compétences |
| `recruteurs.html` | entreprises, secteurs, employeurs ouverts aux débutants |
| `mouvement.html` | les extractions successives, la fraîcheur des annonces |

## Le métier, tel que le marché le nomme

- **Intitulé principal** : commercial / commerciale export
- **Variantes rencontrées dans les offres** : export area manager, responsable
  de zone, business developer international, assistant(e) import-export,
  ADV export, acheteur international, déclarant(e) en douane
- **Code ROME de référence** : **D1433** — Commercial / Commerciale export
  (ROME 4.0, arborescence du 15/06/2026)

## Les questions que je pose à ce marché

1. Combien d'offres, et où : ma région, l'Île-de-France, les ports et
   plateformes logistiques (Le Havre, Marseille, Lyon, Lille), l'étranger ?
2. Quels contrats et quels salaires affichés ?
3. Quelles langues, au-delà de l'anglais ? Quels savoirs techniques
   (Incoterms, douane, crédit documentaire, ERP) reviennent le plus ?
4. Quelles entreprises et quels secteurs recrutent : industriels exportateurs,
   négoce, commissionnaires de transport ?

## Les métiers suivis

23 codes ROME choisis parmi les 1 911 fiches du référentiel France Travail (la
liste vit dans `scripts/extraire.py`, `METIERS`), en quatre groupes :

- **International** — D1433 commercial export, D1414 responsable de zone
  internationale, D1429 assistant import-export, D1409 ADV (dont ADV export),
  N1204 coordinateur transit import-export.
- **Développement** — M1707 responsable du développement commercial (dont
  responsable commercial international), M1715 directeur commercial (dont
  export), D1406 directeur des ventes (dont ventes internationales), D1444
  responsable grands comptes, D1420 ingénieur d'affaires.
- **Achats & douane** — M1101 acheteur (dont acheteur international, sourcing),
  M1102 directeur des achats, D1431 assistant achat, N1202 agent de transit,
  N1203 déclarant en douane, N1205 responsable de service transit, N4106
  responsable de douane, N1201 affréteur.
- **Frontière**, décochés par défaut — D1402 commercial grands comptes, D1407
  technico-commercial, D1401 assistant commercial, M1703 chef de produit, N1301
  responsable logistique. Gros volumes, peu d'international : l'API plafonne à
  1 150 offres par requête, le détail de ces métiers est donc partiel.

La grille des outils et compétences cherchés dans les annonces (Incoterms,
douane, crédit documentaire, ERP/SAP, CRM, langues, déplacements…) est dans
`scripts/resumer.py`, `OUTILS` : adaptez-la.

## La chaîne

```
API France Travail  →  scripts/extraire.py  →  data/brut/<mois>/<ROME>.jsonl   chaque version d'annonce, une seule fois
                                            →  data/actives/<date>.csv         les offres actives du jour (rome, id)
                                            →  data/serie.csv                  par jour et par métier : total, nouvelles, modifiées
                       scripts/resumer.py   →  data/resume.json                ce que les pages affichent (+ data/geo/, cache des positions)
                       index.html + 4 pages →  https://vincentfavarin.github.io/metier/
                       .github/workflows/veille.yml : GitHub relance tout ça chaque matin à 7 h
```

- `scripts/extraire.py` — une requête `codeROME` par métier (token OAuth,
  pagination 150 / 1 150, total lu dans `Content-Range`). Le **brut est
  conservé intégralement** : une offre est écrite la première fois qu'on la
  voit, et de nouveau si son contenu change (empreinte SHA-1 du JSON, hors
  `dateActualisation`) — l'évolution d'une annonce est donc gardée, version
  par version. Relancer le même jour n'écrit rien deux fois.
- `scripts/resumer.py` — retravaille le brut des offres actives : salaires
  (libellé texte → min/max annuels bruts), outils cités dans les descriptions
  (grille à adapter), position (lat/lon de l'API, sinon centre de la commune
  via geo.api.gouv.fr, sinon ville principale du département).
- Cinq pages HTML statiques, un chantier par page, toutes servies telles quelles.
  Chacune charge `data/resume.json` et recalcule ses graphiques Chart.js dans le
  navigateur selon la sélection ; net mensuel estimé = brut × 0,78 / 12.
  - `index.html` — les filtres, les chiffres-clés, la carte Leaflet (survol =
    l'offre, clic = l'annonce sur France Travail), les départements, les
    contrats, et les liens vers les quatre autres pages.
  - `salaires.html` — ce que ça paie. `exigences.html` — ce qu'on vous demande.
    `recruteurs.html` — qui recrute. `mouvement.html` — le marché bouge, et les
    limites de ces chiffres (ancre `#limites`, liée depuis chaque pied de page).
- `assets/commun.js` et `assets/commun.css` — ce que les cinq pages partagent :
  chargement des données, panneau de filtres (mémorisé dans `localStorage`,
  replié ailleurs que sur l'accueil), barre de navigation, utilitaires et
  fabriques de graphiques. Une page ne contient que son HTML et son petit
  script `rendre(offres, D)`.

## Volume et limites GitHub

Mesuré sur la version marketing (≈ 3 400 offres) : jour 1, 13 Mo de brut ; ensuite seulement le flux (nouvelles et modifiées),
de l'ordre de 2 à 3 Mo par jour, soit ~1 Go par an. GitHub gratuit : dépôt
1 Go recommandé, fichier ≤ 100 Mo, Pages 1 Go publié et 100 Go/mois de bande
passante, Actions illimitées sur un dépôt public. Quand le brut dépassera
quelques centaines de Mo, l'Action archivera chaque mois écoulé (compressé)
dans les Releases du dépôt ou sur Hugging Face Datasets, et le dépôt ne
gardera que les derniers mois.

## Faire tourner chez soi

Windows :

```
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env        (puis remplir avec ses identifiants francetravail.io)
.venv\Scripts\python.exe scripts\extraire.py --verifier
.venv\Scripts\python.exe scripts\extraire.py
.venv\Scripts\python.exe scripts\resumer.py
.venv\Scripts\python.exe -m http.server 8125      (puis http://localhost:8125)
```

macOS / Linux :

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          (puis remplir avec ses identifiants francetravail.io)
.venv/bin/python scripts/extraire.py --verifier
.venv/bin/python scripts/extraire.py
.venv/bin/python scripts/resumer.py
.venv/bin/python -m http.server 8125           (puis http://localhost:8125)
```

## Faire tourner sans soi (GitHub)

1. Dépôt **public** (GitHub Pages gratuit ne fonctionne que sur un dépôt public).
2. Settings → Secrets and variables → Actions : `FT_CLIENT_ID` et `FT_CLIENT_SECRET`.
3. Settings → Pages → Source « Deploy from a branch », branche `main`, dossier `/ (root)`.
4. Actions → veille → Run workflow : le premier commit du bot arrive dans `data/`.

## Règles

- Les identifiants sont dans `.env` (local) ou dans les secrets du dépôt
  (GitHub) : jamais dans un fichier versionné.
- Un canal, une requête, une date : chaque chiffre du site les affiche.
- Pas de scraping de LinkedIn, APEC ou Indeed (interdit par leurs CGU).
