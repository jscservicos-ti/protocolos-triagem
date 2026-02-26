import json
import csv
from django.http import HttpResponse
from django.contrib.auth import update_session_auth_hash
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from .models import Paciente, AtendimentoTriagem
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from .models import UnidadeSaude, PerfilAcesso
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.utils import timezone
from datetime import timedelta
import re

def pagina_login(request):
    erro = None
    if request.method == 'POST':
        usuario_digitado = request.POST.get('usuario')
        senha_digitada = request.POST.get('senha')
        unidade_selecionada = request.POST.get('unidade')

        user = authenticate(request, username=usuario_digitado, password=senha_digitada)

        if user is not None:
            # Trava extra: Verifica se o usuário está inativo
            if not user.is_active:
                return render(request, 'login.html', {'erro': "Esta conta foi inativada pelo administrador."})
                
            try:
                perfil = PerfilAcesso.objects.get(usuario=user)
                
                if perfil.unidades.filter(id=unidade_selecionada).exists() or perfil.tipo_perfil == 'ADMIN':
                    login(request, user)
                    request.session['unidade_id'] = unidade_selecionada
                    
                    if getattr(perfil, 'deve_trocar_senha', False):
                        return redirect('trocar_senha')
                    
                    if perfil.tipo_perfil == 'ADMIN':
                        return redirect('painel_admin')
                    else:
                        return redirect('medico')
                else:
                    erro = "Acesso negado para esta unidade de saúde."
            except PerfilAcesso.DoesNotExist:
                erro = "Este usuário não possui um perfil de acesso configurado."
        else:
            erro = "Usuário ou senha incorretos."

    return render(request, 'login.html', {'erro': erro})

def verificar_inativos_24h(unidade_id):
    limite_24h = timezone.now() - timedelta(hours=24)
    atendimentos_abertos = AtendimentoTriagem.objects.filter(unidade_id=unidade_id, finalizado=False)
    pacientes_ids = atendimentos_abertos.values_list('paciente_id', flat=True).distinct()
    
    for pac_id in pacientes_ids:
        ultimo = AtendimentoTriagem.objects.filter(paciente_id=pac_id, unidade_id=unidade_id).order_by('-data_hora_triagem').first()
        if ultimo and ultimo.data_hora_triagem <= limite_24h:
            AtendimentoTriagem.objects.filter(paciente_id=pac_id, unidade_id=unidade_id, finalizado=False).update(
                finalizado=True,
                data_hora_finalizacao=timezone.now(),
                usuario_finalizou=None 
            )

@login_required
def pagina_triagem(request):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    # PERMISSÃO ATUALIZADA: Padrão acessa
    if perfil.tipo_perfil not in ['ENFERMAGEM', 'ADMIN', 'PADRAO']:
        return redirect('medico')
        
    contexto = {
        'nome_usuario': request.user.first_name or request.user.username,
        'perfil_nome': perfil.get_tipo_perfil_display()
    }
    return render(request, 'triagem.html', contexto)

@login_required
def pagina_medico(request):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
        
    unidade_id = request.session.get('unidade_id')
    if not unidade_id:
        return redirect('sair')
        
    unidade_ativa = UnidadeSaude.objects.get(id=unidade_id)
    
    verificar_inativos_24h(unidade_id)
    
    atendimentos = AtendimentoTriagem.objects.filter(unidade=unidade_ativa, finalizado=False)

    periodo_escolhido = request.GET.get('periodo', 'todos')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    risco_escolhido = request.GET.get('risco', 'todos')
    
    agora = timezone.now()

    if periodo_escolhido == 'hoje':
        hoje_inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        atendimentos = atendimentos.filter(data_hora_triagem__gte=hoje_inicio)
    elif periodo_escolhido == '7dias':
        limite = agora - timedelta(days=7)
        atendimentos = atendimentos.filter(data_hora_triagem__gte=limite)
    elif periodo_escolhido == '30dias':
        limite = agora - timedelta(days=30)
        atendimentos = atendimentos.filter(data_hora_triagem__gte=limite)
    elif periodo_escolhido == 'personalizado':
        if data_inicio:
            atendimentos = atendimentos.filter(data_hora_triagem__date__gte=data_inicio)
        if data_fim:
            atendimentos = atendimentos.filter(data_hora_triagem__date__lte=data_fim)

    atendimentos = atendimentos.order_by('-data_hora_triagem')

    atendimentos_unicos = []
    pacientes_vistos = set()
    
    for atd in atendimentos:
        if atd.paciente_id not in pacientes_vistos:
            atendimentos_unicos.append(atd)
            pacientes_vistos.add(atd.paciente_id)

    total_pacientes = len(atendimentos_unicos)
    alto_risco = sum(1 for a in atendimentos_unicos if a.classificacao_risco == 'Alto')
    medio_risco = sum(1 for a in atendimentos_unicos if a.classificacao_risco == 'Médio')
    baixo_risco = sum(1 for a in atendimentos_unicos if a.classificacao_risco == 'Baixo')
    
    alertas_pendentes = [a for a in atendimentos_unicos if a.classificacao_risco == 'Alto' and not a.alerta_reconhecido]
    qtd_nao_reconhecidos = len(alertas_pendentes)

    grade_atendimentos = atendimentos_unicos
    if risco_escolhido == 'Alto':
        grade_atendimentos = [a for a in grade_atendimentos if a.classificacao_risco == 'Alto']
    elif risco_escolhido == 'Médio':
        grade_atendimentos = [a for a in grade_atendimentos if a.classificacao_risco == 'Médio']
    elif risco_escolhido == 'Baixo':
        grade_atendimentos = [a for a in grade_atendimentos if a.classificacao_risco == 'Baixo']

    contexto = {
        'nome_usuario': request.user.first_name or request.user.username,
        'perfil_nome': perfil.get_tipo_perfil_display(),
        'periodo_atual': periodo_escolhido,
        'data_inicio': data_inicio, 
        'data_fim': data_fim,
        'risco_atual': risco_escolhido,
        'total_pacientes': total_pacientes,
        'alto_risco': alto_risco,
        'medio_risco': medio_risco,
        'baixo_risco': baixo_risco,
        'qtd_nao_reconhecidos': qtd_nao_reconhecidos,
        'alertas_recentes': alertas_pendentes[:5], 
        'grade_pacientes': grade_atendimentos[:12]       
    }
    
    return render(request, 'medico.html', contexto)

@login_required
def pagina_paciente(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    atendimento_clicado = get_object_or_404(AtendimentoTriagem, id=id)
    
    if atendimento_clicado.unidade not in perfil.unidades.all():
        return redirect('medico')

    origem = request.GET.get('origem')
    if origem:
        request.session[f'origem_pac_{id}'] = origem
    else:
        origem = request.session.get(f'origem_pac_{id}', 'painel')

    unidade_id = request.session.get('unidade_id')
    historico_qs = AtendimentoTriagem.objects.filter(
        paciente=atendimento_clicado.paciente,
        unidade_id=unidade_id
    ).order_by('-data_hora_triagem')
    
    ultimo_atendimento = historico_qs.first()
    
    is_finalizado = ultimo_atendimento.finalizado if ultimo_atendimento else False
    
    pode_finalizar = False
    pode_reabrir = False
    minutos_restantes = 0
    pode_aferir = False
    
    agora = timezone.now()

    # PERMISSÃO ATUALIZADA: Padrão acessa os controles de alta
    if perfil.tipo_perfil in ['MEDICO', 'ENFERMAGEM', 'ADMIN', 'PADRAO']:
        if is_finalizado:
            if ultimo_atendimento.data_hora_finalizacao:
                tempo_passado = agora - ultimo_atendimento.data_hora_finalizacao
                segundos = tempo_passado.total_seconds()
                if segundos <= 3600:
                    pode_reabrir = True
                    minutos_restantes = int((3600 - segundos) / 60)
        else:
            tem_alerta_pendente = historico_qs.filter(finalizado=False, classificacao_risco='Alto', alerta_reconhecido=False).exists()
            if not tem_alerta_pendente:
                pode_finalizar = True
                
        # PERMISSÃO ATUALIZADA: Padrão pode fazer aferições
        if perfil.tipo_perfil in ['ENFERMAGEM', 'ADMIN', 'PADRAO'] and not is_finalizado:
            tem_alerta_pendente = historico_qs.filter(finalizado=False, classificacao_risco='Alto', alerta_reconhecido=False).exists()
            if not tem_alerta_pendente:
                pode_aferir = True

    historico = []
    for afericao in historico_qs:
        tempo_passado = agora - afericao.data_hora_triagem
        passou_5_min = tempo_passado.total_seconds() > 300 
        
        if not afericao.alerta_reconhecido and not passou_5_min and not afericao.finalizado:
            afericao.pode_editar = True
        else:
            afericao.pode_editar = False
            
        historico.append(afericao)

    contexto = {
        'nome_usuario': request.user.first_name or request.user.username,
        'perfil_nome': perfil.get_tipo_perfil_display(),
        'atendimento': atendimento_clicado, 
        'historico': historico,
        'ultimo_atendimento': ultimo_atendimento,
        'pode_aferir': pode_aferir,
        'is_finalizado': is_finalizado,
        'pode_finalizar': pode_finalizar,
        'pode_reabrir': pode_reabrir,
        'minutos_restantes': minutos_restantes,
        'origem': origem
    }
    return render(request, 'paciente_detalhe.html', contexto)

@login_required
def finalizar_atendimento(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    # PERMISSÃO ATUALIZADA
    if perfil.tipo_perfil not in ['MEDICO', 'ENFERMAGEM', 'ADMIN', 'PADRAO']:
        return redirect('paciente_detalhe', id=id)
        
    atendimento = get_object_or_404(AtendimentoTriagem, id=id)
    
    historico_aberto = AtendimentoTriagem.objects.filter(
        paciente=atendimento.paciente,
        unidade=atendimento.unidade,
        finalizado=False
    )
    
    for atd in historico_aberto:
        if atd.classificacao_risco == 'Alto' and not atd.alerta_reconhecido:
            return redirect('paciente_detalhe', id=id)
            
    agora = timezone.now()
    historico_aberto.update(finalizado=True, data_hora_finalizacao=agora, usuario_finalizou=request.user)
    
    return redirect('paciente_detalhe', id=id)

@login_required
def reabrir_atendimento(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    # PERMISSÃO ATUALIZADA
    if perfil.tipo_perfil not in ['MEDICO', 'ENFERMAGEM', 'ADMIN', 'PADRAO']:
        return redirect('paciente_detalhe', id=id)
        
    atendimento = get_object_or_404(AtendimentoTriagem, id=id)
    
    limite = timezone.now() - timedelta(minutes=60)
    historico_recente = AtendimentoTriagem.objects.filter(
        paciente=atendimento.paciente,
        unidade=atendimento.unidade,
        finalizado=True,
        data_hora_finalizacao__gte=limite
    )
    
    historico_recente.update(finalizado=False, data_hora_finalizacao=None, usuario_finalizou=None)
    return redirect('paciente_detalhe', id=id)

@login_required
def reconhecer_alerta(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    pagina_anterior = request.META.get('HTTP_REFERER', 'medico')
    
    # PERMISSÃO ATUALIZADA
    if perfil.tipo_perfil not in ['MEDICO', 'ADMIN', 'PADRAO']:
        return redirect(pagina_anterior)
        
    atendimento = get_object_or_404(AtendimentoTriagem, id=id)
    unidade_id = request.session.get('unidade_id')
    
    if str(atendimento.unidade.id) == str(unidade_id):
        atendimento.alerta_reconhecido = True
        atendimento.medico_reconheceu = request.user 
        atendimento.save()
        
    return redirect(pagina_anterior)

def sair_sistema(request):
    logout(request) 
    return redirect('login') 

def buscar_unidades_usuario(request):
    username = request.GET.get('usuario', None)
    dados = []
    
    if username:
        try:
            user = User.objects.get(username=username)
            perfil = PerfilAcesso.objects.get(usuario=user)
            unidades = perfil.unidades.all()
            for unidade in unidades:
                dados.append({'id': unidade.id, 'nome': unidade.nome})
        except (User.DoesNotExist, PerfilAcesso.DoesNotExist):
            pass 
            
    return JsonResponse({'unidades': dados})

def calcular_score_news(dados):
    score = 0
    try:
        fr = int(dados.get('freq_respiratoria') or 0)
        if fr <= 8 or fr >= 25: score += 3
        elif fr in range(21, 25): score += 2
        elif fr in range(9, 12): score += 1

        sat = int(dados.get('saturacao_o2') or 0)
        if sat <= 91: score += 3
        elif sat in range(92, 94): score += 2
        elif sat in range(94, 96): score += 1

        if dados.get('uso_o2_suplementar') == 'Sim': score += 2

        temp = float(dados.get('temperatura') or 0)
        if temp <= 35.0: score += 3
        elif temp >= 39.1: score += 2
        elif 35.1 <= temp <= 36.0 or 38.1 <= temp <= 39.0: score += 1

        pas = int(dados.get('pressao_sistolica') or 0)
        if pas <= 90 or pas >= 220: score += 3
        elif 91 <= pas <= 100: score += 2
        elif 101 <= pas <= 110: score += 1

        fc = int(dados.get('freq_cardiaca') or 0)
        if fc <= 40 or fc >= 131: score += 3
        elif 111 <= fc <= 130: score += 2
        elif 41 <= fc <= 50 or 91 <= fc <= 110: score += 1

        consciencia = dados.get('nivel_consciencia')
        if consciencia != 'Alerta': score += 3

        if score >= 7:
            risco = 'Alto'
            conduta = 'Revisão médica imediata necessária. Alerta clínico enviado.'
        elif score >= 5:
            risco = 'Médio'
            conduta = 'Avaliação médica urgente. Aumentar monitoramento.'
        else:
            risco = 'Baixo'
            conduta = 'Manter monitoramento padrão da unidade.'
        return score, risco, conduta
    except ValueError:
        return 0, 'Baixo', 'Erro ao calcular.'

def calcular_score_pews(dados):
    score = 0
    try:
        consciencia = dados.get('nivel_consciencia')
        if consciencia in ['Confusão', 'Voz']: score += 1
        elif consciencia == 'Dor': score += 2
        elif consciencia == 'Inconsciente': score += 3

        fc = int(dados.get('freq_cardiaca') or 0)
        if fc < 60 or fc > 160: score += 3
        elif fc > 140: score += 2
        elif fc < 70 or fc > 120: score += 1

        fr = int(dados.get('freq_respiratoria') or 0)
        if fr < 15 or fr > 50: score += 3
        elif fr > 40: score += 2
        elif fr < 20 or fr > 30: score += 1

        sat = int(dados.get('saturacao_o2') or 0)
        if sat <= 89: score += 3
        elif 90 <= sat <= 93: score += 2
        elif 94 <= sat <= 95: score += 1

        if dados.get('uso_o2_suplementar') == 'Sim': score += 2

        if score >= 7:
            risco = 'Alto'
            conduta = 'PEWS Crítico: Acionar emergência pediátrica imediatamente.'
        elif score >= 4:
            risco = 'Médio'
            conduta = 'PEWS Atenção: Avaliação médica em até 30 minutos.'
        else:
            risco = 'Baixo'
            conduta = 'PEWS Normal: Manter monitoramento de rotina.'
        return score, risco, conduta
    except ValueError:
        return 0, 'Baixo', 'Erro ao calcular.'

def calcular_score_meows(dados):
    score = 0
    try:
        fr = int(dados.get('freq_respiratoria') or 0)
        if fr < 12 or fr > 25: score += 3
        elif 21 <= fr <= 25: score += 1

        sat = int(dados.get('saturacao_o2') or 0)
        if sat < 92: score += 3
        elif 92 <= sat <= 95: score += 1

        temp = float(dados.get('temperatura') or 0)
        if temp < 35.0 or temp > 38.0: score += 3
        elif 35.0 <= temp <= 35.9 or 37.5 <= temp <= 38.0: score += 1

        fc = int(dados.get('freq_cardiaca') or 0)
        if fc < 50 or fc > 120: score += 3
        elif 111 <= fc <= 120: score += 2
        elif 50 <= fc <= 59 or 101 <= fc <= 110: score += 1

        pas = int(dados.get('pressao_sistolica') or 0)
        if pas < 90 or pas >= 160: score += 3
        elif 150 <= pas <= 159: score += 2
        elif 90 <= pas <= 99 or 140 <= pas <= 149: score += 1

        consciencia = dados.get('nivel_consciencia')
        if consciencia != 'Alerta': score += 3

        if score >= 6 or (score >= 3 and consciencia != 'Alerta'):
            risco = 'Alto'
            conduta = 'MEOWS Crítico: Avaliação obstétrica urgente.'
        elif score >= 4:
            risco = 'Médio'
            conduta = 'MEOWS Atenção: Repetir sinais em 1h.'
        else:
            risco = 'Baixo'
            conduta = 'MEOWS Normal: Monitoramento padrão.'
        return score, risco, conduta
    except ValueError:
        return 0, 'Baixo', 'Erro ao calcular.'

@login_required
def salvar_triagem(request):
    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            
            paciente, created = Paciente.objects.get_or_create(
                nome_completo=dados.get('nome').upper(),
                defaults={
                    'cpf': dados.get('cpf'),
                    'data_nascimento': dados.get('nascimento') or None,
                    'nome_mae': dados.get('mae')
                }
            )

            protocolo_escolhido = dados.get('protocolo')
            
            if protocolo_escolhido == 'NEWS':
                score, risco, conduta = calcular_score_news(dados)
            elif protocolo_escolhido == 'PEWS':
                score, risco, conduta = calcular_score_pews(dados)
            elif protocolo_escolhido == 'MEOWS':
                score, risco, conduta = calcular_score_meows(dados)
            else:
                score, risco, conduta = 0, 'Baixo', 'Protocolo não reconhecido.'

            unidade_id = request.session.get('unidade_id')
            if not unidade_id:
                return JsonResponse({'sucesso': False, 'erro': 'Sessão expirada. Faça login novamente.'})
                
            unidade_atual = UnidadeSaude.objects.get(id=unidade_id)
            atendimento_id = dados.get('atendimento_id')
            
            if atendimento_id:
                atendimento = AtendimentoTriagem.objects.get(id=atendimento_id)
                atendimento.paciente = paciente
                atendimento.protocolo = protocolo_escolhido
                atendimento.freq_respiratoria = dados.get('freq_respiratoria') or None
                atendimento.saturacao_o2 = dados.get('saturacao_o2') or None
                atendimento.uso_o2_suplementar = (dados.get('uso_o2_suplementar') == 'Sim')
                atendimento.temperatura = dados.get('temperatura') or None
                atendimento.pressao_sistolica = dados.get('pressao_sistolica') or None
                atendimento.freq_cardiaca = dados.get('freq_cardiaca') or None
                atendimento.nivel_consciencia = dados.get('nivel_consciencia')
                atendimento.score_final = score
                atendimento.classificacao_risco = risco
                atendimento.save()
            else:
                AtendimentoTriagem.objects.create(
                    paciente=paciente,
                    unidade=unidade_atual,
                    enfermeiro=request.user,
                    protocolo=protocolo_escolhido,
                    freq_respiratoria=dados.get('freq_respiratoria') or None,
                    saturacao_o2=dados.get('saturacao_o2') or None,
                    uso_o2_suplementar=(dados.get('uso_o2_suplementar') == 'Sim'),
                    temperatura=dados.get('temperatura') or None,
                    pressao_sistolica=dados.get('pressao_sistolica') or None,
                    freq_cardiaca=dados.get('freq_cardiaca') or None,
                    nivel_consciencia=dados.get('nivel_consciencia'),
                    score_final=score,
                    classificacao_risco=risco
                )

            return JsonResponse({'sucesso': True, 'score': score, 'risco': risco, 'conduta': conduta})
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': str(e)})

@login_required
def historico_triagem(request):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    
    # PERMISSÃO ATUALIZADA
    if perfil.tipo_perfil not in ['ENFERMAGEM', 'ADMIN', 'PADRAO']:
        return redirect('medico')
        
    unidade_id = request.session.get('unidade_id')
    if not unidade_id:
        return redirect('sair')
        
    unidade_ativa = UnidadeSaude.objects.get(id=unidade_id)
    atendimentos = AtendimentoTriagem.objects.filter(unidade=unidade_ativa)
    
    periodo_escolhido = request.GET.get('periodo', 'hoje')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    busca_nome = request.GET.get('busca', '')
    
    agora = timezone.now()
    
    if periodo_escolhido == 'hoje':
        hoje_inicio = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        atendimentos = atendimentos.filter(data_hora_triagem__gte=hoje_inicio)
    elif periodo_escolhido == '7dias':
        limite = agora - timedelta(days=7)
        atendimentos = atendimentos.filter(data_hora_triagem__gte=limite)
    elif periodo_escolhido == '30dias':
        limite = agora - timedelta(days=30)
        atendimentos = atendimentos.filter(data_hora_triagem__gte=limite)
    elif periodo_escolhido == 'personalizado':
        if data_inicio:
            atendimentos = atendimentos.filter(data_hora_triagem__date__gte=data_inicio)
        if data_fim:
            atendimentos = atendimentos.filter(data_hora_triagem__date__lte=data_fim)
            
    if busca_nome:
        atendimentos = atendimentos.filter(paciente__nome_completo__icontains=busca_nome)
        
    atendimentos = atendimentos.order_by('-data_hora_triagem')
    
    for atendimento in atendimentos:
        tempo_passado = agora - atendimento.data_hora_triagem
        passou_5_min = tempo_passado.total_seconds() > 300 
        
        if atendimento.alerta_reconhecido or passou_5_min or atendimento.finalizado:
            atendimento.pode_editar = False
            if atendimento.finalizado:
                atendimento.motivo_bloqueio = "Bloqueado: Atendimento Finalizado"
            elif atendimento.alerta_reconhecido:
                atendimento.motivo_bloqueio = "Bloqueado: Reconhecido pelo médico"
            else:
                atendimento.motivo_bloqueio = "Bloqueado: Tempo limite excedido (>5min)"
        else:
            atendimento.pode_editar = True
            atendimento.motivo_bloqueio = ""
            
    contexto = {
        'nome_usuario': request.user.first_name or request.user.username,
        'perfil_nome': perfil.get_tipo_perfil_display(),
        'periodo_atual': periodo_escolhido,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'busca': busca_nome,
        'atendimentos': atendimentos
    }
    return render(request, 'historico_triagem.html', contexto)

@login_required
def excluir_triagem(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    # PERMISSÃO ATUALIZADA
    if perfil.tipo_perfil not in ['ENFERMAGEM', 'ADMIN', 'PADRAO']:
        return redirect('historico_triagem')
        
    atendimento = get_object_or_404(AtendimentoTriagem, id=id)
    tempo_passado = timezone.now() - atendimento.data_hora_triagem
    passou_5_min = tempo_passado.total_seconds() > 300 
    
    if not atendimento.alerta_reconhecido and not passou_5_min and not atendimento.finalizado:
        atendimento.delete()
        
    return redirect('historico_triagem')

@login_required
def editar_triagem(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    # PERMISSÃO ATUALIZADA
    if perfil.tipo_perfil not in ['ENFERMAGEM', 'ADMIN', 'PADRAO']:
        return redirect('historico_triagem')
        
    atendimento = get_object_or_404(AtendimentoTriagem, id=id)
    tempo_passado = timezone.now() - atendimento.data_hora_triagem
    passou_5_min = tempo_passado.total_seconds() > 300 
    
    if atendimento.alerta_reconhecido or passou_5_min or atendimento.finalizado:
        return redirect('historico_triagem') 
        
    contexto = {
        'nome_usuario': request.user.first_name or request.user.username,
        'perfil_nome': perfil.get_tipo_perfil_display(),
        'atendimento': atendimento 
    }
    return render(request, 'triagem.html', contexto)

@login_required
def painel_admin(request):
    try:
        perfil = PerfilAcesso.objects.get(usuario=request.user)
        if perfil.tipo_perfil != 'ADMIN':
            return redirect('medico')
    except PerfilAcesso.DoesNotExist:
        return redirect('sair')

    busca_usuario = request.GET.get('busca_usuario', '')
    usuarios = PerfilAcesso.objects.select_related('usuario').prefetch_related('unidades').all()
    
    if busca_usuario:
        usuarios = usuarios.filter(
            Q(usuario__first_name__icontains=busca_usuario) | 
            Q(usuario__username__icontains=busca_usuario) |
            Q(usuario__last_name__icontains=busca_usuario)
        )

    unidades = UnidadeSaude.objects.all()

    contexto = {
        'nome_usuario': request.user.first_name or request.user.username,
        'perfil_nome': perfil.get_tipo_perfil_display(),
        'lista_usuarios': usuarios,
        'lista_unidades': unidades,
        'busca_usuario': busca_usuario, 
    }
    return render(request, 'painel_admin.html', contexto)

@login_required
def salvar_unidade(request):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    if perfil.tipo_perfil != 'ADMIN':
        return JsonResponse({'sucesso': False, 'erro': 'Acesso negado.'})

    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            unidade_id = dados.get('id')
            nome = dados.get('nome')

            if not nome:
                return JsonResponse({'sucesso': False, 'erro': 'O nome da unidade é obrigatório.'})

            if unidade_id:
                unidade = UnidadeSaude.objects.get(id=unidade_id)
                unidade.nome = nome
                unidade.save()
            else:
                UnidadeSaude.objects.create(nome=nome)

            return JsonResponse({'sucesso': True})
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': str(e)})
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

@login_required
def toggle_unidade(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    if perfil.tipo_perfil != 'ADMIN':
        return JsonResponse({'sucesso': False, 'erro': 'Acesso negado.'})

    if request.method == 'POST':
        unidade = get_object_or_404(UnidadeSaude, id=id)
        unidade.ativo = not unidade.ativo 
        unidade.save()
        return JsonResponse({'sucesso': True})
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

@login_required
def excluir_unidade(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    if perfil.tipo_perfil != 'ADMIN':
        return JsonResponse({'sucesso': False, 'erro': 'Acesso negado.'})

    if request.method == 'POST':
        try:
            unidade = get_object_or_404(UnidadeSaude, id=id)
            unidade.delete()
            return JsonResponse({'sucesso': True})
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': 'Não é possível excluir uma unidade que já possui pacientes vinculados.'})
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

@login_required
def salvar_usuario(request):
    perfil_admin = PerfilAcesso.objects.get(usuario=request.user)
    if perfil_admin.tipo_perfil != 'ADMIN':
        return JsonResponse({'sucesso': False, 'erro': 'Acesso negado.'})

    if request.method == 'POST':
        try:
            dados = json.loads(request.body)
            user_id = dados.get('id')
            nome_completo = dados.get('nome_completo', '').strip()
            cpf = dados.get('cpf', '')
            username = dados.get('username', '')
            tipo_perfil = dados.get('tipo_perfil', '')
            unidades_ids = dados.get('unidades', [])

            partes_nome = nome_completo.split(' ', 1)
            first_name = partes_nome[0]
            last_name = partes_nome[1] if len(partes_nome) > 1 else ''

            if user_id:
                user = User.objects.get(id=user_id)
                user.first_name = first_name
                user.last_name = last_name
                user.username = username
                user.save()

                perfil = user.perfilacesso
                perfil.cpf = cpf
                perfil.tipo_perfil = tipo_perfil
                perfil.unidades.set(unidades_ids) 
                perfil.save()
            else:
                if User.objects.filter(username=username).exists():
                    return JsonResponse({'sucesso': False, 'erro': 'Este Código de Usuário já existe.'})

                user = User.objects.create_user(username=username, password=username, first_name=first_name, last_name=last_name)
                perfil = PerfilAcesso.objects.create(usuario=user, cpf=cpf, tipo_perfil=tipo_perfil, deve_trocar_senha=True)
                perfil.unidades.set(unidades_ids)

            return JsonResponse({'sucesso': True})
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': str(e)})
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

# ========================================================
# NOVAS FUNÇÕES: INATIVAR E EXCLUIR USUÁRIO
# ========================================================
@login_required
def inativar_usuario(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    if perfil.tipo_perfil != 'ADMIN':
        return JsonResponse({'sucesso': False, 'erro': 'Acesso negado.'})

    if request.method == 'POST':
        user = get_object_or_404(User, id=id)
        if user == request.user:
            return JsonResponse({'sucesso': False, 'erro': 'Você não pode inativar a si mesmo.'})
            
        user.is_active = not user.is_active
        user.save()
        return JsonResponse({'sucesso': True, 'ativo': user.is_active})
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

@login_required
def excluir_usuario(request, id):
    perfil = PerfilAcesso.objects.get(usuario=request.user)
    if perfil.tipo_perfil != 'ADMIN':
        return JsonResponse({'sucesso': False, 'erro': 'Acesso negado.'})

    if request.method == 'POST':
        try:
            user = get_object_or_404(User, id=id)
            if user == request.user:
                return JsonResponse({'sucesso': False, 'erro': 'Você não pode excluir a si mesmo.'})
                
            user.delete()
            return JsonResponse({'sucesso': True})
        except Exception as e:
            return JsonResponse({'sucesso': False, 'erro': 'Não é possível excluir este usuário pois ele possui atendimentos/registros vinculados no sistema. Por favor, utilize a opção de Inativar.'})
            
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

@login_required
def resetar_senha(request, id):
    perfil_admin = PerfilAcesso.objects.get(usuario=request.user)
    if perfil_admin.tipo_perfil != 'ADMIN':
        return JsonResponse({'sucesso': False, 'erro': 'Acesso negado.'})

    if request.method == 'POST':
        user = get_object_or_404(User, id=id)
        user.set_password(user.username)
        user.save()
        
        perfil = user.perfilacesso
        perfil.deve_trocar_senha = True
        perfil.save()
        return JsonResponse({'sucesso': True})
    return JsonResponse({'sucesso': False, 'erro': 'Método inválido.'})

@login_required
def pagina_trocar_senha(request):
    perfil = PerfilAcesso.objects.get(usuario=request.user)

    if request.method == 'POST':
        nova_senha = request.POST.get('nova_senha')
        confirmacao = request.POST.get('confirmacao')
        erro = None

        if len(nova_senha) < 8:
            erro = 'A senha deve ter no mínimo 8 caracteres.'
        elif not re.search(r'[A-Z]', nova_senha):
            erro = 'A senha deve conter no mínimo 1 letra MAIÚSCULA.'
        elif not re.search(r'[a-z]', nova_senha):
            erro = 'A senha deve conter no mínimo 1 letra minúscula.'
        elif not re.search(r'\d', nova_senha):
            erro = 'A senha deve conter no mínimo 1 número.'
        elif not re.search(r'[!@#$%^&*(),.?":{}|<>\-_+=\[\]\\/\'~`]', nova_senha):
            erro = 'A senha deve conter no mínimo 1 símbolo (ex: @, #, !, $).'
        elif nova_senha != confirmacao:
            erro = 'As senhas digitadas não coincidem.'

        if erro:
            return render(request, 'trocar_senha.html', {'erro': erro})

        user = request.user
        user.set_password(nova_senha)
        user.save()

        perfil.deve_trocar_senha = False
        perfil.save()

        update_session_auth_hash(request, user)

        if perfil.tipo_perfil == 'ADMIN':
            return redirect('painel_admin')
        else:
            return redirect('medico')

    return render(request, 'trocar_senha.html')

@login_required
def verificar_alertas(request):
    unidade_id = request.session.get('unidade_id')
    if not unidade_id:
        return JsonResponse({'qtd': 0})
    
    verificar_inativos_24h(unidade_id)
    
    atendimentos_ativos = AtendimentoTriagem.objects.filter(
        unidade_id=unidade_id, 
        finalizado=False 
    ).order_by('-data_hora_triagem')
    
    pacientes_vistos = set()
    qtd_alertas_unicos = 0
    
    for atd in atendimentos_ativos:
        if atd.paciente_id not in pacientes_vistos:
            pacientes_vistos.add(atd.paciente_id)
            if atd.classificacao_risco == 'Alto' and not atd.alerta_reconhecido:
                qtd_alertas_unicos += 1
                
    return JsonResponse({'qtd': qtd_alertas_unicos})

@login_required
def relatorios(request):
    unidade_id = request.session.get('unidade_id')
    if not unidade_id:
        return redirect('pagina_login')
    
    unidade = UnidadeSaude.objects.get(id=unidade_id)

    periodo = request.GET.get('periodo', 'hoje')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    protocolo_filtro = request.GET.get('protocolo', 'todos')
    exportar = request.GET.get('exportar', '')

    triagens = AtendimentoTriagem.objects.filter(unidade=unidade).select_related('paciente')

    hoje = timezone.localtime(timezone.now()).date()
    if periodo == 'hoje':
        triagens = triagens.filter(data_hora_triagem__date=hoje)
    elif periodo == '7dias':
        triagens = triagens.filter(data_hora_triagem__date__gte=hoje - timedelta(days=7))
    elif periodo == '30dias':
        triagens = triagens.filter(data_hora_triagem__date__gte=hoje - timedelta(days=30))
    elif periodo == 'personalizado' and data_inicio and data_fim:
        triagens = triagens.filter(data_hora_triagem__date__range=[data_inicio, data_fim])

    if protocolo_filtro != 'todos':
        triagens = triagens.filter(protocolo__iexact=protocolo_filtro)

    triagens = triagens.order_by('-data_hora_triagem')

    totais = {
        'NEWS': {'Alto': 0, 'Médio': 0, 'Baixo': 0},
        'PEWS': {'Alto': 0, 'Médio': 0, 'Baixo': 0},
        'MEOWS': {'Alto': 0, 'Médio': 0, 'Baixo': 0},
    }
    for t in triagens:
        prot = t.protocolo.upper()
        risco = t.classificacao_risco
        if prot in totais and risco in totais[prot]:
            totais[prot][risco] += 1

    if exportar == 'excel':
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = f'attachment; filename="Relatorio_Triagem_{unidade.nome}.csv"'
        writer = csv.writer(response, delimiter=';')

        writer.writerow(['RELATÓRIO GERENCIAL DE TRIAGEM CLÍNICA'])
        writer.writerow(['Unidade:', unidade.nome])
        writer.writerow(['Período:', periodo.upper()])
        writer.writerow(['Protocolo:', protocolo_filtro.upper()])
        writer.writerow([]) 
        
        writer.writerow(['Paciente', 'Data do Atendimento', 'Protocolo', 'Score', 'Classificação de Risco'])
        
        for t in triagens:
            data_formatada = timezone.localtime(t.data_hora_triagem).strftime('%d/%m/%Y %H:%M')
            writer.writerow([t.paciente.nome_completo, data_formatada, t.protocolo, t.score_final, t.classificacao_risco])
            
        writer.writerow([])
        writer.writerow(['RESUMO GERAL DE CLASSIFICAÇÃO'])
        for prot, riscos in totais.items():
            if protocolo_filtro == 'todos' or protocolo_filtro.upper() == prot:
                writer.writerow([f'Protocolo {prot}:', f"Alto: {riscos['Alto']}", f"Médio: {riscos['Médio']}", f"Baixo: {riscos['Baixo']}"])

        return response

    contexto = {
        'triagens': triagens,
        'totais': totais,
        'unidade_nome': unidade.nome,
        'periodo_atual': periodo,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'protocolo_atual': protocolo_filtro,
        'nome_usuario': request.user.first_name or request.user.username,
        'perfil_nome': request.user.perfilacesso.get_tipo_perfil_display(),
    }
    return render(request, 'relatorios.html', contexto)