from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.urls import path
from django.shortcuts import render, redirect
import pandas as pd
from .models import CustomUser, Empresas

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

class EmpresasAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'detalle', 'memo')
    search_fields = ('nombre', 'detalle', 'memo')
    change_list_template = 'admin/empresas/ButtonUpload.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('empresas/upload-excel/', self.admin_site.admin_view(self.upload_excel), name='core_empresas_upload_excel'),
        ]
        return custom_urls + urls

    def upload_excel(self, request):
        if request.method == 'POST':
            excel_file = request.FILES.get('excel_file')
            if excel_file:
                try:
                    df = pd.read_excel(excel_file)
                    df.columns = [str(c).upper().strip() for c in df.columns]
                    
                    registros_creados_o_actualizados = 0
                    for _, row in df.iterrows():
                        nombre = str(row.get("NOMBRE", "")).upper().strip()
                        if nombre and nombre.lower() != 'nan':
                            detalle = str(row.get("DETALLE", "OTROS")).upper().strip()
                            memo = str(row.get("MEMO", "PROFESIONAL")).upper().strip()
                            
                            Empresas.objects.update_or_create(
                                nombre=nombre,
                                defaults={
                                    'detalle': detalle if detalle.lower() != 'nan' else 'OTROS',
                                    'memo': memo if memo.lower() != 'nan' else 'PROFESIONAL'
                                }
                            )
                            registros_creados_o_actualizados += 1
                            
                    self.message_user(request, f"Se procesaron {registros_creados_o_actualizados} registros correctamente.", level=messages.SUCCESS)
                    return redirect('..')
                except Exception as e:
                    self.message_user(request, f"Error al procesar el archivo Excel: {e}", level=messages.ERROR)
                    return redirect('..')
            else:
                self.message_user(request, "No se seleccionó ningún archivo.", level=messages.WARNING)
                return redirect('..')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Cargar Excel de Empresas',
            'opts': self.model._meta,
        }
        return render(request, 'admin/empresas/upload_excel.html', context)

admin.site.register(Empresas, EmpresasAdmin)
