"""Registro e consulta da trilha de auditoria em um banco Firebird separado."""

import json
import os
import socket
import unicodedata
from datetime import date, datetime, time

import fdb
from fpdf import FPDF
from flask import current_app, g, request

from db import conexao


_CAMPOS_SIGILOSOS = {'senha', 'confirmar_senha', 'token', 'authorization', 'acess_token'}


def conexao_log():
    parametros = {
        'database': current_app.config['LOG_DB_NAME'],
        'user': current_app.config['LOG_DB_USER'],
        'password': current_app.config['LOG_DB_PASSWORD'],
    }

    # A auditoria possui uma configuração própria para não herdar uma DLL de
    # arquitetura incompatível usada por outra conexão do sistema.
    cliente_firebird = os.getenv('LOG_FIREBIRD_CLIENT_DLL')
    if cliente_firebird:
        parametros['fb_library_name'] = cliente_firebird

    return fdb.connect(**parametros)


def _normalizar_valor(valor):
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {
            str(chave): '***' if str(chave).lower() in _CAMPOS_SIGILOSOS else _normalizar_valor(item)
            for chave, item in valor.items()
        }
    if isinstance(valor, (list, tuple)):
        return [_normalizar_valor(item) for item in valor]
    return valor


def _dados_requisicao():
    if request.is_json:
        return _normalizar_valor(request.get_json(silent=True) or {})
    if request.form:
        return _normalizar_valor(request.form.to_dict())
    return {}


def _identificar_escritorio(id_usuario, dados, view_args):
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
        return linha[0] if linha else None
    finally:
        cur.close()
        con.close()


def _nome_usuario(id_usuario):
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


def _descricao_evento():
    caminho = request.path.lower()
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
    if caminho.endswith('/inativar'):
        return 'INATIVAR', caminho.split('/')[1].upper()
    if caminho.endswith('/ativar'):
        return 'ATIVAR', caminho.split('/')[1].upper()

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


def _id_registro(view_args):
    for chave, valor in (view_args or {}).items():
        if chave.startswith('id_'):
            try:
                return int(valor)
            except (TypeError, ValueError):
                return None
    return None


def _alvo_snapshot():
    """Retorna a tabela e a condição do registro alterado pela rota atual."""
    argumentos = request.view_args or {}
    caminho = request.path.lower()
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
    if caminho == '/editar_perfil':
        token = getattr(g, 'auditoria_token', None) or {}
        if token.get('id_usuarios'):
            return 'USUARIOS', 'ID_USUARIOS = ?', (token['id_usuarios'],)
    return None


def _buscar_snapshot(alvo):
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
            descricao[0].strip(): _normalizar_valor(valor)
            for descricao, valor in zip(cur.description, linha)
        }
    finally:
        cur.close()
        con.close()


def preparar_requisicao(token_data):
    """Guarda o estado anterior para que UPDATEs tenham antigo e novo no Log."""
    g.auditoria_token = token_data or {}
    if request.method not in {'PUT', 'PATCH', 'DELETE'}:
        return
    alvo = _alvo_snapshot()
    g.auditoria_alvo = alvo
    g.auditoria_anterior = _buscar_snapshot(alvo)


def _valor_para_log(valor):
    if valor is None:
        return None
    if isinstance(valor, (dict, list, tuple)):
        return json.dumps(valor, ensure_ascii=False, default=str)
    return str(valor)


def _alteracoes_registradas():
    anterior = getattr(g, 'auditoria_anterior', None)
    alvo = getattr(g, 'auditoria_alvo', None)
    if not anterior or not alvo:
        return []
    atual = _buscar_snapshot(alvo)
    if not atual:
        return [('REGISTRO', _valor_para_log(anterior), 'Removido')]
    return [
        (campo, _valor_para_log(valor_antigo), _valor_para_log(atual.get(campo)))
        for campo, valor_antigo in anterior.items()
        if valor_antigo != atual.get(campo)
    ]


def registrar_requisicao(token_data):
    """Grava uma ação concluída. Falhas no log não alteram a resposta da API."""
    if request.path.startswith('/logs'):
        return

    dados = _dados_requisicao()
    view_args = request.view_args or {}
    id_usuario = token_data.get('id_usuarios') if token_data else None
    id_escritorio = _identificar_escritorio(id_usuario, dados, view_args)
    if not id_escritorio:
        return

    acao, tabela = _descricao_evento()
    detalhes = json.dumps({
        'metodo': request.method,
        'rota': request.path,
        'dados': dados,
    }, ensure_ascii=False, default=str)

    alteracoes = _alteracoes_registradas()
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
                    id_escritorio, id_usuario, _nome_usuario(id_usuario), acao,
                    tabela, _id_registro(view_args), campo, antigo, novo, detalhes,
                    socket.gethostname(), request.remote_addr,
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


def listar_logs(id_escritorio, limite=200, data_inicio=None, data_fim=None, advogado=None):
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
        def texto_blob(valor):
            if valor is None:
                return None
            return valor.read() if hasattr(valor, 'read') else str(valor)

        resultado = []
        for linha in cur.fetchall():
            resultado.append({
                'id_log': linha[0], 'id_usuario': linha[1], 'nome_usuario': linha[2],
                'acao': linha[3], 'tabela_afetada': linha[4],
                'id_registro_afetado': linha[5], 'campo': linha[6],
                'valor_antigo': texto_blob(linha[7]),
                'valor_novo': texto_blob(linha[8]),
                'detalhes': texto_blob(linha[9]),
                'data_hora': linha[10].isoformat() if linha[10] else None,
                'maquina': linha[11], 'ip_origem': linha[12],
            })
        if data_inicio:
            resultado = [log for log in resultado if (log['data_hora'] or '')[:10] >= data_inicio]
        if data_fim:
            resultado = [log for log in resultado if (log['data_hora'] or '')[:10] <= data_fim]
        if advogado:
            resultado = [log for log in resultado if log['nome_usuario'] == advogado]
        return resultado
    finally:
        cur.close()
        con.close()


def gerar_pdf_logs(logs, titulo='Log do escritorio'):
    def texto(valor, tamanho=32):
        valor = '-' if valor in (None, '') else str(valor)
        valor = unicodedata.normalize('NFKD', valor).encode('ascii', 'ignore').decode('ascii')
        return valor if len(valor) <= tamanho else f'{valor[:tamanho - 3]}...'

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, texto(titulo, 90), new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, f'Registros encontrados: {len(logs)}', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)

    colunas = [
        ('Nome', 28), ('Acao', 18), ('Data', 21), ('Hora', 14), ('Tabela', 30),
        ('Campo', 25), ('Antigo', 33), ('Novo', 33), ('Maquina', 32)
    ]
    pdf.set_fill_color(237, 243, 252)
    pdf.set_font('Helvetica', 'B', 7)
    for nome, largura in colunas:
        pdf.cell(largura, 8, nome, border=1, fill=True)
    pdf.ln()

    pdf.set_font('Helvetica', '', 6.5)
    for log in logs:
        data_hora = log.get('data_hora') or ''
        valores = [
            texto(log.get('nome_usuario'), 20), texto(log.get('acao'), 14), texto(data_hora[8:10] + '/' + data_hora[5:7] + '/' + data_hora[:4] if len(data_hora) >= 10 else '-', 12),
            texto(data_hora[11:16] if len(data_hora) >= 16 else '-', 8), texto(log.get('tabela_afetada'), 22),
            texto(log.get('campo'), 18), texto(log.get('valor_antigo'), 24), texto(log.get('valor_novo'), 24), texto(log.get('maquina'), 22)
        ]
        for (_, largura), valor in zip(colunas, valores):
            pdf.cell(largura, 7, valor, border=1)
        pdf.ln()

    return bytes(pdf.output())
