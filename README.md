# Le marché de mon métier — retail, expérience client et direction commerciale internationale

Une veille hebdomadaire des offres d'emploi visées par le master marketing-vente,
spécialité DCIB (direction commerciale et international business), et le
parcours management retail et expérience client. Chaque lundi à 8 h, une Action GitHub
interroge l'API France Travail, enregistre les offres du jour et publie les
chiffres sur GitHub Pages.

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
| `desordre.html` | le désordre de la base brute : ce qui manque, le format du salaire, les doublons, les positions (TD 1) |

## Les questions que je pose à ce marché

1. Combien d'offres, et où : ma région, l'Île-de-France, les grandes métropoles ?
2. Quels contrats et quels salaires affichés, du responsable de magasin au directeur commercial ?
3. Quelles langues, quels outils (CRM, ERP, merchandising, KPI) reviennent le plus ?
4. Quelles enseignes et quels secteurs recrutent : distribution, luxe, industrie, services ?

## Offres de Welcome to the Jungle

`data/externes/wttj.csv` : offres relevées dans le navigateur, page « jobs-matches » d'un compte connecté (rôle « responsable de magasin », France,
CDI, débutant) : lien de l'offre, métier ROME rattaché, intitulé, employeur, ville, salaire affiché, contrat, date de publication exacte.
Seules les offres qui affichent un salaire et ressemblent aux métiers suivis sont gardées (une dizaine de pages de résultats parcourues).

## Offres d'Adzuna

`data/externes/adzuna.csv` contient les offres Adzuna relevées dans le navigateur (recherche par métier, filtre « 30 derniers jours »
et salaire minimum, une page ou deux par recherche) : identifiant, métier ROME rattaché, intitulé, employeur, lieu (code INSEE), salaire tel qu'affiché.
`resumer.py` les fusionne avec celles de France Travail et applique les mêmes règles. Adzuna n'affiche ni la date exacte ni le contrat sur la liste :
la date est posée au milieu de la fenêtre (`date_approx`) et un contrat non lu est supposé CDI (`contrat_suppose`).
Pour en ajouter, complétez le CSV puis relancez `scripts/resumer.py`.

## Ce qui est gardé dans les chiffres

`scripts/resumer.py` (fonction `nettoyer`) ne garde que les annonces :
- publiées il y a **moins de 2 mois** (`AGE_MAX_JOURS`) ;
- avec un **nom d'entreprise** et un **salaire lisible** (`EXIGER_ENTREPRISE`, `EXIGER_SALAIRE`) ;
- qui ne viennent pas d'une **école ou d'un organisme de formation** (`ECOLES_NOM`, `ECOLES_SECTEUR`) ;
- en **CDI, CDD, intérim, alternance ou freelance** (champ `famille`) ;
- **sans doublon** : même employeur, même intitulé, même département, on garde la plus récente.

Le décompte de ce qui est retiré, et pourquoi, est écrit dans `data/resume.json` (`retires`).
Les consignes graphiques suivent le TD 1 du cours (data.iae-mod.fr) : trace du nettoyage avant le premier graphique (`trace` dans `data/resume.json`),
une phrase de lecture sous chaque graphique (ce qu'on voit, sur combien d'offres, à quelle date), tableaux d'effectifs et de fréquences,
expérience recodée en années, salaire minimum affiché décrit par médiane, moyenne, mode, écart-type, asymétrie et aplatissement face à la loi normale.
Les pages présentent les graphiques dans un ordre de lecture fixe : camemberts pour les parts,
colonnes dans l'ordre naturel (expérience, diplôme, salaire, âge), courbe pour le temps, barres classées pour les palmarès.

## Les métiers suivis

7 codes ROME (la liste vit dans `scripts/extraire.py`, `METIERS`), en deux groupes :

- **Retail & expérience client** — D1301 management de magasin de détail, D1302
  direction de boutique ou de point de vente, D1509 management du réseau
  commercial de détail (directeur de réseau, area manager, chef de secteur),
  M1704 management relation clientèle (expérience client, CRM, service client).
- **Direction commerciale & international** — M1707 stratégie commerciale
  (directeur commercial, export ou international, business developer), D1402
  relation commerciale grands comptes et entreprises (ingénieur d'affaires
  international, key account manager), H1102 management et ingénierie d'affaires.

Les libellés officiels des codes sont à vérifier avec `scripts/extraire.py --verifier`
puis `--rome <code>` : un code qui ne renvoie aucune offre est probablement mal recopié.

La grille des outils et compétences cherchés dans les annonces est dans
`scripts/resumer.py`, `OUTILS` : management d'équipe, merchandising, KPI,
expérience client (NPS), omnicanal, grands comptes, appels d'offres, import-export,
CRM/ERP et langues.

## La chaîne

```
API France Travail  →  scripts/extraire.py  →  data/brut/<mois>/<ROME>.jsonl   chaque version d'annonce, une seule fois
                                            →  data/actives/<date>.csv         les offres actives du jour (rome, id)
                                            →  data/serie.csv                  par jour et par métier : total, nouvelles, modifiées
                       scripts/resumer.py   →  data/resume.json                ce que les pages affichent (+ data/geo/, cache des positions)
                       index.html + 4 pages →  https://jean-16-maker.github.io/metier/
                       .github/workflows/veille.yml : GitHub relance tout ça chaque lundi à 8 h (heure de Paris)
```

- `scripts/extraire.py` — une recherche `codeROME` par métier, limitée aux annonces créées il y a moins de 62 jours. L'API plafonne à 1 150 offres par requête : quand une
  fenêtre de dates en contient davantage, elle est coupée en deux (`chercher_tout`) jusqu'à tout récupérer. Une requête `codeROME` (token OAuth,
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
- Le scraping de LinkedIn, APEC, Indeed ou Welcome to the Jungle est autorisé
  dans ce dépôt tant qu'il reste **partiel** : consultation ponctuelle de
  quelques pages de résultats, sans moisson exhaustive ni automatisation
  quotidienne. Ces sites l'interdisent dans leurs CGU : c'est un choix assumé
  par l'auteur du dépôt, à ses risques. Les chiffres issus de ces sources
  restent partiels et ne se mélangent pas à ceux de France Travail.
