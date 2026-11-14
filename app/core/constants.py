STATUS_LABELS = {
    "received": "New", "in_progress": "In progress", "needs_documents": "Needs documents",
    "completed": "Completed", "cancelled": "Cancelled",
}
STATUS_STYLES = {
    "received": "bg-brand-red/10 text-brand-red", "in_progress": "bg-amber-100 text-amber-800",
    "needs_documents": "bg-orange-100 text-orange-800", "completed": "bg-emerald-100 text-emerald-800",
    "cancelled": "bg-slate-100 text-slate-600",
}
CATEGORIES = [("government", "Government", 0), ("education", "Education", 1), ("online", "Online", 2)]

PERMISSIONS = {
    "requests.view": "View requests",
    "requests.update": "Change request status and messages",
    "customers.view": "View customers",
    "services.manage": "Manage services and prices",
    "reports.view": "View the dashboard and reports",
    "reports.export": "Export CSV files",
    "admins.manage": "Manage administrators",
    "audit.view": "View the audit log",
}
_STAFF = ["requests.view", "requests.update", "customers.view", "reports.view"]
_MANAGER = _STAFF + ["services.manage", "reports.export"]
ROLE_DEFAULTS = {
    "owner": ("Full access", list(PERMISSIONS)),
    "manager": ("Runs daily operations", _MANAGER),
    "staff": ("Handles requests", _STAFF),
}
