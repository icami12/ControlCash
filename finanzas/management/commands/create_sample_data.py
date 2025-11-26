from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from finanzas.models import Categoria, Transaccion
from decimal import Decimal
from datetime import datetime, timedelta
import random

class Command(BaseCommand):
    help = 'Creates sample data for testing'

    def handle(self, *args, **kwargs):
        # Create a test user if it doesn't exist
        username = 'testuser'
        email = 'test@example.com'
        password = 'password123'
        
        if not User.objects.filter(username=username).exists():
            User.objects.create_user(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f'Created test user: {username}'))
        
        user = User.objects.get(username=username)
        
        # Create categories
        categories = ['Comida', 'Salario', 'Compras', 'Transporte', 'Entretenimiento', 'Servicios']
        
        for category_name in categories:
            Categoria.objects.get_or_create(nombre=category_name, usuario=user)
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(categories)} categories'))
        
        # Create transactions
        Transaccion.objects.filter(usuario=user).delete()  # Clear existing transactions
        
        # Sample transactions
        transactions = [
            {
                'descripcion': 'Restaurante El Sabor',
                'categoria': 'Comida',
                'cantidad': Decimal('35'),
                'tipo': 'gasto',
                'fecha': datetime.now().date() - timedelta(days=1)
            },
            {
                'descripcion': 'Empresa XYZ',
                'categoria': 'Salario',
                'cantidad': Decimal('2000'),
                'tipo': 'ingreso',
                'fecha': datetime.now().date() - timedelta(days=3)
            },
            {
                'descripcion': 'Tienda ABC',
                'categoria': 'Compras',
                'cantidad': Decimal('120'),
                'tipo': 'gasto',
                'fecha': datetime.now().date() - timedelta(days=2)
            },
            {
                'descripcion': 'Freelance Proyecto',
                'categoria': 'Salario',
                'cantidad': Decimal('500'),
                'tipo': 'ingreso',
                'fecha': datetime.now().date() - timedelta(days=5)
            },
            {
                'descripcion': 'Supermercado',
                'categoria': 'Comida',
                'cantidad': Decimal('85'),
                'tipo': 'gasto',
                'fecha': datetime.now().date() - timedelta(days=4)
            }
        ]
        
        for t in transactions:
            categoria = Categoria.objects.get(nombre=t['categoria'], usuario=user)
            Transaccion.objects.create(
                usuario=user,
                descripcion=t['descripcion'],
                categoria=categoria,
                cantidad=t['cantidad'],
                tipo=t['tipo'],
                fecha=t['fecha']
            )
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(transactions)} transactions'))