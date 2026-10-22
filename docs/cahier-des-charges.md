# Cahier des charges — Supervya

Plateforme SaaS de supervision d'infrastructures informatiques  
Projet de stage — Koyitek SARL

---

## 1. Présentation

Supervya permet aux clients de superviser leurs machines (CPU, mémoire, disque, disponibilité) via un espace web unique. La collecte des métriques et le calcul des alertes sont assurés par Zabbix 7.0 LTS. Django expose seule l'interface client et administrateur ; les clients n'accèdent jamais à Zabbix.

### 1.1 Architecture cible

| Composant | Rôle |
|-----------|------|
| Zabbix Server 7.0 LTS | Collecte, stockage des mesures, calcul des alertes |
| PostgreSQL (`zabbix`) | Base Zabbix |
| Zabbix Web | Interface réservée à l'administrateur interne (non exposée publiquement) |
| Zabbix Agent 2 | Sur les machines clientes, checks **actifs** uniquement |
| Django (`supervya`) | Comptes, licences, tableau de bord, alertes, API REST |
| PostgreSQL (`supervya`) | Base applicative Django |
| Redis + Celery (ou cron) | Tâches planifiées (sync alertes, contrôle IP) |

### 1.2 Applications Django

- `accounts` — utilisateurs, clients, authentification
- `licensing` — licences, activation, PSK
- `supervision` — client Zabbix, sync alertes/état
- `dashboard` — espace client (machines, graphiques, alertes)

---

## 2. Exigences fonctionnelles

| ID | Exigence |
|----|----------|
| EF-01 | Création et gestion de comptes clients (espace administrateur) |
| EF-02 | Génération de licences (1 licence = 1 machine = 1 IP) |
| EF-03 | Activation d'une licence via script d'installation (Linux / Windows) |
| EF-04 | Enregistrement automatique de l'hôte dans Zabbix à l'activation |
| EF-05 | Tableau de bord listant les machines avec état (vert / orange / rouge) |
| EF-06 | Détail d'une machine : valeurs actuelles et graphiques (1 h, 24 h, 7 j) |
| EF-07 | Liste des alertes avec rafraîchissement automatique (30 s) |
| EF-08 | Configuration des seuils (macros d'hôte Zabbix) depuis Supervya |
| EF-09 | Notification e-mail au client lors d'une nouvelle alerte |
| EF-10 | Suspension / expiration / révocation d'une licence désactive l'hôte Zabbix |
| EF-11 | Renouvellement d'une licence réactive l'hôte Zabbix |
| EF-12 | Contrôle périodique de l'IP de connexion de l'agent |

---

## 3. Exigences non fonctionnelles

| ID | Exigence |
|----|----------|
| ENF-01 | Aucun port ouvert chez le client : agent en mode actif uniquement |
| ENF-02 | Cloisonnement strict entre clients (groupes d'hôtes Zabbix + filtres Django) |
| ENF-03 | HTTPS en production |
| ENF-04 | Mots de passe hachés (Django) |
| ENF-05 | Identifiants API Zabbix uniquement en variables d'environnement |
| ENF-06 | Limitation de débit sur `/api/activation` |
| ENF-07 | Interface en français, sobre, responsive |
| ENF-08 | Déploiement via Docker Compose |

---

## 4. Règles de gestion

| ID | Règle |
|----|-------|
| RG-01 | Format de clé de licence : `SPV-XXXX-XXXX-XXXX-XXXX` (alphanumérique majuscule, génération sécurisée) |
| RG-02 | À la création d'une licence : génération de la clé et d'une PSK propre |
| RG-03 | Activation : licence à l'état `GENEREE` ; enregistrement de l'IP source ; création hôte/groupe/template/PSK dans Zabbix |
| RG-04 | Si l'IP de connexion de l'agent ≠ IP enregistrée → désactivation de l'hôte + alerte |
| RG-05 | Une licence déjà liée ne peut pas être activée une seconde fois |
| RG-06 | Licence suspendue, expirée ou révoquée → hôte Zabbix désactivé (`status=1`) |
| RG-07 | Nom du groupe d'hôtes : `supervya-client-<id>` |
| RG-08 | Templates : « Linux by Zabbix agent active » ou « Windows by Zabbix agent active » |
| RG-09 | Identité PSK = identifiant de la licence ; Hostname Zabbix = identifiant de la licence |
| RG-10 | Machine hors ligne après 90 s sans données agent |

### États de licence

`GENEREE` → `ACTIVE` → `SUSPENDUE` / `EXPIREE` / `REVOQUEE`

---

## 5. API d'activation

`POST /api/activation`

Corps attendu : clé de licence (`licence_key`).

Réponse (succès) : configuration agent (`Hostname`, `ServerActive`, `PSKIdentity`, `PSK`).

Comportement Django :

1. Vérifier l'état `GENEREE`
2. Enregistrer l'IP source
3. Créer hôte, groupe, lier le template, activer PSK
4. Passer la licence à `ACTIVE`
5. Renvoyer la configuration

---

## 6. Seuils et alertes

Macros d'hôte typiques :

- `{$CPU.UTIL.CRIT}`
- `{$MEMORY.UTIL.MAX}`
- `{$VFS.FS.PUSED.MAX.CRIT}`

Tâche planifiée (toutes les 30 s) :

1. `problem.get` pour les hôtes de chaque client
2. Créer / mettre à jour les alertes Supervya
3. Envoyer l'e-mail au client si nouvelle alerte

---

## 7. Critères de recette

| ID | Critère |
|----|---------|
| CR-01 | Une licence générée peut être activée une seule fois |
| CR-02 | Après activation, l'hôte apparaît dans Zabbix avec le bon template et PSK |
| CR-03 | Un client ne voit que ses propres machines et alertes |
| CR-04 | Changement de seuil via Supervya se reflète dans les macros Zabbix |
| CR-05 | Une alerte Zabbix apparaît dans Supervya sous 30 s et déclenche un e-mail |
| CR-06 | Licence suspendue / expirée / révoquée → hôte désactivé dans Zabbix |
| CR-07 | Renouvellement → hôte réactivé |
| CR-08 | IP agent ≠ IP licence → hôte désactivé + alerte créée |

---

## 8. Sécurité et qualité

- Module unique d'accès Zabbix : `supervision/zabbix_client.py`
- Tests unitaires du client Zabbix (mock), règles de licence, critères CR-01 à CR-08
- Tests de cloisonnement avec deux comptes clients
- Expéditeur e-mail : `Supervya <alertes@exemple.com>` (configurable via `.env`)
