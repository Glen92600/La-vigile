# Mettre « La Vigie » en ligne (privé)

Objectif : un site **accessible seulement aux personnes que tu autorises**, qui se met à jour **tout seul dans le cloud** (Mac éteint).

Architecture : **GitHub** (stocke le projet + lance la mise à jour automatique) → **Cloudflare Pages** (héberge le site) → **Cloudflare Access** (la page de connexion qui filtre les accès).

Tout est **gratuit**.

---

## Phase 2 — Mettre le projet sur GitHub

### 2.1 Créer un compte GitHub
1. Va sur **github.com** → « Sign up »
2. Crée le compte (e-mail pro de préférence). C'est gratuit.

### 2.2 Installer GitHub Desktop (le plus simple, sans ligne de commande)
1. Télécharge **GitHub Desktop** : desktop.github.com
2. Ouvre-le et connecte-toi avec ton compte GitHub.

### 2.3 Publier le projet
1. Dans GitHub Desktop : menu **File → Add Local Repository**
2. Choisis le dossier `Veille médias` (le projet est déjà prêt, je l'ai initialisé).
3. Clique **Publish repository**.
4. ⚠️ **IMPORTANT : coche « Keep this code private »** (dépôt privé).
5. Nom suggéré du dépôt : `la-vigie`.

✅ Ton projet est maintenant sur GitHub, en privé.

### 2.4 Vérifier l'automatisation
- Sur github.com, ouvre ton dépôt → onglet **Actions**.
- Tu verras le workflow « Mise à jour de La Vigie ». Il tournera tout seul chaque heure.
- Tu peux le lancer manuellement : Actions → le workflow → « Run workflow ».

---

## Phase 3 — Héberger + protéger avec Cloudflare

### 3.1 Créer un compte Cloudflare
1. Va sur **cloudflare.com** → « Sign Up ». Gratuit.

### 3.2 Connecter le site (Cloudflare Pages)
1. Dans le tableau de bord Cloudflare : **Workers & Pages → Create → Pages → Connect to Git**
2. Autorise Cloudflare à accéder à ton GitHub, choisis le dépôt `la-vigie`.
3. Réglages de build :
   - **Framework preset** : `None`
   - **Build command** : *(laisser vide)*
   - **Build output directory** : `site`
4. Clique **Save and Deploy**.

✅ Au bout d'une minute, ton site est en ligne à une adresse type `la-vigie.pages.dev`.

### 3.3 Activer la page de connexion (Cloudflare Access)
1. Dans Cloudflare : **Zero Trust** (menu de gauche) → au premier accès, choisis le plan **Free**.
2. **Access → Applications → Add an application → Self-hosted**.
3. Réglages :
   - **Application name** : `La Vigie`
   - **Session duration** : 24 h (ou plus)
   - **Application domain** : l'adresse de ton site (`la-vigie.pages.dev`)
4. **Policies → Add a policy** :
   - **Policy name** : `Équipe autorisée`
   - **Action** : `Allow`
   - **Include** → choisis :
     - **Emails** : liste les e-mails autorisés un par un, **OU**
     - **Emails ending in** : `@chanteloup-les-vignes.fr` (toute la mairie d'un coup)
5. Enregistre.

✅ **C'est fini.** Désormais, ouvrir le site demande une connexion par e-mail. Seules les personnes de ta liste reçoivent le code d'accès et peuvent entrer.

---

## Gérer les accès plus tard
Cloudflare → Zero Trust → Access → Applications → La Vigie → Policies :
- **Ajouter** quelqu'un : ajoute son e-mail dans la policy.
- **Retirer** quelqu'un : enlève son e-mail.
Les changements sont immédiats.

## Bon à savoir
- **Fréquence de mise à jour** : 1×/heure (réglable dans `.github/workflows/update.yml`, ligne `cron`). L'heure est un bon compromis pour rester dans les quotas gratuits.
- **Limites gratuites** : largement suffisantes ici (le site ne se reconstruit que lorsqu'il y a de nouveaux articles).
- **Mac éteint ?** Aucun problème — tout tourne dans le cloud.
