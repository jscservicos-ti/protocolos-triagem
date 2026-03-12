from django.db import models
from django.contrib.auth.models import User

# Tabela para cadastrar as Unidades de Saúde
class UnidadeSaude(models.Model):
    nome = models.CharField(max_length=150, verbose_name="Nome da Unidade")
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return self.nome

# Tabela para vincular o usuário do sistema ao seu Perfil e suas Unidades
class PerfilAcesso(models.Model):
    TIPOS_PERFIL = (
        ('ENFERMAGEM', 'Enfermagem (Triagem)'),
        ('MEDICO', 'Médico (Monitoramento)'),
        ('PADRAO', 'Padrão (Acesso Total Clínico)'),
        ('ADMINISTRATIVO', 'Administrativo (Consulta)'),
        ('ADMIN', 'Administrador de Sistema (Full)'),
    )

    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    tipo_perfil = models.CharField(max_length=20, choices=TIPOS_PERFIL)
    unidades = models.ManyToManyField(UnidadeSaude)
    cpf = models.CharField(max_length=14, null=True, blank=True)
    deve_trocar_senha = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.usuario.username} - {self.get_tipo_perfil_display()}"


# Tabela de Cadastro do Paciente
class Paciente(models.Model):
    nome_completo = models.CharField(max_length=200, verbose_name="Nome Completo")
    cpf = models.CharField(max_length=14, blank=True, null=True, verbose_name="CPF")
    data_nascimento = models.DateField(blank=True, null=True, verbose_name="Data de Nascimento")
    nome_mae = models.CharField(max_length=200, blank=True, null=True, verbose_name="Nome da Mãe")
    data_cadastro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome_completo

# Tabela que vai guardar os Sinais Vitais, o Score e o Alerta gerado
class AtendimentoTriagem(models.Model):
    PROTOCOLOS_OPCOES = (
        ('NEWS', 'NEWS (Adulto)'),
        ('PEWS', 'PEWS (Pediátrico)'),
        ('MEOWS', 'MEOWS (Obstétrico)'),
    )

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE)
    unidade = models.ForeignKey(UnidadeSaude, on_delete=models.CASCADE)
    enfermeiro = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    data_hora_triagem = models.DateTimeField(auto_now_add=True)
    protocolo = models.CharField(max_length=10, choices=PROTOCOLOS_OPCOES)
    
    # --- Sinais Vitais Aferidos ---
    freq_respiratoria = models.IntegerField(null=True, blank=True)
    saturacao_o2 = models.IntegerField(null=True, blank=True)
    uso_o2_suplementar = models.BooleanField(default=False)
    temperatura = models.FloatField(null=True, blank=True)
    pressao_sistolica = models.IntegerField(null=True, blank=True)
    freq_cardiaca = models.IntegerField(null=True, blank=True)
    nivel_consciencia = models.CharField(max_length=50, null=True, blank=True)
    
    # NOVOS CAMPOS PARA O MEOWS
    pressao_diastolica = models.IntegerField(null=True, blank=True)
    debito_urinario = models.FloatField(null=True, blank=True)
    
    # --- Resultados ---
    score_final = models.IntegerField(null=True, blank=True)
    classificacao_risco = models.CharField(max_length=20, null=True, blank=True)
    alerta_reconhecido = models.BooleanField(default=False)
    medico_reconheceu = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='alertas_reconhecidos')
    finalizado = models.BooleanField(default=False)
    data_hora_finalizacao = models.DateTimeField(null=True, blank=True)
    usuario_finalizou = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='altas_realizadas')

    def __str__(self):
        return f"{self.paciente.nome_completo} - {self.protocolo} - Risco: {self.classificacao_risco}"