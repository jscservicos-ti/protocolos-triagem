from django.contrib import admin
from .models import UnidadeSaude, PerfilAcesso, Paciente, AtendimentoTriagem

# Isso diz ao Django para gerar as telas de cadastro para nossas tabelas
admin.site.register(UnidadeSaude)
admin.site.register(PerfilAcesso)
admin.site.register(Paciente)
admin.site.register(AtendimentoTriagem)