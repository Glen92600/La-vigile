#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Générateur de site web — Veille Chanteloup-les-Vignes
Collecte les RSS, maintient une base d'articles (90 jours),
génère site/index.html automatiquement chaque matin.
"""

import feedparser, re, os, json
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
try:
    from zoneinfo import ZoneInfo
    TZ_PARIS = ZoneInfo("Europe/Paris")
except Exception:                       # repli si zoneinfo indisponible
    TZ_PARIS = timezone(timedelta(hours=2))

# ── Extraction d'images ────────────────────────────────────────────────────────
def extract_rss_image(entry):
    """Cherche une image directement dans l'entrée RSS."""
    try:
        if getattr(entry, "media_thumbnail", None):
            u = entry.media_thumbnail[0].get("url")
            if u: return u
        if getattr(entry, "media_content", None):
            u = entry.media_content[0].get("url")
            if u: return u
        for l in getattr(entry, "links", []):
            if l.get("type", "").startswith("image") or l.get("rel") == "enclosure":
                if l.get("href"): return l["href"]
        if getattr(entry, "enclosures", None):
            u = entry.enclosures[0].get("href")
            if u: return u
        blob = entry.get("summary", "") + str(entry.get("content", ""))
        m = re.search(r'<img[^>]+src=["\']([^"\']+)', blob)
        if m: return m.group(1)
    except Exception:
        pass
    return ""

def fetch_og_image(url, timeout=6):
    """Récupère l'og:image / twitter:image depuis la page de l'article."""
    if not url or "news.google.com" in url:
        return ""   # les liens Google News sont des redirections, pas d'og utile
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (veille-bot)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read(150000).decode("utf-8", "ignore")
        for pat in (
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        ):
            m = re.search(pat, html, re.I)
            if m:
                img = m.group(1).strip()
                if img.startswith("//"): img = "https:" + img
                return img
    except Exception:
        pass
    return ""

# ── Chemins ────────────────────────────────────────────────────────────────────
# Dérivé de l'emplacement du script → fonctionne en local ET dans le cloud (CI).
BASE        = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE, "articles_db.json")
SITE_DIR    = os.path.join(BASE, "site")
HTML_PATH   = os.path.join(SITE_DIR, "index.html")
RETENTION   = 90   # jours conservés en base

# ── Accès : mot de passe partagé à l'entrée du site ────────────────────────────
# On ne stocke ici QUE l'empreinte (hash) du mot de passe, jamais le mot de passe
# en clair — ainsi le dépôt peut être public sans révéler le mot de passe.
# Pour changer le mot de passe : calculer la nouvelle empreinte avec vhash(...)
# (même algo djb2 que côté JS) puis remplacer la valeur ci-dessous, et régénérer.
VIGIE_PASSWORD_HASH = "ce307a88"   # empreinte djb2 du mot de passe d'accès
def vhash(s):
    """Petit hachage (djb2) répliqué à l'identique en JS — sert à calculer
    l'empreinte d'un nouveau mot de passe. Barrière dissuasive, non inviolable."""
    h = 5381
    for ch in s:
        h = ((h * 33) + ord(ch)) & 0xFFFFFFFF
    return format(h, "x")

# ── Sources RSS étendues ───────────────────────────────────────────────────────
SOURCES = [
    # ── Chanteloup direct ──
    {
        "id": "chanteloup-gazette",
        "nom": "La Gazette en Yvelines",
        "url": "https://lagazette-yvelines.fr/category/votreville/chanteloup-les-vignes/feed/",
        "categorie": "chanteloup",
        "filtre": False,
    },
    {
        "id": "chanteloup-google",
        "nom": "Google Actualités",
        "url": "https://news.google.com/rss/search?q=%22Chanteloup-les-Vignes%22&hl=fr&gl=FR&ceid=FR:fr",
        "categorie": "chanteloup",
        "filtre": False,
    },
    {
        "id": "chanteloup-mantes",
        "nom": "Mantes-Actu",
        "url": "https://www.mantes-actu.net/feed/",
        "categorie": "chanteloup",
        "filtre": True,
        "mot_cle": "chanteloup",
    },
    {
        "id": "chanteloup-infos78",
        "nom": "InfosYvelines",
        "url": "https://www.infosyvelines.fr/rss",
        "categorie": "chanteloup",
        "filtre": True,
        "mot_cle": "chanteloup",
    },
    {
        "id": "chanteloup-parisien",
        "nom": "Le Parisien – Yvelines",
        "url": "https://feeds.leparisien.fr/leparisien/rss/yvelines-78",
        "categorie": "chanteloup",
        "filtre": True,
        "mot_cle": "chanteloup",
    },
    {
        "id": "chanteloup-google2",
        "nom": "Google Actualités",
        "url": "https://news.google.com/rss/search?q=%22Chanteloup+les+Vignes%22&hl=fr&gl=FR&ceid=FR:fr",
        "categorie": "chanteloup",
        "filtre": False,
    },
    {
        "id": "chanteloup-lanoe",
        "nom": "Google Actualités",
        "url": "https://news.google.com/rss/search?q=%22La+No%C3%A9%22+Chanteloup&hl=fr&gl=FR&ceid=FR:fr",
        "categorie": "chanteloup",
        "filtre": True,
        "mot_cle": "chanteloup",
    },
    {
        "id": "chanteloup-arenou",
        "nom": "Google Actualités",
        "url": "https://news.google.com/rss/search?q=%22Catherine+Arenou%22&hl=fr&gl=FR&ceid=FR:fr",
        "categorie": "chanteloup",
        "filtre": True,
        "mot_cle_liste": ["chanteloup","arenou"],
    },
    {
        "id": "chanteloup-france3",
        "nom": "France 3 Paris IDF",
        "url": "https://france3-regions.francetvinfo.fr/paris-ile-de-france/rss",
        "categorie": "chanteloup",
        "filtre": True,
        "mot_cle": "chanteloup",
    },
    {
        "id": "chanteloup-actu17",
        "nom": "Actu17",
        "url": "https://actu17.fr/feed/",
        "categorie": "chanteloup",
        "filtre": True,
        "mot_cle": "chanteloup",
    },
    {
        "id": "chanteloup-gazettecommunes",
        "nom": "La Gazette des communes",
        "url": "https://news.google.com/rss/search?q=%22Chanteloup-les-Vignes%22+site:lagazettedescommunes.com&hl=fr&gl=FR&ceid=FR:fr",
        "categorie": "chanteloup",
        "filtre": False,   # requête déjà ciblée sur le domaine + phrase exacte
    },
    # ── GPSEO ──
    {
        "id": "gpseo-google",
        "nom": "Google Actualités – GPSEO",
        "url": "https://news.google.com/rss/search?q=GPSEO+%22Grand+Paris+Seine+et+Oise%22&hl=fr&gl=FR&ceid=FR:fr",
        "categorie": "gpseo",
        "filtre": True,
        "mot_cle_liste": ["transport","bus","mobilité","logement","hlm","rénovation","emploi",
                          "culture","sport","loisirs","environnement","subvention","projet","budget",
                          "intercommunalité","travaux","habitat","social","jeunesse","éducation",
                          "collège","piscine","médiathèque","équipement","tarif","aide"],
    },
    # ── Yvelines département ──
    {
        "id": "yvelines-google",
        "nom": "Google Actualités – Yvelines",
        "url": "https://news.google.com/rss/search?q=Yvelines+78&hl=fr&gl=FR&ceid=FR:fr",
        "categorie": "yvelines",
        "filtre": True,
        "mot_cle_liste": ["collège","transport","aide sociale","subvention","route","caf",
                          "insertion","logement","budget","environnement","sécurité","police",
                          "allocations","services","emploi","formation"],
    },
    {
        "id": "gazette-yvelines",
        "nom": "La Gazette en Yvelines",
        "url": "https://lagazette-yvelines.fr/feed/",
        "categorie": "yvelines",
        "filtre": True,
        "mot_cle_liste": ["yvelines","gpseo","seine-et-oise","mantes","poissy","conflans",
                          "andrésy","achères","carrières","verneuil","triel"],
    },
]

# ── Presse nationale & territoriale (Google Actualités ciblé par domaine) ──────
# Ces médias couvrent régulièrement Chanteloup-les-Vignes (banlieue, faits divers,
# politique de la ville). Leur flux direct étant souvent bloqué aux robots, on cible
# le domaine via Google Actualités. La déduplication par titre évite les doublons.
_PRESSE_NATIONALE = [
    ("presse-lemonde",     "Le Monde",               "lemonde.fr"),
    ("presse-lefigaro",    "Le Figaro",              "lefigaro.fr"),
    ("presse-leparisien",  "Le Parisien",            "leparisien.fr"),
    ("presse-liberation",  "Libération",             "liberation.fr"),
    ("presse-20minutes",   "20 Minutes",             "20minutes.fr"),
    ("presse-bfmtv",       "BFM TV",                 "bfmtv.com"),
    ("presse-lepoint",     "Le Point",               "lepoint.fr"),
    ("presse-lobs",        "L'Obs",                  "nouvelobs.com"),
    ("presse-tf1info",     "TF1 Info",               "tf1info.fr"),
    ("presse-cnews",       "CNews",                  "cnews.fr"),
    ("presse-rtl",         "RTL",                    "rtl.fr"),
    ("presse-europe1",     "Europe 1",               "europe1.fr"),
    ("presse-marianne",    "Marianne",               "marianne.net"),
    ("presse-ouestfrance", "Ouest-France",           "ouest-france.fr"),
    ("presse-bondyblog",   "Bondy Blog",             "bondyblog.fr"),
    ("presse-actufr",      "actu.fr",                "actu.fr"),
    ("presse-localtis",    "Banque des Territoires", "banquedesterritoires.fr"),
]
for _sid, _nom, _dom in _PRESSE_NATIONALE:
    SOURCES.append({
        "id": _sid,
        "nom": _nom,
        "url": f"https://news.google.com/rss/search?q=%22Chanteloup-les-Vignes%22+site:{_dom}&hl=fr&gl=FR&ceid=FR:fr",
        "categorie": "chanteloup",
        "filtre": False,   # requête déjà ciblée (domaine + phrase exacte)
    })

# ── Catégories ────────────────────────────────────────────────────────────────
CATEGORIES = {
    "chanteloup": {
        "label": "Chanteloup-les-Vignes",
        "couleur": "#0F172A",
        "bg": "#EFF6FF",
        "border": "#0369A1",
        "sous_cats": [
            ("securite",  "#DC2626", ["police","incendie","accident","agression","crime","violence","émeute","garde à vue","interpellé","cambriolage"]),
            ("politique", "#7C3AED", ["maire","conseil municipal","élection","mandat","mairie","arenou","délibération","subvention","vote"]),
            ("education", "#059669", ["école","collège","lycée","jeune","enfant","éducation","classe","orchestre","musique","festival","sport","association","culture"]),
            ("sante",     "#0369A1", ["santé","médecin","hôpital","maison médicale","social","ccas","aide","service public"]),
            ("cadredevie","#D97706", ["travaux","voirie","transport","pont","aménagement","urbanisme","logement","parking","jardins","éclairage","rénovation"]),
        ],
    },
    "gpseo": {
        "label": "GPSEO",
        "couleur": "#7C3AED",
        "bg": "#FAF5FF",
        "border": "#7C3AED",
        "sous_cats": [],
    },
    "yvelines": {
        "label": "Yvelines",
        "couleur": "#0369A1",
        "bg": "#EFF6FF",
        "border": "#0369A1",
        "sous_cats": [],
    },
}

JOURS_FR = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
MOIS_FR  = ["","janvier","février","mars","avril","mai","juin",
            "juillet","août","septembre","octobre","novembre","décembre"]

def date_fr(dt):
    d = datetime.fromisoformat(dt) if isinstance(dt, str) else dt
    return f"{d.day} {MOIS_FR[d.month]} {d.year}"

def sous_cat(texte, sous_cats):
    for sid, _, mots in sous_cats:
        if any(m in texte for m in mots):
            return sid
    return "autre"

def couleur_sous_cat(sid, sous_cats):
    for s, c, _ in sous_cats:
        if s == sid:
            return c
    return "#64748B"

# ── Base de données ────────────────────────────────────────────────────────────
def charger_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def sauvegarder_db(articles):
    seuil = (datetime.now(timezone.utc) - timedelta(days=RETENTION)).isoformat()
    # Pruner les articles trop anciens
    articles = [a for a in articles if a.get("date","") >= seuil[:10]]
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    return articles

# ── Normalisation de titre (déduplication inter-sources) ──────────────────────
def norm_titre(titre):
    """Normalise un titre pour repérer les doublons entre sources.
    Retire le suffixe ' - NomDuMédia' ajouté par Google News, la ponctuation
    et les espaces superflus."""
    t = titre.strip()
    # Google News ajoute ' - Source' à la fin
    if " - " in t:
        t = t.rsplit(" - ", 1)[0]
    t = t.lower()
    t = re.sub(r"[^a-z0-9àâäéèêëïîôöùûüç]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()

# ── Éditeur réel derrière Google Actualités ────────────────────────────────────
def extract_publisher(entry, titre):
    """Récupère le vrai nom du média (Le Figaro, Actu.fr…) d'un item Google News."""
    src = getattr(entry, "source", None)
    if src:
        t = src.get("title") if isinstance(src, dict) else getattr(src, "title", None)
        if t:
            return t.strip()
    if " - " in titre:
        return titre.rsplit(" - ", 1)[1].strip()
    return ""

def clean_gnews_title(titre):
    """Retire le suffixe ' - Éditeur' que Google News ajoute en fin de titre."""
    return titre.rsplit(" - ", 1)[0].strip() if " - " in titre else titre

# ── Filtrage du bruit (annonces d'emploi, immobilier, courses hippiques…) ──────
NOISE_RE = re.compile(
    # Annonces d'emploi
    r"\b[HF]\s?/\s?[FH]\b|offre d['’ ]?emploi|figaro emploi|trouvez un emploi|"
    r"\bcdi\b|\bcdd\b|recrutement en cours|petites annonces|"
    # Annonces immobilières (ventes / locations de biens)
    r"\b(?:vente|location|achat|à\s+vendre|à\s+louer)\b[^|]*\b(?:maison|appartement|appart|studio|villa|duplex|loft|terrain|pavillon|garage|parking|local\s+commercial)\b|"
    r"\bprix\s+(?:au\s+)?m2\b|\bprix\s+m²|figaro\s+immobilier",
    re.I,
)
# Sources purement « petites annonces » ou hors-sujet (immobilier, courses hippiques)
SOURCES_BRUIT = {"figaro immobilier", "equidia", "paris-turf", "paris turf",
                 "geny", "geny courses", "zeturf", "zone-turf"}
def est_bruit(titre, source):
    if NOISE_RE.search(titre):
        return True
    s = source.lower()
    if "emploi" in s or "immobilier" in s:   # ex. « Figaro Emploi », « Figaro Immobilier »
        return True
    if s in SOURCES_BRUIT:
        return True
    return False

# ── Normalisation des noms de sources (doublons de casse) ──────────────────────
SOURCE_ALIASES = {
    "actu.fr": "Actu.fr",
    "franceinfo": "France Info",
    "ici.fr": "ici (France Bleu)",
}
def canon_source(nom):
    return SOURCE_ALIASES.get(nom.strip().lower(), nom.strip())

# ── Collecte RSS ───────────────────────────────────────────────────────────────
def collecter():
    maintenant = datetime.now(timezone.utc)
    seuil_90   = maintenant - timedelta(days=RETENTION)
    db         = charger_db()
    liens_connus  = {a["lien"] for a in db}
    titres_connus = {norm_titre(a.get("titre","")) for a in db}
    nouveaux   = []
    stats      = {}

    for src in SOURCES:
        sid  = src["id"]
        nom  = src["nom"]
        cat  = src["categorie"]
        stats[sid] = {"nom": nom, "cat": cat, "total": 0, "nouveaux": 0}
        is_google = "news.google.com" in src["url"]
        try:
            feed = feedparser.parse(src["url"])
            for entry in feed.entries:
                stats[sid]["total"] += 1
                titre  = entry.get("title","")
                resume = entry.get("summary","")
                lien   = entry.get("link","")
                texte  = (titre + " " + resume).lower()

                # Google News : récupérer le vrai éditeur + nettoyer le titre
                nom_aff = nom
                if is_google:
                    pub = extract_publisher(entry, titre)
                    if pub:
                        nom_aff = pub
                    titre = clean_gnews_title(titre)
                nom_aff = canon_source(nom_aff)

                # Exclure le bruit (annonces d'emploi, petites annonces…)
                if est_bruit(titre, nom_aff):
                    continue

                # Filtre mot-clé
                if src.get("filtre"):
                    if "mot_cle" in src:
                        if src["mot_cle"] not in texte:
                            continue
                    elif "mot_cle_liste" in src:
                        if not any(m in texte for m in src["mot_cle_liste"]):
                            continue

                # Filtre date
                pub = None
                if hasattr(entry, "published"):
                    try: pub = parsedate_to_datetime(entry.published)
                    except: pass
                if pub is None or pub < seuil_90:
                    continue

                # Dédup par lien
                if lien in liens_connus:
                    continue
                # Dédup par titre normalisé (même article via plusieurs requêtes)
                nt = norm_titre(titre)
                if nt and nt in titres_connus:
                    continue
                liens_connus.add(lien)
                titres_connus.add(nt)

                # Sous-catégorie
                sc = sous_cat(texte, CATEGORIES[cat]["sous_cats"]) if cat == "chanteloup" else "autre"

                resume_propre = re.sub(r"\s*The post .+$","",
                    re.sub(r"&nbsp;"," ",
                    re.sub(r"<[^>]+>","",resume))).strip()[:400]

                art = {
                    "source"   : nom_aff,
                    "titre"    : titre,
                    "lien"     : lien,
                    "date"     : pub.strftime("%Y-%m-%d"),
                    "date_iso" : pub.isoformat(),
                    "resume"   : resume_propre,
                    "categorie": cat,
                    "sous_cat" : sc,
                    "source_id": sid,
                    "image"    : extract_rss_image(entry),   # rapide, sans réseau
                }
                nouveaux.append(art)
                stats[sid]["nouveaux"] += 1

        except Exception as e:
            stats[sid]["erreur"] = str(e)

    db_maj = db + nouveaux
    db_maj.sort(key=lambda a: a["date_iso"], reverse=True)

    # ── Backfill og:image pour les articles récents visibles (borné) ──
    fetch_budget = 16
    for art in db_maj:
        if fetch_budget <= 0:
            break
        if art.get("image"):
            continue
        if art.get("img_checked"):
            continue
        art["image"] = fetch_og_image(art.get("lien", ""))
        art["img_checked"] = True
        fetch_budget -= 1

    db_maj = sauvegarder_db(db_maj)
    db_maj.sort(key=lambda a: a["date_iso"], reverse=True)
    return db_maj, stats, len(nouveaux)

# ── Génération HTML — SPA "La Presse" avec Home + Feed ────────────────────────
def generer_html(articles, stats, nb_nouveaux):
    maintenant    = datetime.now(TZ_PARIS)   # heure de Paris, même exécuté dans le cloud (UTC)
    today         = maintenant.strftime("%Y-%m-%d")
    date_hero     = f"{JOURS_FR[maintenant.weekday()].capitalize()} {maintenant.day} {MOIS_FR[maintenant.month]} {maintenant.year}"
    date_maj      = f"{date_hero} à {maintenant.strftime('%H:%M')}"
    nb_chanteloup = sum(1 for a in articles if a["categorie"] == "chanteloup")
    nb_gpseo      = sum(1 for a in articles if a["categorie"] == "gpseo")
    nb_yvelines   = sum(1 for a in articles if a["categorie"] == "yvelines")
    nb_today      = sum(1 for a in articles if a["date"] == today)
    nb_sources    = len({s["nom"] for s in SOURCES})   # médias distincts surveillés

    # Compteurs par thème (sous-catégorie effective)
    def _cateff(a):
        return a["sous_cat"] if (a.get("sous_cat") and a["sous_cat"] != "autre") else a["categorie"]
    _cc = {}
    for a in articles:
        k = _cateff(a); _cc[k] = _cc.get(k, 0) + 1
    nb_securite   = _cc.get("securite", 0)
    nb_politique  = _cc.get("politique", 0)
    nb_education  = _cc.get("education", 0)
    nb_sante      = _cc.get("sante", 0)
    nb_cadredevie = _cc.get("cadredevie", 0)

    # Sérialiser les articles en JSON pour le JS
    articles_json = json.dumps(articles, ensure_ascii=False)
    pw_hash = VIGIE_PASSWORD_HASH

    # ── Touche 3D : champ de particules en fond du hero (Three.js, chargé en ESM) ──
    # Défini comme chaîne normale (pas f-string) → les accolades JS restent littérales.
    # Discret, dans la palette de la marque ; coupé si l'utilisateur préfère moins
    # d'animations ; ne tourne que si le hero est visible et l'onglet actif.
    bg3d_script = r'''<script type="module">
(async () => {
  try {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const canvas = document.getElementById('bg3d');
    const hero = canvas && canvas.closest('.hero');
    if (!canvas || !hero) return;

    const THREE = await import('https://unpkg.com/three@0.161.0/build/three.module.js');

    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
    camera.position.z = 26;
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'low-power' });
    renderer.setClearColor(0x000000, 0);

    // Particules
    const COUNT = 130, SPREAD = 34, DEPTH = 18;
    const pos = new Float32Array(COUNT * 3);
    const col = new Float32Array(COUNT * 3);
    const vel = new Float32Array(COUNT * 3);
    const cOrange = new THREE.Color(0xE8640A);
    const cBlue   = new THREE.Color(0x7FB2E8);
    const cCream  = new THREE.Color(0xF3EFE6);
    for (let i = 0; i < COUNT; i++) {
      pos[i*3]   = (Math.random() - 0.5) * SPREAD;
      pos[i*3+1] = (Math.random() - 0.5) * SPREAD * 0.62;
      pos[i*3+2] = (Math.random() - 0.5) * DEPTH;
      const r = Math.random();
      const c = r < 0.34 ? cOrange : (r < 0.6 ? cBlue : cCream);
      col[i*3] = c.r; col[i*3+1] = c.g; col[i*3+2] = c.b;
      vel[i*3]   = (Math.random() - 0.5) * 0.012;
      vel[i*3+1] = (Math.random() - 0.5) * 0.012;
      vel[i*3+2] = (Math.random() - 0.5) * 0.012;
    }
    const pgeo = new THREE.BufferGeometry();
    pgeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    pgeo.setAttribute('color',    new THREE.BufferAttribute(col, 3));
    const pmat = new THREE.PointsMaterial({ size: 0.5, vertexColors: true, transparent: true, opacity: 0.95, depthWrite: false, sizeAttenuation: true });
    scene.add(new THREE.Points(pgeo, pmat));

    // Liens entre particules proches (réseau de veille)
    const MAXSEG = COUNT * 6;
    const linkPos = new Float32Array(MAXSEG * 6);
    const lgeo = new THREE.BufferGeometry();
    lgeo.setAttribute('position', new THREE.BufferAttribute(linkPos, 3));
    const lmat = new THREE.LineBasicMaterial({ color: 0x6E89B8, transparent: true, opacity: 0.22 });
    const lines = new THREE.LineSegments(lgeo, lmat);
    scene.add(lines);
    const points = scene.children[0];
    const LINK2 = 6.2 * 6.2;

    // Parallaxe souris (doux, façon ressort)
    let tx = 0, ty = 0, cx = 0, cy = 0;
    window.addEventListener('pointermove', (e) => {
      tx = e.clientX / window.innerWidth - 0.5;
      ty = e.clientY / window.innerHeight - 0.5;
    }, { passive: true });

    const VFOV = 60 * Math.PI / 180;
    function resize() {
      const w = hero.clientWidth, h = hero.clientHeight;
      if (!w || !h) return;
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      // Étirer le réseau pour couvrir toute la largeur visible
      // (sinon il reste concentré au centre sur les écrans larges)
      const visW = 2 * camera.position.z * Math.tan(VFOV / 2) * camera.aspect;
      const sx = Math.max(1, (visW * 1.08) / SPREAD);
      points.scale.x = lines.scale.x = sx;
    }
    resize();
    new ResizeObserver(resize).observe(hero);

    let onScreen = true, tabVisible = true, raf = 0;
    function loop() { cancelAnimationFrame(raf); if (onScreen && tabVisible) raf = requestAnimationFrame(tick); }
    new IntersectionObserver((es) => { onScreen = es[0].isIntersecting; loop(); }, { threshold: 0 }).observe(hero);
    document.addEventListener('visibilitychange', () => { tabVisible = !document.hidden; loop(); });

    function tick() {
      for (let i = 0; i < COUNT; i++) {
        for (let k = 0; k < 3; k++) {
          const idx = i*3 + k;
          pos[idx] += vel[idx];
          const lim = k === 2 ? DEPTH/2 : (k === 1 ? SPREAD*0.31 : SPREAD/2);
          if (pos[idx] > lim || pos[idx] < -lim) vel[idx] *= -1;
        }
      }
      pgeo.attributes.position.needsUpdate = true;

      let p = 0;
      for (let i = 0; i < COUNT && p < MAXSEG*6 - 6; i++) {
        for (let j = i + 1; j < COUNT; j++) {
          const dx = pos[i*3]-pos[j*3], dy = pos[i*3+1]-pos[j*3+1], dz = pos[i*3+2]-pos[j*3+2];
          if (dx*dx + dy*dy + dz*dz < LINK2) {
            linkPos[p++] = pos[i*3];   linkPos[p++] = pos[i*3+1]; linkPos[p++] = pos[i*3+2];
            linkPos[p++] = pos[j*3];   linkPos[p++] = pos[j*3+1]; linkPos[p++] = pos[j*3+2];
            if (p >= MAXSEG*6 - 6) break;
          }
        }
      }
      lgeo.attributes.position.needsUpdate = true;
      lgeo.setDrawRange(0, p / 3);

      cx += (tx - cx) * 0.04; cy += (ty - cy) * 0.04;
      const spin = performance.now() * 0.00002;
      points.rotation.y = lines.rotation.y = cx * 0.5 + spin;
      points.rotation.x = lines.rotation.x = -cy * 0.4;
      camera.position.x = cx * 4;
      camera.position.y = -cy * 3;
      camera.lookAt(0, 0, 0);

      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    }
    loop();
  } catch (e) { /* WebGL indisponible : on garde le fond CSS, sans erreur visible */ }
})();
</script>'''

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>La Vigie — Veille presse · Chanteloup-les-Vignes</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,wght@0,600;0,700;0,800;1,400;1,600&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --navy:    #0F172A;
  --navy2:   #1A2A42;
  --navy3:   #243B55;
  --orange:  #E8640A;
  --accent:  #0369A1;
  --paper:   #FAFAF5;
  --ink:     #0F172A;
  --muted:   #64748B;
  --border:  #E4E4DC;
  --card:    #FFFFFF;
  --r:       12px;
  /* Système d'élévation (style Stripe : ombres multi-couches douces) */
  --sh-sm: 0 1px 2px rgba(15,23,42,.04), 0 1px 3px rgba(15,23,42,.05);
  --sh-md: 0 2px 6px rgba(15,23,42,.05), 0 8px 24px rgba(15,23,42,.08);
  --sh-lg: 0 8px 20px rgba(15,23,42,.10), 0 24px 48px rgba(15,23,42,.10);
  /* Dégradé de marque (chaud) */
  --grad-warm: linear-gradient(120deg, #F59E0B 0%, #E8640A 55%, #DC2626 110%);
}}

*,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0; }}
html {{ scroll-behavior:smooth; }}
body {{ font-family:'DM Sans',sans-serif; background:var(--paper); color:var(--ink); min-height:100dvh; }}
.skip-link {{ position:absolute; left:-9999px; top:0; z-index:300; background:var(--navy); color:#fff; padding:.7rem 1.2rem; border-radius:0 0 8px 0; font-size:.82rem; font-weight:600; }}
.skip-link:focus {{ left:0; outline:2px solid var(--orange); outline-offset:-2px; }}

/* ═══════════ PORTE D'ENTRÉE (mot de passe) ═══════════ */
body.locked {{ overflow:hidden; }}
.gate {{ position:fixed; inset:0; z-index:10000; background:var(--navy); display:flex; align-items:center; justify-content:center; padding:1.5rem; overflow:hidden; }}
.gate::before {{ content:''; position:absolute; inset:-40%; z-index:0;
  background:
    radial-gradient(circle at 20% 30%, rgba(232,100,10,.45), transparent 42%),
    radial-gradient(circle at 80% 25%, rgba(3,105,161,.5), transparent 45%),
    radial-gradient(circle at 60% 75%, rgba(124,58,237,.38), transparent 48%);
  filter:blur(56px); animation:meshFlow 22s ease-in-out infinite alternate; }}
.gate-card {{ position:relative; z-index:1; text-align:center; width:100%; max-width:340px; }}
.gate-logo {{ font-family:'Newsreader',serif; font-size:2.5rem; font-weight:800; color:#fff; letter-spacing:-.03em; line-height:1; }}
.gate-logo span {{ color:var(--orange); }}
.gate-sub {{ font-size:.66rem; color:rgba(255,255,255,.5); text-transform:uppercase; letter-spacing:.14em; margin:.6rem 0 2.2rem; }}
.gate-form {{ display:flex; flex-direction:column; gap:.7rem; }}
.gate-label {{ font-size:.76rem; color:rgba(255,255,255,.7); margin-bottom:.3rem; }}
.gate-input {{ background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.22); border-radius:9px; padding:.8rem 1rem; color:#fff; font-family:'DM Sans',sans-serif; font-size:.95rem; outline:none; text-align:center; transition:border-color .2s, background .2s, box-shadow .2s; }}
.gate-input::placeholder {{ color:rgba(255,255,255,.4); }}
.gate-input:focus {{ border-color:var(--orange); background:rgba(255,255,255,.15); box-shadow:0 0 0 3px rgba(232,100,10,.18); }}
.gate-btn {{ background:var(--grad-warm); color:#fff; border:none; border-radius:9px; padding:.8rem; font-family:'DM Sans',sans-serif; font-size:.9rem; font-weight:600; cursor:pointer; transition:transform .15s, box-shadow .15s; box-shadow:var(--sh-md); }}
.gate-btn:hover {{ transform:translateY(-2px); box-shadow:0 10px 24px rgba(232,100,10,.3); }}
.gate-btn:active {{ transform:translateY(-1px) scale(.97); }}
.gate-err {{ color:#FCA5A5; font-size:.78rem; min-height:1.1em; margin:.2rem 0 0; }}

/* ── Grain texture ── */
body::after {{ content:''; position:fixed; inset:0; pointer-events:none; z-index:9999;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='0.032'/%3E%3C/svg%3E"); opacity:.5; }}

::-webkit-scrollbar {{ width:4px; }}
::-webkit-scrollbar-thumb {{ background:#CBD5E1; border-radius:4px; }}

/* ═══════════ PROGRESS BAR ═══════════ */
#progress-bar {{ position:fixed; top:0; left:0; height:2px; background:var(--orange); z-index:200; width:0; transition:width .08s linear; }}

/* ═══════════ NAV ═══════════ */
.nav {{ background:var(--navy); border-top:3px solid var(--orange); position:sticky; top:0; z-index:100; }}
.nav-inner {{ max-width:1320px; margin:0 auto; padding:0 1.5rem; display:flex; align-items:center; gap:1.5rem; min-height:62px; }}
.nav-logo {{ display:flex; align-items:center; gap:.7rem; cursor:pointer; white-space:nowrap; flex-shrink:0; }}
.nav-logo-chip {{ display:flex; align-items:center; background:#fff; border-radius:7px; padding:5px 8px; box-shadow:0 1px 5px rgba(0,0,0,.18); transition:transform .2s ease; }}
.nav-logo:hover .nav-logo-chip {{ transform:translateY(-1px); }}
.nav-logo-chip img {{ height:25px; width:auto; display:block; }}
.nav-logo-text {{ font-family:'Newsreader',serif; font-size:1.18rem; font-weight:800; color:#fff; letter-spacing:-.03em; }}
.nav-logo-text span {{ color:var(--orange); }}
.nav-links {{ display:flex; align-items:center; gap:.15rem; flex-shrink:0; }}
.nav-link {{ font-size:.75rem; font-weight:500; color:rgba(255,255,255,.5); padding:.35rem .85rem; border-radius:6px 6px 0 0; cursor:pointer; border:none; background:none; transition:color .18s ease, background .18s ease; white-space:nowrap; border-bottom:2px solid transparent; }}
.nav-link:hover {{ color:#fff; background:rgba(255,255,255,.07); }}
.nav-link.active {{ color:#fff; background:rgba(255,255,255,.1); border-bottom-color:var(--orange); }}
.nav-search {{ flex:1; max-width:280px; position:relative; }}
.nav-search input {{ width:100%; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.14); border-radius:20px; color:#fff; padding:.38rem 2rem .38rem .9rem; font-family:'DM Sans',sans-serif; font-size:.75rem; outline:none; transition:background .2s, border-color .2s, box-shadow .2s; }}
.nav-search input::placeholder {{ color:rgba(255,255,255,.45); }}
.nav-search input:focus {{ background:rgba(255,255,255,.13); border-color:var(--orange); box-shadow:0 0 0 3px rgba(232,100,10,.15); }}
.nav-search-icon {{ position:absolute; right:.65rem; top:50%; transform:translateY(-50%); width:13px; height:13px; color:rgba(255,255,255,.3); pointer-events:none; }}
.nav-search-clear {{ position:absolute; right:.55rem; top:50%; transform:translateY(-50%); display:none; background:rgba(255,255,255,.2); border:none; color:#fff; width:16px; height:16px; border-radius:50%; font-size:.7rem; cursor:pointer; align-items:center; justify-content:center; transition:background .15s; }}
.nav-search-clear.visible {{ display:flex; }}
.nav-search-clear:hover {{ background:rgba(255,255,255,.35); }}
.nav-badge {{ background:var(--grad-warm); color:#fff; font-size:.62rem; font-weight:700; padding:.22rem .65rem; border-radius:20px; white-space:nowrap; flex-shrink:0; animation:badgePulse 3s ease infinite; }}
@keyframes badgePulse {{ 0%,100% {{ box-shadow:0 0 0 0 rgba(232,100,10,.4); }} 50% {{ box-shadow:0 0 0 5px rgba(232,100,10,0); }} }}

/* ═══════════ VIEWS ═══════════ */
.view {{ display:none; }}
::view-transition-old(root), ::view-transition-new(root) {{ animation-duration:.35s; }}
.view.active {{ display:block; animation:viewIn .25s cubic-bezier(.4,0,.2,1) both; }}
@keyframes viewIn {{ from {{ opacity:0; transform:translateY(8px) scale(.995); }} to {{ opacity:1; transform:translateY(0) scale(1); }} }}

/* ═══════════ HOME ═══════════ */
.hero {{ background:var(--navy); position:relative; overflow:hidden; isolation:isolate; }}
/* Champ de particules 3D (Three.js) — sous le voile, au-dessus du dégradé */
#bg3d {{ position:absolute; inset:0; width:100%; height:100%; z-index:1; pointer-events:none; }}
/* Dégradé animé fluide — signature Stripe adaptée à la palette navy/orange */
.hero::before {{ content:''; position:absolute; inset:-40%; z-index:0;
  background:
    radial-gradient(circle at 18% 28%, rgba(232,100,10,.50), transparent 42%),
    radial-gradient(circle at 82% 18%, rgba(3,105,161,.55), transparent 45%),
    radial-gradient(circle at 62% 72%, rgba(124,58,237,.40), transparent 48%),
    radial-gradient(circle at 28% 82%, rgba(232,100,10,.34), transparent 44%),
    radial-gradient(circle at 92% 88%, rgba(5,150,105,.30), transparent 40%);
  filter:blur(56px); will-change:transform;
  animation:meshFlow 22s ease-in-out infinite alternate; }}
@keyframes meshFlow {{
  0%   {{ transform:translate(0,0) rotate(0deg) scale(1); }}
  50%  {{ transform:translate(3%,-2%) rotate(6deg) scale(1.12); }}
  100% {{ transform:translate(-2%,3%) rotate(-5deg) scale(1.18); }}
}}
/* Voile sombre pour la lisibilité du texte + grille éditoriale subtile */
.hero-overlay {{ position:absolute; inset:0; z-index:2;
  background:
    linear-gradient(105deg,rgba(15,23,42,.82) 0%,rgba(15,23,42,.55) 52%,rgba(15,23,42,.32) 100%),
    repeating-linear-gradient(0deg,transparent,transparent 39px,rgba(255,255,255,.022) 39px,rgba(255,255,255,.022) 40px); }}
/* Coupe diagonale vers le contenu (transition Stripe) */
.hero::after {{ content:''; position:absolute; left:0; right:0; bottom:-1px; height:64px; z-index:3;
  background:var(--paper); clip-path:polygon(0 100%, 100% 100%, 100% 32%); }}
.hero-inner {{ max-width:1320px; margin:0 auto; padding:4.5rem 1.5rem 5rem; position:relative; z-index:4; }}
.hero-eyebrow {{ font-family:'DM Mono',monospace; font-size:.62rem; text-transform:uppercase; letter-spacing:.16em; color:var(--orange); margin-bottom:.85rem; }}
.hero-title {{ font-family:'Newsreader',serif; font-size:clamp(2.8rem,7vw,6rem); font-weight:800; line-height:.92; letter-spacing:-.04em; color:#fff; margin-bottom:1.2rem; }}
.hero-title em {{ font-style:italic; background:var(--grad-warm); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; color:var(--orange); }}
.hero-intro {{ font-size:1rem; color:rgba(255,255,255,.82); line-height:1.6; max-width:540px; margin-bottom:1.4rem; }}
.hero-sub {{ font-size:.78rem; color:rgba(255,255,255,.6); letter-spacing:.07em; text-transform:uppercase; margin-bottom:2.5rem; }}
.hero-divider {{ width:100%; height:1px; background:rgba(255,255,255,.08); margin-bottom:2rem; }}
.hero-stats {{ display:flex; flex-wrap:wrap; gap:2.5rem; }}
.stat {{ display:flex; flex-direction:column; gap:.15rem; }}
.stat-num {{ font-family:'Newsreader',serif; font-size:2.5rem; font-weight:800; line-height:1; color:#fff; }}
.stat-num b {{ background:var(--grad-warm); -webkit-background-clip:text; background-clip:text; -webkit-text-fill-color:transparent; color:var(--orange); font-weight:inherit; }}
.stat-label {{ font-family:'DM Mono',monospace; font-size:.58rem; text-transform:uppercase; letter-spacing:.1em; color:rgba(255,255,255,.52); }}

.sec {{ max-width:1320px; margin:0 auto; padding:3rem 1.5rem; }}
.sec+.sec {{ padding-top:0; }}
.sec-rule {{ display:flex; align-items:center; gap:1rem; margin-bottom:1.75rem; }}
.sec-rule::before {{ content:''; display:block; width:28px; height:3px; background:var(--grad-warm); flex-shrink:0; border-radius:2px; }}
.sec-rule h2 {{ font-family:'DM Mono',monospace; font-size:.63rem; text-transform:uppercase; letter-spacing:.15em; color:var(--muted); }}
.sec-rule::after {{ content:''; flex:1; height:1px; background:var(--border); }}

/* Featured */
.feat-grid {{ display:grid; grid-template-columns:1.85fr 1fr; grid-template-rows:1fr 1fr; gap:1.1rem; min-height:390px; }}
.feat-main {{ grid-row:1/3; }}
.feat-card {{ background:var(--card); border:1px solid var(--border); border-radius:var(--r); overflow:hidden; display:flex; flex-direction:column; height:100%; transition:transform .25s cubic-bezier(.4,0,.2,1),box-shadow .25s,border-color .25s; box-shadow:var(--sh-sm); }}
.feat-card:hover {{ transform:translateY(-4px); box-shadow:var(--sh-lg); border-color:#D6D6CC; }}
.feat-color {{ height:4px; flex-shrink:0; }}
.feat-body {{ padding:1.25rem; flex:1; display:flex; flex-direction:column; gap:.65rem; }}
.feat-main .thumb {{ height:230px; }}
.feat-card:not(.feat-main) .thumb {{ height:128px; }}

/* ── Carte « une » façon couverture magazine (inspiration 21st.dev) ── */
.feat-hero {{ position:relative; display:block; overflow:hidden; min-height:340px; text-decoration:none; }}
.feat-hero .thumb {{ position:absolute; inset:0; height:100% !important; width:100%; }}
.feat-hero .thumb img {{ height:100%; width:100%; object-fit:cover; }}
.feat-hero-grad {{ position:absolute; inset:0; z-index:1; background:linear-gradient(to top, rgba(15,23,42,.95) 0%, rgba(15,23,42,.62) 40%, rgba(15,23,42,.1) 72%, rgba(15,23,42,.28) 100%); }}
.feat-hero-content {{ position:absolute; left:0; right:0; bottom:0; z-index:2; padding:1.7rem 1.7rem 1.5rem; }}
.feat-hero-tags {{ display:flex; align-items:center; gap:.5rem; margin-bottom:.75rem; }}
.feat-hero-badge {{ font-size:.6rem; font-weight:700; text-transform:uppercase; letter-spacing:.07em; color:#fff; padding:.22rem .6rem; border-radius:5px; }}
.feat-hero-new {{ font-size:.6rem; font-weight:700; text-transform:uppercase; letter-spacing:.07em; color:#fff; background:var(--orange); padding:.22rem .55rem; border-radius:5px; }}
.feat-hero-title {{ font-family:'Newsreader',serif; font-size:1.75rem; font-weight:800; line-height:1.18; color:#fff; letter-spacing:-.01em; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; text-shadow:0 1px 16px rgba(0,0,0,.35); }}
.feat-hero-meta {{ display:flex; align-items:center; gap:.5rem; margin-top:.85rem; font-family:'DM Mono',monospace; font-size:.65rem; color:rgba(255,255,255,.8); }}
.feat-hero-src {{ font-weight:500; color:#fff; }}
.feat-hero-dot {{ color:rgba(255,255,255,.45); }}
.feat-hero-read {{ margin-left:auto; color:#fff; font-weight:500; transition:color .18s; white-space:nowrap; }}
.feat-hero:hover .feat-hero-read {{ color:var(--orange); }}
.feat-hero:hover .thumb img {{ transform:scale(1.05); }}

/* ═══════════ VIGNETTES (images d'articles) ═══════════ */
.thumb {{ position:relative; width:100%; overflow:hidden; background:var(--navy); flex-shrink:0; }}
.thumb img {{ width:100%; height:100%; object-fit:cover; display:block; transition:transform .45s cubic-bezier(.4,0,.2,1); }}
.feat-card:hover .thumb img, .ccard:hover .thumb img {{ transform:scale(1.05); }}
.thumb-fallback {{ display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg, var(--c,#334155) 0%, #0F172A 145%); }}
.thumb-fallback::before {{ content:''; position:absolute; inset:0; background-image:repeating-linear-gradient(45deg, rgba(255,255,255,.045) 0 14px, transparent 14px 28px); }}
.thumb-src {{ display:none; position:relative; z-index:1; font-family:'Newsreader',serif; font-style:italic; font-weight:600; color:rgba(255,255,255,.95); font-size:1.05rem; line-height:1.3; text-align:center; padding:0 1.1rem; }}
.thumb-fallback .thumb-src {{ display:block; }}
.thumb-badge {{ position:absolute; top:.65rem; left:.65rem; z-index:2; font-size:.54rem; font-weight:700; text-transform:uppercase; letter-spacing:.07em; padding:.18rem .5rem; border-radius:4px; color:#fff; box-shadow:0 2px 6px rgba(0,0,0,.2); }}

/* ═══════════ CARROUSEL ═══════════ */
.carousel-wrap {{ position:relative; }}
.carousel {{ display:flex; gap:1.1rem; overflow-x:auto; scroll-snap-type:x mandatory; scroll-behavior:smooth; padding:.3rem .25rem 1rem; scrollbar-width:none; }}
.carousel::-webkit-scrollbar {{ display:none; }}
.ccard {{ scroll-snap-align:start; flex:0 0 300px; max-width:300px; background:var(--card); border:1px solid var(--border); border-radius:var(--r); overflow:hidden; display:flex; flex-direction:column; box-shadow:var(--sh-sm); transition:transform .25s cubic-bezier(.4,0,.2,1),box-shadow .25s,border-color .25s; text-decoration:none; }}
.ccard:hover {{ transform:translateY(-4px); box-shadow:var(--sh-lg); border-color:#D6D6CC; }}
.ccard .thumb {{ height:158px; }}
.ccard-body {{ padding:.9rem 1rem 1.05rem; display:flex; flex-direction:column; gap:.45rem; flex:1; }}
.ccard-byline {{ font-family:'DM Mono',monospace; font-size:.57rem; font-weight:500; text-transform:uppercase; letter-spacing:.1em; display:flex; align-items:center; gap:.4rem; }}
.ccard-byline-dot {{ width:5px; height:5px; border-radius:50%; flex-shrink:0; }}
.ccard-title {{ font-family:'Newsreader',serif; font-size:1rem; font-weight:700; line-height:1.32; color:var(--ink); display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
.ccard-date {{ margin-top:auto; font-family:'DM Mono',monospace; font-size:.6rem; color:var(--muted); }}
.car-btn {{ position:absolute; top:42%; transform:translateY(-50%); width:42px; height:42px; border-radius:50%; background:#fff; border:1px solid var(--border); box-shadow:var(--sh-md); cursor:pointer; display:flex; align-items:center; justify-content:center; z-index:5; transition:opacity .2s,background .2s,color .2s,transform .2s; color:var(--navy); }}
.car-btn:hover {{ background:var(--navy); color:#fff; transform:translateY(-50%) scale(1.07); }}
.car-btn:active {{ transform:translateY(-50%) scale(.95); }}
.car-btn:disabled {{ opacity:0; pointer-events:none; }}
.car-prev {{ left:-14px; }}
.car-next {{ right:-14px; }}
.car-btn svg {{ width:18px; height:18px; }}
.feat-byline {{ font-family:'DM Mono',monospace; font-size:.6rem; font-weight:500; text-transform:uppercase; letter-spacing:.12em; display:flex; align-items:center; gap:.4rem; }}
.feat-byline-dot {{ width:5px; height:5px; border-radius:50%; flex-shrink:0; }}
.feat-title-lg {{ font-family:'Newsreader',serif; font-size:1.5rem; font-weight:700; line-height:1.25; color:var(--ink); display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical; overflow:hidden; }}
.feat-title-sm {{ font-family:'Newsreader',serif; font-size:1.05rem; font-weight:700; line-height:1.3; color:var(--ink); display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
.feat-excerpt {{ font-size:.8rem; color:var(--muted); line-height:1.65; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
.feat-footer {{ margin-top:auto; padding:.85rem 1.25rem; border-top:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; }}
.feat-date {{ font-family:'DM Mono',monospace; font-size:.6rem; color:var(--muted); }}
.feat-link {{ font-size:.7rem; font-weight:600; color:var(--accent); text-decoration:none; display:inline-flex; align-items:center; gap:.25rem; transition:color .15s; }}
.feat-link:hover {{ color:var(--navy); }}
.feat-link svg {{ width:10px; height:10px; }}

/* Themes */
/* Thèmes : pastilles élégantes (icône + libellé) */
.theme-chips {{ display:flex; flex-wrap:wrap; gap:.6rem; }}
.theme-chip {{ display:inline-flex; align-items:center; gap:.5rem; font-family:'DM Sans',sans-serif; font-size:.8rem; font-weight:500; color:var(--ink); background:var(--card); border:1px solid var(--border); border-radius:30px; padding:.5rem .95rem .5rem .55rem; cursor:pointer; transition:border-color .2s cubic-bezier(.4,0,.2,1), transform .2s cubic-bezier(.4,0,.2,1), box-shadow .2s; box-shadow:var(--sh-sm); }}
.theme-chip img {{ width:24px; height:24px; border-radius:7px; }}
.theme-chip:hover {{ border-color:var(--navy); transform:translateY(-2px); box-shadow:var(--sh-md); }}
.theme-chip:active {{ transform:translateY(-1px) scale(.97); }}

/* Sources */
/* Panneau « pouls de la veille » */
.pulse-panel {{ display:grid; grid-template-columns:1.5fr 1px 1fr; gap:1.8rem; background:var(--card); border:1px solid var(--border); border-radius:var(--r); padding:1.5rem 1.7rem; box-shadow:var(--sh-sm); }}
.pulse-divider {{ background:var(--border); }}
.pulse-label {{ display:flex; align-items:baseline; justify-content:space-between; gap:.75rem; font-family:'DM Mono',monospace; font-size:.62rem; text-transform:uppercase; letter-spacing:.12em; color:var(--muted); margin-bottom:1.1rem; padding-bottom:.6rem; border-bottom:1px solid var(--border); }}
.pulse-label span {{ font-size:.6rem; color:#94A3B8; letter-spacing:.06em; }}
.pulse-label b {{ color:var(--orange); font-weight:600; }}
/* Sources : liste classée avec barres fines */
.src-list {{ display:flex; flex-direction:column; gap:.7rem; }}
.src-row {{ display:grid; grid-template-columns:1fr 64px 26px; align-items:center; gap:.7rem; }}
.src-row-name {{ font-size:.74rem; color:var(--ink); font-weight:500; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.src-row-bar {{ height:6px; background:#EEF1F5; border-radius:3px; overflow:hidden; }}
.src-row-bar i {{ display:block; height:100%; background:linear-gradient(90deg,#2E6DB4,#0369A1); border-radius:3px; }}
.src-row-n {{ font-family:'DM Mono',monospace; font-size:.72rem; color:var(--muted); text-align:right; }}
.src-name {{ font-family:'DM Mono',monospace; font-size:.65rem; color:var(--ink); font-weight:500; }}
.src-count {{ font-family:'Newsreader',serif; font-size:1.4rem; font-weight:700; color:var(--orange); }}
.src-zero {{ color:var(--border); }}

/* CTA */
.cta-wrap {{ text-align:center; padding:1.5rem 0 2.5rem; }}
.cta-btn {{ position:relative; display:inline-flex; align-items:center; gap:.6rem; background:var(--navy); color:#fff; font-family:'DM Sans',sans-serif; font-size:.85rem; font-weight:600; padding:.9rem 1.9rem; border-radius:10px; border:none; cursor:pointer; overflow:hidden; transition:transform .2s cubic-bezier(.4,0,.2,1),box-shadow .2s; box-shadow:var(--sh-md); z-index:0; }}
.cta-btn::before {{ content:''; position:absolute; inset:0; z-index:-1; background:var(--grad-warm); opacity:0; transition:opacity .25s ease; }}
.cta-btn:hover {{ transform:translateY(-2px); box-shadow:0 10px 28px rgba(232,100,10,.32); }}
.cta-btn:active {{ transform:translateY(-1px) scale(.97); }}
.cta-btn:hover::before {{ opacity:1; }}
.cta-btn:focus-visible {{ outline:2px solid var(--orange); outline-offset:3px; }}
.cta-btn svg {{ width:14px; height:14px; transition:transform .2s; }}
.cta-btn:hover svg {{ transform:translateX(3px); }}

/* ═══════════ FEED (sidebar de filtres + contenu) ═══════════ */
.feed-layout {{ max-width:1320px; margin:0 auto; padding:1.6rem 1.5rem 2rem; display:grid; grid-template-columns:228px 1fr; gap:1.8rem; align-items:start; }}
.feed-sidebar {{ position:sticky; top:80px; display:flex; flex-direction:column; gap:1.5rem; }}
.filter-group {{ display:flex; flex-direction:column; gap:.25rem; }}
.filter-group-label {{ font-family:'DM Mono',monospace; font-size:.57rem; text-transform:uppercase; letter-spacing:.14em; color:#94A3B8; padding:0 .7rem .4rem; }}
.fbtn {{ display:flex; align-items:center; gap:.6rem; width:100%; font-family:'DM Sans',sans-serif; font-size:.78rem; font-weight:500; padding:.5rem .7rem; border-radius:8px; border:1px solid transparent; color:#475569; background:transparent; cursor:pointer; transition:background .16s, color .16s, transform .16s ease-out; text-align:left; }}
.fbtn:hover {{ background:#EEF1F6; color:var(--navy); }}
.fbtn:active {{ transform:scale(.98); }}
.fbtn.active {{ background:var(--navy); color:#fff; box-shadow:var(--sh-sm); }}
.fbtn-l {{ flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.fbtn-c {{ font-family:'DM Mono',monospace; font-size:.62rem; opacity:.5; }}
.fbtn.active .fbtn-c {{ opacity:.85; }}
.fbtn img {{ width:18px; height:18px; border-radius:5px; flex-shrink:0; }}
.fdot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}

.feed-main {{ min-width:0; }}
.feed-toolbar {{ display:flex; align-items:center; justify-content:space-between; gap:1rem; padding-bottom:.9rem; margin-bottom:1.1rem; border-bottom:1px solid var(--border); }}
.results-count {{ font-family:'DM Mono',monospace; font-size:.7rem; color:var(--muted); white-space:nowrap; }}
.results-count b {{ color:var(--ink); font-size:.95rem; }}
.filter-clear {{ font-size:.7rem; font-weight:600; color:var(--orange); background:none; border:none; cursor:pointer; padding:.3rem .6rem; border-radius:6px; transition:background .15s; display:none; white-space:nowrap; }}
.filter-clear.visible {{ display:block; }}
.filter-clear:hover {{ background:rgba(232,100,10,.08); }}

/* Date group headers */
.date-group {{ grid-column:1/-1; display:flex; align-items:center; gap:1rem; padding:.4rem 0 .2rem; }}
.date-group:first-child {{ padding-top:0; }}
.date-group-label {{ font-family:'DM Mono',monospace; font-size:.6rem; text-transform:uppercase; letter-spacing:.14em; color:var(--muted); white-space:nowrap; }}
.date-group::after {{ content:''; flex:1; height:1px; background:var(--border); }}

/* Grille articles (dans le contenu) */
.art-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(252px,1fr)); gap:1.1rem; align-items:start; }}
.card .thumb {{ height:146px; }}

/* ═══════════ CARTE ═══════════ */
.card {{ background:var(--card); border:1px solid var(--border); border-radius:var(--r); overflow:hidden; display:flex; flex-direction:column; box-shadow:var(--sh-sm); animation:fadeUp .32s ease both; transition:transform .25s cubic-bezier(.4,0,.2,1),box-shadow .25s,border-color .25s; }}
.card:hover {{ transform:translateY(-5px); box-shadow:var(--sh-lg); border-color:#D6D6CC; }}
@keyframes fadeUp {{ from {{ opacity:0; transform:translateY(12px); }} to {{ opacity:1; transform:translateY(0); }} }}

/* ═══════════ RÉVÉLATION AU DÉFILEMENT ═══════════ */
.reveal {{ opacity:0; transform:translateY(24px); transition:opacity .7s cubic-bezier(.16,1,.3,1), transform .7s cubic-bezier(.16,1,.3,1); }}
.reveal.in {{ opacity:1; transform:none; }}

/* ═══════════ FOCUS ACCESSIBLE ═══════════ */
:focus-visible {{ outline:2px solid var(--orange); outline-offset:3px; border-radius:4px; }}
.nav-link:focus-visible, .fbtn:focus-visible, .theme-chip:focus-visible {{ outline-offset:2px; }}

/* ═══════════ POINT « EN DIRECT » ═══════════ */
.live-dot {{ display:inline-block; width:7px; height:7px; border-radius:50%; background:#34D399; position:relative; flex-shrink:0; }}
.live-dot::after {{ content:''; position:absolute; inset:-4px; border-radius:50%; background:#34D399; opacity:.5; animation:livePulse 2.2s ease-out infinite; }}
@keyframes livePulse {{ 0% {{ transform:scale(.6); opacity:.6; }} 100% {{ transform:scale(2.2); opacity:0; }} }}

/* ═══════════ GRAPHE DE TENDANCE (14 jours) ═══════════ */
.trend-card {{ background:var(--card); border:1px solid var(--border); border-radius:var(--r); padding:1.4rem 1.5rem 1.1rem; box-shadow:var(--sh-sm); }}
.trend-head {{ display:flex; align-items:baseline; justify-content:space-between; gap:1rem; margin-bottom:1rem; flex-wrap:wrap; }}
.trend-total {{ font-family:'Newsreader',serif; }}
.trend-total b {{ font-size:1.7rem; font-weight:800; color:var(--ink); }}
.trend-total span {{ font-size:.78rem; color:var(--muted); margin-left:.4rem; }}
.trend-legend {{ font-family:'DM Mono',monospace; font-size:.6rem; color:var(--muted); text-transform:uppercase; letter-spacing:.1em; }}
.trend-bars {{ display:flex; align-items:flex-end; gap:.4rem; height:88px; }}
.trend-col {{ flex:1; display:flex; flex-direction:column; align-items:center; gap:.4rem; min-width:0; }}
.trend-bar {{ width:100%; max-width:26px; border-radius:5px 5px 2px 2px; background:linear-gradient(180deg,#2E6DB4,#0369A1); transition:height .8s cubic-bezier(.16,1,.3,1), background .2s; cursor:default; position:relative; }}
.trend-bar.today {{ background:var(--grad-warm); }}
.trend-bar:hover {{ filter:brightness(1.08); }}
.trend-bar:hover .trend-tip {{ opacity:1; transform:translate(-50%,-6px); }}
.trend-tip {{ position:absolute; bottom:100%; left:50%; transform:translate(-50%,0); background:var(--navy); color:#fff; font-size:.6rem; font-family:'DM Mono',monospace; padding:.18rem .45rem; border-radius:4px; white-space:nowrap; opacity:0; pointer-events:none; transition:opacity .2s, transform .2s; }}
.trend-x {{ font-family:'DM Mono',monospace; font-size:.56rem; color:#64748B; }}

/* ═══════════ SUJETS DU MOMENT ═══════════ */
.kw-row {{ display:flex; flex-wrap:wrap; gap:.5rem; }}
.kw-chip {{ display:inline-flex; align-items:center; gap:.4rem; font-size:.74rem; font-weight:500; color:var(--ink); background:var(--card); border:1px solid var(--border); border-radius:20px; padding:.35rem .85rem; cursor:pointer; transition:border-color .18s cubic-bezier(.4,0,.2,1), background .18s cubic-bezier(.4,0,.2,1), color .18s, transform .18s cubic-bezier(.4,0,.2,1), box-shadow .18s; }}
.kw-chip:hover {{ border-color:var(--navy); background:var(--navy); color:#fff; transform:translateY(-2px); box-shadow:var(--sh-md); }}
.kw-chip:active {{ transform:translateY(-1px) scale(.97); }}
.kw-chip b {{ font-family:'DM Mono',monospace; font-size:.6rem; color:#C2410C; font-weight:600; }}
.kw-chip:hover b {{ color:#FBBF24; }}

.card-top {{ height:3px; flex-shrink:0; }}
.card-body {{ padding:1rem; flex:1; display:flex; flex-direction:column; gap:.5rem; }}
/* Byline = SOURCE EN TÊTE, bien visible */
.card-byline {{ display:flex; align-items:center; gap:.45rem; }}
.card-byline-dot {{ width:5px; height:5px; border-radius:50%; flex-shrink:0; }}
.card-byline-name {{ font-family:'DM Mono',monospace; font-size:.62rem; font-weight:500; text-transform:uppercase; letter-spacing:.1em; line-height:1; }}
.card-byline-sep {{ color:var(--border); font-size:.6rem; }}
.card-byline-date {{ font-family:'DM Mono',monospace; font-size:.6rem; color:var(--muted); }}
.card-title {{ font-family:'Newsreader',serif; font-size:.97rem; font-weight:700; line-height:1.38; color:var(--ink); display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
.card-excerpt {{ font-size:.75rem; color:#64748B; line-height:1.6; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
.card-bottom {{ padding:.6rem 1rem; border-top:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; gap:.5rem; }}
.card-tag {{ font-size:.58rem; font-weight:600; text-transform:uppercase; letter-spacing:.06em; padding:.15rem .5rem; border-radius:4px; white-space:nowrap; }}
.badge-new {{ font-size:.57rem; font-weight:700; text-transform:uppercase; letter-spacing:.08em; padding:.14rem .48rem; background:var(--orange); color:#fff; border-radius:4px; white-space:nowrap; }}
.card-link {{ font-size:.7rem; font-weight:600; color:var(--accent); text-decoration:none; display:inline-flex; align-items:center; gap:.22rem; transition:color .15s; flex-shrink:0; }}
.card-link:hover {{ color:var(--navy); }}
.card-link svg {{ width:10px; height:10px; }}

/* Empty state */
.empty-state {{ grid-column:1/-1; text-align:center; padding:5rem 2rem; display:flex; flex-direction:column; align-items:center; }}
.empty-line {{ width:32px; height:3px; background:var(--orange); margin-bottom:1.4rem; border-radius:2px; }}
.empty-title {{ font-family:'Newsreader',serif; font-style:italic; font-size:1.35rem; color:#94A3B8; margin-bottom:.4rem; }}
.empty-sub {{ font-size:.78rem; color:#64748B; }}
.empty-reset {{ margin-top:1rem; font-size:.75rem; font-weight:600; color:var(--accent); background:none; border:none; cursor:pointer; padding:.4rem .8rem; border-radius:6px; transition:background .15s; }}
.empty-reset:hover {{ background:rgba(3,105,161,.08); }}

/* ═══════════ BACK TO TOP ═══════════ */
#back-top {{ position:fixed; bottom:1.75rem; right:1.75rem; width:40px; height:40px; background:var(--navy); color:#fff; border:none; border-radius:50%; cursor:pointer; display:none; align-items:center; justify-content:center; box-shadow:0 4px 16px rgba(15,23,42,.25); transition:background .2s cubic-bezier(.4,0,.2,1), transform .2s cubic-bezier(.4,0,.2,1); z-index:90; }}
#back-top.visible {{ display:flex; animation:fadeUp .25s ease both; }}
#back-top:hover {{ background:var(--orange); transform:translateY(-2px); }}
#back-top:active {{ transform:translateY(-1px) scale(.94); }}
#back-top svg {{ width:16px; height:16px; }}

/* ═══════════ TOAST ═══════════ */
#toast {{ position:fixed; bottom:1.75rem; left:50%; transform:translateX(-50%) translateY(10px); background:var(--navy); color:#fff; font-size:.75rem; padding:.6rem 1.2rem; border-radius:20px; white-space:nowrap; opacity:0; transition:transform .3s ease, opacity .3s ease; z-index:80; pointer-events:none; border-left:3px solid var(--orange); }}
#toast.show {{ opacity:1; transform:translateX(-50%) translateY(0); }}

/* ═══════════ FOOTER ═══════════ */
.site-footer {{ background:var(--navy); border-top:3px solid var(--orange); padding:1.5rem; margin-top:2.5rem; }}
.footer-inner {{ max-width:1320px; margin:0 auto; display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:1rem; }}
.footer-logo {{ font-family:'Newsreader',serif; font-size:1.1rem; font-weight:800; color:#fff; letter-spacing:-.02em; }}
.footer-links {{ display:flex; justify-content:center; gap:1.5rem; }}
.footer-link {{ font-size:.66rem; color:rgba(255,255,255,.58); text-decoration:none; transition:color .15s; }}
.footer-link:hover {{ color:rgba(255,255,255,.8); }}
.footer-date {{ font-size:.64rem; color:rgba(255,255,255,.5); font-family:'DM Mono',monospace; text-align:right; }}

/* ═══════════ RESPONSIVE ═══════════ */
@media (max-width:900px) {{
  .feat-grid {{ grid-template-columns:1fr; }}
  .feat-main {{ grid-row:auto; }}
  .hero-title {{ font-size:clamp(2.5rem,10vw,4rem); }}
  .footer-inner {{ grid-template-columns:1fr; text-align:center; }}
  .footer-links {{ justify-content:center; }}
  .footer-date {{ text-align:center; }}
  /* La sidebar de filtres devient une barre horizontale */
  .feed-layout {{ grid-template-columns:1fr; gap:1rem; padding-top:0; }}
  .feed-sidebar {{ position:sticky; top:62px; z-index:40; flex-direction:row; gap:.45rem; overflow-x:auto; scrollbar-width:none; background:var(--paper); padding:.7rem 1.5rem; margin:0 -1.5rem; border-bottom:1px solid var(--border); }}
  .feed-sidebar::-webkit-scrollbar {{ display:none; }}
  .filter-group {{ flex-direction:row; gap:.4rem; }}
  .filter-group-label {{ display:none; }}
  .fbtn {{ width:auto; flex-shrink:0; border:1.5px solid var(--border); border-radius:20px; padding:.4rem .85rem; white-space:nowrap; }}
  .fbtn .fbtn-l {{ flex:none; }}
  .fbtn.active {{ border-color:var(--navy); }}
}}
@media (max-width:540px) {{
  .hero-inner {{ padding:2.5rem 1rem 2.5rem; }}
  .sec {{ padding:2rem 1rem; }}
  .feed-layout {{ padding:0 1rem 1.5rem; }}
  .feed-sidebar {{ padding:.7rem 1rem; margin:0 -1rem; }}
  .art-grid {{ gap:.85rem; grid-template-columns:1fr; }}
  .nav-badge {{ display:none; }}
  .car-btn {{ display:none; }}
  .ccard {{ flex:0 0 82%; max-width:82%; }}
  /* Cibles tactiles confortables (≈44px) sur mobile */
  .nav-link {{ min-height:42px; display:inline-flex; align-items:center; }}
  .fbtn {{ min-height:40px; }}
  .pulse-panel {{ grid-template-columns:1fr; gap:1.4rem; }}
  .pulse-divider {{ display:none; }}
  .kw-chip {{ min-height:40px; }}
  .theme-chip {{ min-height:42px; }}
  .nav-search input {{ min-height:40px; }}
}}
@media (prefers-reduced-motion:reduce) {{
  *,*::before,*::after {{ animation-duration:.01ms !important; transition-duration:.01ms !important; }}
  .reveal {{ opacity:1 !important; transform:none !important; }}
}}
</style>
</head>
<body>

<!-- ══════════ PORTE D'ENTRÉE (mot de passe partagé) ══════════ -->
<div id="gate" class="gate">
  <div class="gate-card">
    <div class="gate-logo">La <span>Vigie</span></div>
    <p class="gate-sub">Revue de presse · Chanteloup-les-Vignes</p>
    <form id="gate-form" class="gate-form" autocomplete="off">
      <label for="gate-pw" class="gate-label">Accès réservé — saisissez le mot de passe</label>
      <input id="gate-pw" type="password" class="gate-input" placeholder="Mot de passe" autocomplete="current-password" aria-label="Mot de passe">
      <button type="submit" class="gate-btn">Entrer</button>
      <p id="gate-err" class="gate-err" role="alert"></p>
    </form>
  </div>
</div>
<script>
(function(){{
  var H="{pw_hash}";
  function vh(s){{var h=5381;for(var i=0;i<s.length;i++){{h=((h*33)+s.charCodeAt(i))>>>0;}}return h.toString(16);}}
  var KEY="vigie_auth", gate=document.getElementById('gate');
  function unlock(){{ gate.style.display='none'; document.body.classList.remove('locked'); }}
  try{{ if(localStorage.getItem(KEY)===H){{ unlock(); return; }} }}catch(e){{}}
  document.body.classList.add('locked');
  document.getElementById('gate-form').addEventListener('submit',function(e){{
    e.preventDefault();
    var pw=document.getElementById('gate-pw').value;
    if(vh(pw)===H){{ try{{localStorage.setItem(KEY,H);}}catch(e){{}} unlock(); }}
    else {{ document.getElementById('gate-err').textContent="Mot de passe incorrect."; document.getElementById('gate-pw').value=''; document.getElementById('gate-pw').focus(); }}
  }});
  var inp=document.getElementById('gate-pw'); if(inp) inp.focus();
}})();
</script>

<a class="skip-link" href="#view-home">Aller au contenu</a>
<div id="progress-bar" role="progressbar" aria-hidden="true"></div>

<!-- ══════════ NAV ══════════ -->
<nav class="nav" role="navigation" aria-label="Navigation principale">
  <div class="nav-inner">
    <div class="nav-logo" onclick="goHome()" role="button" tabindex="0" aria-label="Accueil — Ville de Chanteloup-les-Vignes">
      <span class="nav-logo-text">La <span>Vigie</span></span>
    </div>
    <div class="nav-links" role="list">
      <button class="nav-link active" id="btn-home" onclick="goHome()" role="listitem">Accueil</button>
      <button class="nav-link"        id="btn-feed" onclick="goFeed()"  role="listitem">Articles</button>
    </div>
    <div class="nav-search" role="search">
      <input id="search" type="search" placeholder="Rechercher…" oninput="onSearch()" aria-label="Rechercher un article">
      <button class="nav-search-clear" id="search-clear" onclick="clearSearch()" aria-label="Effacer la recherche">×</button>
      <svg class="nav-search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
      </svg>
    </div>
    <div class="nav-badge" aria-label="{nb_nouveaux} nouveaux articles aujourd'hui">+{nb_nouveaux} aujourd'hui</div>
  </div>
</nav>

<!-- ══════════ VUE HOME ══════════ -->
<div id="view-home" class="view active" role="main" tabindex="-1">

  <section class="hero" aria-labelledby="hero-h1">
    <canvas id="bg3d" aria-hidden="true"></canvas>
    <div class="hero-overlay" aria-hidden="true"></div>
    <div class="hero-inner">
      <p class="hero-eyebrow" style="display:flex;align-items:center;gap:.5rem"><span class="live-dot" aria-hidden="true"></span> Veille active · {date_hero}</p>
      <h1 class="hero-title" id="hero-h1">La Vigie<br><em>de Chanteloup</em></h1>
      <p class="hero-intro">Toute la presse qui parle de Chanteloup-les-Vignes et de son territoire, réunie et actualisée en continu, du média local au titre national.</p>
      <p class="hero-sub">Ville de Chanteloup-les-Vignes &nbsp;·&nbsp; {nb_sources} médias &nbsp;·&nbsp; 90 jours</p>
      <div class="hero-divider" aria-hidden="true"></div>
      <div class="hero-stats" role="list" aria-label="Statistiques">
        <div class="stat" role="listitem"><div class="stat-num" id="cnt-total">0</div><div class="stat-label">Archivés</div></div>
        <div class="stat" role="listitem"><div class="stat-num"><b>{nb_today}</b></div><div class="stat-label">Aujourd'hui</div></div>
        <div class="stat" role="listitem"><div class="stat-num" id="cnt-chan">0</div><div class="stat-label">Chanteloup</div></div>
        <div class="stat" role="listitem"><div class="stat-num" id="cnt-gpseo">0</div><div class="stat-label">GPSEO</div></div>
        <div class="stat" role="listitem"><div class="stat-num" id="cnt-yv">0</div><div class="stat-label">Yvelines</div></div>
      </div>
    </div>
  </section>

  <section class="sec reveal" aria-labelledby="sec-sujets" id="sujets-section">
    <div class="sec-rule"><h2 id="sec-sujets">Sujets du moment</h2></div>
    <div id="keywords" class="kw-row" role="list" aria-label="Sujets fréquents"></div>
  </section>

  <section class="sec reveal" aria-labelledby="sec-aune" style="padding-top:0">
    <div class="sec-rule"><h2 id="sec-aune">À la une</h2></div>
    <div id="featured" class="feat-grid" role="list" aria-label="Articles à la une"></div>
  </section>

  <section class="sec reveal" aria-labelledby="sec-derniers" style="padding-top:0">
    <div class="sec-rule"><h2 id="sec-derniers">Les derniers articles</h2></div>
    <div class="carousel-wrap">
      <button class="car-btn car-prev" id="car-prev" onclick="carScroll(-1)" aria-label="Article précédent">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
      </button>
      <div class="carousel" id="carousel" role="list" aria-label="Carrousel des derniers articles"></div>
      <button class="car-btn car-next" id="car-next" onclick="carScroll(1)" aria-label="Article suivant">
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
      </button>
    </div>
  </section>

  <section class="sec reveal" aria-labelledby="sec-themes" style="padding-top:0">
    <div class="sec-rule"><h2 id="sec-themes">Explorer par thème</h2></div>
    <div class="theme-chips" role="list">
      <button class="theme-chip" role="listitem" onclick="goFeedFiltre('securite')"><img src="images/icon-securite.png" alt="" aria-hidden="true">Sécurité</button>
      <button class="theme-chip" role="listitem" onclick="goFeedFiltre('politique')"><img src="images/icon-politique.png" alt="" aria-hidden="true">Politique</button>
      <button class="theme-chip" role="listitem" onclick="goFeedFiltre('education')"><img src="images/icon-education.png" alt="" aria-hidden="true">Éducation</button>
      <button class="theme-chip" role="listitem" onclick="goFeedFiltre('sante')"><img src="images/icon-sante.png" alt="" aria-hidden="true">Santé</button>
      <button class="theme-chip" role="listitem" onclick="goFeedFiltre('cadredevie')"><img src="images/icon-cadredevie.png" alt="" aria-hidden="true">Cadre de vie</button>
      <button class="theme-chip" role="listitem" onclick="goFeedFiltre('gpseo')"><img src="images/icon-gpseo.png" alt="" aria-hidden="true">GPSEO</button>
    </div>
  </section>

  <section class="sec reveal" aria-labelledby="sec-pouls" style="padding-top:0">
    <div class="sec-rule"><h2 id="sec-pouls">Le pouls de la veille</h2></div>
    <div class="pulse-panel">
      <div class="pulse-col">
        <div class="pulse-label">Activité<span><b id="trend-sum">0</b> articles · 14 j</span></div>
        <div class="trend-bars" id="trend-bars" role="img" aria-label="Graphe du volume d'articles sur 14 jours"></div>
      </div>
      <div class="pulse-divider" aria-hidden="true"></div>
      <div class="pulse-col">
        <div class="pulse-label">Sources les plus actives<span>90 j</span></div>
        <div id="sources-grid" class="src-list" role="list" aria-label="Sources les plus actives"></div>
      </div>
    </div>
  </section>

  <div class="cta-wrap">
    <button class="cta-btn" onclick="goFeed()" aria-label="Voir tous les articles">
      Voir tous les articles
      <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/>
      </svg>
    </button>
  </div>

  <footer class="site-footer" role="contentinfo">
    <div class="footer-inner">
      <span class="footer-logo">La Vigie</span>
      <div class="footer-links">
        <a class="footer-link" href="https://chanteloup-les-vignes.fr" target="_blank" rel="noopener">chanteloup-les-vignes.fr</a>
        <span class="footer-link">·</span>
        <span class="footer-link">{nb_sources} médias · Mémoire 90 jours</span>
      </div>
      <span class="footer-date">Mis à jour : {date_maj}</span>
    </div>
  </footer>
</div>

<!-- ══════════ VUE FEED ══════════ -->
<div id="view-feed" class="view" role="main">

  <div class="feed-layout">
    <aside class="feed-sidebar" aria-label="Filtres">
      <div class="filter-group" role="group" aria-label="Catégories">
        <div class="filter-group-label">Catégories</div>
        <button class="fbtn active" id="f-tous" onclick="setFiltre('tous',this)"><span class="fbtn-l">Tous</span><span class="fbtn-c">{len(articles)}</span></button>
        <button class="fbtn" id="f-chanteloup" onclick="setFiltre('chanteloup',this)"><span class="fdot" style="background:#0369A1"></span><span class="fbtn-l">Chanteloup</span><span class="fbtn-c">{nb_chanteloup}</span></button>
        <button class="fbtn" id="f-gpseo" onclick="setFiltre('gpseo',this)"><span class="fdot" style="background:#7C3AED"></span><span class="fbtn-l">GPSEO</span><span class="fbtn-c">{nb_gpseo}</span></button>
        <button class="fbtn" id="f-yvelines" onclick="setFiltre('yvelines',this)"><span class="fdot" style="background:#059669"></span><span class="fbtn-l">Yvelines</span><span class="fbtn-c">{nb_yvelines}</span></button>
      </div>
      <div class="filter-group" role="group" aria-label="Thèmes">
        <div class="filter-group-label">Thèmes</div>
        <button class="fbtn" id="f-securite" onclick="setFiltre('securite',this)"><img src="images/icon-securite.png" alt=""><span class="fbtn-l">Sécurité</span><span class="fbtn-c">{nb_securite}</span></button>
        <button class="fbtn" id="f-politique" onclick="setFiltre('politique',this)"><img src="images/icon-politique.png" alt=""><span class="fbtn-l">Politique</span><span class="fbtn-c">{nb_politique}</span></button>
        <button class="fbtn" id="f-education" onclick="setFiltre('education',this)"><img src="images/icon-education.png" alt=""><span class="fbtn-l">Éducation</span><span class="fbtn-c">{nb_education}</span></button>
        <button class="fbtn" id="f-sante" onclick="setFiltre('sante',this)"><img src="images/icon-sante.png" alt=""><span class="fbtn-l">Santé</span><span class="fbtn-c">{nb_sante}</span></button>
        <button class="fbtn" id="f-cadredevie" onclick="setFiltre('cadredevie',this)"><img src="images/icon-cadredevie.png" alt=""><span class="fbtn-l">Cadre de vie</span><span class="fbtn-c">{nb_cadredevie}</span></button>
      </div>
    </aside>

    <div class="feed-main">
      <div class="feed-toolbar">
        <span class="results-count" id="results-count" aria-live="polite"><b>—</b></span>
        <button class="filter-clear" id="filter-clear" onclick="resetFiltres()" aria-label="Réinitialiser les filtres">✕ Effacer les filtres</button>
      </div>
      <div id="art-grid" class="art-grid" role="list" aria-label="Articles"></div>
    </div>
  </div>

  <footer class="site-footer" role="contentinfo">
    <div class="footer-inner">
      <span class="footer-logo">La Vigie</span>
      <div class="footer-links">
        <span class="footer-link">{nb_sources} médias surveillés · 90 jours de mémoire</span>
      </div>
      <span class="footer-date">Mis à jour : {date_maj}</span>
    </div>
  </footer>
</div>

<!-- ══════════ FLOATING UI ══════════ -->
<button id="back-top" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" aria-label="Retour en haut">
  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"/>
  </svg>
</button>

<div id="toast" role="status" aria-live="polite"></div>

<!-- ══════════ SCRIPT ══════════ -->
<script>
const ARTICLES = {articles_json};
const TODAY    = '{today}';
const COULEURS = {{chanteloup:'#0369A1',gpseo:'#7C3AED',yvelines:'#059669',securite:'#DC2626',politique:'#7C3AED',education:'#059669',sante:'#0369A1',cadredevie:'#D97706',autre:'#94A3B8'}};
const LABELS   = {{chanteloup:'Chanteloup',gpseo:'GPSEO',yvelines:'Yvelines',securite:'Sécurité',politique:'Politique',education:'Éducation',sante:'Santé',cadredevie:'Cadre de vie',autre:'Autre'}};
const MOIS     = ['','janv.','févr.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];

let filtreActif = 'tous', searchQ = '';

/* ── Utils ── */
function catEff(a) {{ return (a.sous_cat && a.sous_cat !== 'autre') ? a.sous_cat : a.categorie; }}
function fmtD(d) {{ const [y,m,j]=d.split('-').map(Number); return j+' '+MOIS[m]+' '+y; }}
function esc(s) {{ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
/* Date relative : « aujourd'hui », « hier », « il y a 3 j », sinon date courte */
function relD(iso, dstr) {{
  const now=new Date(), then=new Date(iso);
  const days=Math.floor((new Date(now.toDateString())-new Date(then.toDateString()))/86400000);
  if(days<=0) {{
    const h=Math.floor((now-then)/3600000);
    if(h<1) return "à l'instant";
    return 'il y a '+h+' h';
  }}
  if(days===1) return 'hier';
  if(days<7) return 'il y a '+days+' j';
  return fmtD(dstr);
}}

/* ── Toast ── */
function showToast(msg, duration=2800) {{
  const t=document.getElementById('toast'); t.textContent=msg;
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'), duration);
}}

/* ── Progress bar ── */
window.addEventListener('scroll', ()=>{{
  const pct = (scrollY / (document.documentElement.scrollHeight - innerHeight)) * 100;
  document.getElementById('progress-bar').style.width = Math.min(pct, 100) + '%';
  document.getElementById('back-top').classList.toggle('visible', scrollY > 320);
}}, {{passive:true}});

/* ── Navigation SPA ── */
function activateView(id) {{
  // Transition fluide entre vues si l'API est dispo (Chrome/Safari récents)
  const swap=()=>{{
    document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
    document.getElementById(id).classList.add('active');
  }};
  if(document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches) {{
    document.startViewTransition(swap);
  }} else {{
    swap();
  }}
  window.scrollTo({{top:0,behavior:'smooth'}});
}}
function goHome() {{
  activateView('view-home');
  document.getElementById('btn-home').classList.add('active');
  document.getElementById('btn-feed').classList.remove('active');
  document.getElementById('search').value=''; searchQ='';
  document.getElementById('search-clear').classList.remove('visible');
}}
function goFeed() {{
  activateView('view-feed');
  document.getElementById('btn-feed').classList.add('active');
  document.getElementById('btn-home').classList.remove('active');
  filtrer();
}}
function goFeedFiltre(cat) {{
  goFeed();
  const btn = document.getElementById('f-'+cat);
  if(btn) setFiltre(cat, btn);
}}

/* ── Recherche ── */
function onSearch() {{
  searchQ = document.getElementById('search').value.toLowerCase().trim();
  document.getElementById('search-clear').classList.toggle('visible', searchQ.length > 0);
  if(searchQ && !document.getElementById('view-feed').classList.contains('active')) goFeed();
  else filtrer();
}}
function clearSearch() {{
  document.getElementById('search').value=''; searchQ='';
  document.getElementById('search-clear').classList.remove('visible');
  document.getElementById('search').focus();
  filtrer();
}}

/* ── Raccourcis clavier ── */
document.addEventListener('keydown', e => {{
  if(e.key==='Escape') {{
    if(searchQ) {{ clearSearch(); return; }}
    if(filtreActif!=='tous') {{ resetFiltres(); return; }}
  }}
  if(e.key==='/' && !['INPUT','TEXTAREA'].includes(e.target.tagName)) {{
    e.preventDefault(); document.getElementById('search').focus();
    if(!document.getElementById('view-feed').classList.contains('active')) goFeed();
  }}
}});

/* ── Carte article ── */
function renderCard(art, idx) {{
  const cat=catEff(art), col=COULEURS[cat]||'#94A3B8', label=LABELS[cat]||cat;
  const isNew=art.date===TODAY, delay=Math.min(idx*30,400), tagBg=col+'14';
  return `
<article class="card" style="animation-delay:${{delay}}ms" role="listitem">
  ${{thumbHTML(art, true)}}
  <div class="card-body">
    <div class="card-byline">
      <span class="card-byline-dot" style="background:${{col}}"></span>
      <span class="card-byline-name" style="color:${{col}}">${{esc(art.source)}}</span>
      <span class="card-byline-sep">·</span>
      <span class="card-byline-date" title="${{fmtD(art.date)}}">${{relD(art.date_iso, art.date)}}</span>
    </div>
    <h3 class="card-title">${{esc(art.titre)}}</h3>
    ${{art.resume?`<p class="card-excerpt">${{esc(art.resume)}}</p>`:''}}
  </div>
  <div class="card-bottom">
    <div style="display:flex;align-items:center;gap:.35rem;flex-wrap:wrap">
      ${{isNew?'<span class="badge-new">Nouveau</span>':`<span class="card-tag" style="background:${{tagBg}};color:${{col}}">${{label}}</span>`}}
    </div>
    <a class="card-link" href="${{art.lien}}" target="_blank" rel="noopener" aria-label="Lire : ${{esc(art.titre)}}">Lire
      <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
      </svg>
    </a>
  </div>
</article>`;
}}

/* ── Groupe de date ── */
function dateGroup(d) {{
  if(d===TODAY) return "Aujourd'hui";
  const diff = (new Date(TODAY) - new Date(d)) / 86400000;
  if(diff<=7) return "Cette semaine";
  return "Plus ancien";
}}
function groupHeader(label) {{
  return `<div class="date-group" role="separator" aria-label="Groupe : ${{label}}">
    <span class="date-group-label">${{label}}</span>
  </div>`;
}}

/* ── Filtrer + afficher ── */
function filtrer() {{
  const grid = document.getElementById('art-grid');
  let vis = ARTICLES
    .filter(a=>{{
      if(filtreActif!=='tous'){{if(catEff(a)!==filtreActif&&a.categorie!==filtreActif)return false;}}
      if(searchQ){{if(!(a.titre+' '+a.resume+' '+a.source).toLowerCase().includes(searchQ))return false;}}
      return true;
    }})
    .sort((a,b)=>b.date_iso.localeCompare(a.date_iso));

  // Compteur résultats
  const cnt = document.getElementById('results-count');
  if(cnt) cnt.innerHTML = `<b>${{vis.length}}</b> résultat${{vis.length!==1?'s':''}}`;

  // Bouton effacer
  const clearBtn = document.getElementById('filter-clear');
  if(clearBtn) clearBtn.classList.toggle('visible', filtreActif!=='tous' || searchQ.length>0);

  if(vis.length===0) {{
    grid.innerHTML=`<div class="empty-state" role="status">
      <div class="empty-line"></div>
      <div class="empty-title">Aucun article trouvé</div>
      <div class="empty-sub">Essayez un autre terme ou une autre catégorie</div>
      <button class="empty-reset" onclick="resetFiltres()">Réinitialiser les filtres</button>
    </div>`;
    return;
  }}

  // Grouper par date
  let html='', lastGroup='';
  vis.forEach((a,i)=>{{
    const g=dateGroup(a.date);
    if(g!==lastGroup){{ html+=groupHeader(g); lastGroup=g; }}
    html+=renderCard(a,i);
  }});
  grid.innerHTML=html;
}}

function setFiltre(cat,btn) {{
  filtreActif=cat;
  document.querySelectorAll('.fbtn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  filtrer();
}}
function resetFiltres() {{
  filtreActif='tous';
  searchQ='';
  document.getElementById('search').value='';
  document.getElementById('search-clear').classList.remove('visible');
  document.querySelectorAll('.fbtn').forEach(b=>b.classList.remove('active'));
  document.getElementById('f-tous')?.classList.add('active');
  filtrer();
}}

/* ── Carte featured ── */
/* ── Vignette image (ou placeholder dégradé) ── */
function thumbHTML(art, badge) {{
  const cat=catEff(art), col=COULEURS[cat]||'#94A3B8', label=LABELS[cat]||cat;
  const b = badge ? `<span class="thumb-badge" style="background:${{col}}E6">${{label}}</span>` : '';
  if(art.image) {{
    return `<div class="thumb" style="--c:${{col}}">${{b}}<img src="${{art.image}}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.classList.add('thumb-fallback');this.remove();"><span class="thumb-src">${{esc(art.source)}}</span></div>`;
  }}
  return `<div class="thumb thumb-fallback" style="--c:${{col}}">${{b}}<span class="thumb-src">${{esc(art.source)}}</span></div>`;
}}

function renderFeat(art, size) {{
  const cat=catEff(art), col=COULEURS[cat]||'#94A3B8', label=LABELS[cat]||cat;
  const isNew=art.date===TODAY;

  // ── Grande carte « une » : couverture magazine (image plein cadre + dégradé) ──
  if(size==='main') {{
    return `
<a class="feat-card feat-main feat-hero" href="${{art.lien}}" target="_blank" rel="noopener" role="listitem" aria-label="${{esc(art.titre)}}">
  ${{thumbHTML(art, false)}}
  <div class="feat-hero-grad"></div>
  <div class="feat-hero-content">
    <div class="feat-hero-tags">
      <span class="feat-hero-badge" style="background:${{col}}">${{label}}</span>
      ${{isNew?'<span class="feat-hero-new">Nouveau</span>':''}}
    </div>
    <h3 class="feat-hero-title">${{esc(art.titre)}}</h3>
    <div class="feat-hero-meta">
      <span class="feat-hero-src">${{esc(art.source)}}</span>
      <span class="feat-hero-dot">·</span>
      <span title="${{fmtD(art.date)}}">${{relD(art.date_iso, art.date)}}</span>
      <span class="feat-hero-read">Lire l'article →</span>
    </div>
  </div>
</a>`;
  }}

  // ── Petites cartes : image en haut + corps ──
  return `
<article class="feat-card" role="listitem">
  ${{thumbHTML(art, true)}}
  <div class="feat-body">
    <div class="feat-byline">
      <span class="feat-byline-dot" style="background:${{col}}"></span>
      <span style="color:${{col}}">${{esc(art.source)}}</span>
      ${{isNew?'&nbsp;<span style="background:var(--orange);color:#fff;font-size:.52rem;padding:.1rem .38rem;border-radius:3px">NOUVEAU</span>':''}}
    </div>
    <h3 class="feat-title-sm">${{esc(art.titre)}}</h3>
  </div>
  <div class="feat-footer">
    <span class="feat-date" title="${{fmtD(art.date)}}">${{relD(art.date_iso, art.date)}}</span>
    <a class="feat-link" href="${{art.lien}}" target="_blank" rel="noopener">Lire l'article
      <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
    </a>
  </div>
</article>`;
}}

/* ── Carrousel des derniers articles ── */
let carTimer=null;
function renderCarousel() {{
  const sorted=[...ARTICLES].sort((a,b)=>b.date_iso.localeCompare(a.date_iso)).slice(0,12);
  const el=document.getElementById('carousel');
  if(!el) return;
  el.innerHTML=sorted.map(art=>{{
    const cat=catEff(art), col=COULEURS[cat]||'#94A3B8';
    const isNew=art.date===TODAY;
    return `<a class="ccard" href="${{art.lien}}" target="_blank" rel="noopener" role="listitem" aria-label="${{esc(art.titre)}}">
      ${{thumbHTML(art, true)}}
      <div class="ccard-body">
        <div class="ccard-byline"><span class="ccard-byline-dot" style="background:${{col}}"></span><span style="color:${{col}}">${{esc(art.source)}}</span>${{isNew?'&nbsp;<span style="background:var(--orange);color:#fff;font-size:.5rem;padding:.08rem .35rem;border-radius:3px;letter-spacing:.05em">NEW</span>':''}}</div>
        <h3 class="ccard-title">${{esc(art.titre)}}</h3>
        <span class="ccard-date" title="${{fmtD(art.date)}}">${{relD(art.date_iso, art.date)}}</span>
      </div>
    </a>`;
  }}).join('');
  updateCarBtns();
}}
function carScroll(dir) {{
  const c=document.getElementById('carousel'); if(!c) return;
  const card=c.querySelector('.ccard');
  const step=(card?card.offsetWidth:300)+18;
  c.scrollBy({{left:dir*step, behavior:'smooth'}});
}}
function updateCarBtns() {{
  const c=document.getElementById('carousel');
  const prev=document.getElementById('car-prev'), next=document.getElementById('car-next');
  if(!c||!prev||!next) return;
  prev.disabled = c.scrollLeft <= 4;
  next.disabled = c.scrollLeft >= c.scrollWidth - c.clientWidth - 4;
}}
function startCarAuto() {{
  if(matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  stopCarAuto();
  carTimer=setInterval(()=>{{
    const c=document.getElementById('carousel');
    if(!c||!document.getElementById('view-home').classList.contains('active')) return;
    if(c.scrollLeft >= c.scrollWidth - c.clientWidth - 4) c.scrollTo({{left:0,behavior:'smooth'}});
    else carScroll(1);
  }}, 5500);
}}
function stopCarAuto() {{ if(carTimer){{ clearInterval(carTimer); carTimer=null; }} }}

/* ── Count-up ── */
function countUp(id, target) {{
  const el=document.getElementById(id); if(!el){{return;}}
  if(target===0 || matchMedia('(prefers-reduced-motion: reduce)').matches){{ el.textContent=target; return; }}
  let cur=0; const step=Math.max(1,Math.ceil(target/45));
  const t=setInterval(()=>{{cur=Math.min(cur+step,target);el.textContent=cur;if(cur>=target)clearInterval(t);}},25);
}}

/* ── Graphe de tendance (14 jours) ── */
function renderTrend() {{
  const bars=document.getElementById('trend-bars'); if(!bars) return;
  const base=new Date(TODAY+'T00:00:00'); const days=[];
  for(let i=13;i>=0;i--) {{
    const d=new Date(base); d.setDate(d.getDate()-i);
    const iso=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    days.push({{iso, count:0, dom:d.getDate(), m:d.getMonth()+1}});
  }}
  const idx={{}}; days.forEach((d,i)=>idx[d.iso]=i);
  let sum=0;
  ARTICLES.forEach(a=>{{ if(a.date in idx) {{ days[idx[a.date]].count++; sum++; }} }});
  const max=Math.max(1, ...days.map(d=>d.count));
  document.getElementById('trend-sum').textContent=sum;
  bars.setAttribute('aria-label', sum+' articles publiés sur les 14 derniers jours');
  bars.innerHTML=days.map(d=>{{
    const h=Math.max(4, Math.round(d.count/max*70));
    const isT=d.iso===TODAY;
    return `<div class="trend-col">
      <div class="trend-bar ${{isT?'today':''}}" style="height:${{h}}px">
        <span class="trend-tip">${{d.count}} le ${{d.dom}}/${{d.m}}</span>
      </div>
      <span class="trend-x">${{d.dom}}</span>
    </div>`;
  }}).join('');
}}

/* ── Sujets du moment (mots-clés des titres récents) ── */
const STOP=new Set("le la les un une de des du et en au aux pour par sur dans avec sans sous entre vers chez ce cet cette ces son sa ses leur leurs notre nos votre vos qui que quoi dont est sont été être avoir fait plus moins tres bien aussi comme mais donc car ne pas rien tout tous toute toutes nous vous ils elles elle après avant pendant contre selon ainsi alors depuis encore deux trois cela ceux celle vont face lors près chanteloup vignes yvelines cette plus elle leur dont fait sera vers chez".split(' '));
function capit(w) {{ return w.charAt(0).toUpperCase()+w.slice(1); }}
function renderKeywords() {{
  const el=document.getElementById('keywords'); if(!el) return;
  const cut=new Date(TODAY+'T00:00:00'); cut.setDate(cut.getDate()-21);
  const cnt={{}};
  ARTICLES.forEach(a=>{{
    if(new Date(a.date+'T00:00:00') < cut) return;
    (a.titre.toLowerCase().match(/[a-zàâäéèêëïîôöùûüç]{{4,}}/g)||[]).forEach(w=>{{
      if(STOP.has(w)) return; cnt[w]=(cnt[w]||0)+1;
    }});
  }});
  const top=Object.entries(cnt).filter(([w,c])=>c>=2).sort((a,b)=>b[1]-a[1]).slice(0,10);
  const sec=document.getElementById('sujets-section');
  if(top.length===0) {{ if(sec) sec.style.display='none'; return; }}
  el.innerHTML=top.map(([w,c])=>`<button class="kw-chip" role="listitem" onclick="searchKw('${{w}}')">${{capit(w)}} <b>${{c}}</b></button>`).join('');
}}
function searchKw(w) {{
  document.getElementById('search').value=w; searchQ=w;
  document.getElementById('search-clear').classList.add('visible');
  goFeed();
}}

/* ── Révélation au défilement ── */
function initReveal() {{
  const els=document.querySelectorAll('.reveal');
  if(!('IntersectionObserver' in window)) {{ els.forEach(e=>e.classList.add('in')); return; }}
  const io=new IntersectionObserver((ents)=>{{
    ents.forEach(en=>{{ if(en.isIntersecting) {{ en.target.classList.add('in'); io.unobserve(en.target); }} }});
  }}, {{threshold:0.08, rootMargin:'0px 0px -40px 0px'}});
  els.forEach(e=>io.observe(e));
  setTimeout(()=>els.forEach(e=>e.classList.add('in')), 2200);  // filet de sécurité
}}

/* ── Init home ── */
function initHome() {{
  countUp('cnt-total', ARTICLES.length);
  countUp('cnt-chan',  ARTICLES.filter(a=>a.categorie==='chanteloup').length);
  countUp('cnt-gpseo',ARTICLES.filter(a=>a.categorie==='gpseo').length);
  countUp('cnt-yv',   ARTICLES.filter(a=>a.categorie==='yvelines').length);
  renderTrend();
  renderKeywords();

  const sorted=[...ARTICLES].sort((a,b)=>b.date_iso.localeCompare(a.date_iso));
  const top3=sorted.slice(0,3);
  const feat=document.getElementById('featured');
  feat.innerHTML = top3.length===0
    ? '<p style="color:var(--muted);font-size:.85rem;grid-column:1/-1">Aucun article récent.</p>'
    : renderFeat(top3[0],'main') + (top3[1]?renderFeat(top3[1],'sm'):'') + (top3[2]?renderFeat(top3[2],'sm'):'');

  const sc={{}};
  ARTICLES.forEach(a=>{{sc[a.source]=(sc[a.source]||0)+1;}});
  const srcEl=document.getElementById('sources-grid');
  const ranked=Object.entries(sc).sort((a,b)=>b[1]-a[1]).slice(0,8);
  const maxSrc=ranked.length?ranked[0][1]:1;
  srcEl.innerHTML=ranked.map(([n,c])=>`<div class="src-row" role="listitem">
      <span class="src-row-name" title="${{esc(n)}}">${{esc(n)}}</span>
      <span class="src-row-bar"><i style="width:${{Math.max(8,Math.round(c/maxSrc*100))}}%"></i></span>
      <span class="src-row-n">${{c}}</span>
    </div>`).join('');

  // Carrousel
  renderCarousel();
  const car=document.getElementById('carousel');
  if(car) {{
    car.addEventListener('scroll', updateCarBtns, {{passive:true}});
    car.addEventListener('mouseenter', stopCarAuto);
    car.addEventListener('mouseleave', startCarAuto);
    car.addEventListener('focusin', stopCarAuto);   // pause au focus clavier (WCAG 2.2.2)
    car.addEventListener('focusout', startCarAuto);
    window.addEventListener('resize', updateCarBtns, {{passive:true}});
    startCarAuto();
  }}
}}

/* ── Keyboard nav logo ── */
document.querySelector('.nav-logo').addEventListener('keydown',e=>{{if(e.key==='Enter')goHome();}});

/* ── Boot ── */
initHome();
filtrer();
initReveal();
setTimeout(()=>showToast('Site mis à jour · {date_maj}', 3000), 800);
</script>
{bg3d_script}
</body>
</html>"""

    os.makedirs(SITE_DIR, exist_ok=True)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Vérification des sources...")
    articles, stats, nb_nouveaux = collecter()

    if nb_nouveaux == 0:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Aucun nouvel article — site inchangé.")
        return

    print(f"[{datetime.now().strftime('%H:%M:%S')}] {nb_nouveaux} nouveau(x) article(s) · {len(articles)} en base")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Mise à jour du site...")
    generer_html(articles, stats, nb_nouveaux)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Site mis à jour : {HTML_PATH}")

if __name__ == "__main__":
    main()
