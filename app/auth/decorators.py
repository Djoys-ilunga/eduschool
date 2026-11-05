from functools import wraps
import time
from flask import abort, redirect, url_for, flash, request
from flask_login import current_user


# --- Rate Limiting (in-memory) ---
_rate_limit_store: dict = {}  # key -> list of timestamps


def rate_limit(max_attempts=5, window=300, lockout=900):
    """Décorateur anti brute-force avec stockage en mémoire.

    Args:
        max_attempts: Nombre max de tentatives autorisées dans la fenêtre.
        window: Fenêtre glissante en secondes (défaut 300 = 5 min).
        lockout: Durée de verrouillage après dépassement (défaut 900 = 15 min).

    La clé de rate-limit est construite à partir de l'IP ou de l'email
    (si présent dans le formulaire).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = request.remote_addr or '127.0.0.1'
            email = request.form.get('email', '').strip().lower()
            key = f"{ip}:{email}" if email else ip

            now = time.time()
            entries = _rate_limit_store.get(key, [])

            # Nettoyer les entrées expirées (hors fenêtre)
            entries = [t for t in entries if now - t < window]

            # Vérifier si verrouillé (la plus ancienne tentative dans la fenêtre
            # déclenche un lockout si on a dépassé max_attempts)
            if len(entries) >= max_attempts:
                # La plus récente tentative
                last_attempt = max(entries)
                if now - last_attempt < lockout:
                    remaining = int(lockout - (now - last_attempt))
                    minutes = remaining // 60
                    seconds = remaining % 60
                    flash(
                        f'Trop de tentatives. Veuillez réessayer dans '
                        f'{minutes} min {seconds} s.',
                        'danger'
                    )
                    return redirect(url_for('auth.login'))
                else:
                    # Lockout expiré, on réinitialise
                    _rate_limit_store[key] = []
                    entries = []

            # Exécute la vue
            response = f(*args, **kwargs)

            # Après exécution, si la réponse est une redirection vers login
            # (signe d'échec), on enregistre la tentative
            # On détecte l'échec via le flash 'danger' ou via le fait que
            # l'utilisateur n'est pas authentifié après un POST
            if request.method == 'POST' and hasattr(response, 'status_code'):
                # Si on est redirigé vers login, c'est un échec
                from flask_login import current_user
                if not current_user.is_authenticated:
                    entries.append(now)
                    _rate_limit_store[key] = entries

                    attempts_left = max_attempts - len(entries)
                    if attempts_left > 0:
                        flash(
                            f'Tentative échouée. {attempts_left} tentative(s) restante(s).',
                            'warning'
                        )

            return response
        return decorated_function
    return decorator


def login_required(f):
    """Alias de flask_login.login_required avec message personnalisé."""
    from flask_login import login_required as flask_login_required
    return flask_login_required(f)


def role_required(*roles):
    """Restreint l'accès à une route aux rôles spécifiés.
    
    Usage:
        @role_required('super_admin')
        @role_required('super_admin', 'school_admin')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Veuillez vous connecter.', 'warning')
                return redirect(url_for('auth.login'))

            if current_user.role not in roles:
                flash("Vous n'avez pas les droits pour accéder à cette page.", 'danger')
                return abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def permission_required(permission_name):
    """Restreint l'accès à une route selon une permission RBAC.
    
    Usage:
        @permission_required('manage_schools')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Veuillez vous connecter.', 'warning')
                return redirect(url_for('auth.login'))

            if not current_user.has_permission(permission_name):
                flash("Vous n'avez pas la permission nécessaire pour cette action.", 'danger')
                return abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def school_admin_required(f):
    """L'utilisateur doit être admin d'une école ET appartenir à cette école."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Veuillez vous connecter.', 'warning')
            return redirect(url_for('auth.login'))

        if current_user.role not in ('super_admin', 'school_admin'):
            flash("Accès réservé aux administrateurs.", 'danger')
            return abort(403)

        if current_user.role == 'school_admin' and not current_user.school_id:
            flash("Aucune école associée à votre compte.", 'warning')
            return redirect(url_for('dashboard.index'))

        return f(*args, **kwargs)
    return decorated_function
