from app.models.audit_log import AuditLog
from app.models import db
from flask import request
from flask_login import current_user


def log_action(action, table_name=None, record_id=None, details=None):
    log = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        table_name=table_name,
        record_id=record_id,
        details=details,
        ip_address=request.remote_addr or '127.0.0.1'
    )
    db.session.add(log)
    db.session.commit()
