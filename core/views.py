from django.shortcuts import render
from django.contrib.auth.forms import AuthenticationForm
# Create your views here.

def index(request):
    # Si el usuario ya inició sesión, lo mandamos al index
    if request.user.is_authenticated:
        return render(request,'dashboard.html')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            # Extraer y limpiar los datos del formulario
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            
            # Validar contra la base de datos de Django (y Supabase)
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)  # Crea la sesión del usuario
                return redirect('main')  # Redirige a tu función index
        else:
            return render(request, 'main.html')
    else:
        return render(request, 'main.html')
