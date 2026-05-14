from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    
    # Para que aparezcan cuando editas un usuario
    fieldsets = UserAdmin.fieldsets + (
        ('Acceso Conexión Premium', {'fields': ('user_premium', 'expire_premium')}),
    )
    
    # Para que aparezcan cuando creas un usuario nuevo desde el admin
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Acceso Conexión Premium', {'fields': ('user_premium', 'expire_premium')}),
    )
    
    # Para que salgan como columnas en la tabla principal
    list_display = ['username', 'email', 'user_premium', 'expire_premium', 'is_staff']

admin.site.register(CustomUser, CustomUserAdmin)
