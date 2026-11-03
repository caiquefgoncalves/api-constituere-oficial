import datetime
import unicodedata
from decimal import Decimal, InvalidOperation
from io import BytesIO

from flask import jsonify, request, send_file
from fpdf import FPDF

from db import conexao
from funcao import decodificar_token, converter_data_pagamento
from main import app


_socketio = None


def set_socketio_emitter(sio):
    global _socketio
    _socketio = sio


def converter_data(valor):
    if isinstance(valor, datetime.datetime):
        return valor.date()
    if isinstance(valor, datetime.date):
        return valor
    if valor:
        for formato in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.datetime.strptime(str(valor), formato).date()
            except ValueError:
                pass
    return None


def periodo_para_datas(periodo, data_ini=None, data_fim=None):
    hoje = datetime.date.today()
    if periodo == 'mes':
        return hoje.replace(day=1), hoje
    if periodo == 'mesAnterior':
        fim = hoje.replace(day=1) - datetime.timedelta(days=1)
        return fim.replace(day=1), fim
    if periodo == '30dias':
        return hoje - datetime.timedelta(days=30), hoje
    if periodo == '90dias':
        return hoje - datetime.timedelta(days=90), hoje
    if periodo == 'personalizado':
        return converter_data(data_ini), converter_data(data_fim)
    return hoje.replace(day=1), hoje


def verificar_acesso_escritorio(cur, id_usuario, id_escritorio):
    cur.execute('''
        SELECT STATUS, ATIVO
        FROM ADVOGADO_ESCRITORIO
        WHERE ID_USUARIOS = ? AND ID_ESCRITORIOS = ?
    ''', (id_usuario, id_escritorio))
    row = cur.fetchone()
    if not row:
        return False, 'Você não possui acesso a este escritório.'
    if row[1] != 1:
        return False, 'Seu acesso a este escritório está inativo.'
    if row[0] != 'PROPRIETARIO':
        return False, 'Apenas o proprietário do escritório pode acessar o financeiro.'
    return True, row[0]


def status_parcela(data_venc, status_db, hoje, data_pagamento=None):
    status = (status_db or '').strip().upper()
    if data_pagamento or status in ('PAGA', 'PAGO', 'RECEBIDA', 'RECEBIDO', 'QUITADA', 'QUITADO'):
        return 'Recebido'
    if data_venc and data_venc < hoje:
        return 'Atrasado'
    return 'A pagar'


def status_lancamento_manual(tipo, status_db, data_lanc, hoje):
    status = (status_db or '').strip().lower()
    if status in ('recebida', 'recebido', 'pago', 'paga', 'quitada', 'quitado'):
        return 'Recebido'
    if data_lanc and data_lanc < hoje:
        return 'Atrasado'
    return 'A pagar'


def dentro_periodo(data_obj, inicio, fim):
    return data_obj is not None and (not inicio or data_obj >= inicio) and (not fim or data_obj <= fim)


def numero_decimal(valor):
    if valor is None or isinstance(valor, bool):
        raise ValueError('Valor inválido')
    if isinstance(valor, (int, float, Decimal)):
        resultado = Decimal(str(valor))
    else:
        texto = str(valor).strip().replace('R$', '').replace(' ', '')
        if '.' in texto and ',' in texto:
            if texto.rfind(',') > texto.rfind('.'):
                texto = texto.replace('.', '').replace(',', '.')
            else:
                texto = texto.replace(',', '')
        elif ',' in texto:
            texto = texto.replace(',', '.')
        resultado = Decimal(texto)
    if not resultado.is_finite():
        raise ValueError('Valor inválido')
    return resultado


def para_float(valor):
    try:
        return float(numero_decimal(valor))
    except (ValueError, TypeError, InvalidOperation):
        return 0.0


def montar_lancamentos(cur, id_escritorio, inicio, fim, tipo='todos'):
    hoje = datetime.date.today()
    lancamentos = []

    if tipo in ('todos', 'receita', 'despesa'):
        sql = '''
            SELECT ID_LANCAMENTOS, TIPO, DESCRICAO, VALOR, "DATA",
                   FORMA_PAGAMENTO, STATUS
            FROM LANCAMENTOS_FINANCEIROS
            WHERE ID_ESCRITORIO = ? AND ATIVO = 1
        '''
        parametros = [id_escritorio]
        if tipo != 'todos':
            sql += ' AND TIPO = ?'
            parametros.append(tipo)
        if inicio:
            sql += ' AND "DATA" >= ?'
            parametros.append(inicio)
        if fim:
            sql += ' AND "DATA" <= ?'
            parametros.append(fim)
        cur.execute(sql, tuple(parametros))
        for row in cur.fetchall():
            data_lanc = converter_data(row[4])
            lancamentos.append({
                'id': f'lanc_{row[0]}',
                'id_real': row[0],
                'tipo': (row[1] or '').lower(),
                'descricao': row[2] or '',
                'valor': para_float(row[3]),
                'data': data_lanc.isoformat() if data_lanc else None,
                'forma_pagamento': row[5] or '',
                'status': status_lancamento_manual(row[1], row[6], data_lanc, hoje),
                'origem': 'manual'
            })

    if tipo in ('todos', 'receita'):
        origens = (
            ('parc', 'PARCELAS', 'parc', 'ID_PARCELAS', '',
             'INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = parc.ID_PAGAMENTO'),
            ('exito', 'PARCELAS_EXITO', 'pe', 'ID_PARCELA_EXITO', 'Êxito - ',
             '''INNER JOIN PAGAMENTO_EXITO pex ON pex.ID_PAGAMENTO_EXITO = pe.ID_PAGAMENTO_EXITO
                INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = pex.ID_PAGAMENTO''')
        )
        for codigo, tabela, alias, coluna_id, prefixo, join in origens:
            sql = f'''
                SELECT {alias}.{coluna_id}, {alias}.VALOR_PARCELA,
                       {alias}.DATA_VENCIMENTO, {alias}.DATA_PAGAMENTO,
                       {alias}.STATUS, {alias}.NUMERO_PARCELA,
                       p.TIPO_PROCESSO, p.NUM_PROCESSO,
                       u.NOME, u.RAZAO_SOCIAL, u.NOME_FANTASIA,
                       pag.FORM_PAGAMENTO
                FROM {tabela} {alias}
                {join}
                INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = pag.ID_PROCESSO
                INNER JOIN USUARIOS u ON u.ID_USUARIOS = p.ID_USUARIOS_CLIENTE
                WHERE (
                    p.ID_ESCRITORIOS = ?
                    OR (
                        p.ID_ESCRITORIOS IS NULL
                        AND p.ID_USUARIOS_ADVOGADO IN (
                            SELECT ID_USUARIOS FROM ADVOGADO_ESCRITORIO
                            WHERE ID_ESCRITORIOS = ? AND ATIVO = 1
                        )
                    )
                )
                AND UPPER(COALESCE({alias}.STATUS, '')) <> 'CANCELADA'
            '''
            cur.execute(sql, (id_escritorio, id_escritorio))
            for row in cur.fetchall():
                vencimento = converter_data_pagamento(row[2])
                pagamento = converter_data_pagamento(row[3])
                status = status_parcela(vencimento, row[4], hoje, pagamento)
                data_exibir = pagamento or vencimento if status == 'Recebido' else vencimento
                if not dentro_periodo(data_exibir, inicio, fim):
                    continue
                numero_parcela = 'Entrada' if row[5] == 0 else f'{row[5]}ª parcela'
                nome_cliente = row[8] or row[9] or row[10] or '--'
                descricao = f'{row[6] or "Processo"} - {prefixo}{numero_parcela} ({nome_cliente})'
                lancamentos.append({
                    'id': f'{codigo}_{row[0]}',
                    'id_real': row[0],
                    'tipo': 'receita',
                    'descricao': descricao,
                    'valor': para_float(row[1]),
                    'data': data_exibir.isoformat() if data_exibir else None,
                    'forma_pagamento': row[11] or '--',
                    'status': status,
                    'origem': 'pagamento_cliente'
                })

    lancamentos.sort(key=lambda item: item['data'] or '', reverse=True)
    return lancamentos


def processar_notificacoes_vencimento():
    con = conexao()
    cur = con.cursor()
    hoje = datetime.date.today()
    limite = hoje + datetime.timedelta(days=3)
    enviadas = 0
    try:
        cur.execute('''
            SELECT p.ID_USUARIOS_ADVOGADO, p.NUM_PROCESSO, u.NOME,
                   parc.VALOR_PARCELA, parc.DATA_VENCIMENTO, parc.ID_PARCELAS
            FROM PARCELAS parc
            INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = parc.ID_PAGAMENTO
            INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = pag.ID_PROCESSO
            INNER JOIN USUARIOS u ON u.ID_USUARIOS = p.ID_USUARIOS_CLIENTE
            WHERE parc.DATA_VENCIMENTO BETWEEN ? AND ?
              AND UPPER(COALESCE(parc.STATUS, '')) NOT IN ('PAGA', 'CANCELADA')
        ''', (hoje, limite))
        parcelas = cur.fetchall()
        for row in parcelas:
            id_advogado, num_processo, nome_cliente, valor_raw, vencimento, _ = row
            valor = para_float(valor_raw)
            data_formatada = vencimento.strftime('%d/%m/%Y') if vencimento else '--'
            titulo = 'Aviso de Vencimento'
            mensagem = (
                f'A parcela de {nome_cliente or "Cliente"} (Proc. {num_processo or "--"}) '
                f'no valor de R$ {valor:.2f} vence em {data_formatada}.'
            )
            cur.execute('''
                SELECT 1 FROM NOTIFICACOES
                WHERE ID_USUARIOS = ? AND TITULO = ? AND MENSAGEM = ?
            ''', (id_advogado, titulo, mensagem))
            if cur.fetchone():
                continue
            cur.execute('''
                INSERT INTO NOTIFICACOES (ID_USUARIOS, TIPO, TITULO, MENSAGEM)
                VALUES (?, ?, ?, ?) RETURNING ID_NOTIFICACAO
            ''', (id_advogado, 'FINANCEIRO_VENCIMENTO', titulo, mensagem))
            id_notificacao = cur.fetchone()[0]
            con.commit()
            agora = datetime.datetime.now()
            print(f"[NOTIF] _socketio é None? {_socketio is None} | id_advogado={id_advogado}", flush=True)
            if _socketio:
                _socketio.emit('nova_notificacao', {
                    'id': id_notificacao,
                    'tipo': 'FINANCEIRO_VENCIMENTO',
                    'titulo': titulo,
                    'mensagem': mensagem,
                    'lida': False,
                    'data_criacao': agora.strftime('%d/%m/%Y'),
                    'hora_criacao': agora.strftime('%H:%M'),
                    'data_leitura': None
                }, room=f'usuario_{id_advogado}')
                print(f"[NOTIF] Emitido para usuario_{id_advogado}", flush=True)
            enviadas += 1
        return enviadas
    except Exception:
        con.rollback()
        print('Erro ao processar notificações de vencimento', flush=True)
        return 0
    finally:
        cur.close()
        con.close()


@app.route('/financeiro/notificar_vencimentos', methods=['GET', 'POST'])
def notificar_vencimentos():
    enviadas = processar_notificacoes_vencimento()
    return jsonify({'mensagem': f'{enviadas} notificações enviadas.'}), 200


@app.route('/escritorio/<int:id_escritorio>/financeiro/lancamentos', methods=['GET'])
def listar_lancamentos_escritorio(id_escritorio):
    token = decodificar_token()
    if not token:
        return jsonify({'error': 'Token necessário'}), 401
    if token.get('tipo') != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    tipo = (request.args.get('tipo') or 'todos').lower()
    if tipo not in ('todos', 'receita', 'despesa'):
        return jsonify({'error': 'Tipo inválido'}), 400
    periodo_solicitado = request.args.get('periodo', 'mes')
    inicio, fim = periodo_para_datas(
        periodo_solicitado,
        request.args.get('data_inicial'),
        request.args.get('data_final')
    )
    if periodo_solicitado == 'personalizado':
        if not inicio or not fim:
            return jsonify({'error': 'Informe a data inicial e a data final.'}), 400
        if fim < inicio:
            return jsonify({'error': 'Período inválido'}), 400
    con = conexao()
    cur = con.cursor()
    try:
        permitido, mensagem = verificar_acesso_escritorio(cur, token['id_usuarios'], id_escritorio)
        if not permitido:
            return jsonify({'error': mensagem}), 403
        lancamentos = montar_lancamentos(cur, id_escritorio, inicio, fim, tipo)
        return jsonify({
            'lancamentos': lancamentos,
            'quantidade': len(lancamentos),
            'periodo': {
                'inicio': inicio.strftime('%d/%m/%Y') if inicio else None,
                'fim': fim.strftime('%d/%m/%Y') if fim else None
            }
        }), 200
    except Exception:
        print('Erro ao listar lançamentos', flush=True)
        return jsonify({'error': 'Erro ao listar lançamentos financeiros.'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>/financeiro/lancamentos', methods=['POST'])
def criar_lancamento_escritorio(id_escritorio):
    token = decodificar_token()
    if not token:
        return jsonify({'error': 'Token necessário'}), 401
    if token.get('tipo') != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json(silent=True) if request.is_json else request.form
    dados = dados or {}
    tipo = str(dados.get('tipo') or '').strip().lower()
    descricao = str(dados.get('descricao') or '').strip()
    if tipo not in ('receita', 'despesa'):
        return jsonify({'error': 'Tipo inválido'}), 400
    if not descricao or len(descricao) > 254:
        return jsonify({'error': 'Descrição deve ter de 1 a 254 caracteres.'}), 400
    try:
        valor = numero_decimal(dados.get('valor'))
        if valor <= 0 or valor.as_tuple().exponent < -2:
            raise ValueError('Valor inválido')
    except (ValueError, TypeError, InvalidOperation):
        return jsonify({'error': 'Valor inválido'}), 400
    data_obj = converter_data(dados.get('data'))
    if not data_obj:
        return jsonify({'error': 'Data inválida'}), 400

    status = 'recebida' if tipo == 'receita' else 'a_pagar'
    con = conexao()
    cur = con.cursor()
    try:
        permitido, mensagem = verificar_acesso_escritorio(cur, token['id_usuarios'], id_escritorio)
        if not permitido:
            return jsonify({'error': mensagem}), 403
        cur.execute('''
            INSERT INTO LANCAMENTOS_FINANCEIROS (
                ID_USUARIOS_ADVOGADO, ID_ESCRITORIO, TIPO, DESCRICAO,
                VALOR, "DATA", STATUS, ATIVO
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            RETURNING ID_LANCAMENTOS
        ''', (token['id_usuarios'], id_escritorio, tipo, descricao, valor, data_obj, status))
        id_lancamento = cur.fetchone()[0]
        con.commit()
        return jsonify({
            'mensagem': 'Lançamento cadastrado com sucesso',
            'id_lancamento': id_lancamento
        }), 201
    except Exception:
        con.rollback()
        print('Erro ao criar lançamento financeiro', flush=True)
        return jsonify({'error': 'Erro ao cadastrar lançamento financeiro.'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>/financeiro/lancamentos/<int:id_lancamento>', methods=['PUT'])
def editar_lancamento_escritorio(id_escritorio, id_lancamento):
    token = decodificar_token()
    if not token:
        return jsonify({'error': 'Token necessário'}), 401
    if token.get('tipo') != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json(silent=True) if request.is_json else request.form
    dados = dados or {}
    assignments = []
    parameters = []

    if 'tipo' in dados:
        tipo = str(dados.get('tipo') or '').strip().lower()
        if tipo not in ('receita', 'despesa'):
            return jsonify({'error': 'Tipo inválido'}), 400
        assignments.append('TIPO = ?')
        parameters.append(tipo)
        assignments.append('STATUS = ?')
        parameters.append('recebida' if tipo == 'receita' else 'a_pagar')

    if 'descricao' in dados:
        descricao = str(dados.get('descricao') or '').strip()
        if not descricao or len(descricao) > 254:
            return jsonify({'error': 'Descrição deve ter de 1 a 254 caracteres.'}), 400
        assignments.append('DESCRICAO = ?')
        parameters.append(descricao)

    if 'valor' in dados:
        try:
            valor = numero_decimal(dados.get('valor'))
            if valor <= 0 or valor.as_tuple().exponent < -2:
                raise ValueError('Valor inválido')
        except (ValueError, TypeError, InvalidOperation):
            return jsonify({'error': 'Valor inválido'}), 400
        assignments.append('VALOR = ?')
        parameters.append(valor)

    if 'data' in dados:
        data_obj = converter_data(dados.get('data'))
        if not data_obj:
            return jsonify({'error': 'Data inválida'}), 400
        assignments.append('"DATA" = ?')
        parameters.append(data_obj)

    if not assignments:
        return jsonify({'error': 'Informe ao menos um campo para alterar'}), 400

    con = conexao()
    cur = con.cursor()
    try:
        permitido, mensagem = verificar_acesso_escritorio(cur, token['id_usuarios'], id_escritorio)
        if not permitido:
            return jsonify({'error': mensagem}), 403
        cur.execute(
            'SELECT 1 FROM LANCAMENTOS_FINANCEIROS '
            'WHERE ID_LANCAMENTOS = ? AND ID_ESCRITORIO = ? AND ATIVO = 1',
            (id_lancamento, id_escritorio),
        )
        if not cur.fetchone():
            return jsonify({'error': 'Lançamento não encontrado'}), 404
        parameters.extend((id_lancamento, id_escritorio))
        cur.execute(
            'UPDATE LANCAMENTOS_FINANCEIROS SET '
            + ', '.join(assignments)
            + ' WHERE ID_LANCAMENTOS = ? AND ID_ESCRITORIO = ? AND ATIVO = 1',
            tuple(parameters),
        )
        con.commit()
        return jsonify({'mensagem': 'Lançamento atualizado com sucesso.'}), 200
    except Exception:
        con.rollback()
        print('Erro ao editar lançamento financeiro', flush=True)
        return jsonify({'error': 'Erro ao editar lançamento financeiro.'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>/financeiro/lancamentos/<int:id_lancamento>', methods=['DELETE'])
def excluir_lancamento_escritorio(id_escritorio, id_lancamento):
    token = decodificar_token()
    if not token:
        return jsonify({'error': 'Token necessário'}), 401
    if token.get('tipo') != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    con = conexao()
    cur = con.cursor()
    try:
        permitido, mensagem = verificar_acesso_escritorio(cur, token['id_usuarios'], id_escritorio)
        if not permitido:
            return jsonify({'error': mensagem}), 403
        cur.execute(
            'SELECT 1 FROM LANCAMENTOS_FINANCEIROS '
            'WHERE ID_LANCAMENTOS = ? AND ID_ESCRITORIO = ? AND ATIVO = 1',
            (id_lancamento, id_escritorio),
        )
        if not cur.fetchone():
            return jsonify({'error': 'Lançamento não encontrado'}), 404
        cur.execute(
            '''UPDATE LANCAMENTOS_FINANCEIROS SET ATIVO = 0
               WHERE ID_LANCAMENTOS = ? AND ID_ESCRITORIO = ? AND ATIVO = 1''',
            (id_lancamento, id_escritorio),
        )
        con.commit()
        return jsonify({'mensagem': 'Lançamento excluído com sucesso.'}), 200
    except Exception:
        con.rollback()
        print('Erro ao excluir lançamento financeiro', flush=True)
        return jsonify({'error': 'Erro ao excluir lançamento financeiro.'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>/financeiro/lancamentos/<int:id_lancamento>/baixar', methods=['PUT'])
def baixar_lancamento_escritorio(id_escritorio, id_lancamento):
    token = decodificar_token()
    if not token:
        return jsonify({'error': 'Token necessário'}), 401
    if token.get('tipo') != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403
    con = conexao()
    cur = con.cursor()
    try:
        permitido, mensagem = verificar_acesso_escritorio(cur, token['id_usuarios'], id_escritorio)
        if not permitido:
            return jsonify({'error': mensagem}), 403
        cur.execute('''
            SELECT TIPO, STATUS, VALOR
            FROM LANCAMENTOS_FINANCEIROS
            WHERE ID_LANCAMENTOS = ? AND ID_ESCRITORIO = ? AND ATIVO = 1
        ''', (id_lancamento, id_escritorio))
        row = cur.fetchone()
        if row:
            tipo, status, valor = (row[0] or '').lower(), (row[1] or '').lower(), para_float(row[2])
            if status in ('recebida', 'recebido', 'pago', 'paga'):
                return jsonify({'error': 'Este lançamento já foi baixado.'}), 400
            if tipo == 'despesa':
                saldo = 0.0
                cur.execute('''
                    SELECT VALOR FROM LANCAMENTOS_FINANCEIROS
                    WHERE ID_ESCRITORIO = ? AND ATIVO = 1 AND TIPO = 'receita'
                      AND LOWER(STATUS) IN ('recebida', 'recebido', 'pago', 'paga')
                ''', (id_escritorio,))
                saldo += sum(para_float(item[0]) for item in cur.fetchall())
                cur.execute('''
                    SELECT parc.VALOR_PARCELA
                    FROM PARCELAS parc
                    INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = parc.ID_PAGAMENTO
                    INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = pag.ID_PROCESSO
                    WHERE (p.ID_ESCRITORIOS = ? OR (
                        p.ID_ESCRITORIOS IS NULL AND p.ID_USUARIOS_ADVOGADO IN (
                            SELECT ID_USUARIOS FROM ADVOGADO_ESCRITORIO
                            WHERE ID_ESCRITORIOS = ? AND ATIVO = 1
                        )
                    ))
                    AND (UPPER(parc.STATUS) IN ('PAGA', 'PAGO', 'RECEBIDA', 'RECEBIDO')
                         OR parc.DATA_PAGAMENTO IS NOT NULL)
                ''', (id_escritorio, id_escritorio))
                saldo += sum(para_float(item[0]) for item in cur.fetchall())
                cur.execute('''
                    SELECT pe.VALOR_PARCELA
                    FROM PARCELAS_EXITO pe
                    INNER JOIN PAGAMENTO_EXITO pex ON pex.ID_PAGAMENTO_EXITO = pe.ID_PAGAMENTO_EXITO
                    INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = pex.ID_PAGAMENTO
                    INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = pag.ID_PROCESSO
                    WHERE (p.ID_ESCRITORIOS = ? OR (
                        p.ID_ESCRITORIOS IS NULL AND p.ID_USUARIOS_ADVOGADO IN (
                            SELECT ID_USUARIOS FROM ADVOGADO_ESCRITORIO
                            WHERE ID_ESCRITORIOS = ? AND ATIVO = 1
                        )
                    ))
                    AND (UPPER(pe.STATUS) IN ('PAGA', 'PAGO', 'RECEBIDA', 'RECEBIDO')
                         OR pe.DATA_PAGAMENTO IS NOT NULL)
                ''', (id_escritorio, id_escritorio))
                saldo += sum(para_float(item[0]) for item in cur.fetchall())
                cur.execute('''
                    SELECT VALOR FROM LANCAMENTOS_FINANCEIROS
                    WHERE ID_ESCRITORIO = ? AND ATIVO = 1 AND TIPO = 'despesa'
                      AND LOWER(STATUS) IN ('pago', 'paga', 'recebida', 'recebido')
                ''', (id_escritorio,))
                saldo -= sum(para_float(item[0]) for item in cur.fetchall())
                if saldo < valor:
                    return jsonify({
                        'error': f'Saldo insuficiente para esta baixa. Saldo: R$ {saldo:.2f} | Valor: R$ {valor:.2f}.'
                    }), 400
            cur.execute('''
                UPDATE LANCAMENTOS_FINANCEIROS
                SET STATUS = 'Recebido'
                WHERE ID_LANCAMENTOS = ? AND ID_ESCRITORIO = ?
            ''', (id_lancamento, id_escritorio))
            con.commit()
            return jsonify({'mensagem': 'Baixa realizada com sucesso.'}), 200

        for tabela, alias, coluna_id, join, msg_sucesso in (
            ('PARCELAS', 'parc', 'ID_PARCELAS',
             'INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = parc.ID_PAGAMENTO',
             'Pagamento da parcela confirmado com sucesso.'),
            ('PARCELAS_EXITO', 'pe', 'ID_PARCELA_EXITO',
             '''INNER JOIN PAGAMENTO_EXITO pex ON pex.ID_PAGAMENTO_EXITO = pe.ID_PAGAMENTO_EXITO
                INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = pex.ID_PAGAMENTO''',
             'Pagamento da parcela de êxito confirmado com sucesso.')
        ):
            cur.execute(f'''
                SELECT {alias}.STATUS
                FROM {tabela} {alias}
                {join}
                INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = pag.ID_PROCESSO
                WHERE {alias}.{coluna_id} = ?
                  AND (p.ID_ESCRITORIOS = ? OR (
                      p.ID_ESCRITORIOS IS NULL AND p.ID_USUARIOS_ADVOGADO IN (
                          SELECT ID_USUARIOS FROM ADVOGADO_ESCRITORIO
                          WHERE ID_ESCRITORIOS = ? AND ATIVO = 1
                      )
                  ))
            ''', (id_lancamento, id_escritorio, id_escritorio))
            row = cur.fetchone()
            if not row:
                continue
            if (row[0] or '').upper() in ('PAGA', 'PAGO', 'RECEBIDA', 'RECEBIDO'):
                return jsonify({'error': 'Esta parcela já foi paga.'}), 400
            cur.execute(f'''
                UPDATE {tabela}
                SET STATUS = 'PAGA', DATA_PAGAMENTO = ?
                WHERE {coluna_id} = ?
            ''', (datetime.date.today(), id_lancamento))
            con.commit()
            return jsonify({'mensagem': msg_sucesso}), 200
        return jsonify({'error': 'Lançamento não encontrado'}), 404
    except Exception:
        con.rollback()
        print('Erro ao dar baixa no lançamento', flush=True)
        return jsonify({'error': 'Erro ao dar baixa no lançamento.'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>/financeiro/resumo', methods=['GET'])
def resumo_financeiro_escritorio(id_escritorio):
    token = decodificar_token()
    if not token:
        return jsonify({'error': 'Token necessário'}), 401
    if token.get('tipo') != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403
    periodo_solicitado = request.args.get('periodo', 'mes')
    inicio, fim = periodo_para_datas(
        periodo_solicitado,
        request.args.get('data_inicial'),
        request.args.get('data_final')
    )
    if periodo_solicitado == 'personalizado':
        if not inicio or not fim:
            return jsonify({'error': 'Informe a data inicial e a data final.'}), 400
        if fim < inicio:
            return jsonify({'error': 'Período inválido'}), 400
    con = conexao()
    cur = con.cursor()
    try:
        permitido, mensagem = verificar_acesso_escritorio(cur, token['id_usuarios'], id_escritorio)
        if not permitido:
            return jsonify({'error': mensagem}), 403
        lancamentos = montar_lancamentos(cur, id_escritorio, inicio, fim)
        receita_recebida = 0.0
        receita_pendente = 0.0
        receita_atrasada = 0.0
        despesa_paga = 0.0
        despesa_pendente = 0.0
        despesa_atrasada = 0.0
        for item in lancamentos:
            valor = item['valor']
            tipo = item['tipo']
            status = item['status']
            if tipo == 'receita':
                if status == 'Recebido':
                    receita_recebida += valor
                elif status == 'Atrasado':
                    receita_atrasada += valor
                else:
                    receita_pendente += valor
            elif tipo == 'despesa':
                if status == 'Recebido':
                    despesa_paga += valor
                elif status == 'Atrasado':
                    despesa_atrasada += valor
                else:
                    despesa_pendente += valor
        receita_a_receber = receita_pendente + receita_atrasada
        total_receitas = receita_recebida + receita_a_receber
        despesas = despesa_paga + despesa_pendente + despesa_atrasada
        saldo = receita_recebida - (despesas + receita_a_receber)
        resultado = 'lucro' if saldo > 0 else 'prejuizo' if saldo < 0 else 'neutro'
        percentual = round(receita_recebida * 100 / total_receitas) if total_receitas > 0 else 0
        situacao = 'Crítica' if saldo < 0 else 'Boa' if percentual >= 70 else 'Atenção'
        return jsonify({
            'receita_recebida': receita_recebida,
            'receita_pendente': receita_pendente,
            'receita_atrasada': receita_atrasada,
            'receita_a_receber': receita_a_receber,
            'total_receitas': total_receitas,
            'despesa_paga': despesa_paga,
            'despesa_pendente': despesa_pendente,
            'despesa_atrasada': despesa_atrasada,
            'despesas': despesas,
            'saldo': saldo,
            'lucro': max(saldo, 0),
            'prejuizo': max(-saldo, 0),
            'resultado': resultado,
            'percentual_recebido': percentual,
            'situacao': situacao
        }), 200
    except Exception:
        print('Erro ao calcular resumo financeiro', flush=True)
        return jsonify({'error': 'Erro ao calcular resumo financeiro.'}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>/financeiro/relatorio', methods=['POST'])
def gerar_relatorio_financeiro(id_escritorio):
    token = decodificar_token()
    if not token:
        return jsonify({'error': 'Token necessário'}), 401
    if token.get('tipo') != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403
    dados = request.get_json(silent=True) or {}
    lancamentos = dados.get('lancamentos') or []
    resumo = dados.get('resumo') or {}
    periodo_texto = dados.get('periodo_texto') or 'Período não especificado'
    con = conexao()
    cur = con.cursor()
    try:
        permitido, mensagem = verificar_acesso_escritorio(cur, token['id_usuarios'], id_escritorio)
        if not permitido:
            return jsonify({'error': mensagem}), 403
        cur.execute('SELECT NOME_FANTASIA FROM ESCRITORIOS WHERE ID_ESCRITORIOS = ?', (id_escritorio,))
        row = cur.fetchone()
        nome_escritorio = row[0] if row and row[0] else 'Escritório'

        def texto(valor, limite=None):
            valor = '-' if valor in (None, '') else str(valor)
            valor = unicodedata.normalize('NFKD', valor).encode('ascii', 'ignore').decode('ascii')
            if limite and len(valor) > limite:
                valor = valor[:limite - 3] + '...'
            return valor

        def dinheiro(valor):
            numero = para_float(valor)
            return f'R$ {numero:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

        class RelatorioFinanceiroPDF(FPDF):
            def header(self):
                self.set_fill_color(0, 71, 171)
                self.rect(0, 0, 297, 20, 'F')
                self.set_text_color(255, 255, 255)
                self.set_font('Helvetica', 'B', 15)
                self.set_xy(16, 6)
                self.cell(0, 8, 'Constituere | Relatorio Financeiro')
                self.set_text_color(35, 35, 35)
                self.set_y(28)

            def footer(self):
                self.set_y(-12)
                self.set_draw_color(220, 228, 238)
                self.line(16, self.get_y(), 281, self.get_y())
                self.set_y(-9)
                self.set_font('Helvetica', '', 8)
                self.set_text_color(100, 100, 100)
                self.cell(0, 5, f'Gerado em {datetime.date.today().strftime("%d/%m/%Y")} | Pagina {self.page_no()}', align='C')

        pdf = RelatorioFinanceiroPDF(orientation='L', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.set_margins(16, 16, 16)
        pdf.add_page()
        pdf.set_fill_color(237, 244, 255)
        pdf.set_text_color(0, 71, 171)
        pdf.set_font('Helvetica', 'B', 12)
        pdf.cell(265, 8, texto(f'Relatório Financeiro - {nome_escritorio}', 80), fill=True, new_x='LMARGIN', new_y='NEXT')
        pdf.set_text_color(90, 90, 90)
        pdf.set_font('Helvetica', '', 9)
        pdf.cell(0, 6, texto(f'Período: {periodo_texto}', 120), new_x='LMARGIN', new_y='NEXT')
        pdf.ln(4)
        pdf.set_fill_color(250, 252, 255)
        pdf.set_draw_color(220, 228, 238)
        for rotulo, valor in (
            ('Total de Receitas Previstas', dinheiro(resumo.get('total_receitas', 0))),
            ('Receita Recebida', dinheiro(resumo.get('receita_recebida', 0))),
            ('Receita a Receber', dinheiro(resumo.get('receita_a_receber', 0))),
            ('Despesas', dinheiro(resumo.get('despesas', 0))),
            ('Saldo Atual', dinheiro(resumo.get('saldo', 0)))
        ):
            pdf.set_text_color(0, 71, 171)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.cell(70, 8, rotulo, border=1, fill=True)
            pdf.set_text_color(35, 35, 35)
            pdf.set_font('Helvetica', '', 9)
            pdf.cell(40, 8, valor, border=1, new_x='LMARGIN', new_y='NEXT')
        pdf.ln(10)
        colunas = [('Data', 25), ('Tipo', 25), ('Descricao', 125), ('Status', 30), ('Valor', 60)]

        def cabecalho_tabela():
            pdf.set_fill_color(237, 244, 255)
            pdf.set_draw_color(220, 228, 238)
            pdf.set_text_color(0, 71, 171)
            pdf.set_font('Helvetica', 'B', 8)
            for nome, largura in colunas:
                pdf.cell(largura, 8, nome, border=1, fill=True)
            pdf.ln()
            pdf.set_text_color(35, 35, 35)

        cabecalho_tabela()
        pdf.set_font('Helvetica', '', 8)
        if not lancamentos:
            pdf.set_fill_color(250, 252, 255)
            pdf.cell(265, 9, 'Nenhum lancamento encontrado neste periodo.', border=1, fill=True, align='C', new_x='LMARGIN', new_y='NEXT')
        for indice, item in enumerate(lancamentos):
            if pdf.get_y() + 8 > 190:
                pdf.add_page()
                cabecalho_tabela()
                pdf.set_font('Helvetica', '', 8)
            data_iso = str(item.get('data') or '')
            partes = data_iso.split('-')
            data_exibir = f'{partes[2]}/{partes[1]}/{partes[0]}' if len(partes) == 3 else data_iso
            valores = [
                data_exibir,
                str(item.get('tipo') or '').capitalize(),
                texto(item.get('descricao', ''), 100),
                texto(item.get('status', '')),
                dinheiro(item.get('valor', 0))
            ]
            pdf.set_fill_color(250, 252, 255) if indice % 2 else pdf.set_fill_color(255, 255, 255)
            for (_, largura), valor in zip(colunas, valores):
                pdf.cell(largura, 7, texto(valor), border=1, fill=True)
            pdf.ln()
        return send_file(
            BytesIO(bytes(pdf.output())),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='relatorio-financeiro.pdf'
        )
    except Exception:
        print('Erro ao gerar PDF financeiro', flush=True)
        return jsonify({'error': 'Erro ao gerar relatório financeiro.'}), 500
    finally:
        cur.close()
        con.close()