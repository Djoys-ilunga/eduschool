import os
import sqlite3
import shutil
import tempfile
from datetime import datetime
from flask import (
    render_template, redirect, url_for, flash, request,
    send_file, current_app as app
)
from werkzeug.utils import secure_filename
from app.admin import admin_bp
from app.auth.decorators import role_required
from app.models.audit_log import AuditLog
from app.utils.audit import log_action


def _get_db_path():
    """Extrait le chemin du fichier SQLite depuis SQLALCHEMY_DATABASE_URI."""
    import os
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if uri.startswith('sqlite:///'):
        path = uri[len('sqlite:///'):]
        # Supporte chemins relatifs et absolus
        if not os.path.isabs(path):
            path = os.path.join(app.instance_path, path)
        return path
    return None


@admin_bp.route('/audit-logs')
@role_required('super_admin')
def audit_logs():
    """Journal d'audit — réservé aux super_admin."""
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return render_template('admin/audit_logs.html', logs=logs,
                          breadcrumbs=[("Journal d'Audit", None)])


@admin_bp.route('/backup')
@role_required('super_admin')
def backup_database():
    """Télécharge une copie de sauvegarde du fichier SQLite."""
    db_path = _get_db_path()
    if not db_path or not os.path.exists(db_path):
        flash('Base de données introuvable.', 'danger')
        return redirect(request.referrer or url_for('dashboard.index'))

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f'eduschool_backup_{timestamp}.db'

    log_action('backup', details=f'Sauvegarde DB téléchargée: {filename}')

    return send_file(
        db_path,
        as_attachment=True,
        download_name=filename,
        mimetype='application/octet-stream'
    )


@admin_bp.route('/restore', methods=['GET', 'POST'])
@role_required('super_admin')
def restore_database():
    """Upload + validation + remplacement du fichier DB (GET: formulaire, POST: traitement)."""
    if request.method == 'GET':
        return render_template(
            'admin/restore.html',
            breadcrumbs=[("Restauration DB", None)]
        )

    # POST: traitement de l'upload
    uploaded = request.files.get('db_file')
    if not uploaded or uploaded.filename == '':
        flash('Aucun fichier sélectionné.', 'danger')
        return redirect(url_for('admin.restore_database'))

    filename = secure_filename(uploaded.filename)
    if not filename.endswith('.db'):
        flash('Fichier invalide. Seuls les fichiers .db (SQLite) sont acceptés.', 'danger')
        return redirect(url_for('admin.restore_database'))

    db_path = _get_db_path()
    if not db_path:
        flash('Base de données non configurée en SQLite.', 'danger')
        return redirect(url_for('admin.restore_database'))

    # Sauvegarde le fichier uploadé dans un fichier temporaire pour validation
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        uploaded.save(tmp.name)
        tmp_path = tmp.name

    try:
        # Validation du fichier SQLite
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        if not tables:
            flash('Fichier invalide : aucune table trouvée dans la base de données.', 'danger')
            os.unlink(tmp_path)
            return redirect(url_for('admin.restore_database'))

        # Sauvegarde de l'ancienne DB avant remplacement
        backup_name = db_path + f'.backup_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}'
        shutil.copy2(db_path, backup_name)

        # Remplacement
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        shutil.copy2(tmp_path, db_path)

        log_action('restore', details=f'DB restaurée depuis upload. Backup: {os.path.basename(backup_name)}')

        flash(
            f'Base de données restaurée avec succès ! '
            f'{len(tables)} tables détectées. '
            f'Ancienne DB sauvegardée: {os.path.basename(backup_name)}',
            'success'
        )
    except sqlite3.Error as e:
        flash(f'Erreur SQLite lors de la validation : {e}', 'danger')
    except Exception as e:
        flash(f'Erreur lors de la restauration : {e}', 'danger')
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return redirect(url_for('admin.restore_database'))
