# permissions.py (DRF custom permission)
from rest_framework.permissions import BasePermission

class HasCustomPermission(BasePermission):
    def __init__(self, code):
        self.code = code

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        return user.role and user.role.permissions.filter(code=self.code).exists()
