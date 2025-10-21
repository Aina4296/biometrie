from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


class Role(models.Model):
    ADMIN = 'admin'
    SAISISSEUR = 'saisisseur'
    CONSULTEUR = 'consulteur'

    ROLE_CHOICES = [
        (ADMIN, 'Administrateur'),
        (SAISISSEUR, 'Saisisseur'),
        (CONSULTEUR, 'Consulteur'),
    ]

    name = models.CharField(max_length=50, choices=ROLE_CHOICES, unique=True)

    def __str__(self):
        return self.name

# Permission
class Permission(models.Model):
    code = models.CharField(max_length=50, unique=True)  # ex: "view_users"
    description = models.TextField(blank=True)

    def __str__(self):
        return self.code

class Utilisateur(AbstractUser):
    role = models.ForeignKey('Role', on_delete=models.SET_NULL, null=True, blank=True)
    permissions = models.ManyToManyField('Permission', blank=True)

    def has_permission(self, perm_code):
        return self.permissions.filter(code=perm_code).exists() or self.is_superuser

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Sauvegarde d’abord l’utilisateur
        from .models import Permission
        try:
            view_users_perm = Permission.objects.get(code='view_users')
        except Permission.DoesNotExist:
            view_users_perm = Permission.objects.create(
                code='view_users', description='Voir la liste des utilisateurs'
            )

        try:
            view_personnes_perm = Permission.objects.get(code='view_personnes')
        except Permission.DoesNotExist:
            view_personnes_perm = Permission.objects.create(
                code='view_personnes', description='Peut voir la liste des fiches Personne'
        )

        # Si superuser ou rôle admin, on ajoute la permission
        if self.is_superuser or (self.role and self.role.name == 'admin'):
            self.permissions.add(view_users_perm)
        elif self.role and self.role.name == 'saisisseur':
            self.permissions.add(view_personnes_perm)


class Personne(models.Model):
    created_by = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL,
        related_name="personnes_creees", null=True, blank=True
    )
    updated_by = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL,
        related_name="personnes_modifiees", null=True, blank=True
    )

    nom = models.CharField(max_length=100, blank=True, null=True)
    prenom = models.CharField(max_length=100, blank=True, null=True)
    surnom = models.CharField(max_length=100, blank=True, null=True)
    genre = models.CharField(max_length=10, blank=True, null=True)
    date_naissance = models.DateField(null=True, blank=True)
    lieu_naissance = models.CharField(max_length=100, blank=True, null=True)
    nationalite = models.CharField(max_length=100, blank=True, null=True)
    domicile = models.CharField(max_length=200, blank=True, null=True)
    filiation_pere = models.CharField(max_length=100, blank=True, null=True)
    filiation_mere = models.CharField(max_length=100, blank=True, null=True)
    nom_epouse = models.CharField(max_length=100, blank=True, null=True)
    profession = models.CharField(max_length=50, blank=True, null=True)

    photo_face = models.ImageField(upload_to="photos/", blank=True, null=True)
    photo_profil = models.ImageField(upload_to="photos/", blank=True, null=True)
    photo_longue = models.ImageField(upload_to="photos/", blank=True, null=True)

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nom} {self.prenom}"


class FicheAnthropometrique(models.Model):
    personne = models.OneToOneField(Personne, on_delete=models.CASCADE, related_name="anthropometrique")
    unite_origine = models.CharField(max_length=200, blank=True, null=True)
    numero = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    province = models.CharField(max_length=100, blank=True, null=True)
    arrondissement = models.CharField(max_length=100, blank=True, null=True)
    faits = models.TextField(blank=True, null=True)
    marque_particuliere = models.TextField(blank=True, null=True)
    vehicule_zone_action = models.CharField(max_length=200, blank=True, null=True)


class FicheDactyloscopique(models.Model):
    personne = models.OneToOneField(Personne, on_delete=models.CASCADE, related_name="dactyloscopique")
    taille = models.CharField(max_length=10, blank=True, null=True)
    corpulance = models.CharField(max_length=50, blank=True, null=True)
    cheveux = models.CharField(max_length=50, blank=True, null=True)
    visage = models.CharField(max_length=50, blank=True, null=True)
    ethnie = models.CharField(max_length=50, blank=True, null=True)
    contact = models.CharField(max_length=50, blank=True, null=True)
    cin = models.CharField(max_length=50, blank=True, null=True)
    service_militaire = models.CharField(max_length=50, blank=True, null=True)
    contact_epouse = models.CharField(max_length=50, blank=True, null=True)
    motifs = models.TextField(blank=True, null=True)
    date_lieu_arrestation = models.TextField(blank=True, null=True)
    unite_arrestation = models.CharField(max_length=50, blank=True, null=True)
    nrpv = models.CharField(max_length=50, blank=True, null=True)
    par = models.CharField(max_length=50, blank=True, null=True)


# Signal pour créer automatiquement les fiches vides
@receiver(post_save, sender=Personne)
def create_fiches(sender, instance, created, **kwargs):
    if created:
        FicheAnthropometrique.objects.create(personne=instance)
        FicheDactyloscopique.objects.create(personne=instance)


class Activite(models.Model):
    ACTIONS = [
        ('connexion', 'Connexion'),
        ('ajout_fiche', 'Ajout de fiche'),
        ('suppression_fiche', 'Suppression de fiche'),
    ]

    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE)
    action = models.CharField(max_length=50, choices=ACTIONS)
    description = models.TextField(blank=True)
    date_heure = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_heure']

    def __str__(self):
        return f"{self.utilisateur.username} - {self.action}"