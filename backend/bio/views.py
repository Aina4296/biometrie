from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse
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
from .models import Personne, FicheAnthropometrique, FicheDactyloscopique, Role, Activite
from .serializers import PersonneSerializer, FicheAnthroSerializer, FicheDactyloSerializer, ActiviteSerializer
import insightface
from django.core.files.storage import default_storage
import os
import cv2
import numpy as np
from django.conf import settings
from django.contrib.auth import authenticate
import pandas as pd
import io
from xml.etree.ElementTree import Element, SubElement, tostring
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from rest_framework_simplejwt.views import TokenObtainPairView


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

class RecherchePhotoView(APIView):
    def post(self, request):
        photo_file = request.FILES.get('photo')
        if not photo_file:
            return Response({"error": "Aucune photo envoyée."}, status=400)

        tmp_path = default_storage.save('tmp_search.jpg', photo_file)
        tmp_full_path = os.path.join(settings.MEDIA_ROOT, tmp_path)

        try:
            model = insightface.app.FaceAnalysis(providers=['CPUExecutionProvider'])
            model.prepare(ctx_id=-1, det_size=(640, 640))

            img = cv2.imread(tmp_full_path)
            if img is None:
                return Response({"error": "Impossible de lire la photo envoyée."}, status=400)

            faces = model.get(img)
            print("👤 Visages détectés dans la photo envoyée :", len(faces))
            if len(faces) == 0:
                return Response({"results": [], "message": "Aucun visage détecté."})

            target_embedding = faces[0].embedding
            results = []

            base_dir = os.path.join(settings.BASE_DIR, "backend", "photos")

            for personne in Personne.objects.all():
                photos_potentielles = [
                    personne.photo_profil,
                    personne.photo_face,
                    personne.photo_longue
                ]

                for p in photos_potentielles:
                    if not p:
                        continue

                    photo_path = os.path.join(settings.BASE_DIR, 'photos', os.path.basename(str(p)))

                    print("🔍 Test photo:", photo_path)

                    if not os.path.exists(photo_path):
                        continue

                    db_img = cv2.imread(photo_path)
                    if db_img is None:
                        continue

                    db_faces = model.get(db_img)
                    print(f"📸 {photo_path} → {len(db_faces)} visage(s) détecté(s)")
                    if len(db_faces) == 0:
                        continue

                    db_embedding = db_faces[0].embedding
                    similarity = np.dot(target_embedding, db_embedding) / (
                        np.linalg.norm(target_embedding) * np.linalg.norm(db_embedding)
                    )

                    print(f"📏 Similarité avec {personne.nom} {personne.prenom}: {similarity:.2f}")

                    if similarity > 0.6:  # seuil
                        results.append({
                            "id": personne.id,
                            "nom": personne.nom,
                            "prenom": personne.prenom,
                            "similarity": float(similarity),
                            "photo": request.build_absolute_uri(p.url)
                        })
                        break  # on passe à la personne suivante dès qu’une correspondance est trouvée

            results.sort(key=lambda x: x["similarity"], reverse=True)
            return Response({"results": results})

        except Exception as e:
            print("Erreur pendant la recherche photo :", e)
            return Response({"error": str(e)}, status=500)
        finally:
            if default_storage.exists(tmp_path):
                default_storage.delete(tmp_path)

#export des données 
class ExportDataView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, format=None):
        username = request.data.get('username')
        password = request.data.get('password')
        format_type = request.data.get('format')
        fiche_id = request.data.get('id')  # ✅ récupère l'ID s'il existe

        # Vérification des identifiants
        user = authenticate(username=username, password=password)
        if user is None:
            return Response({'error': 'Identifiants invalides'}, status=status.HTTP_401_UNAUTHORIZED)

        # Si un ID est fourni → exporter une seule fiche
        if fiche_id:
            personnes = Personne.objects.filter(id=fiche_id).values()
            if not personnes.exists():
                return Response({'error': 'Fiche introuvable'}, status=status.HTTP_404_NOT_FOUND)
        else:
            personnes = Personne.objects.all().values()

        # --- EXPORT EXCEL ---
        if format_type == 'excel':
            df = pd.DataFrame(list(personnes))
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False)
            buffer.seek(0)
            response = HttpResponse(buffer, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = 'attachment; filename="export.xlsx"'
            return response

        # --- EXPORT XML ---
        elif format_type == 'xml':
            root = Element('Personnes')
            for p in personnes:
                person_el = SubElement(root, 'Personne')
                for key, val in p.items():
                    SubElement(person_el, key).text = str(val)
            xml_data = tostring(root, encoding='utf-8')
            response = HttpResponse(xml_data, content_type='application/xml')
            response['Content-Disposition'] = 'attachment; filename="export.xml"'
            return response

        # --- EXPORT PDF ---
        elif format_type == 'pdf':
            buffer = io.BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=A4)
            pdf.setFont("Helvetica", 10)
            y = 800
            for p in personnes:
                text = ", ".join(f"{k}: {v}" for k, v in p.items())
                pdf.drawString(50, y, text)
                y -= 20
                if y < 50:
                    pdf.showPage()
                    y = 800
            pdf.save()
            buffer.seek(0)
            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="export.pdf"'
            return response

        else:
            return Response({'error': 'Format invalide'}, status=status.HTTP_400_BAD_REQUEST)

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Personnalisation du login JWT pour enregistrer une activité.
    """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            username = request.data.get("username")
            from django.contrib.auth.models import User
            try:
                user = Utilisateur.objects.get(username=username)
                Activite.objects.create(
                    utilisateur=user,
                    action="connexion",
                    description=f"{user.username} s'est connecté."
                )
            except Utilisateur.DoesNotExist:
                pass
        return response

class ActiviteListView(generics.ListAPIView):
    queryset = Activite.objects.all()
    serializer_class = ActiviteSerializer
    permission_classes = [permissions.IsAdminUser]