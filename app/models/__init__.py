from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Importer tous les modeles pour que SQLAlchemy les decouvre
from app.models.user import User, Role, Permission, RolePermission  # noqa
from app.models.school import School  # noqa
from app.models.subscription import Plan, Subscription, Payment  # noqa
from app.models.academic import AcademicYear, Subject, Class, ClassSubject, Trimester, Period, Deliberation  # noqa
from app.models.student import StudentProfile, StudentParent, StudentEnrollment  # noqa
from app.models.timetable import Timetable  # noqa
from app.models.grade import Grade  # noqa
from app.models.finance import FeeType, Fee, SchoolPayment  # noqa
from app.models.announcement import Announcement  # noqa
from app.models.attendance import Attendance  # noqa
from app.models.audit_log import AuditLog  # noqa
from app.models.assignment import Assignment, Submission  # noqa
