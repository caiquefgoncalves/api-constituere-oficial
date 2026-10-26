"""Auditoria da Constituere.

O módulo mantém o histórico em Log.FDB, separado do banco operacional. Ele
descobre o escritório e o usuário da requisição, classifica a ação, compara o
estado anterior e posterior quando aplicável e salva uma descrição técnica que
depois é convertida em texto humano para a interface e os PDFs.
"""

import json
import math
import os
import re
import socket
import unicodedata
import uuid
from datetime import date, datetime, time
from functools import lru_cache

import fdb
from fpdf import FPDF
from flask import current_app, g, request

from db import _cliente_firebird, conexao


CAMPOS_SIGILOSOS = {'senha', 'confirmar_senha', 'token', 'authorization', 'acess_token'}
ROTAS_CONVERSA_IA = {'/ai/veritas'}

ARTIGOS = {
    'AGENDAMENTOS': ('um', 'agendamento'),
    'ATUALIZACOES': ('uma', 'atualização'),
    'MODELOS_DOCUMENTOS': ('um', 'modelo de documento'),
    'PROCESSOS': ('um', 'processo'),
    'PARCELAS': ('uma', 'parcela'),
    'USUARIOS': ('um', 'cliente'),
    'ADVOGADO': ('um', 'advogado do escritório'),
    'ADVOGADO_ESCRITORIO': ('um', 'advogado'),
    'ESCRITORIOS': ('um', 'escritório'),
    'SISTEMA': ('uma', 'ação no sistema'),
}

ACOES_HUMANAS = {
    'CRIAR': 'criou',
    'EDITAR': 'editou',
    'EXCLUIR': 'removeu',
    'CONFIRMAR': 'confirmou',
    'RECUSAR': 'recusou',
    'CANCELAR': 'cancelou',
    'CONCLUIR': 'concluiu',
    'INATIVAR': 'inativou',
    'ATIVAR': 'ativou',
    'PROMOVER': 'promoveu',
    'REBAIXAR': 'rebaixou',
    'GERAR_PDF': 'gerou o PDF de',
    'GERAR_PIX': 'gerou um codigo Pix para',
    'CONSULTAR_PIX': 'consultou o status do Pix de',
    'PAGAMENTO_PIX': 'realizou um pagamento via Pix de',
    'LOGIN': 'entrou no sistema',
}


def eh_conversa_ia():
    return request.path.rstrip('/').lower() in ROTAS_CONVERSA_IA


def eh_rota_log():
    return '/logs/' in request.path.rstrip('/').lower()


def conexao_log():
    parametros = {
        'database': current_app.config['LOG_DB_NAME'],
        'user': current_app.config['LOG_DB_USER'],
        'password': current_app.config['LOG_DB_PASSWORD'],
    }

    cliente_firebird = os.getenv('LOG_FIREBIRD_CLIENT_DLL') or _cliente_firebird()
    if cliente_firebird:
        parametros['fb_library_name'] = cliente_firebird

    return fdb.connect(**parametros)


def normalizar_valor(valor):
    """Converte valores para JSON e mascara chaves que nunca devem ir ao Log."""
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {
            str(chave): '***' if str(chave).lower() in CAMPOS_SIGILOSOS else normalizar_valor(item)
            for chave, item in valor.items()
        }
    if isinstance(valor, (list, tuple)):
        return [normalizar_valor(item) for item in valor]
    return valor


def dados_requisicao():
    """Extrai JSON ou formulário já normalizado para compor DETALHES."""
    if request.is_json:
        return normalizar_valor(request.get_json(silent=True) or {})
    if request.form:
        return normalizar_valor(request.form.to_dict())
    return {}


@lru_cache(maxsize=256)
def nome_maquina_por_ip(ip):
    if not ip or ip in {'127.0.0.1', '::1'}:
        return None
    try:
        nome, _, _ = socket.gethostbyaddr(ip)
        return nome.split('.')[0] if nome else None
    except (socket.herror, socket.gaierror, OSError):
        return None


def origem_dispositivo():
    """Determina uma origem legível sem depender de um único cabeçalho.

    A identificação é apenas informativa para investigação: ela não é usada
    para autenticar ou autorizar usuários.
    """
    nome_dispositivo = (request.headers.get('X-Client-Device') or '').strip()
    nome_dispositivo = re.sub(r'[\r\n]+', ' ', nome_dispositivo)[:120]
    if nome_dispositivo:
        return nome_dispositivo

    plataforma = (request.headers.get('X-Client-Platform') or '').strip().lower()
    if plataforma == 'expo-mobile':
        return 'Celular (Expo)'

    agente = (request.headers.get('User-Agent') or '').lower()
    if any(termo in agente for termo in ('android', 'iphone', 'ipad', 'mobile')):
        return 'Celular (navegador)'
    nome_maquina = nome_maquina_por_ip(request.remote_addr)
    if nome_maquina:
        return nome_maquina
    if agente:
        return 'Computador (navegador)'
    return socket.gethostname()


def identificar_escritorio(id_usuario, dados, view_args):
    """Encontra o escritório proprietário do evento.

    Prioriza o escritório explícito na requisição; quando ele não existe,
    encontra o vínculo ativo do advogado ou o responsável do cliente. Assim o
    mesmo mecanismo de auditoria atende rotas de advogado e de cliente.
    """
    for origem in (dados, view_args or {}):
        for chave in ('id_escritorio', 'id_escritorios', 'ID_ESCRITORIO', 'ID_ESCRITORIOS'):
            valor = origem.get(chave) if isinstance(origem, dict) else None
            if valor not in (None, ''):
                try:
                    return int(valor)
                except (TypeError, ValueError):
                    pass

    if not id_usuario:
        return None

    con = conexao()
    cur = con.cursor()
    try:
        cur.execute(
            """
            SELECT FIRST 1 ID_ESCRITORIOS
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ? AND ATIVO = 1
            ORDER BY CASE WHEN STATUS = 'PROPRIETARIO' THEN 0 ELSE 1 END
            """,
            (id_usuario,)
        )
        linha = cur.fetchone()
        if linha:
            return linha[0]

        cur.execute(
            """
            SELECT FIRST 1 vinculo.ID_ESCRITORIOS
            FROM USUARIOS cliente
            INNER JOIN ADVOGADO_ESCRITORIO vinculo
                ON vinculo.ID_USUARIOS = cliente.ID_USUARIO_RESPONSAVEL
            WHERE cliente.ID_USUARIOS = ?
              AND cliente.TIPO IN (2, 3)
              AND cliente.ATIVO = 1
              AND vinculo.ATIVO = 1
            ORDER BY CASE WHEN vinculo.STATUS = 'PROPRIETARIO' THEN 0 ELSE 1 END
            """,
            (id_usuario,)
        )
        linha = cur.fetchone()
        return linha[0] if linha else None
    finally:
        cur.close()
        con.close()


def nome_usuario(id_usuario):
    if not id_usuario:
        return None

    con = conexao()
    cur = con.cursor()
    try:
        cur.execute('SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?', (id_usuario,))
        linha = cur.fetchone()
        return linha[0] if linha else None
    finally:
        cur.close()
        con.close()


def descricao_evento():
    """Converte rota e método HTTP em uma ação de auditoria e seu recurso.

    Regras específicas vêm antes da regra genérica para que um pagamento Pix,
    por exemplo, não seja apresentado apenas como uma edição de parcela.
    """
    caminho = request.path.lower()
    argumentos = request.view_args or {}
    if re.fullmatch(r'/alterar_cargo_advogado/\d+/\d+', caminho):
        novo_cargo = str((dados_requisicao().get('status') or '')).upper()
        acao = 'PROMOVER' if novo_cargo == 'PROPRIETARIO' else 'REBAIXAR'
        return acao, 'ADVOGADO_ESCRITORIO'
    if re.fullmatch(r'/processo/\d+/atualizacoes', caminho) and request.method == 'POST':
        return 'CRIAR', 'ATUALIZACOES'
    if caminho == '/cliente/pagamento/pix' and request.method == 'POST':
        return 'GERAR_PIX', 'PARCELAS'
    if re.fullmatch(r'/cliente/pagamento/pix/\d+', caminho) and request.method == 'GET':
        # A rota consulta a provedora; somente a própria rota define esta marca
        # após atualizar a parcela com sucesso. Sem ela, trata-se de consulta.
        if getattr(g, 'auditoria_pagamento_pix', None):
            return 'PAGAMENTO_PIX', 'PARCELAS'
        return 'CONSULTAR_PIX', 'PARCELAS'
    if caminho.endswith('/documento'):
        return 'GERAR_PDF', 'PROCESSOS'
    if caminho.endswith('/confirmar'):
        return 'CONFIRMAR', 'AGENDAMENTOS'
    if caminho.endswith('/recusar'):
        return 'RECUSAR', 'AGENDAMENTOS'
    if caminho.endswith('/cancelar'):
        return 'CANCELAR', 'AGENDAMENTOS'
    if caminho.endswith('/concluir'):
        return 'CONCLUIR', 'PROCESSOS'
    if re.fullmatch(r'/advogado/\d+/escritorio/\d+/(?:inativar|ativar)', caminho):
        return ('INATIVAR' if caminho.endswith('/inativar') else 'ATIVAR'), 'ADVOGADO_ESCRITORIO'
    if caminho.endswith('/inativar'):
        return 'INATIVAR', caminho.split('/')[1].upper()
    if caminho.endswith('/ativar'):
        return 'ATIVAR', caminho.split('/')[1].upper()

    # Rotas filhas devem registrar a tabela do registro efetivamente alterado,
    # e não a tabela do recurso pai presente no início da URL.
    if 'id_atualizacao' in argumentos:
        return ('EXCLUIR' if request.method == 'DELETE' else 'EDITAR'), 'ATUALIZACOES'
    if 'id_modelo' in argumentos:
        return 'EDITAR', 'MODELOS_DOCUMENTOS'
    if caminho in {'/editar_perfil', '/editar_perfil_cliente'}:
        return 'EDITAR', 'USUARIOS'
    if caminho == '/editar_escritorio':
        return 'EDITAR', 'ESCRITORIOS'

    tabela_por_rota = {
        '/agendamento': 'AGENDAMENTOS',
        '/agendamentos': 'AGENDAMENTOS',
        '/processo': 'PROCESSOS',
        '/cadastrar_processo': 'PROCESSOS',
        '/cliente': 'USUARIOS',
        '/criar_usuarios': 'USUARIOS',
        '/advogado': 'ADVOGADO_ESCRITORIO',
        '/alterar_cargo_advogado': 'ADVOGADO_ESCRITORIO',
        '/escritorio': 'ESCRITORIOS',
        '/criar_escritorio': 'ESCRITORIOS',
    }
    tabela = next((valor for rota, valor in tabela_por_rota.items() if caminho.startswith(rota)), 'SISTEMA')
    acao_por_metodo = {'POST': 'CRIAR', 'PUT': 'EDITAR', 'PATCH': 'EDITAR', 'DELETE': 'EXCLUIR'}
    return acao_por_metodo.get(request.method, request.method), tabela


def id_registro(view_args):
    pagamento_pix = getattr(g, 'auditoria_pagamento_pix', None)
    if isinstance(pagamento_pix, dict):
        try:
            return int(pagamento_pix.get('id_parcela'))
        except (TypeError, ValueError):
            pass

    # Em rotas aninhadas, o último identificador é o registro modificado.
    for chave in ('id_atualizacao', 'id_modelo', 'id_agendamento', 'id_processo', 'id_cliente', 'id_advogado', 'id_escritorio'):
        valor = (view_args or {}).get(chave)
        if valor is not None:
            try:
                return int(valor)
            except (TypeError, ValueError):
                return None
    for chave, valor in (view_args or {}).items():
        if chave.startswith('id_'):
            try:
                return int(valor)
            except (TypeError, ValueError):
                return None

    if request.path.lower() in {'/editar_perfil', '/editar_perfil_cliente'}:
        token = getattr(g, 'auditoria_token', None) or {}
        try:
            return int(token.get('id_usuarios'))
        except (TypeError, ValueError):
            return None
    return None


def alvo_snapshot():
    """Traduz parâmetros da rota na consulta usada para o snapshot anterior."""
    argumentos = request.view_args or {}
    caminho = request.path.lower()
    if 'id_atualizacao' in argumentos:
        return (
            'ATUALIZACOES',
            'ID_ATUALIZACOES = ? AND ID_PROCESSOS = ?',
            (argumentos['id_atualizacao'], argumentos['id_processo'])
        )
    if 'id_modelo' in argumentos:
        return (
            'MODELOS_DOCUMENTOS',
            'ID_MODELOS_DOCUMENTOS = ? AND ID_ESCRITORIOS = ?',
            (argumentos['id_modelo'], argumentos['id_escritorio'])
        )
    if 'id_agendamento' in argumentos:
        return 'AGENDAMENTOS', 'ID_AGENDAMENTOS = ?', (argumentos['id_agendamento'],)
    if 'id_processo' in argumentos:
        return 'PROCESSOS', 'ID_PROCESSOS = ?', (argumentos['id_processo'],)
    if 'id_cliente' in argumentos:
        return 'USUARIOS', 'ID_USUARIOS = ?', (argumentos['id_cliente'],)
    if 'id_advogado' in argumentos and 'id_escritorio' in argumentos:
        return (
            'ADVOGADO_ESCRITORIO',
            'ID_USUARIOS = ? AND ID_ESCRITORIOS = ?',
            (argumentos['id_advogado'], argumentos['id_escritorio'])
        )
    if caminho in {'/editar_perfil', '/editar_perfil_cliente'}:
        token = getattr(g, 'auditoria_token', None) or {}
        if token.get('id_usuarios'):
            return 'USUARIOS', 'ID_USUARIOS = ?', (token['id_usuarios'],)
    if caminho == '/editar_escritorio':
        token = getattr(g, 'auditoria_token', None) or {}
        id_escritorio = identificar_escritorio(token.get('id_usuarios'), {}, argumentos)
        if id_escritorio:
            return 'ESCRITORIOS', 'ID_ESCRITORIOS = ?', (id_escritorio,)
    return None


def buscar_snapshot(alvo):
    """Lê uma linha do banco operacional para comparação na auditoria."""
    if not alvo:
        return None
    tabela, condicao, parametros = alvo
    con = conexao()
    cur = con.cursor()
    try:
        cur.execute(f'SELECT * FROM {tabela} WHERE {condicao}', parametros)
        linha = cur.fetchone()
        if not linha:
            return None
        return {
            descricao[0].strip(): normalizar_valor(valor)
            for descricao, valor in zip(cur.description, linha)
        }
    finally:
        cur.close()
        con.close()


def preparar_requisicao(token_data):
    """Guarda no contexto Flask o token e o snapshot anterior da requisição."""
    if eh_conversa_ia() or eh_rota_log():
        return
    g.auditoria_token = token_data or {}
    if request.method not in {'PUT', 'PATCH', 'DELETE'}:
        return
    alvo = alvo_snapshot()
    g.auditoria_alvo = alvo
    g.auditoria_anterior = buscar_snapshot(alvo)


def valor_para_log(valor):
    if valor is None:
        return None
    if isinstance(valor, (dict, list, tuple)):
        return json.dumps(valor, ensure_ascii=False, default=str)
    return str(valor)


def alteracoes_registradas():
    """Retorna apenas os campos que mudaram entre o snapshot e o banco atual."""
    anterior = getattr(g, 'auditoria_anterior', None)
    alvo = getattr(g, 'auditoria_alvo', None)
    if not anterior or not alvo:
        return []
    atual = buscar_snapshot(alvo)
    if not atual:
        return [('REGISTRO', valor_para_log(anterior), 'Removido')]
    return [
        (campo, valor_para_log(valor_antigo), valor_para_log(atual.get(campo)))
        for campo, valor_antigo in anterior.items()
        if valor_antigo != atual.get(campo)
    ]


def registrar_requisicao(token_data):
    """Grava no Log.FDB o evento concluído pela requisição atual.

    O id_evento no JSON de detalhes é comum às linhas da mesma requisição,
    permitindo que a listagem agrupe uma edição com múltiplos campos.
    """
    if request.path.startswith('/logs') or eh_conversa_ia() or eh_rota_log():
        return

    dados = dados_requisicao()
    pagamento_pix = getattr(g, 'auditoria_pagamento_pix', None)
    if isinstance(pagamento_pix, dict):
        # A confirmação Pix ocorre em uma consulta GET; estes dados vêm da
        # atualização real da parcela e dão contexto ao evento de pagamento.
        dados['pagamento_pix'] = pagamento_pix
    view_args = request.view_args or {}
    id_usuario = token_data.get('id_usuarios') if token_data else None
    id_escritorio = identificar_escritorio(id_usuario, dados, view_args)
    if not id_escritorio:
        return

    acao, tabela = descricao_evento()
    anterior = getattr(g, 'auditoria_anterior', None) or {}
    if tabela == 'ADVOGADO_ESCRITORIO' and acao == 'EXCLUIR':
        id_advogado = anterior.get('ID_USUARIOS') or id_registro(view_args)
        nome_advogado = nome_usuario(id_advogado) if id_advogado else None
        if nome_advogado:
            dados['advogado'] = {'nome': nome_advogado}
    detalhes = json.dumps({
        'id_evento': uuid.uuid4().hex,
        'metodo': request.method,
        'rota': request.path,
        'parametros_rota': view_args,
        'dados': dados,
    }, ensure_ascii=False, default=str)

    alteracoes = alteracoes_registradas()
    if not alteracoes:
        alteracoes = [('REGISTRO', None, 'Criado' if request.method == 'POST' else 'Atualizado')]

    con = None
    cur = None
    try:
        con = conexao_log()
        cur = con.cursor()
        for campo, antigo, novo in alteracoes:
            cur.execute(
                """
                INSERT INTO LOG_AUDITORIA (
                    ID_ESCRITORIO, ID_USUARIO, NOME_USUARIO, ACAO,
                    TABELA_AFETADA, ID_REGISTRO_AFETADO, CAMPO,
                    VALOR_ANTIGO, VALOR_NOVO, DETALHES, MAQUINA, IP_ORIGEM
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id_escritorio, id_usuario, nome_usuario(id_usuario), acao,
                    tabela, id_registro(view_args), campo, antigo, novo, detalhes,
                    origem_dispositivo(), request.remote_addr,
                )
            )
        con.commit()
    except Exception as erro:
        current_app.logger.error('Não foi possível gravar o log de auditoria: %s', erro)
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


def texto_blob(valor):
    if valor is None:
        return None
    return valor.read() if hasattr(valor, 'read') else str(valor)


def buscar_cargo_advogado(id_usuario, id_escritorio):
    if not id_usuario or not id_escritorio:
        return None

    con = conexao()
    cur = con.cursor()
    try:
        cur.execute(
            """
            SELECT STATUS
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ? AND ID_ESCRITORIOS = ?
            """,
            (id_usuario, id_escritorio)
        )
        linha = cur.fetchone()
        return linha[0] if linha else None
    finally:
        cur.close()
        con.close()


def buscar_cargo_usuario(id_usuario, id_escritorio):
    cargo_advogado = buscar_cargo_advogado(id_usuario, id_escritorio)
    if cargo_advogado:
        return cargo_advogado

    if not id_usuario:
        return None

    con = conexao()
    cur = con.cursor()
    try:
        cur.execute(
            'SELECT TIPO FROM USUARIOS WHERE ID_USUARIOS = ?',
            (id_usuario,)
        )
        linha = cur.fetchone()
        return 'Cliente' if linha and linha[0] in (2, 3) else None
    finally:
        cur.close()
        con.close()


def descricao_humana(nome, acao, tabela, id_registro, campo, valor_novo,
                      cargo=None, id_usuario=None, detalhes=None):
    """Converte o registro técnico em uma frase segura para o usuário final.

    Dados complementares vêm de DETALHES somente quando ajudam a dar contexto,
    como o motivo de agenda ou o valor de um pagamento Pix.
    """
    nome = nome or 'O sistema'
    acao_txt = ACOES_HUMANAS.get((acao or '').upper(), f'{(acao or "").lower()}')

    if acao == 'LOGIN':
        return f'{nome} entrou no sistema.'

    if tabela not in ARTIGOS:
        return f'{nome} {acao_txt} {tabela or "um registro"}.'

    alvo = alvo_com_artigo(tabela, id_registro, detalhes)

    if acao == 'GERAR_PDF':
        return f'{nome} {acao_txt} {alvo}.'

    if tabela == 'AGENDAMENTOS' and acao == 'CANCELAR':
        dados = (detalhes or {}).get('dados') or {}
        agendamento = dados.get('agendamento') if isinstance(dados, dict) else None
        nome_cliente = agendamento.get('cliente') if isinstance(agendamento, dict) else None
        if nome_cliente:
            return f'{nome} cancelou o agendamento com {nome_cliente}.'

    if tabela == 'PARCELAS' and acao == 'GERAR_PIX':
        dados = (detalhes or {}).get('dados') or {}
        tipo_parcela = dados.get('tipo_parcela') if isinstance(dados, dict) else None
        complemento = ' de êxito' if tipo_parcela == 'exito' else ''
        return f'{nome} gerou um código Pix para uma parcela{complemento} em aberto.'

    if tabela == 'PARCELAS' and acao == 'CONSULTAR_PIX':
        return f'{nome} consultou o status de uma cobrança Pix.'

    if tabela == 'PARCELAS' and acao == 'PAGAMENTO_PIX':
        dados = (detalhes or {}).get('dados') or {}
        pagamento = dados.get('pagamento_pix') if isinstance(dados, dict) else None
        pagamento = pagamento if isinstance(pagamento, dict) else {}
        tipo_parcela = pagamento.get('tipo_parcela')
        complemento = ' de êxito' if tipo_parcela == 'exito' else ''
        valor = pagamento.get('valor')
        try:
            valor_formatado = f' no valor de R$ {float(valor):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        except (TypeError, ValueError):
            valor_formatado = ''
        return f'{nome} realizou um pagamento via Pix{complemento}{valor_formatado}.'

    if tabela in {'ADVOGADO', 'ADVOGADO_ESCRITORIO'} and acao in {
        'ATIVAR', 'INATIVAR', 'EXCLUIR', 'PROMOVER', 'REBAIXAR'
    }:
        dados = (detalhes or {}).get('dados') or {}
        advogado = dados.get('advogado') if isinstance(dados, dict) else None
        nome_advogado = advogado.get('nome') if isinstance(advogado, dict) else None
        if nome_advogado:
            if acao == 'EXCLUIR':
                return f'{nome} removeu {nome_advogado} do escritório.'
            if acao in {'PROMOVER', 'REBAIXAR'}:
                cargo = str(dados.get('status') or '').lower()
                cargo = {
                    'proprietario': 'proprietário',
                    'parceiro': 'parceiro',
                    'associado': 'associado',
                }.get(cargo, cargo or 'nova posição')
                verbo = 'promoveu' if acao == 'PROMOVER' else 'rebaixou'
                return f'{nome} {verbo} {nome_advogado} para {cargo}.'
            verbo = 'ativou' if acao == 'ATIVAR' else 'inativou'
            return f'{nome} {verbo} o vínculo de {nome_advogado} com o escritório.'

    if tabela == 'USUARIOS' and cargo == 'Cliente':
        if acao == 'EDITAR' and campo and campo.upper() != 'REGISTRO':
            campo_legivel = campo.replace('_', ' ').lower()
            return f'{nome} editou seu cadastro (alterou o campo {campo_legivel}).'
        return f'{nome} {acao_txt} seu cadastro.'

    if acao == 'EDITAR' and campo and campo.upper() != 'REGISTRO':
        campo_legivel = campo.replace('_', ' ').lower()
        return f'{nome} {acao_txt} {alvo} (alterou o campo {campo_legivel}).'

    return f'{nome} {acao_txt} {alvo}.'


def alvo_humano(tabela, id_registro, detalhes=None):
    _, substantivo = ARTIGOS.get(tabela, ('um', (tabela or 'registro').lower()))
    alvo = substantivo

    if tabela == 'ATUALIZACOES':
        parametros = (detalhes or {}).get('parametros_rota') or {}
        id_processo = parametros.get('id_processo')
        if not id_processo:
            rota = (detalhes or {}).get('rota') or ''
            correspondencia = re.search(r'/processo/(\d+)/atualizacoes', rota)
            id_processo = correspondencia.group(1) if correspondencia else None
        titulo_atualizacao, numero_processo = referencia_atualizacao(
            id_registro, id_processo
        )
        if titulo_atualizacao:
            alvo = f'atualiza\u00e7\u00e3o "{titulo_atualizacao}"'
        elif not id_registro:
            alvo = 'atualiza\u00e7\u00e3o'
        if numero_processo:
            alvo += f' do processo {numero_processo}'
    if tabela in {'MODELOS_DOCUMENTOS', 'ADVOGADO_ESCRITORIO'}:
        alvo += ' do escritório'

    return alvo


@lru_cache(maxsize=512)
def referencia_atualizacao(id_atualizacao, id_processo):
    if not id_atualizacao or not id_processo:
        return None, None

    con = None
    cur = None
    try:
        con = conexao()
        cur = con.cursor()
        cur.execute(
            '''
            SELECT a.TITULO, p.NUM_PROCESSO
            FROM ATUALIZACOES a
            INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = a.ID_PROCESSOS
            WHERE a.ID_ATUALIZACOES = ? AND a.ID_PROCESSOS = ?
            ''',
            (id_atualizacao, id_processo)
        )
        linha = cur.fetchone()
        return (linha[0], linha[1]) if linha else (None, None)
    except Exception as erro:
        current_app.logger.warning(
            'Não foi possível buscar a referência da atualização no log: %s',
            erro
        )
        return None, None
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@lru_cache(maxsize=512)
def referencia_agendamento(id_agendamento):
    if not id_agendamento:
        return None

    con = None
    cur = None
    try:
        con = conexao()
        cur = con.cursor()
        cur.execute(
            '''
            SELECT CLIENTE, ASSUNTO, DATA, HORARIO, DURACAO, STATUS
            FROM AGENDAMENTOS
            WHERE ID_AGENDAMENTOS = ?
            ''',
            (id_agendamento,)
        )
        linha = cur.fetchone()
        if not linha:
            return None
        return {
            'cliente': linha[0],
            'assunto': linha[1],
            'data': normalizar_valor(linha[2]),
            'horario': normalizar_valor(linha[3]),
            'duracao': linha[4],
            'status': linha[5],
        }
    except Exception as erro:
        current_app.logger.warning(
            'Não foi possível buscar a referência do agendamento no log: %s',
            erro
        )
        return None
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


@lru_cache(maxsize=512)
def referencia_advogado_escritorio(id_advogado, id_escritorio):
    if not id_advogado or not id_escritorio:
        return None

    con = None
    cur = None
    try:
        con = conexao()
        cur = con.cursor()
        cur.execute(
            '''
            SELECT COALESCE(NULLIF(u.NOME, ''), '--')
            FROM USUARIOS u
            WHERE u.ID_USUARIOS = ? AND u.TIPO = 0
            ''',
            (id_advogado,),
        )
        linha = cur.fetchone()
        return {'nome': linha[0]} if linha else None
    except Exception as erro:
        current_app.logger.warning(
            'Não foi possível buscar a referência do advogado no log: %s', erro
        )
        return None
    finally:
        if cur:
            cur.close()
        if con:
            con.close()


def alvo_com_artigo(tabela, id_registro, detalhes=None):
    artigo, _ = ARTIGOS.get(tabela, ('um', (tabela or 'registro').lower()))
    return f'{artigo} {alvo_humano(tabela, id_registro, detalhes)}'


def agrupar_eventos(todos):
    """Agrupa linhas de uma requisição em um único evento visual.

    Uma edição pode mudar diversos campos e gerar várias linhas no banco. O
    id_evento evita que a interface apresente cada campo como uma ação isolada.
    """
    eventos = {}
    agrupados = []

    for log in todos:
        try:
            detalhes = json.loads(log.get('detalhes') or '{}')
        except (TypeError, json.JSONDecodeError):
            detalhes = {}
        id_evento = detalhes.get('id_evento')

        if not id_evento:
            agrupados.append(log)
            continue

        alteracao = {
            'campo': log['campo'],
            'valor_antigo': log['valor_antigo'],
            'valor_novo': log['valor_novo'],
        }
        evento = eventos.get(id_evento)
        if evento is None:
            log['alteracoes'] = [alteracao]
            eventos[id_evento] = log
            agrupados.append(log)
        else:
            evento['alteracoes'].append(alteracao)

    for log in agrupados:
        alteracoes = log.get('alteracoes', [])
        if log['acao'] == 'EDITAR' and len(alteracoes) > 1:
            try:
                detalhes = json.loads(log.get('detalhes') or '{}')
            except (TypeError, json.JSONDecodeError):
                detalhes = {}
            campos = ', '.join(item['campo'].replace('_', ' ').lower() for item in alteracoes)
            log['descricao_humana'] = (
                f"{log['nome_usuario'] or 'O sistema'} editou "
                f"{len(alteracoes)} campos em {alvo_com_artigo(log['tabela_afetada'], log['id_registro_afetado'], detalhes)}: "
                f"{campos}."
            )

    return agrupados


def listar_logs(id_escritorio, limite=200, data_inicio=None, data_fim=None, advogado=None,
                pagina=1, por_pagina=6):
    """
    Retorna os logs do escritório já paginados.

    Durante a leitura, esta função também interpreta detalhes JSON, corrige
    classificações legadas conhecidas e monta descricao_humana para a tela.

    Parâmetros:
        id_escritorio: ID do escritório
        limite: teto máximo de registros buscados no banco (para evitar consultas gigantes)
        data_inicio, data_fim, advogado: filtros opcionais aplicados em Python
        pagina: número da página (1-based)
        por_pagina: itens por página (default 6)

    Retorno:
        dict com chaves:
            'logs': lista paginada
            'pagina': número da página atual
            'por_pagina': itens por página
            'total': total de registros após filtros
            'total_paginas': total de páginas
            'tem_mais': bool indicando se existe próxima página
    """
    try:
        pagina = max(1, int(pagina))
    except (TypeError, ValueError):
        pagina = 1

    try:
        por_pagina = max(1, int(por_pagina))
    except (TypeError, ValueError):
        por_pagina = 6

    con = conexao_log()
    cur = con.cursor()
    try:
        cur.execute(
            """
            SELECT FIRST ? ID_LOG, ID_USUARIO, NOME_USUARIO, ACAO,
                   TABELA_AFETADA, ID_REGISTRO_AFETADO, CAMPO,
                   VALOR_ANTIGO, VALOR_NOVO, DETALHES, DATA_HORA,
                   MAQUINA, IP_ORIGEM
            FROM LOG_AUDITORIA
            WHERE ID_ESCRITORIO = ?
            ORDER BY DATA_HORA DESC, ID_LOG DESC
            """,
            (limite, id_escritorio)
        )

        todos = []
        for linha in cur.fetchall():
            nome_usuario = linha[2]
            acao = linha[3]
            tabela_afetada = linha[4]
            id_registro_afetado = linha[5]
            campo = linha[6]
            valor_novo = texto_blob(linha[8])
            cargo = buscar_cargo_usuario(linha[1], id_escritorio)
            detalhes_brutos = texto_blob(linha[9])
            try:
                detalhes = json.loads(detalhes_brutos or '{}')
            except (TypeError, json.JSONDecodeError):
                detalhes = {}
            if not isinstance(detalhes, dict):
                detalhes = {}

            # Corrige a leitura de logs antigos: antes de existir uma regra
            # específica, a geração de Pix era confundida com criação de cliente
            # porque a rota começa com "/cliente".
            rota = (detalhes.get('rota') or '').lower()
            if rota == '/cliente/pagamento/pix' and acao == 'CRIAR':
                acao = 'GERAR_PIX'
                tabela_afetada = 'PARCELAS'
            elif re.fullmatch(r'/cliente/pagamento/pix/\d+', rota) and acao == 'GET':
                acao = 'CONSULTAR_PIX'
                tabela_afetada = 'PARCELAS'
            elif (
                re.fullmatch(r'/processo/\d+/atualizacoes', rota)
                and acao == 'CRIAR'
                and tabela_afetada == 'PROCESSOS'
            ):
                tabela_afetada = 'ATUALIZACOES'
                id_registro_afetado = None
            elif (
                re.fullmatch(r'/alterar_cargo_advogado/\d+/\d+', rota)
                and acao == 'EDITAR'
                and tabela_afetada == 'ADVOGADO_ESCRITORIO'
            ):
                novo_cargo = str((detalhes.get('dados') or {}).get('status') or '').upper()
                acao = 'PROMOVER' if novo_cargo == 'PROPRIETARIO' else 'REBAIXAR'

            try:
                if tabela_afetada == 'AGENDAMENTOS':
                    agendamento = referencia_agendamento(id_registro_afetado)
                    if agendamento:
                        dados_evento = detalhes.get('dados')
                        dados_evento = dados_evento if isinstance(dados_evento, dict) else {}
                        detalhes['dados'] = {
                            **dados_evento,
                            'agendamento': agendamento,
                        }
                        detalhes_brutos = json.dumps(
                            detalhes, ensure_ascii=False, default=str
                        )

                if tabela_afetada in {'ADVOGADO', 'ADVOGADO_ESCRITORIO'} and acao in {
                    'ATIVAR', 'INATIVAR', 'EXCLUIR', 'PROMOVER', 'REBAIXAR'
                }:
                    parametros = detalhes.get('parametros_rota') or {}
                    referencia_advogado = referencia_advogado_escritorio(
                        id_registro_afetado, parametros.get('id_escritorio')
                    )
                    if referencia_advogado:
                        dados_evento = detalhes.get('dados')
                        dados_evento = dados_evento if isinstance(dados_evento, dict) else {}
                        detalhes['dados'] = {
                            **dados_evento,
                            'advogado': referencia_advogado,
                        }
                        detalhes_brutos = json.dumps(
                            detalhes, ensure_ascii=False, default=str
                        )
            except Exception as erro:
                current_app.logger.warning(
                    'Não foi possível complementar um registro do log: %s', erro
                )

            todos.append({
                'id_log': linha[0],
                'id_usuario': linha[1],
                'nome_usuario': nome_usuario,
                'acao': acao,
                'tabela_afetada': tabela_afetada,
                'id_registro_afetado': id_registro_afetado,
                'campo': campo,
                'valor_antigo': texto_blob(linha[7]),
                'valor_novo': valor_novo,
                'detalhes': detalhes_brutos,
                'data_hora': linha[10].isoformat() if linha[10] else None,
                'maquina': linha[11],
                'ip_origem': linha[12],
                'cargo': cargo,
                'descricao_humana': descricao_humana(
                    nome_usuario, acao, tabela_afetada,
                    id_registro_afetado, campo, valor_novo,
                    cargo, linha[1], detalhes
                ),
            })

        if data_inicio:
            todos = [log for log in todos if (log['data_hora'] or '')[:10] >= data_inicio]
        if data_fim:
            todos = [log for log in todos if (log['data_hora'] or '')[:10] <= data_fim]
        if advogado:
            todos = [log for log in todos if log['nome_usuario'] == advogado]

        todos = agrupar_eventos(todos)

        total = len(todos)
        total_paginas = max(1, math.ceil(total / por_pagina)) if total > 0 else 1

        if pagina > total_paginas:
            pagina = total_paginas

        inicio = (pagina - 1) * por_pagina
        fim = inicio + por_pagina
        logs_paginados = todos[inicio:fim]

        return {
            'logs': logs_paginados,
            'pagina': pagina,
            'por_pagina': por_pagina,
            'total': total,
            'total_paginas': total_paginas,
            'tem_mais': pagina < total_paginas,
        }
    finally:
        cur.close()
        con.close()


def texto_pdf_log(valor, tamanho=None):
    texto = '-' if valor in (None, '') else str(valor)
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    if tamanho and len(texto) > tamanho:
        return f'{texto[:tamanho - 3]}...'
    return texto


def resumo_alteracoes_pdf(log):
    alteracoes = log.get('alteracoes') or [{
        'campo': log.get('campo'),
        'valor_antigo': log.get('valor_antigo'),
        'valor_novo': log.get('valor_novo'),
    }]
    partes = []
    for alteracao in alteracoes:
        campo_original = str(alteracao.get('campo') or '')
        if campo_original.lower() == 'id' or campo_original.lower().startswith('id_'):
            continue
        campo = texto_pdf_log(campo_original)
        antigo = texto_pdf_log(alteracao.get('valor_antigo'))
        novo = texto_pdf_log(alteracao.get('valor_novo'))
        partes.append(f'{campo}: {antigo} -> {novo}')
    return ' | '.join(partes)


ROTULOS_PDF_LOG = {
    'id_advogado': 'Advogado',
    'id_advogado_2': 'Segundo advogado',
    'id_cliente': 'Cliente',
    'id_escritorio': 'Escritorio',
    'assunto': 'Assunto',
    'cliente': 'Cliente',
    'data': 'Data',
    'horario': 'Horario',
    'duracao': 'Duracao',
    'motivo': 'Motivo',
    'status': 'Status',
    'nome': 'Nome',
    'email': 'E-mail',
    'telefone': 'Telefone',
    'area_atuacao': 'Area de atuacao',
    'ativo': 'Situacao',
    'processo': 'Processo',
    'agendamento': 'Agendamento',
    'advogado': 'Advogado',
    'rota': 'Rota',
    'metodo': 'Metodo',
}


def rotulo_pdf_log(chave):
    return ROTULOS_PDF_LOG.get(
        str(chave), str(chave).replace('_', ' ').capitalize()
    )


def linhas_detalhes_pdf(valor, prefixo=''):
    """Converte os detalhes JSON de um log em linhas legiveis para o PDF."""
    if isinstance(valor, dict):
        linhas = []
        for chave, item in valor.items():
            chave_normalizada = str(chave).lower()
            if (
                chave_normalizada in CAMPOS_SIGILOSOS
                or chave_normalizada == 'id_evento'
                or chave_normalizada == 'id'
                or chave_normalizada.startswith('id_')
            ):
                continue
            rotulo = rotulo_pdf_log(chave)
            caminho = f'{prefixo} - {rotulo}' if prefixo else rotulo
            if isinstance(item, (dict, list, tuple)):
                linhas.extend(linhas_detalhes_pdf(item, caminho))
            elif item not in (None, ''):
                if str(chave).lower() == 'ativo':
                    item = 'Ativado' if str(item).lower() in {'1', 'true'} else 'Desativado'
                linhas.append(f'{caminho}: {texto_pdf_log(item, 500)}')
        return linhas

    if isinstance(valor, (list, tuple)):
        linhas = []
        for indice, item in enumerate(valor, start=1):
            linhas.extend(linhas_detalhes_pdf(item, f'{prefixo} {indice}'.strip()))
        return linhas

    return [f'{prefixo}: {texto_pdf_log(valor, 500)}'] if valor not in (None, '') else []


def detalhes_pdf_log(log):
    try:
        detalhes = json.loads(log.get('detalhes') or '{}')
    except (TypeError, json.JSONDecodeError):
        detalhes = {}
    if not isinstance(detalhes, dict):
        return []

    linhas = []
    dados = detalhes.get('dados')
    if isinstance(dados, dict):
        linhas.extend(linhas_detalhes_pdf(dados))
    return linhas


class RelatorioLogPDF(FPDF):
    def header(self):
        self.set_fill_color(0, 71, 171)
        self.rect(0, 0, self.w, 20, 'F')
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 15)
        self.set_xy(16, 6)
        self.cell(0, 8, 'Constituere | Relatorio de Log')
        self.set_text_color(35, 35, 35)
        self.set_y(28)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(220, 228, 238)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.set_y(-9)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, f'Gerado em {datetime.now().strftime("%d/%m/%Y")} | Pagina {self.page_no()}', align='C')


def gerar_pdf_logs(logs, titulo='Log do escritorio'):
    """Produz o relatório PDF do Log em visão resumida e detalhada.

    A parte detalhada usa somente os campos permitidos por linhas_detalhes_pdf,
    que remove IDs internos, senhas, tokens e o identificador técnico do evento.
    """
    # A API paginada retorna um dicionário; chamadas internas podem fornecer
    # diretamente a lista de registros.
    if isinstance(logs, dict):
        logs = logs.get('logs', [])

    pdf = RelatorioLogPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_fill_color(237, 244, 255)
    pdf.set_text_color(0, 71, 171)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, texto_pdf_log(titulo, 80), fill=True, new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(35, 35, 35)
    pdf.ln(4)

    pdf.set_fill_color(245, 248, 252)
    pdf.set_draw_color(220, 228, 238)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(0, 71, 171)
    pdf.cell(64, 9, 'REGISTROS ENCONTRADOS', border=1, fill=True)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(35, 9, str(len(logs)), border=1, fill=True, new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(35, 35, 35)
    pdf.ln(5)

    colunas = [
        ('Usuario', 38, 28), ('Acao', 22, 18), ('Registro afetado', 42, 34),
        ('Data e hora', 30, 18), ('Resumo da acao', 111, 105), ('IP', 22, 16)
    ]

    def cabecalho_tabela():
        pdf.set_fill_color(237, 244, 255)
        pdf.set_draw_color(220, 228, 238)
        pdf.set_text_color(0, 71, 171)
        pdf.set_font('Helvetica', 'B', 7)
        for nome, largura, _ in colunas:
            pdf.cell(largura, 8, nome, border=1, fill=True)
        pdf.ln()
        pdf.set_text_color(35, 35, 35)

    cabecalho_tabela()
    pdf.set_font('Helvetica', '', 6.5)
    for indice, log in enumerate(logs):
        if pdf.get_y() + 8 > 190:
            pdf.add_page()
            cabecalho_tabela()
            pdf.set_font('Helvetica', '', 6.5)
        data_hora = log.get('data_hora') or ''
        data = f'{data_hora[8:10]}/{data_hora[5:7]}/{data_hora[:4]}' if len(data_hora) >= 10 else '-'
        hora = data_hora[11:16] if len(data_hora) >= 16 else '-'
        registro = alvo_humano(
            log.get('tabela_afetada'),
            log.get('id_registro_afetado'),
        )
        valores = [
            log.get('nome_usuario'),
            log.get('acao'),
            registro,
            f'{data} {hora}',
            log.get('descricao_humana') or resumo_alteracoes_pdf(log),
            log.get('ip_origem'),
        ]

        if indice % 2:
            pdf.set_fill_color(250, 252, 255)
        else:
            pdf.set_fill_color(255, 255, 255)
        for (_, largura, limite), valor in zip(colunas, valores):
            pdf.cell(largura, 8, texto_pdf_log(valor, limite), border=1, fill=True)
        pdf.ln()

    pdf.add_page()
    pdf.set_fill_color(237, 244, 255)
    pdf.set_text_color(0, 71, 171)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, 'DETALHAMENTO DOS REGISTROS', fill=True, new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(35, 35, 35)
    pdf.ln(3)

    for indice, log in enumerate(logs, start=1):
        data_hora = log.get('data_hora') or ''
        data_hora_legivel = (
            f'{data_hora[8:10]}/{data_hora[5:7]}/{data_hora[:4]} {data_hora[11:16]}'
            if len(data_hora) >= 16 else '-'
        )
        registro = alvo_humano(
            log.get('tabela_afetada'), log.get('id_registro_afetado')
        )
        alteracoes = resumo_alteracoes_pdf(log)
        detalhes = detalhes_pdf_log(log)
        cabecalho = (
            f'Ação {indice} | {log.get("acao") or "Acao"} | '
            f'{texto_pdf_log(log.get("nome_usuario") or "Sistema", 80)}'
        )
        altura_estimada = 34 + min(90, 4 * (len(detalhes) + max(1, len(alteracoes) // 105)))
        if pdf.get_y() + altura_estimada > 186:
            pdf.add_page()

        pdf.set_fill_color(0, 71, 171)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 8)
        pdf.cell(0, 6, texto_pdf_log(cabecalho, 180), fill=True, new_x='LMARGIN', new_y='NEXT')
        pdf.set_text_color(35, 35, 35)
        pdf.set_font('Helvetica', '', 8)
        resumo = log.get('descricao_humana') or 'Acao registrada no sistema.'
        pdf.multi_cell(
            0, 4.5, f'Resumo: {texto_pdf_log(resumo, 900)}', border=1,
            new_x='LMARGIN', new_y='NEXT',
        )
        pdf.multi_cell(
            0,
            4.5,
            texto_pdf_log(
                f'Registro afetado: {registro}\n'
                f'Data e hora: {data_hora_legivel}\n'
                f'Cargo: {log.get("cargo") or "--"}\n'
                f'Dispositivo: {log.get("maquina") or "--"}\n'
                f'IP de origem: {log.get("ip_origem") or "--"}',
                1200,
            ),
            border=1,
            new_x='LMARGIN',
            new_y='NEXT',
        )
        if alteracoes:
            pdf.set_font('Helvetica', 'B', 8)
            pdf.cell(0, 5, 'Alteracoes registradas', border='LTR', new_x='LMARGIN', new_y='NEXT')
            pdf.set_font('Helvetica', '', 8)
            pdf.multi_cell(
                0, 4.5, texto_pdf_log(alteracoes, 1400), border='LBR',
                new_x='LMARGIN', new_y='NEXT',
            )
        if detalhes:
            pdf.set_font('Helvetica', 'B', 8)
            pdf.cell(0, 5, 'Informacoes adicionais', border='LTR', new_x='LMARGIN', new_y='NEXT')
            pdf.set_font('Helvetica', '', 8)
            pdf.multi_cell(
                0, 4.5, '\n'.join(detalhes), border='LBR',
                new_x='LMARGIN', new_y='NEXT',
            )
        pdf.ln(4)

    return bytes(pdf.output())
