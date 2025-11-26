from django.db import models
from django.contrib.auth.models import User

class Categoria(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre

class Transaccion(models.Model):
    TIPO_CHOICES = [
        ('ingreso', 'Ingreso'),
        ('gasto', 'Gasto'),
    ]
    CATEGORIA_CHOICES = [
        ('Comida', 'comida'),
        ('Salario', 'salario'),
        ('Compras', 'compras'),
        ('Transferencias', 'transferencias'),
        ('Servicios', 'servicios'),
        ('Ventas', 'ventas'),
        ('Otros', 'otros'),
    ]
    
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion = models.CharField(max_length=200)
    categoria = models.CharField(max_length=50, choices=CATEGORIA_CHOICES, default='Otros')
    destino = models.CharField(max_length=200, null=True, blank=True)  # Campo opcional
    fecha = models.DateField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.descripcion} - {self.cantidad}"
    
    class Meta:
        verbose_name = "Transacción"
        verbose_name_plural = "Transacciones"
        ordering = ['-fecha', '-fecha_creacion']

class Perfil(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    telegram_code = models.CharField(max_length=10, null=True, blank=True)
    telegram_chat_id = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return self.user.username

class Notificacion(models.Model):
    texto = models.CharField(max_length=255)
    fecha = models.DateTimeField(auto_now_add=True)
    leido = models.BooleanField(default=False)

    def __str__(self):
        return self.texto
