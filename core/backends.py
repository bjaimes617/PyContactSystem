from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        try:
            # Intentar buscar al usuario por su email
            user = UserModel.objects.get(email=username)
        except UserModel.DoesNotExist:
            # Si no se encuentra por email, buscar por username (comportamiento por defecto)
            try:
                user = UserModel.objects.get(username=username)
            except UserModel.DoesNotExist:
                return None

        # Si el usuario existe y la contraseña es correcta, permitir acceso
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
