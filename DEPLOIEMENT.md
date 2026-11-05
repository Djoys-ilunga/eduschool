# EduSchool - Guide de Déploiement

## Prérequis

- Windows 10/11 ou Windows Server
- Python 3.10+

## Installation

### 1. Installer les dépendances

```powershell
cd C:\Users\nicol\Desktop\eduschool
pip install -r requirements.txt
```

### 2. Configurer le .env

Éditer le fichier `.env` :
- `SECRET_KEY` : déjà générée (forte). Ne pas changer sauf compromission.
- `BREVO_API_KEY` : vérifier que la clé est valide.
- `FLASK_ENV=production` : ne pas changer.

### 3. Ouvrir le pare-feu (PowerShell Admin)

```powershell
netsh advfirewall firewall add rule name="EduSchool 8080" dir=in action=allow protocol=TCP localport=8080
```

### 4. Démarrer le serveur

```powershell
# Production (recommandé)
python run_prod.py

# Développement uniquement
python app.py
```

### 5. Accéder

- **PC local** : http://127.0.0.1:8080
- **Réseau local (téléphone/autres PC)** : http://<IP_LOCALE>:8080

### 6. Démarrer automatiquement au boot (optionnel)

```powershell
$action = New-ScheduledTaskAction -Execute "python" -Argument "run_prod.py" -WorkingDirectory "C:\Users\nicol\Desktop\eduschool"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "EduSchool" -Action $action -Trigger $trigger -RunLevel Highest
```

---

## Comptes par défaut

| Rôle | Email/Login | Mot de passe |
|------|------------|-------------|
| Super Admin | super@admin.com | Admin12345 |
| Directeur | directeur@eduschool.cd | Directeur2026 |

> ⚠️ **CHANGER TOUS LES MOTS DE PASSE AVANT MISE EN PRODUCTION REELLE**

---

## Maintenance

### Backup de la base de données

```powershell
copy instance\eduschool.db eduschool_backup_$(Get-Date -Format yyyyMMdd).db
```

### Logs persistants

```powershell
python run_prod.py > logs.txt 2>&1
```

---

## Sécurité

- ✅ Tous les formulaires protégés par CSRF
- ✅ Rate limiting anti brute-force (login + reset password)
- ✅ Mots de passe hashés (bcrypt)
- ✅ Complexité mot de passe obligatoire
- ✅ Clé API email dans .env (pas dans le code)
- ✅ Debug mode OFF en production
- ⚠️ SQLite → migrer vers PostgreSQL pour >50 utilisateurs simultanés
- ⚠️ Pas de HTTPS intégré → utiliser nginx ou ngrok pour HTTPS
