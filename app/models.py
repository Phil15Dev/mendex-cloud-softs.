"""Imports every model so Alembic and the tests see the full schema."""
from app.modules.admin.models import AdminAuditLog, AdminRole, Permission, role_permissions  # noqa: F401
from app.modules.auth.models import AdminAccount, AdminSession, PasswordReset  # noqa: F401
from app.modules.customers.models import Customer  # noqa: F401
from app.modules.notifications.models import EmailLog, Notification  # noqa: F401
from app.modules.requests.models import RequestStatusHistory, ServiceRequest  # noqa: F401
from app.modules.services.models import Service, ServiceCategory, service_category_links  # noqa: F401
