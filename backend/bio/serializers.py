from rest_framework import serializers
from .models import Utilisateur, Role
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Personne, FicheAnthropometrique, FicheDactyloscopique
from datetime import date

# serializers.py
class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name']

class UtilisateurSerializer(serializers.ModelSerializer):
    role = RoleSerializer()  # inclut name
    class Meta:
        model = Utilisateur
        fields = ['id', 'username', 'email', 'role']


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'  # Utiliser email pour login

    def validate(self, attrs):
        # Vérifie email et password
        data = super().validate(attrs)
        data['user'] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": self.user.role.name if self.user.role else None
        }
        return data


class FicheAnthroSerializer(serializers.ModelSerializer):
    class Meta:
        model = FicheAnthropometrique
        exclude = ('personne',)  # on gère la liaison côté view

class FicheDactyloSerializer(serializers.ModelSerializer):
    class Meta:
        model = FicheDactyloscopique
        exclude = ('personne',)


class PersonneSerializer(serializers.ModelSerializer):
    anthropometrique = FicheAnthroSerializer(read_only=True)
    dactyloscopique = FicheDactyloSerializer(read_only=True)
    age = serializers.SerializerMethodField()

    class Meta:
        model = Personne
        fields = [
            'id', 'nom', 'prenom', 'surnom', 'genre', 'date_naissance', 'lieu_naissance',
            'nationalite', 'domicile', 'filiation_pere', 'filiation_mere', 'nom_epouse',
            'profession', 'photo_face', 'photo_profil', 'photo_longue',
            'date_creation', 'date_modification',
            'anthropometrique', 'dactyloscopique','age',
        ]
        read_only_fields = ('date_creation','date_modification',)
    def get_age(self, obj):
        if obj.date_naissance:
            today = date.today()
            age = today.year - obj.date_naissance.year
            if (today.month, today.day) < (obj.date_naissance.month, obj.date_naissance.day):
                age -= 1
            return age
        return None
