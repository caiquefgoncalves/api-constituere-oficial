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
_ROTAS_CONVERSA_IA = {'/ai/veritas'}


def _eh_conversa_ia():
    """A conversa e somente leitura e nao deve entrar no Log."""
    return request.path.rstrip('/').lower() in _ROTAS_CONVERSA_IA


def _eh_rota_log():
    """Operações no próprio Log não devem gerar um novo registro de auditoria."""
    return '/logs/' in request.path.rstrip('/').lower()


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
    if _eh_conversa_ia() or _eh_rota_log():
        return
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
    if request.path.startswith('/logs') or _eh_conversa_ia() or _eh_rota_log():
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


def excluir_log(id_escritorio, id_log):
    """Exclui um registro somente quando ele pertence ao escritório informado."""
    con = conexao_log()
    cur = con.cursor()
    try:
        cur.execute(
            'DELETE FROM LOG_AUDITORIA WHERE ID_LOG = ? AND ID_ESCRITORIO = ?',
            (id_log, id_escritorio),
        )
        if cur.rowcount != 1:
            con.rollback()
            return False
        con.commit()
        return True
    finally:
        cur.close()
        con.close()


def _texto_pdf_log(valor, tamanho=None):
    texto = '-' if valor in (None, '') else str(valor)
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    if tamanho and len(texto) > tamanho:
        return f'{texto[:tamanho - 3]}...'
    return texto


class RelatorioLogPDF(FPDF):
    """Mantém a identidade visual usada nos relatórios do Constituere."""
    def header(self):
        self.set_fill_color(0, 71, 171)
        self.rect(0, 0, 297, 20, 'F')
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 15)
        self.set_xy(16, 6)
        self.cell(0, 8, 'Constituere | Relatorio de Log')
        self.set_text_color(35, 35, 35)
        self.set_y(28)

    def footer(self):
        self.set_y(-12)
        self.set_draw_color(220, 228, 238)
        self.line(16, self.get_y(), 281, self.get_y())
        self.set_y(-9)
        self.set_font('Helvetica', '', 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, f'Gerado em {datetime.now().strftime("%d/%m/%Y")} | Pagina {self.page_no()}', align='C')


def gerar_pdf_logs(logs, titulo='Log do escritorio'):
    pdf = RelatorioLogPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_fill_color(237, 244, 255)
    pdf.set_text_color(0, 71, 171)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, _texto_pdf_log(titulo, 80), fill=True, new_x='LMARGIN', new_y='NEXT')
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
        ('Nome', 28, 20), ('Acao', 20, 14), ('Data', 20, 12), ('Hora', 15, 8),
        ('Tabela', 31, 22), ('Campo', 27, 18), ('Valor antigo', 39, 27),
        ('Valor novo', 39, 27), ('Maquina', 30, 20)
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
        valores = [log.get('nome_usuario'), log.get('acao'), data, hora, log.get('tabela_afetada'), log.get('campo'), log.get('valor_antigo'), log.get('valor_novo'), log.get('maquina')]
        if indice % 2:
            pdf.set_fill_color(250, 252, 255)
        else:
            pdf.set_fill_color(255, 255, 255)
        for (_, largura, limite), valor in zip(colunas, valores):
            pdf.cell(largura, 7, _texto_pdf_log(valor, limite), border=1, fill=True)
        pdf.ln()

    return bytes(pdf.output())
