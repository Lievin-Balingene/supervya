# Supervya

Plateforme SaaS de supervision d'infrastructures informatiques (projet de stage — Koyitek SARL).

Supervya est l'interface unique vue par les clients : comptes, licences, tableau de bord et alertes. La collecte des métriques et le calcul des alertes sont assurés par **Zabbix 7.0 LTS**. Les clients n'accèdent jamais à l'interface ni à l'API de Zabbix.

## Architecture

| Composant | Rôle |
|-----------|------|
| `supervya-web` | Application Django (API REST, espace client, admin) |
| `supervya-scheduler` | Synchronisation alertes / états / contrôle IP (toutes les 30 s) |
| `supervya-postgres` | Base PostgreSQL Supervya |
| `supervya-postgres-zabbix` | Base PostgreSQL Zabbix |
| `supervya-zabbix-server` | Zabbix Server 7.0 (port 10051 pour agents actifs) |
| `supervya-zabbix-web` | Interface Zabbix (localhost uniquement, admin interne) |
| `supervya-redis` | Redis (réservé / cache) |

Les agents clients (Zabbix Agent 2) fonctionnent en **checks actifs uniquement** : l'agent se connecte au serveur, aucun port n'est ouvert chez le client.

## Prérequis

- Docker et Docker Compose
- (optionnel) Python 3.12+ pour les tests locaux

## Installation

```bash
git clone <url-du-depot> supervya
cd supervya
cp .env.example .env
# Éditer .env : mots de passe, DJANGO_SECRET_KEY, ZABBIX_API_TOKEN, ZABBIX_SERVER_ACTIVE, e-mails
docker compose up -d --build
```

Premier démarrage :

1. Ouvrir Zabbix Web : [http://127.0.0.1:8080](http://127.0.0.1:8080) (compte par défaut `Admin` / `zabbix`).
2. Créer un jeton d'API (Administration → Users → API tokens) et le reporter dans `.env` (`ZABBIX_API_TOKEN`).
3. Recréer le service web / scheduler si besoin : `docker compose up -d web scheduler`.
4. Créer un superutilisateur Supervya :

```bash
docker compose exec web python manage.py createsuperuser
```

5. Connexion : [http://localhost:8000/accounts/login/](http://localhost:8000/accounts/login/)  
   - Administrateur → [http://localhost:8000/gestion/](http://localhost:8000/gestion/) (clients, licences, utilisateurs)  
   - Client → [http://localhost:8000/](http://localhost:8000/) (machines, licences, alertes)

## Variables d'environnement

Voir `.env.example`. Principales variables :

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Clé secrète Django |
| `DJANGO_DEBUG` | `True` en développement |
| `DATABASE_URL` | URL PostgreSQL Supervya |
| `ZABBIX_API_URL` | URL JSON-RPC Zabbix (interne Docker : `http://zabbix-web:8080/api_jsonrpc.php`) |
| `ZABBIX_API_TOKEN` | Jeton d'API Zabbix |
| `ZABBIX_SERVER_ACTIVE` | Adresse renvoyée aux agents (`hôte:10051`) |
| `DEFAULT_FROM_EMAIL` | Expéditeur, ex. `Supervya <alertes@exemple.com>` |
| `EMAIL_HOST` / `EMAIL_PORT` / … | SMTP pour les notifications |

## Démarrage

```bash
docker compose up -d
docker compose ps
docker compose logs -f web scheduler
```

Synchronisation manuelle :

```bash
docker compose exec web python manage.py synchroniser_supervision
```

## Installation de l'agent sur une machine cliente

1. Dans l'admin Supervya, créer un **client**, puis une **licence** (état *Générée*), en choisissant Linux ou Windows.
2. Sur la machine à superviser, lancer le script d'installation avec la clé `SPV-XXXX-XXXX-XXXX-XXXX`.

Les scripts sont publiés sur GitHub :
`https://raw.githubusercontent.com/Lievin-Balingene/supervya/main/scripts/`

`SUPERVYA_API_URL` doit pointer vers **votre instance Supervya** (joignable depuis la machine cliente), pas vers GitHub.

### Linux

```bash
export SUPERVYA_API_URL="https://supervya.exemple.com"
curl -fsSL https://raw.githubusercontent.com/Lievin-Balingene/supervya/main/scripts/supervya-install.sh \
  -o /tmp/supervya-install.sh
sudo -E bash /tmp/supervya-install.sh SPV-XXXX-XXXX-XXXX-XXXX
```

Le script active la licence via `POST /api/activation`, écrit la configuration PSK de Zabbix Agent 2 et démarre le service. Aucun port entrant n'est ouvert.

### Windows (PowerShell administrateur)

```powershell
$env:SUPERVYA_API_URL = "https://supervya.exemple.com"
$script = "$env:TEMP\supervya-install.ps1"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/Lievin-Balingene/supervya/main/scripts/supervya-install.ps1" -OutFile $script
& $script -LicenceKey "SPV-XXXX-XXXX-XXXX-XXXX"
```

Zabbix Agent 2 doit être installé (ou l'URL MSI fournie via `ZABBIX_AGENT_MSI_URL`).

Variable optionnelle : `SUPERVYA_PUBLIC_URL` dans `.env` pour forcer l'URL affichée dans l'espace client (utile derrière un reverse proxy).

## Applications Django

- `accounts` — clients et utilisateurs
- `licensing` — licences, activation, PSK
- `supervision` — client Zabbix, synchronisation
- `dashboard` — tableau de bord client

## Tests

```bash
python -m venv .venv
# Windows : .\.venv\Scripts\activate
# Linux   : source .venv/bin/activate
pip install -r requirements.txt
python manage.py test
```

Les tests couvrent le client Zabbix (mock), les règles de licence, le cloisonnement entre clients et les critères de recette CR-01 à CR-08.

## Licence métier (rappels)

- 1 licence = 1 machine = 1 adresse IP
- Format de clé : `SPV-XXXX-XXXX-XXXX-XXXX`
- Une licence déjà liée ne peut pas être réactivée
- Suspension / expiration / révocation désactive l'hôte Zabbix
- Écart d'IP agent → désactivation de l'hôte + alerte

Référence fonctionnelle : `docs/cahier-des-charges.md`.
