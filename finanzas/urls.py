from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),  # Changed to use custom view
    path('nuevo-registro/', views.nuevo_registro, name='nuevo_registro'),
    path('historial-transacciones/', views.historial_transacciones, name='historial_transacciones'),
    path('webhook/telegram/', views.webhook, name='webhook'),
    path('telegramBot/', views.vincular_telegram, name='vincularConBot'),
    path('desvincular-telegram/', views.desvincular_telegram, name='desvincular_telegram'),
    path("marcar-notificaciones-leidas/", views.marcar_notificaciones_leidas, name="marcar_notificaciones_leidas"),
    path('transaccion/eliminar/<int:id>/', views.eliminar_transaccion, name='eliminar_transaccion'),
    path('terminos/', views.terminos, name='terminos')
]