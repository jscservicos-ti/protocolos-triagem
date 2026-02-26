from django.contrib import admin
from django.urls import path
from clinica import views

urlpatterns = [
    # Painel Administrativo padrão do Django
    path('admin/', admin.site.urls),
    
    # Rotas das Telas Principais (Front-End)
    path('', views.pagina_login, name='login'),
    path('triagem/', views.pagina_triagem, name='triagem'),
    path('historico/', views.historico_triagem, name='historico_triagem'),
    path('triagem/editar/<int:id>/', views.editar_triagem, name='editar_triagem'),
    path('triagem/excluir/<int:id>/', views.excluir_triagem, name='excluir_triagem'),
    path('administracao/', views.painel_admin, name='painel_admin'),
    path('medico/', views.pagina_medico, name='medico'),
    path('api/verificar-alertas/', views.verificar_alertas, name='verificar_alertas'),
    path('relatorios/', views.relatorios, name='relatorios'),
    path('finalizar/<int:id>/', views.finalizar_atendimento, name='finalizar_atendimento'),
    path('reabrir/<int:id>/', views.reabrir_atendimento, name='reabrir_atendimento'),
    path('api/inativar-usuario/<int:id>/', views.inativar_usuario, name='inativar_usuario'),
    path('api/excluir-usuario/<int:id>/', views.excluir_usuario, name='excluir_usuario'),
        
    # Rotas com ID dinâmico (Ações específicas para um paciente/alerta)
    path('paciente/<int:id>/', views.pagina_paciente, name='paciente_detalhe'),
    path('reconhecer/<int:id>/', views.reconhecer_alerta, name='reconhecer_alerta'),
    
    # Rotas de API (Aquelas que o JavaScript chama nos bastidores)
    path('api/unidades/', views.buscar_unidades_usuario, name='buscar_unidades'),
    path('api/salvar-triagem/', views.salvar_triagem, name='salvar_triagem'),
    path('api/salvar-unidade/', views.salvar_unidade, name='salvar_unidade'),
    path('api/unidade/<int:id>/toggle/', views.toggle_unidade, name='toggle_unidade'),
    path('api/unidade/<int:id>/excluir/', views.excluir_unidade, name='excluir_unidade'),
    
    # Rota de Segurança
    path('sair/', views.sair_sistema, name='sair'),

    #Rota Gestão de Usuários
    path('api/salvar-usuario/', views.salvar_usuario, name='salvar_usuario'),
    path('api/usuario/<int:id>/reset-senha/', views.resetar_senha, name='resetar_senha'),
    path('trocar-senha/', views.pagina_trocar_senha, name='trocar_senha'),

]