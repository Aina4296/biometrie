from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .models import Role, Permission

@receiver(post_migrate)
def create_default_roles_permissions(sender, **kwargs):
    # Création des rôles
    for role_name in ['admin', 'saisisseur', 'consulteur']:
        Role.objects.get_or_create(name=role_name)

    # Création de la permission view_users
    Permission.objects.get_or_create(
        code='view_users', description='Voir la liste des utilisateurs'
    )
