from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from datetime import date
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as auth_logout
from django.views.decorators.cache import never_cache

@never_cache
def index(request):
    # Si el usuario ya inició sesión, lo mandamos al index
    if request.user.is_authenticated:        
        return redirect('dashboard')

    if request.method == 'POST':
        # Sacamos los datos directamente del POST
        username_input = request.POST.get('username')
        password_input = request.POST.get('password')
    
        if username_input == "" or password_input == "":
            messages.error(request, 'Los Campos Email y Contraseña no pueden estar vacios.')
            return redirect('/')            
            
        from .models import CustomUser
        
        # 1. Verificar si el usuario existe (por email o por username)
        try:
            user = CustomUser.objects.get(email=username_input)
        except CustomUser.DoesNotExist:
            try:
                user = CustomUser.objects.get(username=username_input)
            except CustomUser.DoesNotExist:
                # No existe ni por email ni por username
                messages.error(request, 'El Email Ingresado no se encuentra registrado.')
                return redirect('/')
                
        # 2. El usuario existe. Verificamos si la contraseña es correcta.
        if not user.check_password(password_input):
            messages.error(request, 'Lo sentimos, tus credenciales no son válidas.')
            return redirect('/')
            
        # 3. La contraseña es correcta. Verificamos permisos (Staff y Premium)
        if user.is_staff:
            login(request, user)
            return redirect('dashboard')
            
        if user.user_premium and user.expire_premium and user.expire_premium >= date.today():
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Tu cuenta no tiene acceso Premium o tu suscripción ha expirado.')
            return redirect('/')
            
    else:        
        return render(request, 'login/index.html')

@login_required
def dashboard(request):    
    return render(request, 'dashboard/index.html')   

@login_required
def logout(request):   
    if request.method == 'POST':
        auth_logout(request)
        return redirect('index')
    return redirect('dashboard')