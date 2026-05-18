from django.urls import path
from . import views
from .controllers.Uploads import Uploadindex

urlpatterns = [
    path('', views.index, name='index'),
    path('login', views.index, name='login'),   
    path('dashboard', views.dashboard, name='dashboard'),
    path('logout', views.logout, name='logout'),   
    path('Cargador', Uploadindex, name='Cargador'),
]