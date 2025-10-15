from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Utilisateur, Role
from .serializers import UtilisateurSerializer
from rest_framework.decorators import api_view, permission_classes
from django.contrib.auth import get_user_model
from rest_framework import status , permissions, generics, viewsets
import json
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from django.db.models import Count, Q
from datetime import date
from rest_framework.generics import ListAPIView

from .models import Personne, FicheAnthropometrique, FicheDactyloscopique, Role
from .serializers import PersonneSerializer, FicheAnthroSerializer, FicheDactyloSerializer

class UsersListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.has_permission('view_users'):
            users = Utilisateur.objects.all()
            serializer = UtilisateurSerializer(users, many=True)
            return Response(serializer.data)
        return Response({"detail": "Permission refusée"}, status=403)



User = get_user_model()

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    user = request.user
    serializer = UtilisateurSerializer(user)
    return Response(serializer.data)

    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_user(request):
    current_user = request.user

    if not (current_user.is_superuser or (current_user.role and current_user.role.name == "admin")):
        return Response({"detail": "Accès refusé"}, status=status.HTTP_403_FORBIDDEN)

    data = request.data
    if data["password"] != data["confirm_password"]:
        return Response({"detail": "Mots de passe différents"}, status=status.HTTP_400_BAD_REQUEST)

    # Récupérer l'instance Role par nom
    try:
        role_instance = Role.objects.get(name=data["role"])
    except Role.DoesNotExist:
        return Response({"detail": "Rôle invalide"}, status=status.HTTP_400_BAD_REQUEST)

    # Créer l’utilisateur avec instance de rôle
    user = User.objects.create_user(
        username=data["username"],
        email=data["email"],
        password=data["password"],
        role=role_instance
    )

    return Response({"detail": "Utilisateur créé avec succès"}, status=status.HTTP_201_CREATED)




class CanCreatePersonne(permissions.BasePermission):
    """
    Seuls les users ayant role 'admin' ou 'saisisseur' ou les superusers peuvent créer.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        
        role = getattr(user, 'role', None)
        role_name = getattr(role, 'name', role) if role is not None else None
        return role_name in ('admin','saisisseur')

class PersonneCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, CanCreatePersonne]
    parser_classes = [MultiPartParser, FormParser]  

    def post(self, request, format=None):
        data = request.data.copy()
        anthro_json = data.get('anthropometrique', None)
        dactylo_json = data.get('dactyloscopique', None)

        anthropo_data = {}
        dactylo_data = {}
        if anthro_json:
            try:
                anthropo_data = json.loads(anthro_json)
            except Exception:
                anthropo_data = {}
        if dactylo_json:
            try:
                dactylo_data = json.loads(dactylo_json)
            except Exception:
                dactylo_data = {}
        # Construire la personne 
        personne_fields = {}
        allowed = [
            'nom','prenom','surnom','genre','date_naissance','lieu_naissance',
            'nationalite','domicile','filiation_pere','filiation_mere','nom_epouse',
            'profession'
        ]
        for f in allowed:
            if f in data:
                personne_fields[f] = data.get(f)

    # images
        if 'photo_face' in request.FILES:
            personne_fields['photo_face'] = request.FILES['photo_face']
        if 'photo_profil' in request.FILES:
            personne_fields['photo_profil'] = request.FILES['photo_profil']
        if 'photo_longue' in request.FILES:
            personne_fields['photo_longue'] = request.FILES['photo_longue']

    # créer Personne en liant created_by
        personne = Personne.objects.create(created_by=request.user, **personne_fields)

    # créer/mettre à jour fiches associées
        FicheAnthropometrique.objects.update_or_create(
            personne=personne,
            defaults={k: v for k, v in anthropo_data.items()}
        )

        FicheDactyloscopique.objects.update_or_create(
            personne=personne,
            defaults={k: v for k, v in dactylo_data.items()}
        )

        serializer = PersonneSerializer(personne, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)



class PersonneListView(generics.ListAPIView):
    queryset = Personne.objects.all()
    serializer_class = PersonneSerializer
    permission_classes = [permissions.IsAuthenticated]  # tous les users connectés

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search', None)
        if search:
            qs = qs.filter(
                Q(nom__icontains=search) |
                Q(prenom__icontains=search) |
                Q(lieu_naissance__icontains=search) |
                Q(domicile__icontains=search)
            )
        return qs


class DashboardViewSet(viewsets.ViewSet):
    """
    ViewSet du tableau de bord : tous les utilisateurs connectés
    peuvent voir les statistiques globales sur les fiches Personne.
    """
    permission_classes = [permissions.IsAuthenticated]  # tous les users connectés ont accès

    def list(self, request):
        personnes = Personne.objects.all()

        # --- Total fiches ---
        total = personnes.count()

        # --- Fiches par date ---
        fiches_par_date = (
            personnes
            .extra(select={'date': "date(date_creation)"})
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )

        # --- Répartition par âge ---
        fiches_par_age = []
        for p in personnes:
            if p.date_naissance:
                age = date.today().year - p.date_naissance.year
                fiches_par_age.append(age)

        age_stats = {}
        for a in fiches_par_age:
            age_stats[a] = age_stats.get(a, 0) + 1
        fiches_par_age = [{"age": k, "count": v} for k, v in age_stats.items()]

        # --- Répartition par genre ---
        fiches_par_genre = (
            personnes.values('genre')
            .annotate(value=Count('id'))
        )
        fiches_par_genre = [
            {"name": f["genre"] or "Non spécifié", "value": f["value"]}
            for f in fiches_par_genre
        ]

        return Response({
            "total": total,
            "par_date": list(fiches_par_date),
            "par_age": fiches_par_age,
            "par_genre": fiches_par_genre,
        })