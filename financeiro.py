from flask import jsonify, request
from funcao import decodificar_token, converter_data_pagamento, formatar_valor_br
from main import app
from db import conexao
import datetime


def _converter_data(valor):
    if not valor:
        return None
    if isinstance(valor, datetime.date):
        return valor
    if isinstance(valor, str):
        for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.datetime.strptime(valor, fmt).date()
            except:
                continue
    return None


def _periodo_para_datas(periodo, data_ini=None, data_fim=None):
    hoje = datetime.date.today()

    if periodo == 'mes':
        inicio = hoje.replace(day=1)
        fim = hoje
    elif periodo == 'mesAnterior':
        primeiro_mes_atual = hoje.replace(day=1)
        fim = primeiro_mes_atual - datetime.timedelta(days=1)
        inicio = fim.replace(day=1)
    elif periodo == '30dias':
        inicio = hoje - datetime.timedelta(days=30)
        fim = hoje
    elif periodo == '90dias':
        inicio = hoje - datetime.timedelta(days=90)
        fim = hoje
    elif periodo == 'personalizado':
        inicio = _converter_data(data_ini)
        fim = _converter_data(data_fim)
    else:
        inicio = hoje.replace(day=1)
        fim = hoje

    return inicio, fim


def _verificar_acesso_escritorio(cur, id_usuario, id_escritorio):
    cur.execute("""
        SELECT STATUS, ATIVO
        FROM ADVOGADO_ESCRITORIO
        WHERE ID_USUARIOS = ? AND ID_ESCRITORIOS = ?
    """, (id_usuario, id_escritorio))

    row = cur.fetchone()

    if not row:
        return False, 'Você não possui acesso a este escritório.'

    if row[1] != 1:
        return False, 'Seu acesso a este escritório está inativo.'

    return True, row[0]


def _status_parcela(data_venc, status_db, hoje, data_pagamento=None):
    status_db = (status_db or '').strip().upper()

    if data_pagamento or status_db in ('PAGA', 'PAGO', 'RECEBIDA', 'RECEBIDO', 'QUITADA', 'QUITADO'):
        return 'recebida'

    if data_venc and data_venc < hoje:
        return 'atrasado'

    return 'pendente'


def _status_lancamento_manual(tipo, status_db, data_lanc, hoje):
    tipo = (tipo or '').lower()
    status_db = (status_db or '').lower()

    if tipo == 'receita':
        if status_db in ('recebida', 'recebido', 'pago', 'paga'):
            return 'recebida'
        if data_lanc and data_lanc < hoje:
            return 'atrasado'
        return 'pendente'

    if tipo == 'despesa':
        if status_db in ('pago', 'paga', 'recebida', 'recebido'):
            return 'pago'
        if data_lanc and data_lanc < hoje:
            return 'atrasado'
        return 'pendente'

    return status_db or 'pendente'


def _dentro_periodo(data_obj, inicio, fim):
    if data_obj is None:
        return False
    if inicio and data_obj < inicio:
        return False
    if fim and data_obj > fim:
        return False
    return True


@app.route('/escritorio/<int:id_escritorio>/financeiro/lancamentos', methods=['GET'])
def listar_lancamentos_escritorio(id_escritorio):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    if token_data['tipo'] != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    id_usuario = token_data['id_usuarios']

    periodo = request.args.get('periodo', 'mes')
    tipo = (request.args.get('tipo') or 'todos').lower()
    data_ini = request.args.get('data_inicial')
    data_fim = request.args.get('data_final')

    if tipo not in ['todos', 'receita', 'despesa']:
        return jsonify({'error': 'Tipo inválido'}), 400

    inicio, fim = _periodo_para_datas(periodo, data_ini, data_fim)

    hoje = datetime.date.today()

    con = conexao()
    cur = con.cursor()

    try:
        permitido, msg = _verificar_acesso_escritorio(cur, id_usuario, id_escritorio)
        if not permitido:
            return jsonify({'error': msg}), 403

        lancamentos = []

        if tipo in ['todos', 'despesa']:
            sql_desp = """
                SELECT ID_LANCAMENTOS, TIPO, DESCRICAO, VALOR, "DATA",
                       CATEGORIA, FORMA_PAGAMENTO, STATUS, OBSERVACOES
                FROM LANCAMENTOS_FINANCEIROS
                WHERE ID_ESCRITORIO = ? AND ATIVO = 1 AND TIPO = 'despesa'
            """
            params_desp = [id_escritorio]

            if inicio:
                sql_desp += ' AND "DATA" >= ?'
                params_desp.append(inicio)

            if fim:
                sql_desp += ' AND "DATA" <= ?'
                params_desp.append(fim)

            cur.execute(sql_desp, tuple(params_desp))

            for row in cur.fetchall():
                data_lanc = row[4]
                data_obj = data_lanc.date() if hasattr(data_lanc, 'date') else data_lanc

                status_calc = _status_lancamento_manual(
                    'despesa', row[7], data_obj, hoje
                )

                lancamentos.append({
                    'id': f"lanc_{row[0]}",
                    'id_real': row[0],
                    'tipo': 'despesa',
                    'descricao': row[2],
                    'valor': float(row[3]) if row[3] else 0,
                    'data': data_lanc.strftime('%Y-%m-%d') if hasattr(data_lanc, 'strftime') else str(data_lanc),
                    'categoria': row[5] or '',
                    'forma_pagamento': row[6] or '',
                    'status': status_calc,
                    'observacoes': row[8] or '',
                    'origem': 'manual'
                })

        if tipo in ['todos', 'receita']:
            sql_receita = """
                SELECT ID_LANCAMENTOS, TIPO, DESCRICAO, VALOR, "DATA",
                       CATEGORIA, FORMA_PAGAMENTO, STATUS, OBSERVACOES
                FROM LANCAMENTOS_FINANCEIROS
                WHERE ID_ESCRITORIO = ? AND ATIVO = 1 AND TIPO = 'receita'
            """
            params_rec = [id_escritorio]

            if inicio:
                sql_receita += ' AND "DATA" >= ?'
                params_rec.append(inicio)

            if fim:
                sql_receita += ' AND "DATA" <= ?'
                params_rec.append(fim)

            cur.execute(sql_receita, tuple(params_rec))

            for row in cur.fetchall():
                data_lanc = row[4]
                data_obj = data_lanc.date() if hasattr(data_lanc, 'date') else data_lanc

                status_calc = _status_lancamento_manual(
                    'receita', row[7], data_obj, hoje
                )

                lancamentos.append({
                    'id': f"lanc_{row[0]}",
                    'id_real': row[0],
                    'tipo': 'receita',
                    'descricao': row[2],
                    'valor': float(row[3]) if row[3] else 0,
                    'data': data_lanc.strftime('%Y-%m-%d') if hasattr(data_lanc, 'strftime') else str(data_lanc),
                    'categoria': row[5] or '',
                    'forma_pagamento': row[6] or '',
                    'status': status_calc,
                    'observacoes': row[8] or '',
                    'origem': 'manual'
                })

        if tipo in ['todos', 'receita']:
            sql_parcelas = """
                SELECT
                    parc.ID_PARCELAS,
                    parc.VALOR_PARCELA,
                    parc.DATA_VENCIMENTO,
                    parc.DATA_PAGAMENTO,
                    parc.STATUS,
                    parc.NUMERO_PARCELA,
                    p.TIPO_PROCESSO,
                    p.NUM_PROCESSO,
                    u.NOME,
                    u.RAZAO_SOCIAL,
                    u.NOME_FANTASIA,
                    pag.FORM_PAGAMENTO
                FROM PARCELAS parc
                INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = parc.ID_PAGAMENTO
                INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = pag.ID_PROCESSO
                INNER JOIN USUARIOS u ON u.ID_USUARIOS = p.ID_USUARIOS_CLIENTE
                WHERE (
                    p.ID_ESCRITORIOS = ?
                    OR (
                        p.ID_ESCRITORIOS IS NULL
                        AND p.ID_USUARIOS_ADVOGADO IN (
                            SELECT ID_USUARIOS
                            FROM ADVOGADO_ESCRITORIO
                            WHERE ID_ESCRITORIOS = ? AND ATIVO = 1
                        )
                    )
                )
                AND UPPER(COALESCE(parc.STATUS, '')) <> 'CANCELADA'
            """

            cur.execute(sql_parcelas, (id_escritorio, id_escritorio))

            for row in cur.fetchall():
                id_parc = row[0]
                valor = float(row[1]) if row[1] else 0
                venc_raw = row[2]
                pag_raw = row[3]
                status_db = row[4]
                num_parc = row[5]
                tipo_proc = row[6] or 'Processo'
                num_proc = row[7] or '--'
                nome_cliente = row[8] or row[9] or row[10] or '--'
                forma = row[11] or '--'

                venc = converter_data_pagamento(venc_raw)
                pag = converter_data_pagamento(pag_raw)

                status_calc = _status_parcela(venc, status_db, hoje, pag)

                if status_calc == 'recebida':
                    data_exibir = pag if pag else venc
                else:
                    data_exibir = venc

                if not _dentro_periodo(data_exibir, inicio, fim):
                    continue

                identificacao = 'Entrada' if num_parc == 0 else f'{num_parc}ª parcela'

                lancamentos.append({
                    'id': f"parc_{id_parc}",
                    'id_real': id_parc,
                    'tipo': 'receita',
                    'descricao': f'{tipo_proc} - {identificacao} ({nome_cliente})',
                    'valor': valor,
                    'data': data_exibir.strftime('%Y-%m-%d') if data_exibir else None,
                    'categoria': 'Honorários',
                    'forma_pagamento': forma,
                    'status': status_calc,
                    'observacoes': f'Processo {num_proc}',
                    'origem': 'pagamento_cliente'
                })

        if tipo in ['todos', 'receita']:
            sql_exito = """
                SELECT
                    pe.ID_PARCELA_EXITO,
                    pe.VALOR_PARCELA,
                    pe.DATA_VENCIMENTO,
                    pe.DATA_PAGAMENTO,
                    pe.STATUS,
                    pe.NUMERO_PARCELA,
                    p.TIPO_PROCESSO,
                    p.NUM_PROCESSO,
                    u.NOME,
                    u.RAZAO_SOCIAL,
                    u.NOME_FANTASIA,
                    pag.FORM_PAGAMENTO
                FROM PARCELAS_EXITO pe
                INNER JOIN PAGAMENTO_EXITO pex ON pex.ID_PAGAMENTO_EXITO = pe.ID_PAGAMENTO_EXITO
                INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = pex.ID_PAGAMENTO
                INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = pag.ID_PROCESSO
                INNER JOIN USUARIOS u ON u.ID_USUARIOS = p.ID_USUARIOS_CLIENTE
                WHERE (
                    p.ID_ESCRITORIOS = ?
                    OR (
                        p.ID_ESCRITORIOS IS NULL
                        AND p.ID_USUARIOS_ADVOGADO IN (
                            SELECT ID_USUARIOS
                            FROM ADVOGADO_ESCRITORIO
                            WHERE ID_ESCRITORIOS = ? AND ATIVO = 1
                        )
                    )
                )
                AND UPPER(COALESCE(pe.STATUS, '')) <> 'CANCELADA'
            """

            cur.execute(sql_exito, (id_escritorio, id_escritorio))

            for row in cur.fetchall():
                id_parc = row[0]
                valor = float(row[1]) if row[1] else 0
                venc_raw = row[2]
                pag_raw = row[3]
                status_db = row[4]
                num_parc = row[5]
                tipo_proc = row[6] or 'Processo'
                num_proc = row[7] or '--'
                nome_cliente = row[8] or row[9] or row[10] or '--'
                forma = row[11] or '--'

                venc = converter_data_pagamento(venc_raw)
                pag = converter_data_pagamento(pag_raw)

                status_calc = _status_parcela(venc, status_db, hoje, pag)

                if status_calc == 'recebida':
                    data_exibir = pag if pag else venc
                else:
                    data_exibir = venc

                if not _dentro_periodo(data_exibir, inicio, fim):
                    continue

                identificacao = 'Entrada' if num_parc == 0 else f'{num_parc}ª parcela'

                lancamentos.append({
                    'id': f"exito_{id_parc}",
                    'id_real': id_parc,
                    'tipo': 'receita',
                    'descricao': f'{tipo_proc} - Êxito - {identificacao} ({nome_cliente})',
                    'valor': valor,
                    'data': data_exibir.strftime('%Y-%m-%d') if data_exibir else None,
                    'categoria': 'Honorários de êxito',
                    'forma_pagamento': forma,
                    'status': status_calc,
                    'observacoes': f'Processo {num_proc}',
                    'origem': 'pagamento_cliente'
                })

        lancamentos.sort(
            key=lambda x: x['data'] or '',
            reverse=True
        )

        return jsonify({
            'lancamentos': lancamentos,
            'quantidade': len(lancamentos),
            'periodo': {
                'inicio': inicio.strftime('%d/%m/%Y') if inicio else None,
                'fim': fim.strftime('%d/%m/%Y') if fim else None
            }
        }), 200

    except Exception as e:
        print(f'Erro ao listar lançamentos: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>/financeiro/lancamentos', methods=['POST'])
def criar_lancamento_escritorio(id_escritorio):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    if token_data['tipo'] != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    id_usuario = token_data['id_usuarios']

    if request.is_json:
        dados = request.get_json() or {}
    else:
        dados = request.form

    tipo = (dados.get('tipo') or '').strip().lower()
    descricao = (dados.get('descricao') or '').strip()
    valor_raw = dados.get('valor')
    data_raw = dados.get('data')
    status_raw = (dados.get('status') or '').strip().lower()

    if tipo not in ['despesa', 'receita']:
        return jsonify({'error': 'Tipo inválido'}), 400

    if not descricao:
        return jsonify({'error': 'Descrição é obrigatória'}), 400

    if len(descricao) > 254:
        return jsonify({'error': 'Descrição deve ter no máximo 254 caracteres'}), 400

    try:
        valor_limpo = str(valor_raw).replace('.', '').replace(',', '.')
        valor = float(valor_limpo)
    except (TypeError, ValueError):
        return jsonify({'error': 'Valor inválido'}), 400

    if valor <= 0:
        return jsonify({'error': 'Valor deve ser maior que zero'}), 400

    data_obj = _converter_data(data_raw)
    if not data_obj:
        return jsonify({'error': 'Data inválida'}), 400

    if data_obj > datetime.date.today():
        return jsonify({'error': 'A data não pode ser futura'}), 400

    if tipo == 'receita':
        if status_raw not in ['recebida', 'pendente', 'atrasado', '']:
            return jsonify({'error': 'Status inválido para receita'}), 400

        if not status_raw:
            status_raw = 'pendente'

    if tipo == 'despesa':
        if status_raw not in ['pago', 'pendente', 'atrasado', '']:
            return jsonify({'error': 'Status inválido para despesa'}), 400

        if not status_raw:
            status_raw = 'pendente'

    con = conexao()
    cur = con.cursor()

    try:
        permitido, msg = _verificar_acesso_escritorio(cur, id_usuario, id_escritorio)
        if not permitido:
            return jsonify({'error': msg}), 403

        cur.execute("""
            INSERT INTO LANCAMENTOS_FINANCEIROS (
                ID_USUARIOS_ADVOGADO,
                ID_ESCRITORIO,
                TIPO,
                DESCRICAO,
                VALOR,
                "DATA",
                STATUS,
                ATIVO
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            RETURNING ID_LANCAMENTOS
        """, (
            id_usuario,
            id_escritorio,
            tipo,
            descricao,
            valor,
            data_obj,
            status_raw
        ))

        id_lancamento = cur.fetchone()[0]

        con.commit()

        return jsonify({
            'mensagem': 'Lançamento cadastrado com sucesso',
            'id_lancamento': id_lancamento
        }), 201

    except Exception as e:
        con.rollback()
        print(f'Erro ao criar lançamento: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>/financeiro/resumo', methods=['GET'])
def resumo_financeiro_escritorio(id_escritorio):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    if token_data['tipo'] != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    id_usuario = token_data['id_usuarios']

    periodo = request.args.get('periodo', 'mes')
    data_ini = request.args.get('data_inicial')
    data_fim = request.args.get('data_final')

    inicio, fim = _periodo_para_datas(periodo, data_ini, data_fim)

    con = conexao()
    cur = con.cursor()

    hoje = datetime.date.today()

    try:
        permitido, msg = _verificar_acesso_escritorio(cur, id_usuario, id_escritorio)
        if not permitido:
            return jsonify({'error': msg}), 403

        receita_manual_recebida = 0.0
        receita_manual_pendente = 0.0
        receita_manual_atrasada = 0.0
        despesa_paga = 0.0
        despesa_pendente = 0.0
        despesa_atrasada = 0.0

        sql_manual = """
            SELECT TIPO, STATUS, VALOR, "DATA"
            FROM LANCAMENTOS_FINANCEIROS
            WHERE ID_ESCRITORIO = ? AND ATIVO = 1
        """
        params_manual = [id_escritorio]

        if inicio:
            sql_manual += ' AND "DATA" >= ?'
            params_manual.append(inicio)

        if fim:
            sql_manual += ' AND "DATA" <= ?'
            params_manual.append(fim)

        cur.execute(sql_manual, tuple(params_manual))

        for tipo, status_db, valor, data_lanc in cur.fetchall():
            v = float(valor) if valor else 0.0
            tipo = (tipo or '').lower()

            data_obj = data_lanc.date() if hasattr(data_lanc, 'date') else data_lanc

            status_calc = _status_lancamento_manual(tipo, status_db, data_obj, hoje)

            if tipo == 'receita':
                if status_calc == 'recebida':
                    receita_manual_recebida += v
                elif status_calc == 'atrasado':
                    receita_manual_atrasada += v
                else:
                    receita_manual_pendente += v

            elif tipo == 'despesa':
                if status_calc == 'pago':
                    despesa_paga += v
                elif status_calc == 'atrasado':
                    despesa_atrasada += v
                else:
                    despesa_pendente += v

        receita_parcelas_pagas = 0.0
        receita_parcelas_pendente = 0.0
        receita_parcelas_atrasada = 0.0

        sql_parcelas = """
            SELECT parc.VALOR_PARCELA, parc.DATA_VENCIMENTO, parc.STATUS, parc.DATA_PAGAMENTO
            FROM PARCELAS parc
            INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = parc.ID_PAGAMENTO
            INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = pag.ID_PROCESSO
            WHERE (
                p.ID_ESCRITORIOS = ?
                OR (
                    p.ID_ESCRITORIOS IS NULL
                    AND p.ID_USUARIOS_ADVOGADO IN (
                        SELECT ID_USUARIOS
                        FROM ADVOGADO_ESCRITORIO
                        WHERE ID_ESCRITORIOS = ? AND ATIVO = 1
                    )
                )
            )
            AND UPPER(COALESCE(parc.STATUS, '')) <> 'CANCELADA'
        """

        cur.execute(sql_parcelas, (id_escritorio, id_escritorio))

        for valor, venc_raw, status_db, pag_raw in cur.fetchall():
            v = float(valor) if valor else 0.0
            venc = converter_data_pagamento(venc_raw)
            pag = converter_data_pagamento(pag_raw)

            status_calc = _status_parcela(venc, status_db, hoje, pag)

            if status_calc == 'recebida':
                data_ref = pag if pag else venc
            else:
                data_ref = venc

            if not _dentro_periodo(data_ref, inicio, fim):
                continue

            if status_calc == 'recebida':
                receita_parcelas_pagas += v
            elif status_calc == 'atrasado':
                receita_parcelas_atrasada += v
            else:
                receita_parcelas_pendente += v

        sql_exito = """
            SELECT pe.VALOR_PARCELA, pe.DATA_VENCIMENTO, pe.STATUS, pe.DATA_PAGAMENTO
            FROM PARCELAS_EXITO pe
            INNER JOIN PAGAMENTO_EXITO pex ON pex.ID_PAGAMENTO_EXITO = pe.ID_PAGAMENTO_EXITO
            INNER JOIN PAGAMENTOS pag ON pag.ID_PAGAMENTOS = pex.ID_PAGAMENTO
            INNER JOIN PROCESSOS p ON p.ID_PROCESSOS = pag.ID_PROCESSO
            WHERE (
                p.ID_ESCRITORIOS = ?
                OR (
                    p.ID_ESCRITORIOS IS NULL
                    AND p.ID_USUARIOS_ADVOGADO IN (
                        SELECT ID_USUARIOS
                        FROM ADVOGADO_ESCRITORIO
                        WHERE ID_ESCRITORIOS = ? AND ATIVO = 1
                    )
                )
            )
            AND UPPER(COALESCE(pe.STATUS, '')) <> 'CANCELADA'
        """

        cur.execute(sql_exito, (id_escritorio, id_escritorio))

        for valor, venc_raw, status_db, pag_raw in cur.fetchall():
            v = float(valor) if valor else 0.0
            venc = converter_data_pagamento(venc_raw)
            pag = converter_data_pagamento(pag_raw)

            status_calc = _status_parcela(venc, status_db, hoje, pag)

            if status_calc == 'recebida':
                data_ref = pag if pag else venc
            else:
                data_ref = venc

            if not _dentro_periodo(data_ref, inicio, fim):
                continue

            if status_calc == 'recebida':
                receita_parcelas_pagas += v
            elif status_calc == 'atrasado':
                receita_parcelas_atrasada += v
            else:
                receita_parcelas_pendente += v

        receita_recebida = receita_manual_recebida + receita_parcelas_pagas
        receita_pendente = receita_manual_pendente + receita_parcelas_pendente
        receita_atrasada = receita_manual_atrasada + receita_parcelas_atrasada

        receita_a_receber = receita_pendente + receita_atrasada
        total_receitas = receita_recebida + receita_a_receber
        despesas = despesa_paga + despesa_pendente + despesa_atrasada

        saldo = receita_recebida - despesa_paga

        if saldo > 0:
            resultado = 'lucro'
            lucro = saldo
            prejuizo = 0.0
        elif saldo < 0:
            resultado = 'prejuizo'
            lucro = 0.0
            prejuizo = abs(saldo)
        else:
            resultado = 'neutro'
            lucro = 0.0
            prejuizo = 0.0

        percentual_recebido = (receita_recebida / total_receitas * 100) if total_receitas > 0 else 0
        percentual_arredondado = round(percentual_recebido)

        if saldo > 0 and percentual_recebido >= 70:
            situacao = 'Boa'
        elif saldo >= 0:
            situacao = 'Atenção'
        else:
            situacao = 'Crítica'

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
            'lucro': lucro,
            'prejuizo': prejuizo,
            'resultado': resultado,
            'percentual_recebido': percentual_arredondado,
            'situacao': situacao
        }), 200

    except Exception as e:
        print(f'Erro ao calcular resumo: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()