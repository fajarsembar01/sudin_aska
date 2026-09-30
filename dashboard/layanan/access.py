"""One access policy for the portal card and every service endpoint."""
from functools import wraps

from flask import abort
from dashboard.auth import current_user, login_required
from .queries import has_layanan_access

STAFF_ROLES = ('staff', 'pengawas', 'kasi', 'operator')


def can_access_layanan(user):
    if not user or not user.get('id'):
        return False
    if user.get('role') == 'admin':
        return True
    return user.get('role') in STAFF_ROLES and has_layanan_access(user['id'])


def layanan_access_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not can_access_layanan(current_user()):
            abort(403, 'Akses Layanan belum diberikan. Hubungi admin untuk meminta akses.')
        return view(*args, **kwargs)
    return wrapped
