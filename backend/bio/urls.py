from django.urls import path
from .views import UsersListView, create_user, me, PersonneCreateView, PersonneListView, DashboardViewSet, RecherchePhotoView, ExportDataView, ActiviteListView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import CustomTokenObtainPairView

urlpatterns = [
    path('api/users/', UsersListView.as_view(), name='users-list'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/create-user/', create_user, name="create-user"),
    path('api/me/', me, name='api-me'),
    path('api/personnes/', PersonneCreateView.as_view(), name='personne-list-create'),
    path('api/listes/', PersonneListView.as_view(), name='personne-list'),  
    path('api/dashboard/', DashboardViewSet.as_view({'get': 'list'}), name='dashboard'),
    path('api/recherche-photo/', RecherchePhotoView.as_view(), name='recherche-photo'),
    path('api/export/', ExportDataView.as_view(), name='export-data'),
    path('api/activites/', ActiviteListView.as_view()),

]
   
