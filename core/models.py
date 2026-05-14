from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    # Aquí puedes agregar tus campos personalizados, por ejemplo:
    # telefono = models.CharField(max_length=20, blank=True, null=True)
    # direccion = models.CharField(max_length=255, blank=True, null=True)
    user_premium = models.BooleanField(default=False)
    expire_premium = models.DateField(null=True, blank=True)    
    
    def __str__(self):
        return self.email

