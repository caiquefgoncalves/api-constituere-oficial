from flask import jsonify, request, make_response, send_file
from funcao import *
from flask_bcrypt import generate_password_hash, check_password_hash
from main import app, socketio
from db import conexao, conexao_log
import os
import datetime
from io import BytesIO
import concurrent.futures
import time
from consulta_cnsa import consultar_cnsa
from consulta_oab import consultar_oab
from fpdf import FPDF
from io import BytesIO
import unicodedata


@app.route('/escritorio/<int:id_escritorio>/logs', methods=['GET'])
def listar_logs_escritorio(id_escritorio):
    token = decodificar_token()

    if not token:
        return jsonify({'error': 'Token necessário'}), 401

    if token.get('tipo') != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    principal = None
    auditoria = None
    cur = None
    cur_log = None

    def texto(valor):
        if valor is None:
            return ''

        if hasattr(valor, 'read'):
            valor = valor.read()

        if isinstance(valor, bytes):
            return valor.decode('utf-8', errors='replace')

        return str(valor)

    def inteiro(valor):
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    def extrair_campos(valor):
        resultado = {}

        for parte in re.split(
            r'\s+\|\s+|\x1e',
            texto(valor).replace('\r', '')
        ):
            chave, separador, conteudo = parte.partition(':')

            if not separador:
                continue

            chave = chave.strip().upper().replace(' ', '_')

            if not re.fullmatch(r'[A-Z0-9_]+', chave):
                continue

            resultado[chave] = conteudo.strip()

        return resultado

    try:
        principal = conexao()
        cur = principal.cursor()

        cur.execute("""
            SELECT 1
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
              AND STATUS = 'PROPRIETARIO'
              AND ATIVO = 1
        """, (
            token['id_usuarios'],
            id_escritorio
        ))

        if not cur.fetchone():
            return jsonify({
                'error': 'Apenas o proprietário pode consultar os logs.'
            }), 403

        auditoria = conexao_log()
        cur_log = auditoria.cursor()

        cur_log.execute("""
            SELECT FIRST 500
                ID_LOG,
                ID_USUARIO,
                NOME_USUARIO,
                ACAO,
                TABELA_AFETADA,
                ID_REGISTRO_AFETADO,
                CAMPO,
                VALOR_ANTIGO,
                VALOR_NOVO,
                DETALHES,
                DATA_HORA,
                MAQUINA,
                IP_ORIGEM
            FROM LOG_AUDITORIA
            WHERE ID_ESCRITORIO = ?
            ORDER BY DATA_HORA DESC, ID_LOG DESC
        """, (id_escritorio,))

        registros = cur_log.fetchall()
        cache = {}

        def consultar(sql, parametros):
            chave = (sql, tuple(parametros))

            if chave not in cache:
                cur.execute(sql, tuple(parametros))
                cache[chave] = cur.fetchone()

            return cache[chave]

        def nome_usuario(id_usuario):
            if id_usuario is None:
                return None

            linha = consultar(
                'SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?',
                (id_usuario,)
            )

            return linha[0] if linha else None

        def nome_alvo(tabela, identificador, antigo, novo):
            atributos = {**antigo, **novo}

            def campo(chave):
                valor = atributos.get(chave)

                if valor is None or valor.upper() == 'NULL':
                    return None

                return valor

            if tabela == 'USUARIOS':
                return (
                    nome_usuario(identificador)
                    or campo('NOME')
                    or 'Cadastro de usuário'
                )

            if tabela == 'ESCRITORIOS':
                nome = (
                    campo('NOME_FANTASIA')
                    or campo('RAZAO_SOCIAL')
                )

                if not nome:
                    linha = consultar("""
                        SELECT NOME_FANTASIA, RAZAO_SOCIAL
                        FROM ESCRITORIOS
                        WHERE ID_ESCRITORIOS = ?
                    """, (identificador,))

                    nome = (
                        linha[0] or linha[1]
                        if linha
                        else None
                    )

                return nome or 'Escritório'

            if tabela == 'ADVOGADO_ESCRITORIO':
                advogado_id = inteiro(campo('ID_USUARIOS'))

                if advogado_id is None:
                    linha = consultar("""
                        SELECT ID_USUARIOS
                        FROM ADVOGADO_ESCRITORIO
                        WHERE ID = ?
                    """, (identificador,))

                    advogado_id = linha[0] if linha else None

                return (
                    nome_usuario(advogado_id)
                    or 'Advogado vinculado'
                )

            if tabela == 'ATUALIZACOES':
                titulo = campo('TITULO')

                if not titulo:
                    linha = consultar("""
                        SELECT TITULO
                        FROM ATUALIZACOES
                        WHERE ID_ATUALIZACOES = ?
                    """, (identificador,))

                    titulo = linha[0] if linha else None

                return titulo or 'Atualização do processo'

            if tabela == 'AGENDAMENTOS':
                assunto = campo('ASSUNTO')
                cliente = campo('CLIENTE')

                if not assunto and not cliente:
                    linha = consultar("""
                        SELECT ASSUNTO, CLIENTE
                        FROM AGENDAMENTOS
                        WHERE ID_AGENDAMENTOS = ?
                    """, (identificador,))

                    if linha:
                        assunto, cliente = linha

                if not cliente:
                    cliente = nome_usuario(
                        inteiro(campo('ID_USUARIOS_CLIENTE'))
                    )

                if assunto and cliente:
                    return f'{assunto} ({cliente})'

                return assunto or cliente or 'Agendamento'

            if tabela == 'LANCAMENTOS_FINANCEIROS':
                descricao = campo('DESCRICAO')

                if not descricao:
                    linha = consultar("""
                        SELECT DESCRICAO
                        FROM LANCAMENTOS_FINANCEIROS
                        WHERE ID_LANCAMENTOS = ?
                    """, (identificador,))

                    descricao = linha[0] if linha else None

                return descricao or 'Lançamento financeiro'

            if tabela == 'GOOGLE_CALENDAR':
                return 'Google Agenda'

            if tabela == 'PROCESSOS':
                linha = consultar("""
                    SELECT NUM_PROCESSO
                    FROM PROCESSOS
                    WHERE ID_PROCESSOS = ?
                """, (identificador,))

                if linha and linha[0]:
                    return f'Processo {linha[0]}'

                return 'Processo'

            if tabela == 'NOTIFICACOES':
                linha = consultar("""
                    SELECT TITULO
                    FROM NOTIFICACOES
                    WHERE ID_NOTIFICACAO = ?
                """, (identificador,))

                return linha[0] if linha and linha[0] else 'Notificação'

            if tabela == 'PARTE_CONTRARIA':
                linha = consultar("""
                    SELECT NOME
                    FROM PARTE_CONTRARIA
                    WHERE ID_PARTE_CONTRARIA = ?
                """, (identificador,))

                return linha[0] if linha and linha[0] else 'Parte contrária'

            if tabela == 'DOCUMENTOS_GERADOS':
                linha = consultar("""
                    SELECT NOME_ARQUIVO
                    FROM DOCUMENTOS_GERADOS
                    WHERE ID_DOCUMENTOS_GERADOS = ?
                """, (identificador,))

                return linha[0] if linha and linha[0] else 'Documento'

            if tabela == 'MODELOS_DOCUMENTOS':
                linha = consultar("""
                    SELECT NOME
                    FROM MODELOS_DOCUMENTOS
                    WHERE ID_MODELOS_DOCUMENTOS = ?
                """, (identificador,))

                return linha[0] if linha and linha[0] else 'Modelo de documento'

            if tabela == 'REPRESENTANTES':
                linha = consultar("""
                    SELECT NOME_COMPLETO
                    FROM REPRESENTANTES
                    WHERE ID_REPRESENTANTE = ?
                """, (identificador,))

                return linha[0] if linha and linha[0] else 'Representante'

            if tabela in ('MENSAGENS', 'CONVERSAS'):
                conversa_id = inteiro(campo('ID_CONVERSA'))
                mensagem_id = inteiro(campo('ID_MENSAGEM'))

                if tabela == 'MENSAGENS' and conversa_id is None:
                    linha = consultar("""
                        SELECT ID_CONVERSA
                        FROM MENSAGENS
                        WHERE ID_MENSAGEM = ?
                    """, (mensagem_id or identificador,))

                    conversa_id = linha[0] if linha else None

                if tabela == 'CONVERSAS':
                    conversa_id = conversa_id or identificador

                if conversa_id:
                    linha = consultar("""
                        SELECT ID_ADVOGADO, ID_CLIENTE
                        FROM CONVERSAS
                        WHERE ID_CONVERSA = ?
                    """, (conversa_id,))

                    if linha:
                        nome1 = nome_usuario(linha[0])
                        nome2 = nome_usuario(linha[1])

                        if tabela == 'MENSAGENS':
                            if nome2 or nome1:
                                return (
                                    f'Mensagem (conversa com '
                                    f'{nome2 or nome1})'
                                )

                            return 'Mensagem'

                        return (
                            f'Conversa ({nome1 or "Advogado"} '
                            f'x {nome2 or "Cliente"})'
                        )

                return (
                    'Mensagem'
                    if tabela == 'MENSAGENS'
                    else 'Conversa'
                )

            return (
                campo('NOME')
                or campo('DESCRICAO')
                or campo('TITULO')
                or 'Registro'
            )

        campos_protegidos = {
            'SENHA',
            'REFRESH_TOKEN',
            'ACCESS_TOKEN',
            'CLIENT_SECRET',
            'ID_TOKEN',
            'TOKEN',
            'GOOGLE_EVENT_ID'
        }

        logs = []

        for row in registros:
            tabela = (
                texto(row[4])
                .strip()
                .upper()
                .replace(' ', '_')
            )

            acao = texto(row[3]).strip().upper()
            detalhes = texto(row[9])
            antigo = extrair_campos(row[7])
            novo = extrair_campos(row[8])

            mudancas = []

            for campo in dict.fromkeys([*antigo, *novo]):
                if (
                    campo.startswith('ID_')
                    or campo in campos_protegidos
                ):
                    continue

                antes = antigo.get(campo, '')
                depois = novo.get(campo, '')

                if antes == depois:
                    continue

                mudancas.append({
                    'campo': campo,
                    'antes': (
                        '(Vazio)'
                        if not antes or antes.upper() == 'NULL'
                        else antes
                    ),
                    'depois': (
                        '(Vazio)'
                        if not depois or depois.upper() == 'NULL'
                        else depois
                    )
                })

            if (
                tabela == 'NOTIFICACOES'
                and acao == 'UPDATE'
                and len(mudancas) == 1
                and mudancas[0]['campo'] == 'LIDA'
            ):
                acao = (
                    'LIDO'
                    if mudancas[0]['depois'] in ('1', 'Lido')
                    else 'NAO_LIDO'
                )

            if acao == 'UPDATE' and antigo == novo:
                continue

            autor = re.search(
                r'(?im)^AUTOR_ID:\s*(\d+)\s*$',
                detalhes
            )

            autor_id = (
                inteiro(autor.group(1))
                if autor
                else None
            )

            sistema = (
                'ORIGEM: SISTEMA' in detalhes
                or 'ORIGEM: APP' in detalhes
            )

            banco = (
                'ORIGEM: BANCO_DIRETO' in detalhes
                or not sistema
            )

            if sistema:
                nome_autor = (
                    nome_usuario(autor_id)
                    if autor_id and autor_id > 0
                    else None
                )

                nome_realizador = (
                    nome_autor
                    or 'Ação realizada pelo sistema'
                )

                cargo = (
                    'Advogado'
                    if nome_autor
                    else 'Sistema'
                )

                id_realizador = (
                    autor_id
                    if nome_autor
                    else None
                )
            else:
                nome_realizador = 'Alterado diretamente no banco'
                cargo = 'Banco de dados'
                id_realizador = None

            alvo = nome_alvo(
                tabela,
                row[5],
                antigo,
                novo
            )

            ip = texto(row[12]) or '--'

            if ip == '::1':
                ip = '127.0.0.1'

            logs.append({
                'id_log': row[0],
                'id_usuario': id_realizador,
                'nome_usuario': nome_realizador,
                'acao': acao,
                'tabela_afetada': tabela.replace('_', ' ').title(),
                'id_registro_afetado': row[5],
                'nome_registro_afetado': alvo,
                'mudancas': mudancas,
                'data_hora': (
                    row[10].isoformat()
                    if row[10]
                    else None
                ),
                'maquina': texto(row[11]) or '--',
                'ip_origem': ip,
                'cargo': cargo,
                'alerta_banco': banco
            })

        return jsonify({
            'logs': logs,
            'pagina': 1,
            'por_pagina': 500,
            'total': len(logs),
            'total_paginas': 1,
            'tem_mais': False
        }), 200

    except Exception:
        app.logger.exception(
            'Erro ao consultar logs de auditoria'
        )

        return jsonify({
            'error': 'Erro ao consultar logs de auditoria.'
        }), 500

    finally:
        if cur_log is not None:
            cur_log.close()

        if auditoria is not None:
            auditoria.close()

        if cur is not None:
            cur.close()

        if principal is not None:
            principal.close()



@app.route('/escritorio/<int:id_escritorio>/logs/pdf', methods=['GET'])
def gerar_relatorio_logs_pdf(id_escritorio):
    import re
    import unicodedata
    import datetime
    from io import BytesIO
    from fpdf import FPDF
    from flask import jsonify, request, send_file

    token_data = decodificar_token()

    if not token_data or token_data.get('tipo') != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    con = None
    cur = None
    con_log = None
    cur_log = None

    try:
        con = conexao()
        cur = con.cursor()

        cur.execute("""
            SELECT 1
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
              AND STATUS = 'PROPRIETARIO'
              AND ATIVO = 1
        """, (token_data['id_usuarios'], id_escritorio))

        if not cur.fetchone():
            return jsonify({
                'error': 'Apenas o proprietário pode consultar os logs.'
            }), 403

        cur.execute("""
            SELECT NOME
            FROM USUARIOS
            WHERE ID_USUARIOS = ?
        """, (token_data['id_usuarios'],))

        resultado_advogado = cur.fetchone()
        nome_advogado = resultado_advogado[0] if resultado_advogado else 'Advogado'

        con_log = conexao_log()
        cur_log = con_log.cursor()

        cur_log.execute("""
            SELECT FIRST 500
                ID_LOG,
                ID_USUARIO,
                NOME_USUARIO,
                ACAO,
                TABELA_AFETADA,
                ID_REGISTRO_AFETADO,
                CAMPO,
                VALOR_ANTIGO,
                VALOR_NOVO,
                DETALHES,
                DATA_HORA,
                MAQUINA,
                IP_ORIGEM
            FROM LOG_AUDITORIA
            WHERE ID_ESCRITORIO = ?
            ORDER BY DATA_HORA DESC, ID_LOG DESC
        """, (id_escritorio,))

        rows = cur_log.fetchall()

        if not rows:
            return jsonify({
                'error': 'Nenhum log encontrado para gerar o PDF.'
            }), 404

        def texto(valor):
            if valor is None:
                return ''

            if hasattr(valor, 'read'):
                valor = valor.read()

            if isinstance(valor, bytes):
                valor = valor.decode('utf-8', errors='replace')

            return str(valor).strip()

        def texto_pdf(valor):
            valor = texto(valor) or '-'
            return unicodedata.normalize(
                'NFKD', valor
            ).encode('ascii', 'ignore').decode('ascii')

        def inteiro(valor):
            try:
                return int(valor)
            except (TypeError, ValueError):
                return None

        def consultar(sql, parametros):
            try:
                cur.execute(sql, parametros)
                return cur.fetchone()
            except Exception:
                return None

        def nome_usuario(id_usuario):
            if not id_usuario:
                return None

            linha = consultar("""
                SELECT NOME
                FROM USUARIOS
                WHERE ID_USUARIOS = ?
            """, (id_usuario,))

            return linha[0] if linha else None

        def extrair_campos(valor):
            resultado = {}

            for parte in re.split(
                r'\s+\|\s+|\x1e',
                texto(valor).replace('\r', '').replace('\n', ' ')
            ):
                chave, separador, conteudo = parte.partition(':')

                if not separador:
                    continue

                chave = chave.strip().upper().replace(' ', '_')
                conteudo = conteudo.strip()

                if not re.fullmatch(r'[A-Z0-9_]+', chave):
                    continue

                resultado[chave] = (
                    '(Vazio)'
                    if not conteudo or conteudo.upper() == 'NULL'
                    else conteudo
                )

            return resultado

        campos_protegidos = {
            'SENHA',
            'REFRESH_TOKEN',
            'ACCESS_TOKEN',
            'CLIENT_SECRET',
            'ID_TOKEN',
            'TOKEN',
            'GOOGLE_EVENT_ID'
        }

        def obter_mudancas(antigo, novo):
            mudancas = []

            for campo in dict.fromkeys([*antigo, *novo]):
                if campo.startswith('ID_') or campo in campos_protegidos:
                    continue

                antes = antigo.get(campo, '(Vazio)')
                depois = novo.get(campo, '(Vazio)')

                if antes == depois:
                    continue

                mudancas.append({
                    'campo': campo,
                    'antes': antes,
                    'depois': depois
                })

            return mudancas

        def obter_alvo(tabela, identificador, antigo, novo):
            atributos = {**antigo, **novo}

            def campo(chave):
                valor = atributos.get(chave)

                if valor is None or valor.upper() in ('NULL', '(VAZIO)'):
                    return None

                return valor

            consultas = {
                'USUARIOS': (
                    'SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?',
                    (identificador,)
                ),
                'ESCRITORIOS': (
                    'SELECT COALESCE(NOME_FANTASIA, RAZAO_SOCIAL) FROM ESCRITORIOS WHERE ID_ESCRITORIOS = ?',
                    (identificador,)
                ),
                'ATUALIZACOES': (
                    'SELECT TITULO FROM ATUALIZACOES WHERE ID_ATUALIZACOES = ?',
                    (identificador,)
                ),
                'AGENDAMENTOS': (
                    'SELECT ASSUNTO FROM AGENDAMENTOS WHERE ID_AGENDAMENTOS = ?',
                    (identificador,)
                ),
                'LANCAMENTOS_FINANCEIROS': (
                    'SELECT DESCRICAO FROM LANCAMENTOS_FINANCEIROS WHERE ID_LANCAMENTOS = ?',
                    (identificador,)
                ),
                'PROCESSOS': (
                    'SELECT NUM_PROCESSO FROM PROCESSOS WHERE ID_PROCESSOS = ?',
                    (identificador,)
                ),
                'NOTIFICACOES': (
                    'SELECT TITULO FROM NOTIFICACOES WHERE ID_NOTIFICACAO = ?',
                    (identificador,)
                ),
                'PARTE_CONTRARIA': (
                    'SELECT NOME FROM PARTE_CONTRARIA WHERE ID_PARTE_CONTRARIA = ?',
                    (identificador,)
                ),
                'DOCUMENTOS_GERADOS': (
                    'SELECT NOME_ARQUIVO FROM DOCUMENTOS_GERADOS WHERE ID_DOCUMENTOS_GERADOS = ?',
                    (identificador,)
                ),
                'MODELOS_DOCUMENTOS': (
                    'SELECT NOME FROM MODELOS_DOCUMENTOS WHERE ID_MODELOS_DOCUMENTOS = ?',
                    (identificador,)
                ),
                'REPRESENTANTES': (
                    'SELECT NOME_COMPLETO FROM REPRESENTANTES WHERE ID_REPRESENTANTE = ?',
                    (identificador,)
                )
            }

            if tabela == 'ADVOGADO_ESCRITORIO':
                advogado_id = inteiro(campo('ID_USUARIOS'))

                if advogado_id is None:
                    linha = consultar("""
                        SELECT ID_USUARIOS
                        FROM ADVOGADO_ESCRITORIO
                        WHERE ID = ?
                    """, (identificador,))
                    advogado_id = linha[0] if linha else None

                return nome_usuario(advogado_id) or 'Advogado vinculado'

            if tabela == 'GOOGLE_CALENDAR':
                return 'Google Agenda'

            if tabela in ('MENSAGENS', 'CONVERSAS'):
                return 'Mensagem' if tabela == 'MENSAGENS' else 'Conversa'

            if tabela == 'AGENDAMENTOS':
                return campo('ASSUNTO') or 'Agendamento'

            if tabela == 'ESCRITORIOS':
                return (
                    campo('NOME_FANTASIA')
                    or campo('RAZAO_SOCIAL')
                    or 'Escritório'
                )

            if tabela == 'USUARIOS':
                return campo('NOME') or nome_usuario(identificador) or 'Cadastro de usuário'

            if tabela in consultas:
                sql, parametros = consultas[tabela]
                linha = consultar(sql, parametros)

                if linha and linha[0]:
                    return str(linha[0])

            return (
                campo('NOME')
                or campo('DESCRICAO')
                or campo('TITULO')
                or 'Registro'
            )

        nomes_tabelas = {
            'MENSAGENS': 'mensagem',
            'CONVERSAS': 'conversa',
            'ESCRITORIOS': 'escritório',
            'ATUALIZACOES': 'atualização do processo',
            'AGENDAMENTOS': 'agendamento',
            'ADVOGADO_ESCRITORIO': 'advogado',
            'LANCAMENTOS_FINANCEIROS': 'lançamento financeiro',
            'GOOGLE_CALENDAR': 'integração do Google Agenda',
            'NOTIFICACOES': 'notificação',
            'DOCUMENTOS_GERADOS': 'documento',
            'MODELOS_DOCUMENTOS': 'modelo',
            'PARTE_CONTRARIA': 'parte contrária',
            'PROCESSOS': 'processo',
            'PAGAMENTOS': 'pagamento',
            'PARCELAS': 'parcela',
            'PAGAMENTO_EXITO': 'honorário de êxito',
            'PARCELAS_EXITO': 'parcela de êxito'
        }

        verbos = {
            'MENSAGENS': {
                'INSERT': 'enviou',
                'UPDATE': 'editou',
                'DELETE': 'excluiu'
            },
            'CONVERSAS': {
                'INSERT': 'iniciou',
                'UPDATE': 'atualizou',
                'DELETE': 'excluiu'
            },
            'ESCRITORIOS': {
                'INSERT': 'cadastrou',
                'UPDATE': 'atualizou',
                'DELETE': 'excluiu'
            },
            'ATUALIZACOES': {
                'INSERT': 'registrou',
                'UPDATE': 'editou',
                'DELETE': 'excluiu'
            },
            'AGENDAMENTOS': {
                'INSERT': 'marcou',
                'UPDATE': 'atualizou',
                'DELETE': 'excluiu'
            },
            'ADVOGADO_ESCRITORIO': {
                'INSERT': 'vinculou',
                'UPDATE': 'alterou o vínculo de',
                'DELETE': 'removeu o vínculo de'
            },
            'GOOGLE_CALENDAR': {
                'INSERT': 'conectou',
                'UPDATE': 'atualizou',
                'DELETE': 'desconectou'
            }
        }

        rotulos_acoes = {
            'MENSAGENS': {
                'INSERT': 'Mensagem Enviada',
                'UPDATE': 'Mensagem Editada',
                'DELETE': 'Mensagem Excluída'
            },
            'CONVERSAS': {
                'INSERT': 'Nova Conversa',
                'UPDATE': 'Conversa Atualizada',
                'DELETE': 'Conversa Excluída'
            },
            'ESCRITORIOS': {
                'INSERT': 'Escritório Cadastrado',
                'UPDATE': 'Escritório Atualizado',
                'DELETE': 'Escritório Excluído'
            },
            'ATUALIZACOES': {
                'INSERT': 'Atualização Registrada',
                'UPDATE': 'Atualização Editada',
                'DELETE': 'Atualização Excluída'
            },
            'AGENDAMENTOS': {
                'INSERT': 'Agendamento Criado',
                'UPDATE': 'Agendamento Atualizado',
                'DELETE': 'Agendamento Excluído'
            },
            'ADVOGADO_ESCRITORIO': {
                'INSERT': 'Advogado Vinculado',
                'UPDATE': 'Vínculo Atualizado',
                'DELETE': 'Vínculo Removido'
            },
            'LANCAMENTOS_FINANCEIROS': {
                'INSERT': 'Novo Lançamento',
                'UPDATE': 'Lançamento Atualizado',
                'DELETE': 'Lançamento Excluído'
            },
            'GOOGLE_CALENDAR': {
                'INSERT': 'Google Conectado',
                'UPDATE': 'Integração Atualizada',
                'DELETE': 'Google Desconectado'
            }
        }

        acoes_personalizadas = {
            'PROCESSO_CRIADO': ('INSERT', 'Processo Cadastrado'),
            'PROCESSO_ATUALIZADO': ('UPDATE', 'Processo Atualizado'),
            'PROCESSO_EDITADO': ('UPDATE', 'Processo Atualizado'),
            'PROCESSO_EXCLUIDO': ('DELETE', 'Processo Excluído'),
            'USUARIO_CRIADO': ('INSERT', 'Usuário Cadastrado'),
            'USUARIO_ATUALIZADO': ('UPDATE', 'Usuário Atualizado'),
            'USUARIO_EXCLUIDO': ('DELETE', 'Usuário Excluído'),
            'AGENDAMENTO_CRIADO': ('INSERT', 'Agendamento Criado'),
            'AGENDAMENTO_ATUALIZADO': ('UPDATE', 'Agendamento Atualizado'),
            'AGENDAMENTO_EXCLUIDO': ('DELETE', 'Agendamento Excluído'),
            'DOCUMENTO_CRIADO': ('INSERT', 'Documento Cadastrado'),
            'DOCUMENTO_ATUALIZADO': ('UPDATE', 'Documento Atualizado'),
            'DOCUMENTO_EXCLUIDO': ('DELETE', 'Documento Excluído'),
            'PAGAMENTO_CRIADO': ('INSERT', 'Pagamento Cadastrado'),
            'PAGAMENTO_ATUALIZADO': ('UPDATE', 'Pagamento Atualizado'),
            'PAGAMENTO_EXCLUIDO': ('DELETE', 'Pagamento Excluído')
        }

        campos_legiveis = {
            'RAZAO_SOCIAL': 'Razão social',
            'NOME_FANTASIA': 'Nome fantasia',
            'REGISTRO_OAB': 'Registro OAB',
            'UF_OAB': 'UF da OAB',
            'TELEFONE': 'Telefone',
            'EMAIL': 'E-mail',
            'CNPJ': 'CNPJ',
            'CPF': 'CPF',
            'RG': 'RG',
            'CEP': 'CEP',
            'LOGRADOURO': 'Endereço',
            'NUMERO': 'Número',
            'COMPLEMENTO': 'Complemento',
            'BAIRRO': 'Bairro',
            'CIDADE': 'Cidade',
            'ESTADO': 'Estado',
            'TITULO': 'Título',
            'DESCRICAO': 'Descrição',
            'DATA': 'Data',
            'DATA_INICIO': 'Data de início',
            'DATA_ATUALIZACAO': 'Data de atualização',
            'PROCESSO_CONCLUIDO': 'Processo concluído',
            'CLIENTE': 'Cliente',
            'ASSUNTO': 'Assunto',
            'HORARIO': 'Horário',
            'DURACAO': 'Duração em minutos',
            'STATUS': 'Situação',
            'MOTIVO': 'Motivo',
            'TIPO': 'Tipo',
            'VALOR': 'Valor',
            'VALOR_TOTAL': 'Valor total',
            'VALOR_PAGO': 'Valor pago',
            'VALOR_PARCELA': 'Valor da parcela',
            'FORMA_PAGAMENTO': 'Forma de pagamento',
            'ATIVO': 'Status',
            'LIDA': 'Status de leitura',
            'NOME': 'Nome',
            'NOME_COMPLETO': 'Nome completo',
            'NUM_PROCESSO': 'Número do processo',
            'TIPO_PROCESSO': 'Tipo de processo',
            'AREA': 'Área',
            'COMARCA': 'Comarca',
            'VARA': 'Vara',
            'INSTANCIA': 'Instância',
            'PROFISSAO': 'Profissão',
            'SEXO': 'Sexo',
            'NACIONALIDADE': 'Nacionalidade',
            'ESTADO_CIVIL': 'Estado civil',
            'NOME_ARQUIVO': 'Nome do arquivo',
            'MENSAGEM': 'Mensagem',
            'ULTIMA_MENSAGEM': 'Última mensagem',
            'GOOGLE_EMAIL': 'Conta Google',
            'CONTA_GOOGLE': 'Conta Google',
            'CONEXAO': 'Conexão com Google',
            'CREDENCIAL': 'Credencial de acesso',
            'SALARIOS': 'Salários',
            'SALARIO': 'Salário',
            'SALARIO_BASE': 'Salário base',
            'DATA_NASCIMENTO': 'Data de nascimento',
            'DATA_VENCIMENTO': 'Data de vencimento',
            'DATA_PAGAMENTO': 'Data de pagamento'
        }

        def formatar_campo(campo):
            campo = str(campo or '').strip().upper()

            return campos_legiveis.get(
                campo,
                campo.replace('_', ' ').capitalize()
            )

        def formatar_valor(campo, valor, tabela):
            if valor is None or str(valor).strip().upper() in ('', 'NULL', '(VAZIO)'):
                return 'Não existia'

            valor = str(valor).strip()
            chave = str(campo or '').upper()

            def somente_numeros(texto):
                return re.sub(r'\D', '', str(texto))

            def formatar_cpf(numero):
                if len(numero) == 11:
                    return f'{numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}'
                return numero

            def formatar_cnpj(numero):
                if len(numero) == 14:
                    return f'{numero[:2]}.{numero[2:5]}.{numero[5:8]}/{numero[8:12]}-{numero[12:]}'
                return numero

            def formatar_telefone(numero):
                if len(numero) == 11:
                    return f'({numero[:2]}) {numero[2:7]}-{numero[7:]}'
                if len(numero) == 10:
                    return f'({numero[:2]}) {numero[2:6]}-{numero[6:]}'
                return numero

            if chave == 'CPF':
                return formatar_cpf(somente_numeros(valor))

            if chave == 'CNPJ':
                return formatar_cnpj(somente_numeros(valor))

            if chave in ('TELEFONE', 'CELULAR', 'WHATSAPP'):
                return formatar_telefone(somente_numeros(valor))

            if chave == 'CEP':
                numero = somente_numeros(valor)
                if len(numero) == 8:
                    return f'{numero[:5]}-{numero[5:]}'
                return valor

            if chave in ('NUM_PROCESSO', 'NUMERO_PROCESSO'):
                numero = somente_numeros(valor)
                if len(numero) == 20:
                    return (
                        f'{numero[:7]}-{numero[7:9]}.'
                        f'{numero[9:13]}.{numero[13]}.'
                        f'{numero[14:16]}.{numero[16:]}'
                    )
                return valor

            if chave == 'PROCESSO_CONCLUIDO':
                return 'Sim' if valor.upper() in ('1', 'TRUE', 'SIM') else 'Não'

            if chave.startswith(('CONFIRMADO_', 'RECUSADO_')):
                return 'Sim' if valor.upper() in ('1', 'TRUE', 'SIM') else 'Não'

            if chave == 'ATIVO':
                return 'Ativo' if valor.upper() in ('1', 'TRUE', 'SIM') else 'Inativo'

            if chave == 'LIDA':
                return 'Lido' if valor.upper() in ('1', 'TRUE', 'SIM') else 'Não lido'

            if chave == 'STATUS':
                status = {
                    'A_CONFIRMAR': 'A confirmar',
                    'CONFIRMADO': 'Confirmado',
                    'RECUSADO': 'Recusado',
                    'CANCELADO': 'Cancelado',
                    'PENDENTE': 'Pendente',
                    'PAGO': 'Pago',
                    'PAGA': 'Paga',
                    'RECEBIDO': 'Recebido',
                    'ATRASADO': 'Atrasado',
                    'CONCLUIDO': 'Concluído',
                    'EM_ANDAMENTO': 'Em andamento',
                    'ATIVO': 'Ativo',
                    'INATIVO': 'Inativo'
                }
                return status.get(valor.upper(), valor.replace('_', ' ').capitalize())

            if chave == 'TIPO' and tabela == 'USUARIOS':
                return {
                    '0': 'Advogado',
                    '1': 'Escritório',
                    '2': 'Cliente (Pessoa Física)',
                    '3': 'Cliente (Pessoa Jurídica)'
                }.get(valor, valor)

            campos_monetarios = (
                chave == 'VALOR'
                or chave.startswith('VALOR_')
                or 'SALARIO' in chave
                or chave in ('HONORARIOS', 'HONORARIO', 'SALARIOS')
            )

            if campos_monetarios:
                numero = valor.replace('R$', '').replace(' ', '')

                if ',' in numero and '.' in numero:
                    numero = numero.replace('.', '').replace(',', '.')
                elif ',' in numero:
                    numero = numero.replace(',', '.')

                try:
                    numero = float(numero)
                    return f'R$ {numero:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
                except (ValueError, TypeError):
                    pass

            if chave == 'DATA' or chave.startswith('DATA_') or 'NASCIMENTO' in chave or 'VENCIMENTO' in chave:
                data = re.match(r'^(\d{4})-(\d{2})-(\d{2})', valor)

                if data:
                    return f'{data.group(3)}/{data.group(2)}/{data.group(1)}'

                data_br = re.match(r'^(\d{2})/(\d{2})/(\d{4})', valor)

                if data_br:
                    return valor

            traducoes = {
                'PROPRIETARIO': 'Proprietário',
                'PARCEIRO': 'Parceiro',
                'ASSOCIADO': 'Associado',
                'FISICA': 'Pessoa Física',
                'JURIDICA': 'Pessoa Jurídica',
                'SALARIOS': 'Salários',
                'SALARIO': 'Salário',
                'PENDENTE': 'Pendente',
                'PAGA': 'Paga',
                'PAGO': 'Pago',
                'RECEBIDO': 'Recebido',
                'A_PAGAR': 'A pagar',
                'A_RECEBER': 'A receber',
                'PIX': 'Pix',
                'BOLETO': 'Boleto',
                'CARTAO_CREDITO': 'Cartão de crédito',
                'CARTAO_DE_CREDITO': 'Cartão de crédito',
                'DINHEIRO': 'Dinheiro',
                'TRANSFERENCIA': 'Transferência',
                'DEBITO': 'Débito',
                'CREDITO': 'Crédito',
                'MENSAL': 'Mensal',
                'ANUAL': 'Anual',
                'TRABALHISTA': 'Trabalhista',
                'CIVIL': 'Cível',
                'PENAL': 'Penal',
                'FAMILIA': 'Família',
                'PREVIDENCIARIO': 'Previdenciário',
                'TRIBUTARIO': 'Tributário'
            }

            return traducoes.get(
                valor.upper(),
                valor.replace('_', ' ').capitalize()
            )

        class RelatorioLogsPDF(FPDF):
            def header(self):
                self.set_fill_color(0, 71, 171)
                self.rect(0, 0, 210, 23, 'F')
                self.set_text_color(255, 255, 255)
                self.set_font('Helvetica', 'B', 15)
                self.set_xy(15, 7)
                self.cell(0, 8, 'Constituere | Historico de Alteracoes')
                self.set_y(30)

            def footer(self):
                self.set_y(-14)
                self.set_draw_color(220, 228, 238)
                self.line(15, self.get_y(), 195, self.get_y())
                self.set_y(-11)
                self.set_font('Helvetica', '', 8)
                self.set_text_color(100, 100, 100)
                self.cell(
                    0,
                    5,
                    f'Relatorio gerado em {datetime.date.today().strftime("%d/%m/%Y")} | Pagina {self.page_no()}',
                    align='C'
                )

        pdf = RelatorioLogsPDF(orientation='P', unit='mm', format='A4')
        pdf.set_margins(15, 15, 15)
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        pdf.set_text_color(0, 71, 171)
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 9, 'Historico de Alteracoes do Escritorio', new_x='LMARGIN', new_y='NEXT')

        pdf.set_text_color(90, 100, 115)
        pdf.set_font('Helvetica', '', 9)
        pdf.cell(
            0,
            6,
            f'Responsavel pelo relatorio: {texto_pdf(nome_advogado)}',
            new_x='LMARGIN',
            new_y='NEXT'
        )

        total_banco = sum(
            1 for row in rows
            if 'ORIGEM: BANCO_DIRETO' in texto(row[9])
            or not (
                'ORIGEM: SISTEMA' in texto(row[9])
                or 'ORIGEM: APP' in texto(row[9])
            )
        )

        total_sistema = len(rows) - total_banco

        pdf.ln(4)

        largura_card = 180
        largura_resumo = 85

        def verificar_espaco(altura=35):
            if pdf.get_y() + altura > 275:
                pdf.add_page()

        def escrever_texto(valor, largura, altura=5, negrito=False, cor=(35, 45, 60)):
            pdf.set_text_color(*cor)
            pdf.set_font('Helvetica', 'B' if negrito else '', 9)
            pdf.multi_cell(
                largura,
                altura,
                texto_pdf(valor),
                border=0,
                new_x='LMARGIN',
                new_y='NEXT'
            )

        def escrever_mudanca(mudanca, tabela):
            verificar_espaco(27)

            y_inicio = pdf.get_y()

            pdf.set_fill_color(245, 248, 252)
            pdf.set_draw_color(225, 232, 240)
            pdf.rect(18, y_inicio, 174, 24, 'DF')

            pdf.set_xy(21, y_inicio + 2)
            escrever_texto(
                formatar_campo(mudanca['campo']),
                168,
                4,
                True,
                (30, 50, 75)
            )

            y_valores = pdf.get_y() + 1

            pdf.set_xy(21, y_valores)
            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_text_color(153, 27, 27)
            pdf.cell(82, 4, 'ANTES')

            pdf.set_xy(108, y_valores)
            pdf.set_text_color(22, 101, 52)
            pdf.cell(82, 4, 'DEPOIS')

            pdf.set_xy(21, y_valores + 5)
            escrever_texto(
                formatar_valor(
                    mudanca['campo'],
                    mudanca['antes'],
                    tabela
                ),
                82,
                4,
                False,
                (100, 35, 35)
            )

            pdf.set_xy(108, y_valores + 5)
            escrever_texto(
                formatar_valor(
                    mudanca['campo'],
                    mudanca['depois'],
                    tabela
                ),
                82,
                4,
                False,
                (25, 90, 50)
            )

            pdf.set_y(max(pdf.get_y(), y_inicio + 26))
            pdf.ln(2)

        for indice, row in enumerate(rows):
            tabela = texto(row[4]).strip().upper().replace(' ', '_')
            acao_original = texto(row[3]).strip().upper()

            acao_personalizada = acoes_personalizadas.get(acao_original)

            if acao_personalizada:
                acao = acao_personalizada[0]
                rotulo_personalizado = acao_personalizada[1]
            else:
                acao = acao_original
                rotulo_personalizado = None

            detalhes = texto(row[9])

            antigo = extrair_campos(row[7])
            novo = extrair_campos(row[8])
            mudancas = obter_mudancas(antigo, novo)

            if tabela == 'NOTIFICACOES' and acao == 'UPDATE' and len(mudancas) == 1 and mudancas[0]['campo'] == 'LIDA':
                acao = 'LIDO' if mudancas[0]['depois'] in ('1', 'Lido') else 'NAO_LIDO'

            if acao == 'UPDATE' and antigo == novo:
                continue

            autor_match = re.search(
                r'(?im)^AUTOR_ID:\s*(\d+)\s*$',
                detalhes
            )

            autor_id = inteiro(autor_match.group(1)) if autor_match else None

            sistema = (
                'ORIGEM: SISTEMA' in detalhes
                or 'ORIGEM: APP' in detalhes
            )

            foi_banco = (
                'ORIGEM: BANCO_DIRETO' in detalhes
                or not sistema
            )

            if foi_banco:
                nome_realizador = 'Alterado diretamente no banco'
                cargo = 'Banco de dados'
            else:
                nome_realizador = (
                    nome_usuario(autor_id)
                    if autor_id and autor_id > 0
                    else None
                ) or 'Ação realizada pelo sistema'

                cargo = 'Advogado' if autor_id and nome_usuario(autor_id) else 'Sistema'

            alvo = obter_alvo(
                tabela,
                row[5],
                antigo,
                novo
            )

            verbo = verbos.get(tabela, {}).get(
                acao,
                {
                    'INSERT': 'cadastrou',
                    'CRIAR': 'cadastrou',
                    'UPDATE': 'atualizou',
                    'EDITAR': 'atualizou',
                    'DELETE': 'excluiu',
                    'EXCLUIR': 'excluiu',
                    'LIDO': 'marcou como lida',
                    'NAO_LIDO': 'marcou como não lida'
                }.get(acao, 'modificou')
            )

            objeto = nomes_tabelas.get(tabela, 'cadastro')

            if tabela == 'ADVOGADO_ESCRITORIO' and acao != 'INSERT':
                resumo = f'{nome_realizador} {verbo} {alvo}.'
            elif tabela == 'MENSAGENS':
                resumo = f'{nome_realizador} {verbo} a mensagem.'
            elif tabela == 'CONVERSAS':
                resumo = f'{nome_realizador} {verbo} a conversa.'
            elif tabela == 'GOOGLE_CALENDAR':
                resumo = f'{nome_realizador} {verbo} a integração do Google Agenda.'
            else:
                resumo = f'{nome_realizador} {verbo} {objeto} {alvo}.'

            rotulo_acao = rotulo_personalizado or rotulos_acoes.get(tabela, {}).get(
                acao,
                {
                    'INSERT': 'Novo Cadastro',
                    'CRIAR': 'Novo Cadastro',
                    'UPDATE': 'Atualização',
                    'EDITAR': 'Atualização',
                    'DELETE': 'Exclusão',
                    'EXCLUIR': 'Exclusão',
                    'LIDO': 'Lido',
                    'NAO_LIDO': 'Não lida'
                }.get(acao, 'Atualização')
            )

            data_hora = row[10]

            if data_hora:
                if isinstance(data_hora, str):
                    try:
                        data_hora = datetime.datetime.fromisoformat(data_hora)
                    except ValueError:
                        data = data_hora[:10]
                        hora = data_hora[11:19]
                        partes = data.split('-')
                        if len(partes) == 3:
                            data = f'{partes[2]}/{partes[1]}/{partes[0]}'
                    else:
                        data = data_hora.strftime('%d/%m/%Y')
                        hora = data_hora.strftime('%H:%M:%S')
                else:
                    data = data_hora.strftime('%d/%m/%Y')
                    hora = data_hora.strftime('%H:%M:%S')
            else:
                data = '-'
                hora = '-'

            ip = texto(row[12]) or '-'

            if ip == '::1':
                ip = '127.0.0.1'

            maquina = texto(row[11]) or '-'

            verificar_espaco(48)

            y_inicio = pdf.get_y()

            pdf.set_draw_color(215, 225, 238)
            pdf.set_fill_color(255, 255, 255)
            pdf.rect(15, y_inicio, largura_card, 10, 'F')

            pdf.set_fill_color(0, 71, 171)
            pdf.rect(15, y_inicio, 2, 10, 'F')

            pdf.set_xy(20, y_inicio + 2)
            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_text_color(
                153 if foi_banco else 15,
                27 if foi_banco else 23,
                27 if foi_banco else 42
            )
            pdf.cell(largura_resumo, 5, texto_pdf(nome_realizador))

            pdf.set_xy(145, y_inicio + 2)
            pdf.set_font('Helvetica', 'B', 8)

            if foi_banco:
                pdf.set_text_color(153, 27, 27)
            else:
                pdf.set_text_color(0, 71, 171)

            pdf.cell(45, 5, texto_pdf(rotulo_acao), align='R')

            pdf.set_xy(20, y_inicio + 12)
            pdf.set_font('Helvetica', '', 8)
            pdf.set_text_color(110, 120, 135)
            pdf.cell(0, 5, texto_pdf(cargo), new_x='LMARGIN', new_y='NEXT')

            if foi_banco:
                pdf.set_x(20)
                pdf.set_font('Helvetica', 'B', 8)
                pdf.set_text_color(153, 27, 27)
                pdf.multi_cell(
                    170,
                    5,
                    'ALTERACAO DIRETA NO BANCO DE DADOS',
                    new_x='LMARGIN',
                    new_y='NEXT'
                )

            pdf.set_x(20)
            pdf.set_font('Helvetica', '', 9)
            pdf.set_text_color(51, 65, 85)
            pdf.multi_cell(
                170,
                5,
                texto_pdf(resumo),
                new_x='LMARGIN',
                new_y='NEXT'
            )

            pdf.ln(2)

            y_meta = pdf.get_y()
            pdf.set_fill_color(237, 244, 255)
            pdf.rect(20, y_meta, 170, 13, 'F')

            metadados = [
                ('DATA', data, 20),
                ('HORA', hora, 65),
                ('MEIO', 'Banco de Dados' if foi_banco else 'Sistema', 110)
            ]

            for titulo, valor, x in metadados:
                pdf.set_xy(x + 3, y_meta + 1)
                pdf.set_font('Helvetica', 'B', 7)
                pdf.set_text_color(90, 105, 125)
                pdf.cell(45, 4, titulo)

                pdf.set_xy(x + 3, y_meta + 6)
                pdf.set_font('Helvetica', 'B', 8)
                pdf.set_text_color(35, 50, 70)
                pdf.cell(55, 4, texto_pdf(valor))

            pdf.set_y(y_meta + 16)

            pdf.set_x(20)
            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_text_color(50, 65, 85)
            pdf.cell(0, 5, 'DETALHES DA ACAO', new_x='LMARGIN', new_y='NEXT')

            pdf.set_x(20)
            pdf.set_font('Helvetica', '', 8)
            pdf.set_text_color(90, 100, 115)
            pdf.multi_cell(
                170,
                4,
                f'Registro: {texto_pdf(alvo)}',
                new_x='LMARGIN',
                new_y='NEXT'
            )

            pdf.set_x(20)
            pdf.set_font('Helvetica', '', 8)
            pdf.set_text_color(90, 100, 115)
            pdf.multi_cell(
                170,
                4,
                f'IP: {texto_pdf(ip)}    |    Maquina: {texto_pdf(maquina)}',
                new_x='LMARGIN',
                new_y='NEXT'
            )

            if mudancas:
                pdf.ln(2)

                pdf.set_x(20)
                pdf.set_font('Helvetica', 'B', 9)
                pdf.set_text_color(30, 50, 75)
                pdf.cell(0, 5, 'O QUE MUDOU?', new_x='LMARGIN', new_y='NEXT')

                for mudanca in mudancas:
                    escrever_mudanca(mudanca, tabela)
            else:
                pdf.ln(2)
                pdf.set_x(20)
                pdf.set_font('Helvetica', 'I', 8)
                pdf.set_text_color(110, 120, 135)
                pdf.multi_cell(
                    170,
                    5,
                    'Nenhuma informacao detalhada foi registrada nesta alteracao.',
                    new_x='LMARGIN',
                    new_y='NEXT'
                )

            pdf.ln(5)
            pdf.set_draw_color(220, 228, 238)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(5)

        pdf.ln(2)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(70, 85, 105)
        pdf.cell(
            0,
            6,
            f'Total de acoes: {len(rows)}  |  Pelo sistema: {total_sistema}  |  Direto no banco: {total_banco}',
            new_x='LMARGIN',
            new_y='NEXT'
        )

        return send_file(
            BytesIO(bytes(pdf.output())),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='historico-alteracoes.pdf'
        )

    except Exception:
        app.logger.exception('Erro ao gerar PDF de logs de auditoria')

        return jsonify({
            'error': 'Não foi possível gerar o relatório.'
        }), 500

    finally:
        if cur_log is not None:
            cur_log.close()

        if con_log is not None:
            con_log.close()

        if cur is not None:
            cur.close()

        if con is not None:
            con.close()

@app.route('/escritorio/<int:id_escritorio>/informacoes', methods=['PUT'])
def editar_informacao_escritorio_ia(id_escritorio):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessario'}), 401
    if token_data['tipo'] != 0:
        return jsonify({'error': 'Acesso nao autorizado'}), 403

    dados = request.get_json(silent=True) or {}
    campo = str(dados.get('campo') or '').strip().lower()
    valor = str(dados.get('valor') or '').strip()
    campos = {
        'razao_social': 'RAZAO_SOCIAL', 'nome_fantasia': 'NOME_FANTASIA',
        'registro_oab': 'REGISTRO_OAB', 'uf_oab': 'UF_OAB', 'telefone': 'TELEFONE',
        'email': 'EMAIL', 'cep': 'CEP', 'logradouro': 'LOGRADOURO', 'numero': 'NUMERO',
        'complemento': 'COMPLEMENTO', 'bairro': 'BAIRRO', 'cidade': 'CIDADE', 'estado': 'ESTADO',
    }
    if campo not in campos or not valor:
        return jsonify({'error': 'Campo ou valor invalido'}), 400

    con = conexao()
    cur = con.cursor()
    try:
        cur.execute(
            """SELECT 1 FROM ADVOGADO_ESCRITORIO
               WHERE ID_USUARIOS = ? AND ID_ESCRITORIOS = ?
                 AND STATUS = 'PROPRIETARIO' AND ATIVO = 1""",
            (token_data['id_usuarios'], id_escritorio),
        )
        if not cur.fetchone():
            return jsonify({'error': 'Apenas o proprietario pode editar o escritório'}), 403
        cur.execute(
            f'UPDATE ESCRITORIOS SET {campos[campo]} = ? WHERE ID_ESCRITORIOS = ?',
            (valor.upper() if campo in {'uf_oab', 'estado'} else valor, id_escritorio),
        )
        con.commit()
        return jsonify({'message': 'Informação do escritório atualizada com sucesso'}), 200
    except Exception as erro:
        con.rollback()
        return jsonify({'error': f'Não foi possível atualizar a informação: {erro}'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/criar_usuarios', methods=['POST'])
def criar_usuarios():
    tipo = request.form.get('tipo')

    if tipo is None:
        return jsonify({"error": "Tipo de usuário é obrigatório"}), 400

    try:
        tipo = int(tipo)
    except ValueError:
        return jsonify({"error": "Tipo de usuário inválido"}), 400

    if tipo not in [0, 1, 2, 3]:
        return jsonify({"error": "Tipo de usuário inválido"}), 400

    id_usuario_logado = None
    tipo_usuario_logado = None

    if tipo in [2, 3]:
        token_data = decodificar_token()

        if token_data == False:
            return jsonify({'error': 'Token necessário'}), 401

        id_usuario_logado = token_data['id_usuarios']
        tipo_usuario_logado = token_data['tipo']

        if tipo_usuario_logado not in [0, 1]:
            return jsonify({'error': 'Apenas advogados ou escritórios podem cadastrar clientes'}), 403

    nome = request.form.get('nome')
    email = request.form.get('email')
    cpf = request.form.get('cpf_cnpj')
    telefone = request.form.get('telefone')
    senha = request.form.get('senha')
    confirmar_senha = request.form.get('confirmar_senha')

    cep = request.form.get('cep')
    logradouro = request.form.get('logradouro')
    numero = request.form.get('numero')
    complemento = request.form.get('complemento')
    bairro = request.form.get('bairro')
    cidade = request.form.get('cidade')
    estado = request.form.get('estado')

    rg = request.form.get('rg')
    orgao_expedidor = request.form.get('orgao_expedidor')
    nacionalidade = request.form.get('nacionalidade')
    estado_civil = request.form.get('estado_civil')
    data_nascimento = request.form.get('data_nascimento')
    sexo = request.form.get('sexo')
    profissao = request.form.get('profissao')

    num_oab = request.form.get('num_oab')
    uf_oab = request.form.get('uf_oab')
    area_atuacao = request.form.get('area_atuacao')

    razao_social = request.form.get('razao_social')
    nome_fantasia = request.form.get('nome_fantasia')
    cnpj = request.form.get('cnpj')

    carteira_trabalho = request.form.get('carteira_trabalho')
    serie_carteira = request.form.get('serie_carteira')

    if not nome:
        return jsonify({"error": "Nome é obrigatório"}), 400
    if not email:
        return jsonify({"error": "E-mail é obrigatório"}), 400
    if not senha:
        return jsonify({"error": "Senha é obrigatória"}), 400
    if not confirmar_senha:
        return jsonify({"error": "Confirmar senha é obrigatório"}), 400
    if not telefone:
        return jsonify({"error": "Telefone é obrigatório"}), 400

    if tipo == 0:
        if not cpf:
            return jsonify({"error": "CPF é obrigatório"}), 400
        if not validar_cpf(cpf):
            return jsonify({"error": "CPF inválido"}), 400
        if verificar_existente(cpf, "CPF"):
            return jsonify({"error": "CPF já cadastrado"}), 400
        if verificar_existente(email, "EMAIL"):
            return jsonify({"error": "E-mail já cadastrado"}), 400
        if not num_oab:
            return jsonify({"error": "Número da OAB é obrigatório"}), 400
        if not uf_oab:
            return jsonify({"error": "UF da OAB é obrigatória"}), 400
        if not area_atuacao:
            return jsonify({"error": "Área de atuação é obrigatória"}), 400
        if verificar_existente(num_oab, "NUM_OAB"):
            return jsonify({"error": "Número da OAB já cadastrado"}), 400

    elif tipo == 1:
        if not cnpj:
            return jsonify({"error": "CNPJ é obrigatório"}), 400
        if verificar_existente(cnpj, "CNPJ"):
            return jsonify({"error": "CNPJ já cadastrado"}), 400
        if verificar_existente(email, "EMAIL"):
            return jsonify({"error": "E-mail já cadastrado"}), 400

    elif tipo == 2:
        if not cpf:
            return jsonify({"error": "CPF é obrigatório"}), 400
        if not validar_cpf(cpf):
            return jsonify({"error": "CPF inválido"}), 400
        if verificar_existente(cpf, "CPF"):
            return jsonify({"error": "CPF já cadastrado"}), 400
        if verificar_existente(email, "EMAIL"):
            return jsonify({"error": "E-mail já cadastrado"}), 400
        if not data_nascimento:
            return jsonify({"error": "Data de nascimento é obrigatória"}), 400
        if not sexo:
            return jsonify({"error": "Sexo é obrigatório"}), 400

        valido, msg = validar_idade(data_nascimento)
        if not valido:
            return jsonify({"error": msg}), 400

        try:
            texto_nasc = str(data_nascimento).strip()

            if '/' in texto_nasc:
                data_nasc_obj = datetime.datetime.strptime(texto_nasc, '%d/%m/%Y').date()
            elif '-' in texto_nasc:
                data_nasc_obj = datetime.datetime.strptime(texto_nasc[:10], '%Y-%m-%d').date()
            else:
                raise ValueError('Formato desconhecido')

            if data_nasc_obj > datetime.date.today():
                return jsonify({"error": "A data de nascimento não pode ser uma data futura"}), 400

            limite_120_anos = datetime.date.today() - datetime.timedelta(days=120 * 365)
            if data_nasc_obj < limite_120_anos:
                return jsonify({"error": "A data de nascimento não pode ser superior a 120 anos atrás"}), 400

        except:
            return jsonify({"error": "Data de nascimento inválida"}), 400

    elif tipo == 3:
        if not cnpj:
            return jsonify({"error": "CNPJ é obrigatório"}), 400
        if verificar_existente(cnpj, "CNPJ"):
            return jsonify({"error": "CNPJ já cadastrado"}), 400
        if verificar_existente(email, "EMAIL"):
            return jsonify({"error": "E-mail já cadastrado"}), 400
        if not razao_social:
            return jsonify({"error": "Razão social é obrigatória"}), 400
        if not nome_fantasia:
            return jsonify({"error": "Nome fantasia é obrigatório"}), 400

    if not senha_forte(senha):
        return jsonify({"error": "Senha fraca. Use 8+ caracteres, maiúsculas, minúsculas, números e especiais"}), 400
    if senha != confirmar_senha:
        return jsonify({"error": "Senhas não correspondem"}), 400

    if tipo == 0:
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(consultar_oab, uf_oab=uf_oab, num_oab=num_oab, nome=nome, apenas_regular=True)
                resultado_oab = future.result(timeout=30)
            if not resultado_oab:
                return jsonify({"error": "Não foi possível obter uma resposta da OAB."}), 400
            items = resultado_oab.get("items", [])
            if not items:
                return jsonify({"error": f"OAB {uf_oab}-{num_oab} não encontrada."}), 400
            adv = items[0]
            if adv.get("situacao", "").upper() != "REGULAR":
                return jsonify({"error": f"Situação da OAB: {adv.get('situacao')}. Apenas regulares."}), 400
            if nome.strip().upper() != adv.get("nome", "").strip().upper():
                return jsonify({"error": "Nome não confere com o da OAB."}), 400
        except Exception as e:
            return jsonify({"error": "Erro ao consultar a OAB."}), 500

    data_nascimento_salvar = None

    if tipo == 2 and data_nascimento:
        try:
            texto = str(data_nascimento).strip()

            if '/' in texto:
                data_obj = datetime.datetime.strptime(texto, '%d/%m/%Y').date()
            elif '-' in texto:
                data_obj = datetime.datetime.strptime(texto[:10], '%Y-%m-%d').date()
            else:
                data_obj = None

            if data_obj:
                data_nascimento_salvar = data_obj.strftime('%Y-%m-%d')
        except Exception as e:
            print(f"Erro ao converter data de nascimento: {e}")
            data_nascimento_salvar = None

    senha_cripto = generate_password_hash(senha).decode('utf-8')
    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
                    INSERT INTO USUARIOS (
                        NOME, EMAIL, SENHA, CPF, TELEFONE, TIPO,
                        RG, ORGAO_EXPEDIDOR, NUM_OAB, UF_OAB, AREA_ATUACAO,
                        NACIONALIDADE, ESTADO_CIVIL, DATA_NASCIMENTO,
                        SEXO, PROFISSAO, CNPJ, RAZAO_SOCIAL, NOME_FANTASIA,
                        CEP, LOGRADOURO, NUMERO, COMPLEMENTO, BAIRRO,
                        CIDADE, ESTADO, CARTERA_TRABALHO, SERIE_CARTERA,
                        DATA_CADASTRO, ATIVO, ID_USUARIO_RESPONSAVEL
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        RETURNING ID_USUARIOS
                    """, (
            nome, email, senha_cripto, cpf, telefone, tipo,
            rg, orgao_expedidor, num_oab, uf_oab, area_atuacao,
            nacionalidade, estado_civil, data_nascimento_salvar,
            sexo, profissao, cnpj, razao_social, nome_fantasia,
            cep, logradouro, numero, complemento, bairro,
            cidade, estado, carteira_trabalho, serie_carteira,
            datetime.datetime.now(), 1, id_usuario_logado
        ))

        id_usuario = cur.fetchone()[0]
        con.commit()

        cpf_email = cpf if cpf else cnpj
        cpf_email_limpo = ''.join(filter(str.isdigit, cpf_email or ''))

        if len(cpf_email_limpo) == 11:
            cpf_email_formatado = f"{cpf_email_limpo[:3]}.{cpf_email_limpo[3:6]}.{cpf_email_limpo[6:9]}-{cpf_email_limpo[9:]}"
        elif len(cpf_email_limpo) == 14:
            cpf_email_formatado = f"{cpf_email_limpo[:2]}.{cpf_email_limpo[2:5]}.{cpf_email_limpo[5:8]}/{cpf_email_limpo[8:12]}-{cpf_email_limpo[12:]}"
        else:
            cpf_email_formatado = cpf_email or '--'

        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                executor.submit(
                    enviar_email_boas_vindas,
                    email,
                    nome,
                    cpf_email_formatado,
                    senha
                )
            print(f"Solicitação de envio de e-mail de boas-vindas criada para {email}")
        except Exception as e:
            print(f"Erro ao agendar envio de e-mail de boas-vindas: {e}")

        foto_perfil = request.files.get('foto_perfil')
        if foto_perfil:
            try:
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'Usuarios')
                os.makedirs(caminho, exist_ok=True)
                foto_perfil.save(os.path.join(caminho, f'{id_usuario}.jpeg'))
            except Exception as e:
                print(f"Erro ao salvar imagem: {e}")

        return jsonify({'message': 'Cadastro realizado com sucesso!', 'id': id_usuario}), 201

    except Exception as e:
        con.rollback()
        return jsonify({'error': f'Erro interno: {e}'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/editar_perfil', methods=['PUT'])
def editar_perfil():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuario = token_data['id_usuarios']
    tipo_usuario = token_data['tipo']

    nome = request.form.get('nome')
    email = request.form.get('email')
    cpf = request.form.get('cpf_cnpj')
    telefone = request.form.get('telefone')
    senha = request.form.get('senha')
    confirmar_senha = request.form.get('confirmar_senha')
    rg = request.form.get('rg')
    orgao_expedidor = request.form.get('orgao_expedidor')
    num_oab = request.form.get('num_oab')
    uf_oab = request.form.get('uf_oab')
    area_atuacao = request.form.get('area_atuacao')
    nacionalidade = request.form.get('nacionalidade')
    estado_civil = request.form.get('estado_civil')

    if tipo_usuario != 0:
        return jsonify({"error": "Apenas advogados podem editar o perfil completo"}), 403

    if not nome:
        return jsonify({"error": "Nome é obrigatório"}), 400
    if not cpf:
        return jsonify({"error": "CPF é obrigatório"}), 400
    if not email:
        return jsonify({"error": "E-mail é obrigatório"}), 400
    if not telefone:
        return jsonify({"error": "Telefone é obrigatório"}), 400
    if not rg:
        return jsonify({"error": "RG é obrigatório"}), 400
    if not orgao_expedidor:
        return jsonify({"error": "Órgão expedidor é obrigatório"}), 400
    if not num_oab:
        return jsonify({"error": "Número da OAB é obrigatório"}), 400
    if not uf_oab:
        return jsonify({"error": "UF da OAB é obrigatória"}), 400
    if not area_atuacao:
        return jsonify({"error": "Área de atuação é obrigatória"}), 400
    if not nacionalidade:
        return jsonify({"error": "Nacionalidade é obrigatória"}), 400
    if not estado_civil:
        return jsonify({"error": "Estado civil é obrigatório"}), 400

    cpf_limpo = ''.join(filter(str.isdigit, cpf))

    try:
        from funcao import validar_cpf
        if not validar_cpf(cpf_limpo):
            return jsonify({"error": "CPF inválido"}), 400
    except Exception as e:
        print(f"Erro ao validar CPF: {e}")

    con = conexao()
    cur = con.cursor()
    try:
        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE CPF = ? AND ID_USUARIOS != ?", (cpf_limpo, id_usuario))
        if cur.fetchone():
            return jsonify({"error": "CPF já cadastrado para outro usuário"}), 400

        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE EMAIL = ? AND ID_USUARIOS != ?", (email, id_usuario))
        if cur.fetchone():
            return jsonify({"error": "E-mail já cadastrado para outro usuário"}), 400

        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE NUM_OAB = ? AND UF_OAB = ? AND ID_USUARIOS != ?",
                    (num_oab, uf_oab, id_usuario))
        if cur.fetchone():
            return jsonify(
                {"error": f"Este número de OAB ({uf_oab}-{num_oab}) já está cadastrado para outro usuário."}), 400

        cur.execute("""
            SELECT NOME, NUM_OAB, UF_OAB
            FROM USUARIOS
            WHERE ID_USUARIOS = ?
        """, (id_usuario,))
        usuario_atual = cur.fetchone()

        nome_atual = usuario_atual[0] if usuario_atual else None
        oab_atual = usuario_atual[1] if usuario_atual else None
        uf_oab_atual = usuario_atual[2] if usuario_atual else None

    except Exception as e:
        return jsonify({"error": f"Erro ao verificar duplicidade: {e}"}), 500
    finally:
        cur.close()
        con.close()

    if senha and senha.strip() != '':
        if senha_forte(senha) == False:
            return jsonify({
                "error": "Senha fraca. Use 8+ caracteres, maiúsculas, minúsculas, números e especiais"
            }), 400

        if senha_correspondente(senha, confirmar_senha) == False:
            return jsonify({"error": "Senhas não correspondem"}), 400

        senha_cripto = generate_password_hash(senha).decode('utf-8')
    else:
        senha_cripto = None

    nome_alterado = (
            nome_atual is None
            or nome.strip().upper() != (nome_atual or '').strip().upper()
    )

    oab_alterada = (num_oab != oab_atual) or (uf_oab != uf_oab_atual)

    precisa_validar_oab = oab_alterada or nome_alterado

    if precisa_validar_oab:
        from consulta_oab import consultar_oab

        try:
            print(f"Consultando OAB para edição: {uf_oab}-{num_oab} | Nome: {nome}")

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    consultar_oab,
                    uf_oab=uf_oab,
                    num_oab=num_oab,
                    nome=nome,
                    apenas_regular=True
                )

                try:
                    resultado_oab = future.result(timeout=30)
                except concurrent.futures.TimeoutError:
                    return jsonify({
                        "error": "A consulta à OAB está demorando muito. Tente novamente mais tarde."
                    }), 408

            print("Resultado da OAB (edição):", resultado_oab)

        except Exception as e:
            print(f"Erro ao consultar a OAB: {e}")
            return jsonify({
                "error": "Erro ao consultar a OAB."
            }), 500

        if not resultado_oab:
            return jsonify({
                "error": "Não foi possível obter uma resposta da OAB."
            }), 400

        items = resultado_oab.get("items", [])

        if not items:
            mensagem = resultado_oab.get("mensagem", "")
            if mensagem and "Advogado encontrado, mas a situação é" in mensagem:
                return jsonify({"error": mensagem}), 400
            return jsonify({
                "error": f"OAB {uf_oab}-{num_oab} não encontrada no cadastro da OAB. Verifique se o número e a UF estão corretos."
            }), 400

        nome_normalizado = nome.strip().upper()
        advogado_valido = None

        for item in items:
            nome_item = (item.get("nome") or "").strip().upper()
            situacao_item = (item.get("situacao") or "").strip().upper()

            if situacao_item == "REGULAR" and nome_item == nome_normalizado:
                advogado_valido = item
                break

        if not advogado_valido:
            for item in items:
                situacao_item = (item.get("situacao") or "").strip().upper()
                if situacao_item and situacao_item != "REGULAR":
                    return jsonify({
                        "error": f"Sua situação é {situacao_item}. Apenas advogados regulares podem editar seu perfil."
                    }), 400

            return jsonify({
                "error": "O nome informado não corresponde ao nome cadastrado na OAB."
            }), 400

        print(f"OAB validada com sucesso na edição: {uf_oab}-{num_oab} - {advogado_valido.get('nome')}")

    con = conexao()
    cur = con.cursor()

    try:
        if senha_cripto:
            cur.execute("""
                UPDATE USUARIOS
                SET NOME            = ?,
                    EMAIL           = ?,
                    CPF             = ?,
                    TELEFONE        = ?,
                    RG              = ?,
                    ORGAO_EXPEDIDOR = ?,
                    NUM_OAB         = ?,
                    UF_OAB          = ?,
                    AREA_ATUACAO    = ?,
                    NACIONALIDADE   = ?,
                    ESTADO_CIVIL    = ?,
                    SENHA           = ?
                WHERE ID_USUARIOS = ?
            """, (
                nome,
                email,
                cpf_limpo,
                telefone,
                rg,
                orgao_expedidor,
                num_oab,
                uf_oab,
                area_atuacao,
                nacionalidade,
                estado_civil,
                senha_cripto,
                id_usuario
            ))
        else:
            cur.execute("""
                UPDATE USUARIOS
                SET NOME            = ?,
                    EMAIL           = ?,
                    CPF             = ?,
                    TELEFONE        = ?,
                    RG              = ?,
                    ORGAO_EXPEDIDOR = ?,
                    NUM_OAB         = ?,
                    UF_OAB          = ?,
                    AREA_ATUACAO    = ?,
                    NACIONALIDADE   = ?,
                    ESTADO_CIVIL    = ?
                WHERE ID_USUARIOS = ?
            """, (
                nome,
                email,
                cpf_limpo,
                telefone,
                rg,
                orgao_expedidor,
                num_oab,
                uf_oab,
                area_atuacao,
                nacionalidade,
                estado_civil,
                id_usuario
            ))

        con.commit()

        foto_perfil = request.files.get('foto_perfil')
        if foto_perfil:
            try:
                nome_imagem = f'{id_usuario}.jpeg'
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'Usuarios')
                os.makedirs(caminho, exist_ok=True)
                foto_perfil.save(os.path.join(caminho, nome_imagem))
            except Exception as e:
                print(f"Erro ao salvar imagem: {e}")

        return jsonify({'message': 'Perfil atualizado com sucesso!'}), 200

    except Exception as e:
        con.rollback()
        return jsonify({'error': f'Erro interno: {e}'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/login', methods=['POST'])
def login():
    cpf_cnpj = request.json.get('cpf_cnpj')
    senha = request.json.get('senha')

    if not cpf_cnpj:
        return jsonify({'error': 'CPF/CNPJ é obrigatório'}), 400
    if not senha:
        return jsonify({'error': 'Senha é obrigatória'}), 400

    cpf_limpo = ''.join(filter(str.isdigit, str(cpf_cnpj)))

    if not validar_cpf(cpf_limpo):
        return jsonify({"error": "Usuário não encontrado"}), 404

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_USUARIOS, TIPO, NOME, SENHA, ATIVO, PRIMEIRO_ACESSO
            FROM USUARIOS WHERE CPF = ?
        """, (cpf_limpo,))

        usuario = cur.fetchone()

        if not usuario:
            return jsonify({"error": "Usuário não encontrado"}), 404

        id_usuario, tipo, nome, senha_hash, ativo, primeiro_acesso = usuario

        if ativo == 0:
            return jsonify({"error": "Usuário inativado"}), 400

        if not check_password_hash(senha_hash, senha):
            return jsonify({"error": "CPF/CNPJ ou senha incorretos"}), 400

        origem = request.headers.get('X-Client-Platform', '').strip().lower()

        if origem != 'expo-mobile' and tipo in (2, 3):
            return jsonify({
                'error': 'Clientes não podem acessar o site pela web. Apenas advogados podem fazer login por aqui. Utilize o aplicativo Constituere.',
                'bloqueado_web': True
            }), 403

        if origem == 'expo-mobile' and tipo in (0, 1):
            return jsonify({
                'error': 'Advogados e escritórios não podem acessar o aplicativo. Utilize o site oficial para fazer login.',
                'bloqueado_app': True
            }), 403

        token = gerar_token(tipo, id_usuario, 1440)

        resp = make_response(jsonify({
            'message': f'Bem-vindo, {nome}!',
            'nome': nome,
            'token': token,
            'tipo': tipo,
            'id_usuario': id_usuario,
            'primeiro_acesso': primeiro_acesso is None or primeiro_acesso == 1,
            'foto_perfil': f'{id_usuario}.jpeg'
        }))

        resp.set_cookie(
            'acess_token',
            token,
            httponly=True,
            secure=False,
            samesite='Lax',
            path="/",
            max_age=7600
        )

        return resp

    except Exception as e:
        print('Erro no login:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Erro: {e}'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/meus_dados', methods=['GET'])
def meus_dados():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuarios = token_data['id_usuarios']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT 
                ID_USUARIOS, 
                NOME, 
                EMAIL, 
                CPF, 
                TELEFONE, 
                TIPO,
                RG,
                ORGAO_EXPEDIDOR,
                NUM_OAB,
                UF_OAB,
                NACIONALIDADE,
                ESTADO_CIVIL
            FROM USUARIOS WHERE ID_USUARIOS = ?
        """, (id_usuarios,))
        usuario = cur.fetchone()

        if not usuario:
            return jsonify({'error': 'Usuário não encontrado'}), 404

        return jsonify({
            'usuario': {
                'id': usuario[0],
                'nome': usuario[1],
                'email': usuario[2],
                'cpf': usuario[3],
                'telefone': usuario[4],
                'tipo': usuario[5],
                'rg': usuario[6],
                'orgao_expedidor': usuario[7],
                'num_oab': usuario[8],
                'uf_oab': usuario[9],
                'nacionalidade': usuario[10],
                'estado_civil': usuario[11]
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>', methods=['GET'])
def detalhes_escritorio(id_escritorio):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    id_usuario = token_data['id_usuarios']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                e.ID_ESCRITORIOS,
                e.RAZAO_SOCIAL,
                e.NOME_FANTASIA,
                e.REGISTRO_OAB,
                e.UF_OAB,
                e.TELEFONE,
                e.EMAIL,
                e.CNPJ,
                e.CEP,
                e.LOGRADOURO,
                e.NUMERO,
                e.COMPLEMENTO,
                e.BAIRRO,
                e.CIDADE,
                e.ESTADO,
                e.DATA_CADASTRO,

                ae.STATUS,
                ae.ATIVO

            FROM ESCRITORIOS e

            INNER JOIN ADVOGADO_ESCRITORIO ae
                ON ae.ID_ESCRITORIOS = e.ID_ESCRITORIOS

            WHERE e.ID_ESCRITORIOS = ?
              AND ae.ID_USUARIOS = ?
        """, (
            id_escritorio,
            id_usuario
        ))

        escritorio = cur.fetchone()

        if not escritorio:
            return jsonify({
                'error': 'Escritório não encontrado ou você não possui acesso'
            }), 404

        status_advogado = escritorio[16]
        ativo_advogado = escritorio[17]

        if ativo_advogado != 1:
            return jsonify({
                'error': 'Seu acesso a este escritório está inativo.',
                'escritorio_inativo': True,
                'id_escritorio': id_escritorio
            }), 403

        return jsonify({
            'escritorio': {
                'id': escritorio[0],
                'razao_social': escritorio[1],
                'nome_fantasia': escritorio[2],
                'registro_oab': escritorio[3],
                'uf_oab': escritorio[4],
                'telefone': escritorio[5],
                'email': escritorio[6],
                'cnpj': escritorio[7],
                'cep': escritorio[8],
                'logradouro': escritorio[9],
                'numero': escritorio[10],
                'complemento': escritorio[11],
                'bairro': escritorio[12],
                'cidade': escritorio[13],
                'estado': escritorio[14],

                'data_cadastro': (
                    escritorio[15].strftime(
                        '%d/%m/%Y %H:%M'
                    )
                    if escritorio[15]
                    else None
                ),

                'status': status_advogado,
                'ativo': ativo_advogado == 1
            }
        }), 200

    except Exception as e:
        print(
            f'Erro ao buscar detalhes do escritório: {e}'
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/meus_escritorios', methods=['GET'])
def meus_escritorios():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    id_usuario = token_data['id_usuarios']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                e.ID_ESCRITORIOS,
                e.RAZAO_SOCIAL,
                e.NOME_FANTASIA,
                e.REGISTRO_OAB,
                e.UF_OAB,
                e.TELEFONE,
                e.EMAIL,
                e.CNPJ,
                e.CEP,
                e.LOGRADOURO,
                e.NUMERO,
                e.COMPLEMENTO,
                e.BAIRRO,
                e.CIDADE,
                e.ESTADO,
                e.DATA_CADASTRO,
                ae.STATUS,
                ae.ATIVO
            FROM ESCRITORIOS e

            INNER JOIN ADVOGADO_ESCRITORIO ae
                ON e.ID_ESCRITORIOS =
                   ae.ID_ESCRITORIOS

            WHERE ae.ID_USUARIOS = ?

            ORDER BY
                ae.ATIVO DESC,
                e.ID_ESCRITORIOS DESC
        """, (
            id_usuario,
        ))

        escritorios = cur.fetchall()

        resultado = []

        for escritorio in escritorios:
            resultado.append({
                'id': escritorio[0],
                'razao_social':
                    escritorio[1],
                'nome_fantasia':
                    escritorio[2],
                'registro_oab':
                    escritorio[3],
                'uf_oab':
                    escritorio[4],
                'telefone':
                    escritorio[5],
                'email':
                    escritorio[6],
                'cnpj':
                    escritorio[7],
                'cep':
                    escritorio[8],
                'logradouro':
                    escritorio[9],
                'numero':
                    escritorio[10],
                'complemento':
                    escritorio[11],
                'bairro':
                    escritorio[12],
                'cidade':
                    escritorio[13],
                'estado':
                    escritorio[14],

                'data_cadastro': (
                    escritorio[15].strftime(
                        '%d/%m/%Y %H:%M'
                    )
                    if escritorio[15]
                    else None
                ),

                'status':
                    escritorio[16],

                'ativo':
                    escritorio[17] == 1
            })

        return jsonify({
            'escritorios': resultado
        }), 200

    except Exception as e:
        con.rollback()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/criar_escritorio', methods=['POST'])
def criar_escritorio():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuario = token_data['id_usuarios']

    razao_social = request.form.get('razao_social')
    nome_fantasia = request.form.get('nome_fantasia')
    registro_oab = request.form.get('registro_oab')
    uf_oab = request.form.get('uf_oab')
    telefone = request.form.get('telefone')
    email = request.form.get('email')
    cnpj = request.form.get('cnpj')
    cep = request.form.get('cep')
    logradouro = request.form.get('logradouro')
    numero = request.form.get('numero')
    complemento = request.form.get('complemento')
    bairro = request.form.get('bairro')
    cidade = request.form.get('cidade')
    estado = request.form.get('estado')
    senha = request.form.get('senha')

    if not razao_social or not razao_social.strip():
        return jsonify({"error": "Razão social é obrigatória"}), 400
    if not nome_fantasia or not nome_fantasia.strip():
        return jsonify({"error": "Nome fantasia é obrigatório"}), 400
    if not registro_oab or not registro_oab.strip():
        return jsonify({"error": "Registro na OAB é obrigatório"}), 400
    if not uf_oab or not uf_oab.strip():
        return jsonify({"error": "UF da OAB é obrigatória"}), 400
    if not telefone or not telefone.strip():
        return jsonify({"error": "Telefone é obrigatório"}), 400
    if not email or not email.strip():
        return jsonify({"error": "E-mail é obrigatório"}), 400
    if not cnpj or not cnpj.strip():
        return jsonify({"error": "CNPJ é obrigatório"}), 400
    if not cep or not cep.strip():
        return jsonify({"error": "CEP é obrigatório"}), 400
    if not logradouro or not logradouro.strip():
        return jsonify({"error": "Logradouro é obrigatório"}), 400
    if not bairro or not bairro.strip():
        return jsonify({"error": "Bairro é obrigatório"}), 400
    if not cidade or not cidade.strip():
        return jsonify({"error": "Cidade é obrigatória"}), 400
    if not estado or not estado.strip():
        return jsonify({"error": "Estado é obrigatório"}), 400

    cnpj_numeros = ''.join(filter(str.isdigit, cnpj))
    if len(cnpj_numeros) != 14:
        return jsonify({"error": "CNPJ inválido. Digite os 14 números do CNPJ."}), 400

    telefone_numeros = ''.join(filter(str.isdigit, telefone))
    if len(telefone_numeros) < 10 or len(telefone_numeros) > 11:
        return jsonify({"error": "Telefone inválido. Digite DDD + número."}), 400

    cep_numeros = ''.join(filter(str.isdigit, cep))
    if len(cep_numeros) != 8:
        return jsonify({"error": "CEP inválido. Digite os 8 números do CEP."}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("SELECT ID_ESCRITORIOS FROM ESCRITORIOS WHERE CNPJ = ?", (cnpj_numeros,))
        if cur.fetchone():
            return jsonify({"error": "CNPJ já cadastrado"}), 400

        cur.execute("SELECT ID_ESCRITORIOS FROM ESCRITORIOS WHERE EMAIL = ?", (email,))
        if cur.fetchone():
            return jsonify({"error": "E-mail já cadastrado"}), 400

    except Exception as e:
        return jsonify({"error": f"Erro ao verificar duplicidade: {e}"}), 500
    finally:
        cur.close()
        con.close()

    try:
        print()
        print("========================================")
        print("CONSULTANDO CNSA")
        print(f"UF: {uf_oab}")
        print(f"Registro OAB: {registro_oab}")
        print("========================================")

        inicio_oab = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                consultar_cnsa,
                uf=uf_oab,
                inscricao=registro_oab
            )

            try:
                resultado_cnsa = future.result(timeout=60)
            except concurrent.futures.TimeoutError:
                return jsonify({
                    "error": "A consulta à OAB está demorando muito. Tente novamente mais tarde."
                }), 408

        tempo_oab = time.perf_counter() - inicio_oab
        print(f"[TEMPO] Consulta CNSA finalizada: {tempo_oab:.2f} segundos")
        print("Resultado CNSA:", resultado_cnsa)

    except Exception as e:
        print(f"Erro ao consultar a CNSA: {e}")
        return jsonify({"error": "Erro ao consultar a OAB."}), 500

    if not resultado_cnsa:
        return jsonify({"error": "Não foi possível obter uma resposta da OAB."}), 400

    if resultado_cnsa.get("timeout"):
        return jsonify({"error": "A consulta à OAB demorou muito. Tente novamente."}), 408

    status = resultado_cnsa.get("status")
    if status != 200:
        return jsonify({"error": "Não foi possível validar a inscrição na OAB."}), 400

    dados = resultado_cnsa.get("dados")
    if not dados:
        return jsonify({"error": "A OAB não retornou dados para essa inscrição."}), 400

    if isinstance(dados, str):
        try:
            dados = json.loads(dados)
        except Exception:
            return jsonify({"error": "A resposta da OAB não possui um formato válido."}), 400

    if not isinstance(dados, dict):
        return jsonify({"error": "Resposta inválida recebida da OAB."}), 400

    items = dados.get("items", [])
    if not items:
        mensagem = dados.get("mensagem", "")
        if mensagem:
            return jsonify({"error": mensagem}), 400
        return jsonify({
            "error": f"OAB {uf_oab}-{registro_oab} não encontrada no cadastro da OAB. Verifique se o número e a UF estão corretos."
        }), 400

    inscricao_oab = items[0]
    situacao = inscricao_oab.get("situacao", "")

    if situacao:
        if situacao.strip().upper() != "REGULAR":
            return jsonify({
                "error": f"A inscrição da OAB está com situação {situacao}. Apenas inscrições regulares podem cadastrar um escritório."
            }), 400

    print()
    print("========================================")
    print("OAB VALIDADA COM SUCESSO")
    print(f"UF: {uf_oab}")
    print(f"Registro: {registro_oab}")
    if situacao:
        print(f"Situação: {situacao}")
    print("========================================")

    senha_cripto = None
    if senha:
        if senha_forte(senha) == False:
            return jsonify({
                "error": "Senha fraca. Use 8+ caracteres, maiúsculas, minúsculas, números e especiais"
            }), 400
        senha_cripto = generate_password_hash(senha).decode('utf-8')

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
                    INSERT INTO ESCRITORIOS (RAZAO_SOCIAL,
                                             NOME_FANTASIA,
                                             REGISTRO_OAB,
                                             UF_OAB,
                                             TELEFONE,
                                             EMAIL,
                                             CNPJ,
                                             CEP,
                                             LOGRADOURO,
                                             NUMERO,
                                             COMPLEMENTO,
                                             BAIRRO,
                                             CIDADE,
                                             ESTADO,
                                             SENHA,
                                             DATA_CADASTRO)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING ID_ESCRITORIOS
                    """, (
            razao_social.strip(),
            nome_fantasia.strip(),
            registro_oab.strip(),
            uf_oab.strip().upper(),
            telefone_numeros,
            email.strip(),
            cnpj_numeros,
            cep_numeros,
            logradouro.strip(),
            numero,
            complemento,
            bairro.strip(),
            cidade.strip(),
            estado.strip().upper(),
            senha_cripto,
            datetime.datetime.now()
        ))

        id_escritorio = cur.fetchone()[0]

        cur.execute("""
                    INSERT INTO ADVOGADO_ESCRITORIO (ID_USUARIOS,
                                                     ID_ESCRITORIOS,
                                                     STATUS)
                    VALUES (?, ?, ?)
                    """, (
            id_usuario,
            id_escritorio,
            'PROPRIETARIO'
        ))

        con.commit()

        print(f"✅ Escritório cadastrado. ID: {id_escritorio}")
        print(f"✅ Advogado {id_usuario} vinculado como PROPRIETARIO")

        foto_perfil = request.files.get('foto_perfil')
        if foto_perfil:
            try:
                nome_imagem = f'escritorio_{id_escritorio}.jpeg'
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'Escritorios')
                os.makedirs(caminho, exist_ok=True)
                foto_perfil.save(os.path.join(caminho, nome_imagem))
                print(f"✅ Imagem salva: {nome_imagem}")
            except Exception as e:
                print(f"⚠️ Erro ao salvar imagem: {e}")

        return jsonify({
            'message': 'Escritório cadastrado com sucesso!',
            'id_escritorio': id_escritorio
        }), 201

    except Exception as e:
        con.rollback()
        print(f"Erro ao cadastrar escritório: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Erro interno: {e}'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/adicionar_advogado_escritorio', methods=['POST'])
def adicionar_advogado_escritorio():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'sucesso': False,
            'mensagem': 'Token necessário.'
        }), 401

    id_usuario_logado = token_data['id_usuarios']
    tipo_usuario_logado = token_data['tipo']

    if tipo_usuario_logado != 0:
        return jsonify({
            'sucesso': False,
            'mensagem': 'Apenas advogados podem realizar esta ação.'
        }), 403

    dados = request.get_json()

    if not dados:
        return jsonify({
            'sucesso': False,
            'mensagem': 'Dados não enviados.'
        }), 400

    email = dados.get('email')
    status = dados.get('status')
    id_escritorio = dados.get('id_escritorio')

    if not email:
        return jsonify({
            'sucesso': False,
            'mensagem': 'Informe o e-mail do advogado.'
        }), 400

    if not status:
        return jsonify({
            'sucesso': False,
            'mensagem': 'Informe a posição do advogado.'
        }), 400

    if not id_escritorio:
        return jsonify({
            'sucesso': False,
            'mensagem': 'Escritório não informado.'
        }), 400

    email = email.strip()
    status = status.strip().upper()

    if status not in [
        'PROPRIETARIO',
        'PARCEIRO',
        'ASSOCIADO'
    ]:
        return jsonify({
            'sucesso': False,
            'mensagem':
                'A posição deve ser PROPRIETARIO, PARCEIRO ou ASSOCIADO.'
        }), 400

    try:
        id_escritorio = int(id_escritorio)

    except (ValueError, TypeError):
        return jsonify({
            'sucesso': False,
            'mensagem': 'ID do escritório inválido.'
        }), 400

    conexao_db = None
    cursor = None

    try:
        conexao_db = conexao()
        cursor = conexao_db.cursor()

        cursor.execute("""
            SELECT
                ID,
                STATUS,
                ATIVO
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_usuario_logado,
            id_escritorio
        ))

        vinculo_usuario = cursor.fetchone()

        if not vinculo_usuario:
            return jsonify({
                'sucesso': False,
                'mensagem':
                    'Você não possui acesso a este escritório.'
            }), 403

        status_usuario = vinculo_usuario[1]
        ativo_usuario = vinculo_usuario[2]

        if ativo_usuario != 1:
            return jsonify({
                'sucesso': False,
                'mensagem':
                    'Seu acesso a este escritório está inativo.',
                'escritorio_inativo': True
            }), 403

        if (
                not status_usuario
                or status_usuario.upper() != 'PROPRIETARIO'
        ):
            return jsonify({
                'sucesso': False,
                'mensagem':
                    'Somente proprietários podem adicionar advogados ao escritório.'
            }), 403

        cursor.execute("""
            SELECT
                ID_ESCRITORIOS,
                NOME_FANTASIA,
                RAZAO_SOCIAL
            FROM ESCRITORIOS
            WHERE ID_ESCRITORIOS = ?
        """, (
            id_escritorio,
        ))

        escritorio_dados = cursor.fetchone()

        if not escritorio_dados:
            return jsonify({
                'sucesso': False,
                'mensagem': 'Escritório não encontrado.'
            }), 404

        nome_escritorio = (
                escritorio_dados[1]
                or escritorio_dados[2]
                or 'Escritório'
        )

        cursor.execute("""
            SELECT
                ID_USUARIOS,
                NOME,
                EMAIL,
                TIPO,
                ATIVO
            FROM USUARIOS
            WHERE UPPER(EMAIL) = UPPER(?)
        """, (
            email,
        ))

        advogado = cursor.fetchone()

        if not advogado:
            return jsonify({
                'sucesso': False,
                'mensagem':
                    'Não foi encontrado nenhum usuário cadastrado com esse e-mail.'
            }), 404

        id_advogado = advogado[0]
        nome_advogado = advogado[1]
        email_advogado = advogado[2]
        tipo_usuario = advogado[3]
        ativo_usuario_sistema = advogado[4]

        if tipo_usuario != 0:
            return jsonify({
                'sucesso': False,
                'mensagem':
                    'O usuário informado não é um advogado.'
            }), 400

        if ativo_usuario_sistema != 1:
            return jsonify({
                'sucesso': False,
                'mensagem':
                    'Este advogado está inativo no sistema.'
            }), 400

        if id_advogado == id_usuario_logado:
            return jsonify({
                'sucesso': False,
                'mensagem':
                    'Você não pode adicionar a si mesmo ao escritório.'
            }), 400

        cursor.execute("""
            SELECT
                ID,
                STATUS,
                ATIVO
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_advogado,
            id_escritorio
        ))

        vinculo = cursor.fetchone()

        if vinculo:
            if vinculo[2] == 0:
                return jsonify({
                    'sucesso': False,
                    'mensagem':
                        'Este advogado já está vinculado a este escritório, mas está inativo. Reative o vínculo em vez de adicioná-lo novamente.'
                }), 400

            return jsonify({
                'sucesso': False,
                'mensagem':
                    'Este advogado já está vinculado a este escritório.'
            }), 400

        cursor.execute("""
            INSERT INTO ADVOGADO_ESCRITORIO (
                ID_USUARIOS,
                ID_ESCRITORIOS,
                STATUS,
                ATIVO
            )
            VALUES (?, ?, ?, ?)
        """, (
            id_advogado,
            id_escritorio,
            status,
            1
        ))

        titulo_notificacao = 'Adicionado ao escritório'

        mensagem_notificacao = (
            f'Você foi adicionado ao escritório {nome_escritorio} '
            f'como {status.lower().capitalize()}.'
        )

        cursor.execute("""
            INSERT INTO NOTIFICACOES (
                ID_USUARIOS,
                TIPO,
                TITULO,
                MENSAGEM
            )
            VALUES (?, ?, ?, ?)
            RETURNING ID_NOTIFICACAO
        """, (
            id_advogado,
            'ADVOGADO_ADICIONADO_ESCRITORIO',
            titulo_notificacao,
            mensagem_notificacao
        ))

        id_notificacao = cursor.fetchone()[0]

        conexao_db.commit()

        agora = datetime.datetime.now()

        notificacao = {
            'id': id_notificacao,
            'tipo': 'ADVOGADO_ADICIONADO_ESCRITORIO',
            'titulo': titulo_notificacao,
            'mensagem': mensagem_notificacao,
            'lida': False,
            'data_criacao': agora.isoformat(),
            'data_leitura': None,
            'id_advogado': id_advogado,
            'nome_advogado': nome_advogado,
            'id_escritorio': id_escritorio,
            'nome_escritorio': nome_escritorio,
            'status': status
        }

        socketio.emit(
            'nova_notificacao',
            notificacao,
            room=f'usuario_{id_advogado}'
        )

        try:
            enviar_email(
                email_advogado,
                'Convite para escritório - Constituere',
                nome_escritorio,
                nome_advogado
            )

        except Exception as e:
            print(
                f'Erro ao enviar e-mail para o advogado: {e}'
            )

        return jsonify({
            'sucesso': True,
            'mensagem':
                'Advogado adicionado ao escritório com sucesso.',
            'advogado': {
                'id': id_advogado,
                'nome': nome_advogado,
                'email': email_advogado,
                'status': status,
                'ativo': True
            },
            'escritorio': {
                'id': id_escritorio,
                'nome': nome_escritorio
            }
        }), 200

    except Exception as e:
        if conexao_db:
            try:
                conexao_db.rollback()
            except Exception:
                pass

        print(
            f'Erro ao adicionar advogado ao escritório: {e}'
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'sucesso': False,
            'mensagem':
                f'Erro ao adicionar advogado: {str(e)}'
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conexao_db:
            conexao_db.close()


@app.route('/representante', methods=['POST'])
def criar_representante():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    if tipo_usuario not in [0, 1]:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json()

    id_cliente = dados.get('id_cliente')
    nome_completo = dados.get('nome_completo')
    profissao = dados.get('profissao')
    cpf = dados.get('cpf')
    sexo = dados.get('sexo')
    rg = dados.get('rg')
    orgao_expedidor = dados.get('orgao_expedidor')
    nacionalidade = dados.get('nacionalidade')
    estado_civil = dados.get('estado_civil')

    if not id_cliente:
        return jsonify({'error': 'ID do cliente é obrigatório'}), 400
    if not nome_completo or not nome_completo.strip():
        return jsonify({'error': 'Nome completo é obrigatório'}), 400
    if not cpf:
        return jsonify({'error': 'CPF é obrigatório'}), 400
    if not validar_cpf(cpf):
        return jsonify({'error': 'CPF inválido'}), 400
    if not sexo:
        return jsonify({'error': 'Sexo é obrigatório'}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE ID_USUARIOS = ? AND TIPO = 3", (id_cliente,))
        if not cur.fetchone():
            return jsonify({'error': 'Cliente jurídico não encontrado'}), 404

        cur.execute("SELECT ID_REPRESENTANTE FROM REPRESENTANTES WHERE CPF = ? AND ID_CLIENTE_JURIDICO = ?",
                    (cpf, id_cliente))
        if cur.fetchone():
            return jsonify({'error': 'Este CPF já está cadastrado como representante para este cliente'}), 400

        cur.execute("""
            INSERT INTO REPRESENTANTES
            (ID_CLIENTE_JURIDICO, NOME_COMPLETO, PROFISSAO, CPF, SEXO, RG, ORGAO_EXPEDIDOR, NACIONALIDADE, ESTADO_CIVIL)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID_REPRESENTANTE
        """, (
            id_cliente,
            nome_completo.strip(),
            profissao.strip() if profissao else None,
            cpf,
            sexo,
            rg.strip() if rg else None,
            orgao_expedidor.strip() if orgao_expedidor else None,
            nacionalidade.strip() if nacionalidade else None,
            estado_civil.strip() if estado_civil else None
        ))

        id_representante = cur.fetchone()[0]
        con.commit()

        return jsonify({
            'mensagem': 'Representante cadastrado com sucesso!',
            'id_representante': id_representante
        }), 201

    except Exception as e:
        con.rollback()
        return jsonify({'error': f'Erro ao cadastrar representante: {str(e)}'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/clientes', methods=['GET'])
def listar_clientes():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    if tipo_usuario not in [0, 1]:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    id_usuario = token_data['id_usuarios']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
                    SELECT
                        u.ID_USUARIOS,
                        u.NOME,
                        u.CPF,
                        u.EMAIL,
                        u.TELEFONE,
                        u.TIPO,
                        u.ATIVO,
                        u.RAZAO_SOCIAL,
                        u.NOME_FANTASIA,
                        u.CNPJ,
                        u.DATA_CADASTRO
                    FROM USUARIOS u
                    WHERE u.TIPO IN (2, 3)
                      AND u.ID_USUARIO_RESPONSAVEL = ?
                    ORDER BY u.DATA_CADASTRO DESC
                    """, (id_usuario,))

        rows = cur.fetchall()

        ids_clientes = [row[0] for row in rows]

        status_por_cliente = {}
        tem_parcela_por_cliente = {}

        if ids_clientes:
            try:
                placeholders = ','.join(['?'] * len(ids_clientes))

                sql_parcelas = f"""
                    SELECT
                        p.ID_USUARIOS_CLIENTE,
                        parc.DATA_VENCIMENTO,
                        parc.STATUS
                    FROM PARCELAS parc
                    INNER JOIN PAGAMENTOS pag ON parc.ID_PAGAMENTO = pag.ID_PAGAMENTOS
                    INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
                    WHERE p.ID_USUARIOS_CLIENTE IN ({placeholders})

                    UNION ALL

                    SELECT
                        p.ID_USUARIOS_CLIENTE,
                        pe.DATA_VENCIMENTO,
                        pe.STATUS
                    FROM PARCELAS_EXITO pe
                    INNER JOIN PAGAMENTO_EXITO pex ON pe.ID_PAGAMENTO_EXITO = pex.ID_PAGAMENTO_EXITO
                    INNER JOIN PAGAMENTOS pag ON pex.ID_PAGAMENTO = pag.ID_PAGAMENTOS
                    INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
                    WHERE p.ID_USUARIOS_CLIENTE IN ({placeholders})
                """

                cur.execute(
                    sql_parcelas,
                    tuple(ids_clientes) + tuple(ids_clientes)
                )
                parcelas = cur.fetchall()

                hoje = datetime.date.today()
                limite_proximo = hoje + datetime.timedelta(days=7)

                for id_cliente, data_venc_raw, status_parcela in parcelas:
                    tem_parcela_por_cliente[id_cliente] = True

                    data_venc = converter_data_pagamento(data_venc_raw)

                    if not data_venc:
                        continue

                    status_parcela = (status_parcela or '').upper()

                    if status_parcela == 'PAGA':
                        continue

                    status_atual = status_por_cliente.get(id_cliente, 'em_dia')

                    if data_venc < hoje:
                        status_por_cliente[id_cliente] = 'inadimplente'
                    elif data_venc <= limite_proximo:
                        if status_atual != 'inadimplente':
                            status_por_cliente[id_cliente] = 'proximo_vencimento'

            except Exception as erro_parcelas:
                print("Aviso: nao foi possivel calcular status financeiro:", erro_parcelas)
                import traceback
                traceback.print_exc()

        clientes = []
        for row in rows:
            id_cliente = row[0]

            nome_exibicao = row[1] if row[1] else (row[7] or row[8] or '--')
            doc = row[2] if row[2] else (row[9] if row[9] else '--')

            if doc and doc != '--':
                if len(doc) == 11:
                    doc = f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
                elif len(doc) == 14:
                    doc = f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"

            if row[6] == 1:
                status = 'ativo'
            else:
                status = 'inativo'

            if row[6] == 0:
                status_financeiro = 'inativo'
            else:
                if not tem_parcela_por_cliente:
                    status_financeiro = 'em_dia'
                elif id_cliente not in tem_parcela_por_cliente:
                    status_financeiro = 'sem_parcelas'
                else:
                    status_financeiro = status_por_cliente.get(id_cliente, 'em_dia')

            data_cadastro = None
            if row[10]:
                if hasattr(row[10], 'strftime'):
                    data_cadastro = row[10].strftime('%d/%m/%Y')
                else:
                    data_cadastro = str(row[10])

            clientes.append({
                'id': id_cliente,
                'nome': nome_exibicao,
                'cpf': doc,
                'email': row[3] or '--',
                'telefone': row[4] or '--',
                'tipo': 'fisico' if row[5] == 2 else 'juridico',
                'status': status,
                'status_financeiro': status_financeiro,
                'data_cadastro': data_cadastro
            })

        return jsonify({'clientes': clientes}), 200

    except Exception as e:
        print(f"Erro ao listar clientes: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/cliente/<int:id_cliente>', methods=['GET'])
def buscar_cliente(id_cliente):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    if tipo_usuario not in [0, 1]:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    id_usuario = token_data['id_usuarios']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                ID_USUARIOS, NOME, CPF, EMAIL, TELEFONE,
                TIPO, ATIVO, RAZAO_SOCIAL, NOME_FANTASIA,
                CNPJ, DATA_CADASTRO,
                RG, ORGAO_EXPEDIDOR, NACIONALIDADE,
                ESTADO_CIVIL, PROFISSAO, CEP, LOGRADOURO,
                NUMERO, COMPLEMENTO, BAIRRO, CIDADE, ESTADO,
                SEXO, DATA_NASCIMENTO, CARTERA_TRABALHO,
                SERIE_CARTERA, ID_USUARIO_RESPONSAVEL
            FROM USUARIOS
            WHERE ID_USUARIOS = ? AND TIPO IN (2, 3)
        """, (id_cliente,))

        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Cliente não encontrado'}), 404

        if row[27] != id_usuario:
            return jsonify({'error': 'Você não tem permissão para acessar este cliente'}), 403

        cliente = {
            'id': row[0],
            'nome': row[1] or '',
            'cpf': row[2] or '',
            'email': row[3] if row[3] and row[3] != '--' else '',
            'telefone': row[4] or '',
            'tipo': 'fisico' if row[5] == 2 else 'juridico',
            'status': 'ativo' if row[6] == 1 else 'inativo',
            'razao_social': row[7] or '',
            'nome_fantasia': row[8] or '',
            'cnpj': row[9] or '',
            'data_cadastro': (
                row[10].strftime('%d/%m/%Y') if hasattr(row[10], 'strftime') else (str(row[10]) if row[10] else None)),
            'rg': row[11] or '',
            'orgao_expedidor': row[12] or '',
            'nacionalidade': row[13] or '',
            'estado_civil': row[14] or '',
            'profissao': row[15] or '',
            'cep': row[16] or '',
            'logradouro': row[17] or '',
            'numero': row[18] or '',
            'complemento': row[19] or '',
            'bairro': row[20] or '',
            'cidade': row[21] or '',
            'estado': row[22] or '',
            'sexo': row[23] or '',
            'data_nascimento': (
                row[24].strftime('%d/%m/%Y') if hasattr(row[24], 'strftime') else (str(row[24]) if row[24] else '')),
            'carteira_trabalho': row[25] or '',
            'serie_carteira': row[26] or ''
        }

        if cliente['tipo'] == 'juridico':
            cur.execute("""
                SELECT
                    ID_REPRESENTANTE,
                    NOME_COMPLETO, PROFISSAO, CPF, SEXO,
                    RG, ORGAO_EXPEDIDOR, NACIONALIDADE, ESTADO_CIVIL
                FROM REPRESENTANTES
                WHERE ID_CLIENTE_JURIDICO = ? AND ATIVO = 1
            """, (id_cliente,))
            rep = cur.fetchone()
            if rep:
                cliente['representante'] = {
                    'id': rep[0],
                    'nome': rep[1] or '',
                    'profissao': rep[2] or '',
                    'cpf': rep[3] or '',
                    'sexo': rep[4] or '',
                    'rg': rep[5] or '',
                    'orgao_expedidor': rep[6] or '',
                    'nacionalidade': rep[7] or '',
                    'estado_civil': rep[8] or ''
                }

        return jsonify({'cliente': cliente}), 200

    except Exception as e:
        print(f"Erro ao buscar cliente: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/cliente/<int:id_cliente>', methods=['PUT'])
def atualizar_cliente(id_cliente):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    if tipo_usuario not in [0, 1]:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    id_usuario = token_data['id_usuarios']
    dados = request.get_json()

    if not dados:
        return jsonify({'error': 'Dados não enviados'}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_USUARIOS, TIPO,
                   NOME, RAZAO_SOCIAL, NOME_FANTASIA, CPF, CNPJ,
                   EMAIL, TELEFONE, DATA_NASCIMENTO, SEXO, RG,
                   ORGAO_EXPEDIDOR, CARTERA_TRABALHO, SERIE_CARTERA,
                   PROFISSAO, ESTADO_CIVIL, NACIONALIDADE, CEP,
                   LOGRADOURO, NUMERO, COMPLEMENTO, BAIRRO, CIDADE, ESTADO
            FROM USUARIOS
            WHERE ID_USUARIOS = ?
              AND TIPO IN (2, 3)
              AND ID_USUARIO_RESPONSAVEL = ?
        """, (id_cliente, id_usuario))

        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Cliente não encontrado ou não pertence a você'}), 404

        tipo_cliente = row[1]
        valores_atuais = dict(zip((
            'nome', 'razao_social', 'nome_fantasia', 'cpf', 'cnpj',
            'email', 'telefone', 'data_nascimento', 'sexo', 'rg',
            'orgao_expedidor', 'carteira_trabalho', 'serie_carteira',
            'profissao', 'estado_civil', 'nacionalidade', 'cep',
            'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'estado'
        ), row[2:]))

        def valor_atualizado(campo):
            if campo not in dados or dados.get(campo) in (None, ''):
                return valores_atuais[campo]
            return dados.get(campo)

        if tipo_cliente == 2:
            cpf = dados.get('cpf')
            if cpf:
                cpf_limpo = ''.join(filter(str.isdigit, cpf))
                if len(cpf_limpo) != 11:
                    return jsonify({'error': 'CPF inválido'}), 400
                cur.execute("""
                    SELECT ID_USUARIOS FROM USUARIOS
                    WHERE CPF = ? AND ID_USUARIOS != ?
                """, (cpf_limpo, id_cliente))
                if cur.fetchone():
                    return jsonify({'error': 'CPF já cadastrado para outro usuário'}), 400

        if tipo_cliente == 3:
            cnpj = dados.get('cnpj')
            if cnpj:
                cnpj_limpo = ''.join(filter(str.isdigit, cnpj))
                if len(cnpj_limpo) != 14:
                    return jsonify({'error': 'CNPJ inválido'}), 400
                cur.execute("""
                    SELECT ID_USUARIOS FROM USUARIOS
                    WHERE CNPJ = ? AND ID_USUARIOS != ?
                """, (cnpj_limpo, id_cliente))
                if cur.fetchone():
                    return jsonify({'error': 'CNPJ já cadastrado para outro usuário'}), 400

        email = dados.get('email')
        if email:
            cur.execute("""
                SELECT ID_USUARIOS FROM USUARIOS
                WHERE EMAIL = ? AND ID_USUARIOS != ?
            """, (email, id_cliente))
            if cur.fetchone():
                return jsonify({'error': 'E-mail já cadastrado para outro usuário'}), 400

        data_nasc = valor_atualizado('data_nascimento')

        cur.execute("""
            UPDATE USUARIOS SET
                NOME = ?,
                RAZAO_SOCIAL = ?,
                NOME_FANTASIA = ?,
                CPF = ?,
                CNPJ = ?,
                EMAIL = ?,
                TELEFONE = ?,
                DATA_NASCIMENTO = ?,
                SEXO = ?,
                RG = ?,
                ORGAO_EXPEDIDOR = ?,
                CARTERA_TRABALHO = ?,
                SERIE_CARTERA = ?,
                PROFISSAO = ?,
                ESTADO_CIVIL = ?,
                NACIONALIDADE = ?,
                CEP = ?,
                LOGRADOURO = ?,
                NUMERO = ?,
                COMPLEMENTO = ?,
                BAIRRO = ?,
                CIDADE = ?,
                ESTADO = ?
            WHERE ID_USUARIOS = ?
        """, (
            valor_atualizado('nome'),
            valor_atualizado('razao_social'),
            valor_atualizado('nome_fantasia'),
            valor_atualizado('cpf'),
            valor_atualizado('cnpj'),
            valor_atualizado('email'),
            valor_atualizado('telefone'),
            data_nasc,
            valor_atualizado('sexo'),
            valor_atualizado('rg'),
            valor_atualizado('orgao_expedidor'),
            valor_atualizado('carteira_trabalho'),
            valor_atualizado('serie_carteira'),
            valor_atualizado('profissao'),
            valor_atualizado('estado_civil'),
            valor_atualizado('nacionalidade'),
            valor_atualizado('cep'),
            valor_atualizado('logradouro'),
            valor_atualizado('numero'),
            valor_atualizado('complemento'),
            valor_atualizado('bairro'),
            valor_atualizado('cidade'),
            valor_atualizado('estado'),
            id_cliente
        ))

        if tipo_cliente == 3:
            representante = dados.get('representante')
            if representante:
                cur.execute("""
                    SELECT ID_REPRESENTANTE
                    FROM REPRESENTANTES
                    WHERE ID_CLIENTE_JURIDICO = ? AND ATIVO = 1
                """, (id_cliente,))
                existe = cur.fetchone()

                if existe:
                    cur.execute("""
                        UPDATE REPRESENTANTES SET
                            NOME_COMPLETO = ?,
                            PROFISSAO = ?,
                            CPF = ?,
                            SEXO = ?,
                            RG = ?,
                            ORGAO_EXPEDIDOR = ?,
                            NACIONALIDADE = ?,
                            ESTADO_CIVIL = ?
                        WHERE ID_REPRESENTANTE = ?
                    """, (
                        representante.get('nome'),
                        representante.get('profissao'),
                        representante.get('cpf'),
                        representante.get('sexo'),
                        representante.get('rg'),
                        representante.get('orgao_expedidor'),
                        representante.get('nacionalidade'),
                        representante.get('estado_civil'),
                        existe[0]
                    ))
                else:
                    if representante.get('nome') and representante.get('cpf'):
                        cur.execute("""
                            INSERT INTO REPRESENTANTES
                            (ID_CLIENTE_JURIDICO, NOME_COMPLETO, PROFISSAO, CPF, SEXO,
                             RG, ORGAO_EXPEDIDOR, NACIONALIDADE, ESTADO_CIVIL, ATIVO)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """, (
                            id_cliente,
                            representante.get('nome'),
                            representante.get('profissao'),
                            representante.get('cpf'),
                            representante.get('sexo'),
                            representante.get('rg'),
                            representante.get('orgao_expedidor'),
                            representante.get('nacionalidade'),
                            representante.get('estado_civil')
                        ))

        con.commit()
        return jsonify({'mensagem': 'Cliente atualizado com sucesso!'}), 200

    except Exception as e:
        con.rollback()
        print(f"Erro ao atualizar cliente: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/cliente/<int:id_cliente>/inativar', methods=['PUT'])
def inativar_cliente(id_cliente):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    if tipo_usuario not in [0, 1]:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE ID_USUARIOS = ?", (id_cliente,))
        if not cur.fetchone():
            return jsonify({'error': 'Cliente não encontrado'}), 404

        cur.execute("""
            UPDATE USUARIOS
            SET ATIVO = 0
            WHERE ID_USUARIOS = ?
        """, (id_cliente,))

        con.commit()
        return jsonify({'message': 'Cliente inativado com sucesso!'}), 200

    except Exception as e:
        con.rollback()
        print(f"Erro ao inativar cliente: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/cliente/<int:id_cliente>/ativar', methods=['PUT'])
def ativar_cliente(id_cliente):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    if tipo_usuario not in [0, 1]:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE ID_USUARIOS = ?", (id_cliente,))
        if not cur.fetchone():
            return jsonify({'error': 'Cliente não encontrado'}), 404

        cur.execute("""
            UPDATE USUARIOS
            SET ATIVO = 1
            WHERE ID_USUARIOS = ?
        """, (id_cliente,))

        con.commit()
        return jsonify({'message': 'Cliente ativado com sucesso!'}), 200

    except Exception as e:
        con.rollback()
        print(f"Erro ao ativar cliente: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/editar_escritorio', methods=['PUT'])
def editar_escritorio():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuario = token_data['id_usuarios']
    tipo_usuario = token_data['tipo']

    if tipo_usuario != 0:
        return jsonify({'error': 'Apenas advogados podem editar escritório'}), 403

    razao_social = request.form.get('razao_social')
    nome_fantasia = request.form.get('nome_fantasia')
    registro_oab = request.form.get('registro_oab')
    uf_oab = request.form.get('uf_oab')
    telefone = request.form.get('telefone')
    email = request.form.get('email')
    cnpj = request.form.get('cnpj')
    cep = request.form.get('cep')
    logradouro = request.form.get('logradouro')
    numero = request.form.get('numero')
    complemento = request.form.get('complemento')
    bairro = request.form.get('bairro')
    cidade = request.form.get('cidade')
    estado = request.form.get('estado')

    if not razao_social or not razao_social.strip():
        return jsonify({"error": "Razão social é obrigatória"}), 400
    if not nome_fantasia or not nome_fantasia.strip():
        return jsonify({"error": "Nome fantasia é obrigatório"}), 400
    if not registro_oab or not registro_oab.strip():
        return jsonify({"error": "Registro OAB é obrigatório"}), 400
    if not uf_oab or not uf_oab.strip():
        return jsonify({"error": "UF da OAB é obrigatória"}), 400
    if not telefone or not telefone.strip():
        return jsonify({"error": "Telefone é obrigatório"}), 400
    if not email or not email.strip():
        return jsonify({"error": "E-mail é obrigatório"}), 400
    if not cnpj or not cnpj.strip():
        return jsonify({"error": "CNPJ é obrigatório"}), 400
    if not cep or not cep.strip():
        return jsonify({"error": "CEP é obrigatório"}), 400
    if not logradouro or not logradouro.strip():
        return jsonify({"error": "Logradouro é obrigatório"}), 400
    if not bairro or not bairro.strip():
        return jsonify({"error": "Bairro é obrigatório"}), 400
    if not cidade or not cidade.strip():
        return jsonify({"error": "Cidade é obrigatória"}), 400
    if not estado or not estado.strip():
        return jsonify({"error": "Estado é obrigatório"}), 400

    cnpj_numeros = ''.join(filter(str.isdigit, cnpj))
    if len(cnpj_numeros) != 14:
        return jsonify({"error": "CNPJ inválido"}), 400

    telefone_numeros = ''.join(filter(str.isdigit, telefone))
    if len(telefone_numeros) < 10 or len(telefone_numeros) > 11:
        return jsonify({"error": "Telefone inválido"}), 400

    cep_numeros = ''.join(filter(str.isdigit, cep))
    if len(cep_numeros) != 8:
        return jsonify({"error": "CEP inválido"}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_ESCRITORIOS
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ? AND STATUS = 'PROPRIETARIO' AND ATIVO = 1
        """, (id_usuario,))
        escritorio = cur.fetchone()
        if not escritorio:
            return jsonify({'error': 'Nenhum escritório encontrado para edição'}), 404

        id_escritorio = escritorio[0]

        cur.execute("SELECT ID_ESCRITORIOS FROM ESCRITORIOS WHERE CNPJ = ? AND ID_ESCRITORIOS != ?",
                    (cnpj_numeros, id_escritorio))
        if cur.fetchone():
            return jsonify({"error": "CNPJ já cadastrado em outro escritório"}), 400

        cur.execute("SELECT ID_ESCRITORIOS FROM ESCRITORIOS WHERE EMAIL = ? AND ID_ESCRITORIOS != ?",
                    (email, id_escritorio))
        if cur.fetchone():
            return jsonify({"error": "E-mail já cadastrado em outro escritório"}), 400

        cur.execute("""
            UPDATE ESCRITORIOS
            SET RAZAO_SOCIAL = ?,
                NOME_FANTASIA = ?,
                REGISTRO_OAB = ?,
                UF_OAB = ?,
                TELEFONE = ?,
                EMAIL = ?,
                CNPJ = ?,
                CEP = ?,
                LOGRADOURO = ?,
                NUMERO = ?,
                COMPLEMENTO = ?,
                BAIRRO = ?,
                CIDADE = ?,
                ESTADO = ?
            WHERE ID_ESCRITORIOS = ?
        """, (
            razao_social.strip(),
            nome_fantasia.strip(),
            registro_oab.strip(),
            uf_oab.strip().upper(),
            telefone_numeros,
            email.strip(),
            cnpj_numeros,
            cep_numeros,
            logradouro.strip(),
            numero,
            complemento,
            bairro.strip(),
            cidade.strip(),
            estado.strip().upper(),
            id_escritorio
        ))

        con.commit()

        foto_perfil = request.files.get('foto_perfil')
        if foto_perfil:
            try:
                nome_imagem = f'escritorio_{id_escritorio}.jpeg'
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'Escritorios')
                os.makedirs(caminho, exist_ok=True)
                foto_perfil.save(os.path.join(caminho, nome_imagem))
            except Exception as e:
                print(f"Erro ao salvar imagem: {e}")

        return jsonify({'message': 'Escritório atualizado com sucesso!'}), 200

    except Exception as e:
        con.rollback()
        print(f"Erro ao editar escritório: {e}")
        return jsonify({'error': f'Erro interno: {e}'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/meu_escritorio', methods=['GET'])
def meu_escritorio():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuario = token_data['id_usuarios']
    tipo_usuario = token_data['tipo']

    if tipo_usuario != 0:
        return jsonify({'error': 'Apenas advogados podem acessar esta rota'}), 403

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
                    SELECT FIRST 1 ID_ESCRITORIOS
                    FROM ADVOGADO_ESCRITORIO
                    WHERE ID_USUARIOS = ? AND ATIVO = 1
                    ORDER BY CASE WHEN STATUS = 'PROPRIETARIO' THEN 0 ELSE 1
                    END
                    """, (id_usuario,))

        escritorio = cur.fetchone()

        if not escritorio:
            return jsonify({'error': 'Nenhum escritório ativo encontrado'}), 404

        id_escritorio = escritorio[0]

        cur.execute("""
                    SELECT ID_ESCRITORIOS,
                           RAZAO_SOCIAL,
                           NOME_FANTASIA,
                           REGISTRO_OAB,
                           UF_OAB,
                           TELEFONE,
                           EMAIL,
                           CNPJ,
                           CEP,
                           LOGRADOURO,
                           NUMERO,
                           COMPLEMENTO,
                           BAIRRO,
                           CIDADE,
                           ESTADO,
                           DATA_CADASTRO
                    FROM ESCRITORIOS
                    WHERE ID_ESCRITORIOS = ?
                    """, (id_escritorio,))

        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Escritório não encontrado'}), 404

        escritorio_data = {
            'id': row[0],
            'razao_social': row[1],
            'nome_fantasia': row[2],
            'registro_oab': row[3],
            'uf_oab': row[4],
            'telefone': row[5],
            'email': row[6],
            'cnpj': row[7],
            'cep': row[8],
            'logradouro': row[9],
            'numero': row[10],
            'complemento': row[11],
            'bairro': row[12],
            'cidade': row[13],
            'estado': row[14],
            'data_cadastro': row[15].strftime('%d/%m/%Y') if row[15] else None
        }

        return jsonify({'escritorio': escritorio_data}), 200

    except Exception as e:
        print(f"Erro ao buscar escritório: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/listar_advogados', methods=['GET'])
def listar_advogados():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    id_usuario_logado = token_data['id_usuarios']

    id_escritorio = request.args.get('id_escritorio')
    status = request.args.get('status')

    if status:
        status = status.upper()

        if status not in ['PROPRIETARIO', 'PARCEIRO']:
            return jsonify({
                'error': 'Cargo inválido. Use PROPRIETARIO ou PARCEIRO'
            }), 400

    con = conexao()
    cur = con.cursor()

    try:
        if id_escritorio:
            cur.execute("""
                SELECT 1
                FROM ADVOGADO_ESCRITORIO
                WHERE ID_USUARIOS = ?
                  AND ID_ESCRITORIOS = ?
                  AND ATIVO = 1
            """, (
                id_usuario_logado,
                id_escritorio
            ))

            pertence = cur.fetchone()

            if not pertence:
                return jsonify({
                    'error': 'Você não possui acesso ativo a este escritório'
                }), 403

        sql = """
            SELECT
                u.ID_USUARIOS,
                u.NOME,
                u.EMAIL,
                u.NUM_OAB,
                u.UF_OAB,

                e.ID_ESCRITORIOS,
                e.NOME_FANTASIA,
                e.RAZAO_SOCIAL,

                ae.STATUS,
                ae.ATIVO,

                ae_logado.STATUS,
                ae_logado.ATIVO,
                u.AREA_ATUACAO

            FROM ADVOGADO_ESCRITORIO ae

            INNER JOIN USUARIOS u
                ON u.ID_USUARIOS = ae.ID_USUARIOS

            INNER JOIN ESCRITORIOS e
                ON e.ID_ESCRITORIOS = ae.ID_ESCRITORIOS

            INNER JOIN ADVOGADO_ESCRITORIO ae_logado
                ON ae_logado.ID_ESCRITORIOS = ae.ID_ESCRITORIOS
               AND ae_logado.ID_USUARIOS = ?

            WHERE
                u.TIPO = 0
                AND u.ID_USUARIOS <> ?
        """

        parametros = [
            id_usuario_logado,
            id_usuario_logado
        ]

        if id_escritorio:
            sql += """
                AND ae.ID_ESCRITORIOS = ?
            """
            parametros.append(id_escritorio)

        if status:
            sql += """
                AND UPPER(ae.STATUS) = ?
            """
            parametros.append(status)

        sql += """
            ORDER BY
                u.NOME,
                e.NOME_FANTASIA
        """

        cur.execute(
            sql,
            tuple(parametros)
        )

        rows = cur.fetchall()

        advogados_dict = {}

        for row in rows:
            id_advogado = row[0]

            if id_advogado not in advogados_dict:
                advogados_dict[id_advogado] = {
                    'id': row[0],
                    'nome': row[1] or '--',
                    'email': row[2] or '--',
                    'numero_oab': row[3] or '--',
                    'uf_oab': row[4] or '--',
                    'area_atuacao': row[12] or '--',
                    'oab': (
                        f'{row[3]}/{row[4]}'
                        if row[3] and row[4]
                        else row[3] or '--'
                    ),
                    'escritorios': []
                }

            status_logado = row[10]
            ativo_logado = row[11]

            pode_gerenciar = (
                    status_logado is not None
                    and status_logado.upper() == 'PROPRIETARIO'
                    and ativo_logado == 1
            )

            advogados_dict[
                id_advogado
            ]['escritorios'].append({
                'id': row[5],

                'nome': (
                        row[6]
                        or row[7]
                        or '--'
                ),

                'status': (
                        row[8]
                        or '--'
                ),

                'ativo': (
                        row[9] == 1
                ),

                'pode_gerenciar':
                    pode_gerenciar
            })

        advogados = list(
            advogados_dict.values()
        )

        return jsonify({
            'advogados': advogados,
            'quantidade': len(advogados),

            'filtros': {
                'id_escritorio': (
                    int(id_escritorio)
                    if id_escritorio
                    else None
                ),

                'status': (
                    status
                    if status
                    else None
                )
            }
        }), 200

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/filtro_escritorios_advogados', methods=['GET'])
def filtro_escritorios_advogados():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    id_usuario_logado = token_data['id_usuarios']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                e.ID_ESCRITORIOS,
                e.NOME_FANTASIA,
                e.RAZAO_SOCIAL
            FROM ADVOGADO_ESCRITORIO ae

            INNER JOIN ESCRITORIOS e
                ON e.ID_ESCRITORIOS = ae.ID_ESCRITORIOS

            WHERE ae.ID_USUARIOS = ?

            ORDER BY e.NOME_FANTASIA
        """, (id_usuario_logado,))

        rows = cur.fetchall()

        escritorios = []

        for row in rows:
            escritorios.append({
                'id': row[0],
                'nome': row[1] or row[2] or '--'
            })

        return jsonify({
            'escritorios': escritorios
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cur.close()
        con.close()


@app.route('/alterar_cargo_advogado/<int:id_advogado>/<int:id_escritorio>', methods=['PUT'])
def alterar_cargo_advogado(id_advogado, id_escritorio):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_usuario_logado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json()

    if not dados:
        return jsonify({'error': 'Dados não enviados'}), 400

    novo_status = dados.get('status')

    if not novo_status:
        return jsonify({'error': 'Status é obrigatório'}), 400

    novo_status = novo_status.strip().upper()

    if novo_status not in ['PROPRIETARIO', 'PARCEIRO']:
        return jsonify({
            'error': 'Status inválido. Use PROPRIETARIO ou PARCEIRO'
        }), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT STATUS
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_usuario_logado,
            id_escritorio
        ))

        vinculo_logado = cur.fetchone()

        if not vinculo_logado:
            return jsonify({
                'error': 'Você não pertence a este escritório'
            }), 403

        status_logado = vinculo_logado[0]

        if not status_logado or status_logado.upper() != 'PROPRIETARIO':
            return jsonify({
                'error': 'Somente proprietários podem alterar cargos'
            }), 403

        if id_advogado == id_usuario_logado:
            return jsonify({
                'error': 'Você não pode alterar seu próprio cargo'
            }), 403

        cur.execute("""
            SELECT
                ae.STATUS,
                u.NOME
            FROM ADVOGADO_ESCRITORIO ae
            INNER JOIN USUARIOS u
                ON u.ID_USUARIOS = ae.ID_USUARIOS
            WHERE ae.ID_USUARIOS = ?
              AND ae.ID_ESCRITORIOS = ?
        """, (
            id_advogado,
            id_escritorio
        ))

        vinculo_advogado = cur.fetchone()

        if not vinculo_advogado:
            return jsonify({
                'error': 'Advogado não pertence a este escritório'
            }), 404

        status_atual = vinculo_advogado[0]
        nome_advogado = vinculo_advogado[1]

        if status_atual and status_atual.upper() == novo_status:
            return jsonify({
                'error': f'Advogado já é {novo_status}'
            }), 400

        cur.execute("""
            SELECT
                NOME_FANTASIA,
                RAZAO_SOCIAL
            FROM ESCRITORIOS
            WHERE ID_ESCRITORIOS = ?
        """, (
            id_escritorio,
        ))

        escritorio = cur.fetchone()

        if not escritorio:
            return jsonify({
                'error': 'Escritório não encontrado'
            }), 404

        nome_escritorio = (
                escritorio[0]
                or escritorio[1]
                or 'Escritório'
        )

        nomes_cargos = {
            'PROPRIETARIO': 'Proprietário',
            'PARCEIRO': 'Parceiro',
            'ASSOCIADO': 'Associado'
        }

        status_anterior_formatado = (
            nomes_cargos.get(
                status_atual.upper(),
                status_atual
            )
            if status_atual
            else 'Não definido'
        )

        status_novo_formatado = nomes_cargos.get(
            novo_status,
            novo_status
        )

        mensagem_notificacao = (
            f'Sua posição no escritório {nome_escritorio} '
            f'foi alterada de {status_anterior_formatado} '
            f'para {status_novo_formatado}.'
        )

        cur.execute("""
            UPDATE ADVOGADO_ESCRITORIO
            SET STATUS = ?
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            novo_status,
            id_advogado,
            id_escritorio
        ))

        cur.execute("""
            INSERT INTO NOTIFICACOES (
                ID_USUARIOS,
                TIPO,
                TITULO,
                MENSAGEM
            )
            VALUES (?, ?, ?, ?)
            RETURNING ID_NOTIFICACAO
        """, (
            id_advogado,
            'ALTERACAO_CARGO',
            'Posição alterada',
            mensagem_notificacao
        ))

        id_notificacao = cur.fetchone()[0]

        con.commit()

        agora = datetime.datetime.now()

        notificacao = {
            'id': id_notificacao,
            'tipo': 'ALTERACAO_CARGO',
            'titulo': 'Posição alterada',
            'mensagem': mensagem_notificacao,
            'lida': False,
            'data_criacao': agora.isoformat(),
            'data_leitura': None,
            'id_advogado': id_advogado,
            'nome_advogado': nome_advogado,
            'id_escritorio': id_escritorio,
            'nome_escritorio': nome_escritorio,
            'status_anterior': status_atual,
            'status_novo': novo_status
        }

        socketio.emit(
            'nova_notificacao',
            notificacao,
            room=f'usuario_{id_advogado}'
        )

        return jsonify({
            'mensagem': 'Cargo alterado com sucesso',
            'id_advogado': id_advogado,
            'id_escritorio': id_escritorio,
            'status_anterior': status_atual,
            'status_novo': novo_status
        }), 200

    except Exception as e:
        con.rollback()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/filtro_cargos_advogados', methods=['GET'])
def filtro_cargos_advogados():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    cargos = [
        {
            'valor': 'PROPRIETARIO',
            'nome': 'Proprietário'
        },
        {
            'valor': 'PARCEIRO',
            'nome': 'Parceiro'
        }
    ]

    return jsonify({
        'cargos': cargos
    }), 200


@app.route('/advogado/<int:id_advogado>/escritorio/<int:id_escritorio>/inativar', methods=['PUT'])
def inativar_advogado_escritorio(id_advogado, id_escritorio):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_usuario_logado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    if id_advogado == id_usuario_logado:
        return jsonify({
            'error': 'Você não pode inativar seu próprio vínculo'
        }), 403

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT STATUS, ATIVO
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_usuario_logado,
            id_escritorio
        ))

        vinculo_logado = cur.fetchone()

        if not vinculo_logado:
            return jsonify({
                'error': 'Você não pertence a este escritório'
            }), 403

        status_logado = vinculo_logado[0]
        ativo_logado = vinculo_logado[1]

        if ativo_logado != 1:
            return jsonify({
                'error': 'Seu vínculo com este escritório está inativo'
            }), 403

        if not status_logado or status_logado.upper() != 'PROPRIETARIO':
            return jsonify({
                'error': 'Somente proprietários podem inativar advogados'
            }), 403

        cur.execute("""
            SELECT
                ae.STATUS,
                ae.ATIVO,
                u.NOME
            FROM ADVOGADO_ESCRITORIO ae
            INNER JOIN USUARIOS u
                ON u.ID_USUARIOS = ae.ID_USUARIOS
            WHERE ae.ID_USUARIOS = ?
              AND ae.ID_ESCRITORIOS = ?
        """, (
            id_advogado,
            id_escritorio
        ))

        vinculo_advogado = cur.fetchone()

        if not vinculo_advogado:
            return jsonify({
                'error': 'Advogado não pertence a este escritório'
            }), 404

        status_advogado = vinculo_advogado[0]
        ativo_advogado = vinculo_advogado[1]
        nome_advogado = vinculo_advogado[2]

        if ativo_advogado == 0:
            return jsonify({
                'error': 'Advogado já está inativo neste escritório'
            }), 400

        if (
                status_advogado
                and status_advogado.upper() == 'PROPRIETARIO'
        ):
            return jsonify({
                'error': 'Não é possível inativar outro proprietário'
            }), 403

        cur.execute("""
            SELECT
                NOME_FANTASIA,
                RAZAO_SOCIAL
            FROM ESCRITORIOS
            WHERE ID_ESCRITORIOS = ?
        """, (
            id_escritorio,
        ))

        escritorio = cur.fetchone()

        if not escritorio:
            return jsonify({
                'error': 'Escritório não encontrado'
            }), 404

        nome_escritorio = (
                escritorio[0]
                or escritorio[1]
                or 'Escritório'
        )

        mensagem_notificacao = (
            f'Seu acesso ao escritório {nome_escritorio} '
            f'foi inativado.'
        )

        cur.execute("""
            UPDATE ADVOGADO_ESCRITORIO
            SET ATIVO = 0
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_advogado,
            id_escritorio
        ))

        cur.execute("""
            INSERT INTO NOTIFICACOES (
                ID_USUARIOS,
                TIPO,
                TITULO,
                MENSAGEM
            )
            VALUES (?, ?, ?, ?)
            RETURNING ID_NOTIFICACAO
        """, (
            id_advogado,
            'ADVOGADO_INATIVADO_ESCRITORIO',
            'Acesso ao escritório inativado',
            mensagem_notificacao
        ))

        id_notificacao = cur.fetchone()[0]

        con.commit()

        agora = datetime.datetime.now()

        notificacao = {
            'id': id_notificacao,
            'tipo': 'ADVOGADO_INATIVADO_ESCRITORIO',
            'titulo': 'Acesso ao escritório inativado',
            'mensagem': mensagem_notificacao,
            'lida': False,
            'data_criacao': agora.isoformat(),
            'data_leitura': None,
            'id_advogado': id_advogado,
            'nome_advogado': nome_advogado,
            'id_escritorio': id_escritorio,
            'nome_escritorio': nome_escritorio
        }

        socketio.emit(
            'nova_notificacao',
            notificacao,
            room=f'usuario_{id_advogado}'
        )

        return jsonify({
            'mensagem': 'Advogado inativado neste escritório com sucesso',
            'id_advogado': id_advogado,
            'id_escritorio': id_escritorio
        }), 200

    except Exception as e:
        con.rollback()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/advogado/<int:id_advogado>/escritorio/<int:id_escritorio>/ativar', methods=['PUT'])
def ativar_advogado_escritorio(id_advogado, id_escritorio):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_usuario_logado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT STATUS, ATIVO
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_usuario_logado,
            id_escritorio
        ))

        vinculo_logado = cur.fetchone()

        if not vinculo_logado:
            return jsonify({
                'error': 'Você não pertence a este escritório'
            }), 403

        status_logado = vinculo_logado[0]
        ativo_logado = vinculo_logado[1]

        if ativo_logado != 1:
            return jsonify({
                'error': 'Seu vínculo com este escritório está inativo'
            }), 403

        if not status_logado or status_logado.upper() != 'PROPRIETARIO':
            return jsonify({
                'error': 'Somente proprietários podem reativar advogados'
            }), 403

        cur.execute("""
            SELECT
                ae.ATIVO,
                u.NOME
            FROM ADVOGADO_ESCRITORIO ae
            INNER JOIN USUARIOS u
                ON u.ID_USUARIOS = ae.ID_USUARIOS
            WHERE ae.ID_USUARIOS = ?
              AND ae.ID_ESCRITORIOS = ?
        """, (
            id_advogado,
            id_escritorio
        ))

        vinculo_advogado = cur.fetchone()

        if not vinculo_advogado:
            return jsonify({
                'error': 'Advogado não pertence a este escritório'
            }), 404

        ativo_advogado = vinculo_advogado[0]
        nome_advogado = vinculo_advogado[1]

        if ativo_advogado == 1:
            return jsonify({
                'error': 'Advogado já está ativo neste escritório'
            }), 400

        cur.execute("""
            SELECT
                NOME_FANTASIA,
                RAZAO_SOCIAL
            FROM ESCRITORIOS
            WHERE ID_ESCRITORIOS = ?
        """, (
            id_escritorio,
        ))

        escritorio = cur.fetchone()

        if not escritorio:
            return jsonify({
                'error': 'Escritório não encontrado'
            }), 404

        nome_escritorio = (
                escritorio[0]
                or escritorio[1]
                or 'Escritório'
        )

        mensagem_notificacao = (
            f'Seu acesso ao escritório {nome_escritorio} '
            f'foi reativado.'
        )

        cur.execute("""
            UPDATE ADVOGADO_ESCRITORIO
            SET ATIVO = 1
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_advogado,
            id_escritorio
        ))

        cur.execute("""
            INSERT INTO NOTIFICACOES (
                ID_USUARIOS,
                TIPO,
                TITULO,
                MENSAGEM
            )
            VALUES (?, ?, ?, ?)
            RETURNING ID_NOTIFICACAO
        """, (
            id_advogado,
            'ADVOGADO_REATIVADO_ESCRITORIO',
            'Acesso ao escritório reativado',
            mensagem_notificacao
        ))

        id_notificacao = cur.fetchone()[0]

        con.commit()

        agora = datetime.datetime.now()

        notificacao = {
            'id': id_notificacao,
            'tipo': 'ADVOGADO_REATIVADO_ESCRITORIO',
            'titulo': 'Acesso ao escritório reativado',
            'mensagem': mensagem_notificacao,
            'lida': False,
            'data_criacao': agora.isoformat(),
            'data_leitura': None,
            'id_advogado': id_advogado,
            'nome_advogado': nome_advogado,
            'id_escritorio': id_escritorio,
            'nome_escritorio': nome_escritorio
        }

        socketio.emit(
            'nova_notificacao',
            notificacao,
            room=f'usuario_{id_advogado}'
        )

        return jsonify({
            'mensagem': 'Advogado reativado neste escritório com sucesso',
            'id_advogado': id_advogado,
            'id_escritorio': id_escritorio
        }), 200

    except Exception as e:
        con.rollback()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/advogado_escritorio/<int:id_advogado>/<int:id_escritorio>', methods=['DELETE'])
def remover_advogado_escritorio(id_advogado, id_escritorio):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_usuario_logado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT STATUS, ATIVO
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_usuario_logado,
            id_escritorio
        ))

        vinculo_logado = cur.fetchone()

        if not vinculo_logado:
            return jsonify({
                'error': 'Você não pertence a este escritório'
            }), 403

        status_logado = vinculo_logado[0]
        ativo_logado = vinculo_logado[1]

        if ativo_logado != 1:
            return jsonify({
                'error': 'Seu acesso a este escritório está inativo'
            }), 403

        if (
                not status_logado
                or status_logado.upper() != 'PROPRIETARIO'
        ):
            return jsonify({
                'error': 'Somente proprietários podem remover advogados'
            }), 403

        if id_advogado == id_usuario_logado:
            return jsonify({
                'error': 'Você não pode remover a si mesmo do escritório'
            }), 403

        cur.execute("""
            SELECT
                ae.STATUS,
                ae.ATIVO,
                u.NOME,
                u.EMAIL
            FROM ADVOGADO_ESCRITORIO ae
            INNER JOIN USUARIOS u
                ON u.ID_USUARIOS = ae.ID_USUARIOS
            WHERE ae.ID_USUARIOS = ?
              AND ae.ID_ESCRITORIOS = ?
        """, (
            id_advogado,
            id_escritorio
        ))

        vinculo_advogado = cur.fetchone()

        if not vinculo_advogado:
            return jsonify({
                'error': 'Advogado não pertence a este escritório'
            }), 404

        status_advogado = vinculo_advogado[0]
        nome_advogado = vinculo_advogado[2]

        if (
                status_advogado
                and status_advogado.upper() == 'PROPRIETARIO'
        ):
            cur.execute("""
                SELECT COUNT(*)
                FROM ADVOGADO_ESCRITORIO
                WHERE ID_ESCRITORIOS = ?
                  AND UPPER(STATUS) = 'PROPRIETARIO'
                  AND ATIVO = 1
            """, (
                id_escritorio,
            ))

            total_proprietarios = cur.fetchone()[0]

            if total_proprietarios <= 1:
                return jsonify({
                    'error': 'Não é possível remover o único proprietário do escritório'
                }), 400

        cur.execute("""
            SELECT
                NOME_FANTASIA,
                RAZAO_SOCIAL
            FROM ESCRITORIOS
            WHERE ID_ESCRITORIOS = ?
        """, (
            id_escritorio,
        ))

        escritorio = cur.fetchone()

        if not escritorio:
            return jsonify({
                'error': 'Escritório não encontrado'
            }), 404

        nome_escritorio = (
                escritorio[0]
                or escritorio[1]
                or 'Escritório'
        )

        titulo_notificacao = 'Removido do escritório'

        mensagem_notificacao = (
            f'Você foi removido do escritório {nome_escritorio}.'
        )

        cur.execute("""
            DELETE FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_advogado,
            id_escritorio
        ))

        cur.execute("""
            INSERT INTO NOTIFICACOES (
                ID_USUARIOS,
                TIPO,
                TITULO,
                MENSAGEM
            )
            VALUES (?, ?, ?, ?)
            RETURNING ID_NOTIFICACAO
        """, (
            id_advogado,
            'ADVOGADO_REMOVIDO_ESCRITORIO',
            titulo_notificacao,
            mensagem_notificacao
        ))

        id_notificacao = cur.fetchone()[0]

        con.commit()

        agora = datetime.datetime.now()

        notificacao = {
            'id': id_notificacao,
            'tipo': 'ADVOGADO_REMOVIDO_ESCRITORIO',
            'titulo': titulo_notificacao,
            'mensagem': mensagem_notificacao,
            'lida': False,
            'data_criacao': agora.isoformat(),
            'data_leitura': None,
            'id_advogado': id_advogado,
            'nome_advogado': nome_advogado,
            'id_escritorio': id_escritorio,
            'nome_escritorio': nome_escritorio
        }

        socketio.emit(
            'nova_notificacao',
            notificacao,
            room=f'usuario_{id_advogado}'
        )

        return jsonify({
            'mensagem': 'Advogado retirado do escritório com sucesso',
            'id_advogado': id_advogado,
            'id_escritorio': id_escritorio
        }), 200

    except Exception as e:
        con.rollback()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/notificacoes', methods=['GET'])
def listar_notificacoes():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    id_usuario = token_data['id_usuarios']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT FIRST 10
                ID_NOTIFICACAO,
                TIPO,
                TITULO,
                MENSAGEM,
                LIDA,
                DATA_CRIACAO,
                DATA_LEITURA
            FROM NOTIFICACOES
            WHERE ID_USUARIOS = ?
            ORDER BY DATA_CRIACAO DESC
        """, (
            id_usuario,
        ))

        rows = cur.fetchall()

        notificacoes = []

        for row in rows:
            notificacoes.append({
                'id': row[0],
                'tipo': row[1],
                'titulo': row[2],
                'mensagem': row[3],
                'lida': row[4] == 1,
                'data_criacao': (
                    row[5].strftime('%d/%m/%Y')
                    if row[5]
                    else None
                ),
                'hora_criacao': (
                    row[5].strftime('%H:%M')
                    if row[5]
                    else None
                ),
                'data_leitura': (
                    row[6].strftime('%d/%m/%Y %H:%M')
                    if row[6]
                    else None
                )
            })

        return jsonify({
            'notificacoes': notificacoes,
            'quantidade': len(notificacoes),
            'nao_lidas': sum(
                1
                for notificacao in notificacoes
                if not notificacao['lida']
            )
        }), 200

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/notificacoes/marcar_todas_lidas', methods=['PUT'])
def marcar_todas_notificacoes_lidas():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    id_usuario = token_data['id_usuarios']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            UPDATE NOTIFICACOES
            SET
                LIDA = 1,
                DATA_LEITURA = CURRENT_TIMESTAMP
            WHERE ID_USUARIOS = ?
              AND LIDA = 0
        """, (
            id_usuario,
        ))

        con.commit()

        return jsonify({
            'mensagem': 'Notificações marcadas como lidas'
        }), 200

    except Exception as e:
        con.rollback()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/logout', methods=['POST'])
def logout():
    resp = make_response(jsonify({'message': 'Logout realizado com sucesso'}))

    resp.set_cookie(
        'acess_token',
        '',
        httponly=True,
        secure=False,
        samesite='Lax',
        path='/',
        max_age=0,
        expires=0
    )

    return resp


@app.route('/redefinir_senha', methods=['PUT'])
def redefinir_senha():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuario = token_data['id_usuarios']

    dados = request.get_json()

    if not dados:
        return jsonify({'error': 'Dados não enviados'}), 400

    senha = dados.get('senha')
    confirmar_senha = dados.get('confirmar_senha')

    if not senha:
        return jsonify({'error': 'Senha é obrigatória'}), 400

    if not confirmar_senha:
        return jsonify({'error': 'Confirmação de senha é obrigatória'}), 400

    if senha != confirmar_senha:
        return jsonify({'error': 'Senhas não correspondem'}), 400

    if not senha_forte(senha):
        return jsonify({
            'error': 'Senha fraca. Use 8+ caracteres, maiúsculas, minúsculas, números e especiais'
        }), 400

    con = conexao()
    cur = con.cursor()

    try:
        senha_cripto = generate_password_hash(senha).decode('utf-8')

        cur.execute("""
            UPDATE USUARIOS
            SET SENHA = ?,
                PRIMEIRO_ACESSO = 0
            WHERE ID_USUARIOS = ?
        """, (senha_cripto, id_usuario))

        con.commit()

        return jsonify({'mensagem': 'Senha redefinida com sucesso'}), 200

    except Exception as e:
        con.rollback()
        print('Erro ao redefinir senha:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/editar_perfil_cliente', methods=['PUT'])
def editar_perfil_cliente():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_usuario = token_data['id_usuarios']

    if tipo_usuario not in [2, 3]:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    if request.is_json:
        dados = request.get_json() or {}
    else:
        dados = request.form

    nome = dados.get('nome')
    email = dados.get('email')
    cpf = dados.get('cpf')
    cnpj = dados.get('cnpj')
    telefone = dados.get('telefone')

    razao_social = dados.get('razao_social')
    nome_fantasia = dados.get('nome_fantasia')

    data_nascimento = dados.get('data_nascimento')
    sexo = dados.get('sexo')
    rg = dados.get('rg')
    orgao_expedidor = dados.get('orgao_expedidor')
    nacionalidade = dados.get('nacionalidade')
    estado_civil = dados.get('estado_civil')

    carteira_trabalho = dados.get('carteira_trabalho')
    serie_carteira = dados.get('serie_carteira')
    profissao = dados.get('profissao')

    cep = dados.get('cep')
    logradouro = dados.get('logradouro')
    numero = dados.get('numero')
    complemento = dados.get('complemento')
    bairro = dados.get('bairro')
    cidade = dados.get('cidade')
    estado = dados.get('estado')

    if not nome and not razao_social:
        return jsonify({'error': 'Nome é obrigatório'}), 400

    if not email:
        return jsonify({'error': 'E-mail é obrigatório'}), 400

    if not telefone:
        return jsonify({'error': 'Telefone é obrigatório'}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute(
            "SELECT ID_USUARIOS FROM USUARIOS WHERE EMAIL = ? AND ID_USUARIOS != ?",
            (email, id_usuario)
        )

        if cur.fetchone():
            return jsonify({'error': 'E-mail já cadastrado para outro usuário'}), 400

        if tipo_usuario == 2 and cpf:
            cpf_limpo = ''.join(filter(str.isdigit, cpf))

            if len(cpf_limpo) != 11:
                return jsonify({'error': 'CPF inválido'}), 400

            cur.execute(
                "SELECT ID_USUARIOS FROM USUARIOS WHERE CPF = ? AND ID_USUARIOS != ?",
                (cpf_limpo, id_usuario)
            )

            if cur.fetchone():
                return jsonify({'error': 'CPF já cadastrado para outro usuário'}), 400

        if tipo_usuario == 3 and cnpj:
            cnpj_limpo = ''.join(filter(str.isdigit, cnpj))

            if len(cnpj_limpo) != 14:
                return jsonify({'error': 'CNPJ inválido'}), 400

            cur.execute(
                "SELECT ID_USUARIOS FROM USUARIOS WHERE CNPJ = ? AND ID_USUARIOS != ?",
                (cnpj_limpo, id_usuario)
            )

            if cur.fetchone():
                return jsonify({'error': 'CNPJ já cadastrado para outro usuário'}), 400

        cur.execute(
            "UPDATE USUARIOS SET "
            "NOME = ?, EMAIL = ?, TELEFONE = ?, "
            "CPF = ?, CNPJ = ?, "
            "RAZAO_SOCIAL = ?, NOME_FANTASIA = ?, "
            "DATA_NASCIMENTO = ?, SEXO = ?, RG = ?, "
            "ORGAO_EXPEDIDOR = ?, NACIONALIDADE = ?, ESTADO_CIVIL = ?, "
            "CARTERA_TRABALHO = ?, SERIE_CARTERA = ?, PROFISSAO = ?, "
            "CEP = ?, LOGRADOURO = ?, NUMERO = ?, COMPLEMENTO = ?, "
            "BAIRRO = ?, CIDADE = ?, ESTADO = ? "
            "WHERE ID_USUARIOS = ?",
            (
                nome,
                email,
                telefone,
                cpf if cpf else None,
                cnpj if cnpj else None,
                razao_social,
                nome_fantasia,
                data_nascimento if data_nascimento else None,
                sexo,
                rg,
                orgao_expedidor,
                nacionalidade,
                estado_civil,
                carteira_trabalho,
                serie_carteira,
                profissao,
                cep,
                logradouro,
                numero,
                complemento,
                bairro,
                cidade,
                estado,
                id_usuario
            )
        )

        con.commit()

        foto_perfil = request.files.get('foto_perfil')

        if foto_perfil:
            try:
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'Usuarios')
                os.makedirs(caminho, exist_ok=True)

                nome_arquivo = f'{id_usuario}.jpeg'
                foto_perfil.save(os.path.join(caminho, nome_arquivo))

                print(f'Foto do cliente {id_usuario} salva em {nome_arquivo}')
            except Exception as e:
                print(f'Erro ao salvar foto do cliente: {e}')

        nome_exibicao = nome or razao_social or nome_fantasia or ''

        try:
            from main import socketio
            socketio.emit(
                'atualizar_dados',
                {
                    'entidade': 'usuario',
                    'acao': 'atualizado',
                    'id_usuario': id_usuario,
                    'nome': nome_exibicao
                },
                room=f'usuario_{id_usuario}'
            )
            print(f'[REFRESH] usuario/atualizado emitido para usuario_{id_usuario}')
        except Exception as e:
            print(f'[REFRESH] Erro ao emitir socket: {e}')

        return jsonify({
            'mensagem': 'Perfil atualizado com sucesso',
            'nome': nome_exibicao
        }), 200

    except Exception as e:
        con.rollback()
        print(f'Erro ao editar perfil do cliente: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

    finally:
        cur.close()
        con.close()