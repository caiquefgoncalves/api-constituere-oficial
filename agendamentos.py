from flask import jsonify, request
from funcao import decodificar_token, enviar_email_motivo
from main import app
from db import conexao
import datetime


def converter_data(data_texto):
    if not data_texto:
        return None

    texto = str(data_texto).strip()

    try:
        if '/' in texto:
            return datetime.datetime.strptime(texto, '%d/%m/%Y').date()
        return datetime.datetime.strptime(texto[:10], '%Y-%m-%d').date()
    except:
        return None


def converter_horario(horario_texto):
    if not horario_texto:
        return None

    texto = str(horario_texto).strip()

    if ':' not in texto:
        return None

    partes = texto.split(':')
    if len(partes) != 2:
        return None

    try:
        horas = int(partes[0])
        minutos = int(partes[1])
    except:
        return None

    if horas < 0 or horas > 23 or minutos < 0 or minutos > 59:
        return None

    return datetime.time(horas, minutos)


def horario_para_minutos(horario):
    if horario is None:
        return None

    if isinstance(horario, datetime.time):
        return horario.hour * 60 + horario.minute

    if isinstance(horario, str):
        if ':' in horario:
            partes = horario.split(':')
            return int(partes[0]) * 60 + int(partes[1])

    return None


def converter_duracao(duracao_texto):
    if duracao_texto is None or duracao_texto == '':
        return None

    texto = str(duracao_texto).strip()

    if ':' in texto:
        partes = texto.split(':')
        if len(partes) != 2:
            return None
        try:
            horas = int(partes[0])
            minutos = int(partes[1])
        except:
            return None
        if horas < 0 or minutos < 0 or minutos >= 60:
            return None
        return horas * 60 + minutos

    if texto.isdigit():
        return int(texto)

    return None


def verificar_conflito(cur, id_advogado, data_agendamento, horario_min, duracao_min, ignorar_id=None):
    sql = """
        SELECT ID_AGENDAMENTOS, HORARIO, DURACAO
        FROM AGENDAMENTOS
        WHERE DATA = ?
          AND (ID_USUARIOS_ADVOGADO_1 = ? OR ID_USUARIOS_ADVOGADO_2 = ?)
          AND UPPER(STATUS) NOT IN ('CANCELADO', 'RECUSADO')
    """

    params = [data_agendamento, id_advogado, id_advogado]

    if ignorar_id:
        sql += " AND ID_AGENDAMENTOS != ?"
        params.append(ignorar_id)

    cur.execute(sql, tuple(params))
    existentes = cur.fetchall()

    inicio_novo = horario_min
    fim_novo = horario_min + duracao_min

    for existente in existentes:
        horario_existente = existente[1]
        duracao_existente = existente[2]

        inicio_existente = horario_para_minutos(horario_existente)

        if inicio_existente is None:
            continue

        if isinstance(duracao_existente, int):
            duracao_existente_min = duracao_existente
        else:
            duracao_existente_min = converter_duracao(duracao_existente)

        if duracao_existente_min is None:
            continue

        fim_existente = inicio_existente + duracao_existente_min

        sobrepoe = (inicio_novo < fim_existente) and (fim_novo > inicio_existente)

        if sobrepoe:
            return True

    return False


@app.route('/agendamentos', methods=['POST'])
def cadastrar_agendamento():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado_logado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json()

    if not dados:
        return jsonify({'error': 'Dados não enviados'}), 400

    id_cliente = dados.get('id_cliente')
    id_advogado_2 = dados.get('id_advogado_2')
    nome_cliente = (dados.get('cliente') or '').strip()
    assunto = (dados.get('assunto') or '').strip()
    data_recebida = dados.get('data')
    horario_recebido = dados.get('horario')
    duracao_recebida = dados.get('duracao')

    if not id_cliente:
        return jsonify({'error': 'Cliente é obrigatório'}), 400

    if not assunto:
        return jsonify({'error': 'Assunto é obrigatório'}), 400

    if not data_recebida:
        return jsonify({'error': 'Data é obrigatória'}), 400

    if not horario_recebido:
        return jsonify({'error': 'Horário é obrigatório'}), 400

    if not duracao_recebida:
        return jsonify({'error': 'Duração é obrigatória'}), 400

    data_agendamento = converter_data(data_recebida)

    if data_agendamento is None:
        return jsonify({'error': 'Data inválida'}), 400

    if data_agendamento < datetime.date.today():
        return jsonify({'error': 'A data não pode ser anterior ao dia de hoje'}), 400

    horario_obj = converter_horario(horario_recebido)

    if horario_obj is None:
        return jsonify({'error': 'Horário inválido'}), 400

    duracao_min = converter_duracao(duracao_recebida)

    if duracao_min is None:
        return jsonify({'error': 'Duração inválida'}), 400

    if duracao_min <= 0:
        return jsonify({'error': 'A duração deve ser maior que 0'}), 400

    if duracao_min > 480:
        return jsonify({'error': 'A duração não pode ser maior que 8 horas'}), 400

    horario_min = horario_obj.hour * 60 + horario_obj.minute

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_USUARIOS
            FROM USUARIOS
            WHERE ID_USUARIOS = ?
              AND TIPO IN (2, 3)
              AND ATIVO = 1
              AND ID_USUARIO_RESPONSAVEL = ?
        """, (id_cliente, id_advogado_logado))

        if not cur.fetchone():
            return jsonify({'error': 'Cliente não encontrado ou não pertence a este advogado'}), 403

        if id_advogado_2:
            cur.execute("""
                SELECT ID_USUARIOS
                FROM USUARIOS
                WHERE ID_USUARIOS = ?
                  AND TIPO = 0
                  AND ATIVO = 1
            """, (id_advogado_2,))

            if not cur.fetchone():
                return jsonify({'error': 'Advogado 2 não encontrado'}), 400

        if verificar_conflito(cur, id_advogado_logado, data_agendamento, horario_min, duracao_min):
            return jsonify({'error': 'Já existe um agendamento neste dia e horário'}), 409

        if id_advogado_2:
            if verificar_conflito(cur, id_advogado_2, data_agendamento, horario_min, duracao_min):
                return jsonify({'error': 'O advogado 2 já possui agendamento neste dia e horário'}), 409

        cur.execute("""
            INSERT INTO AGENDAMENTOS (
                ID_USUARIOS_ADVOGADO_1,
                ID_USUARIOS_ADVOGADO_2,
                ID_USUARIOS_CLIENTE,
                CLIENTE,
                ASSUNTO,
                DATA,
                HORARIO,
                DURACAO,
                STATUS,
                DATA_CADASTRO
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID_AGENDAMENTOS
        """, (
            id_advogado_logado,
            id_advogado_2 if id_advogado_2 else None,
            id_cliente,
            nome_cliente if nome_cliente else '--',
            assunto,
            data_agendamento,
            horario_obj,
            duracao_min,
            'a_confirmar',
            datetime.datetime.now()
        ))

        id_agendamento = cur.fetchone()[0]
        con.commit()

        return jsonify({
            'mensagem': 'Agendamento cadastrado com sucesso',
            'id_agendamento': id_agendamento
        }), 201

    except Exception as e:
        con.rollback()
        print('Erro ao cadastrar agendamento:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/agendamentos', methods=['GET'])
def listar_agendamentos():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    data_inicio_recebida = request.args.get('data_inicio')
    data_fim_recebida = request.args.get('data_fim')
    filtro_status = (request.args.get('status') or '').strip()

    con = conexao()
    cur = con.cursor()

    meses_pt = {
        1: 'JAN', 2: 'FEV', 3: 'MAR', 4: 'ABR',
        5: 'MAI', 6: 'JUN', 7: 'JUL', 8: 'AGO',
        9: 'SET', 10: 'OUT', 11: 'NOV', 12: 'DEZ'
    }

    try:
        sql = """
            SELECT
                a.ID_AGENDAMENTOS,
                a.ID_USUARIOS_ADVOGADO_1,
                a.ID_USUARIOS_ADVOGADO_2,
                a.ID_USUARIOS_CLIENTE,
                a.CLIENTE,
                a.ASSUNTO,
                a.DATA,
                a.HORARIO,
                a.DURACAO,
                a.STATUS,
                a.MOTIVO
            FROM AGENDAMENTOS a
            WHERE (a.ID_USUARIOS_ADVOGADO_1 = ? OR a.ID_USUARIOS_ADVOGADO_2 = ?)
        """

        parametros = [id_advogado, id_advogado]

        if data_inicio_recebida:
            data_inicio = converter_data(data_inicio_recebida)
            if data_inicio:
                sql += " AND a.DATA >= ?"
                parametros.append(data_inicio)

        if data_fim_recebida:
            data_fim = converter_data(data_fim_recebida)
            if data_fim:
                sql += " AND a.DATA <= ?"
                parametros.append(data_fim)

        if filtro_status and filtro_status.lower() != 'todos':
            sql += " AND LOWER(a.STATUS) = ?"
            parametros.append(filtro_status.lower())

        sql += " ORDER BY a.DATA ASC, a.HORARIO ASC"

        cur.execute(sql, tuple(parametros))
        rows = cur.fetchall()

        agendamentos = []

        for row in rows:
            data_agendamento = row[6]
            horario = row[7]
            duracao = row[8]

            if hasattr(data_agendamento, 'strftime'):
                data_formatada = data_agendamento.strftime('%d/%m/%Y')
                data_iso = data_agendamento.strftime('%Y-%m-%d')
                dia = data_agendamento.strftime('%d')
                mes = meses_pt.get(data_agendamento.month, data_agendamento.strftime('%b').upper())
            else:
                data_formatada = str(data_agendamento)
                data_iso = str(data_agendamento)
                dia = '--'
                mes = '--'

            if isinstance(horario, datetime.time):
                horario_formatado = horario.strftime('%H:%M')
            else:
                horario_formatado = str(horario)[:5] if horario else '--'

            if isinstance(duracao, int):
                horas = duracao // 60
                minutos = duracao % 60
                duracao_formatada = f"{horas:02d}:{minutos:02d}"
            else:
                duracao_formatada = str(duracao)

            agendamentos.append({
                'id': row[0],
                'id_advogado_1': row[1],
                'id_advogado_2': row[2],
                'id_cliente': row[3],
                'cliente': row[4] or '--',
                'assunto': row[5] or '--',
                'data': data_formatada,
                'data_iso': data_iso,
                'dia': dia,
                'mes': mes,
                'horario': horario_formatado,
                'duracao': duracao_formatada,
                'duracao_minutos': duracao,
                'status': row[9] or '--',
                'motivo': row[10] or ''
            })

        return jsonify({
            'agendamentos': agendamentos,
            'quantidade': len(agendamentos)
        }), 200

    except Exception as e:
        print('Erro ao listar agendamentos:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/agendamento/<int:id_agendamento>', methods=['PUT'])
def editar_agendamento(id_agendamento):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json()

    if not dados:
        return jsonify({'error': 'Dados não enviados'}), 400

    id_cliente = dados.get('id_cliente')
    id_advogado_2 = dados.get('id_advogado_2')
    nome_cliente = (dados.get('cliente') or '').strip()
    assunto = (dados.get('assunto') or '').strip()
    data_recebida = dados.get('data')
    horario_recebido = dados.get('horario')
    duracao_recebida = dados.get('duracao')

    if not assunto:
        return jsonify({'error': 'Assunto é obrigatório'}), 400

    if not data_recebida:
        return jsonify({'error': 'Data é obrigatória'}), 400

    if not horario_recebido:
        return jsonify({'error': 'Horário é obrigatório'}), 400

    if not duracao_recebida:
        return jsonify({'error': 'Duração é obrigatória'}), 400

    data_agendamento = converter_data(data_recebida)

    if data_agendamento is None:
        return jsonify({'error': 'Data inválida'}), 400

    if data_agendamento < datetime.date.today():
        return jsonify({'error': 'A data não pode ser anterior ao dia de hoje'}), 400

    horario_obj = converter_horario(horario_recebido)

    if horario_obj is None:
        return jsonify({'error': 'Horário inválido'}), 400

    duracao_min = converter_duracao(duracao_recebida)

    if duracao_min is None:
        return jsonify({'error': 'Duração inválida'}), 400

    if duracao_min <= 0:
        return jsonify({'error': 'A duração deve ser maior que 0'}), 400

    if duracao_min > 480:
        return jsonify({'error': 'A duração não pode ser maior que 8 horas'}), 400

    horario_min = horario_obj.hour * 60 + horario_obj.minute

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_AGENDAMENTOS
            FROM AGENDAMENTOS
            WHERE ID_AGENDAMENTOS = ?
              AND (ID_USUARIOS_ADVOGADO_1 = ? OR ID_USUARIOS_ADVOGADO_2 = ?)
        """, (id_agendamento, id_advogado, id_advogado))

        if not cur.fetchone():
            return jsonify({'error': 'Agendamento não encontrado'}), 404

        if id_cliente:
            cur.execute("""
                SELECT ID_USUARIOS
                FROM USUARIOS
                WHERE ID_USUARIOS = ?
                  AND TIPO IN (2, 3)
                  AND ATIVO = 1
                  AND ID_USUARIO_RESPONSAVEL = ?
            """, (id_cliente, id_advogado))

            if not cur.fetchone():
                return jsonify({'error': 'Cliente não encontrado ou não pertence a este advogado'}), 403

        if id_advogado_2:
            cur.execute("""
                SELECT ID_USUARIOS
                FROM USUARIOS
                WHERE ID_USUARIOS = ?
                  AND TIPO = 0
                  AND ATIVO = 1
            """, (id_advogado_2,))

            if not cur.fetchone():
                return jsonify({'error': 'Advogado 2 não encontrado'}), 400

        if verificar_conflito(cur, id_advogado, data_agendamento, horario_min, duracao_min, ignorar_id=id_agendamento):
            return jsonify({'error': 'Já existe um agendamento neste dia e horário'}), 409

        if id_advogado_2:
            if verificar_conflito(cur, id_advogado_2, data_agendamento, horario_min, duracao_min, ignorar_id=id_agendamento):
                return jsonify({'error': 'O advogado 2 já possui agendamento neste dia e horário'}), 409

        cur.execute("""
            UPDATE AGENDAMENTOS
            SET ID_USUARIOS_ADVOGADO_2 = ?,
                ID_USUARIOS_CLIENTE = ?,
                CLIENTE = ?,
                ASSUNTO = ?,
                DATA = ?,
                HORARIO = ?,
                DURACAO = ?
            WHERE ID_AGENDAMENTOS = ?
        """, (
            id_advogado_2 if id_advogado_2 else None,
            id_cliente if id_cliente else None,
            nome_cliente if nome_cliente else '--',
            assunto,
            data_agendamento,
            horario_obj,
            duracao_min,
            id_agendamento
        ))

        con.commit()

        return jsonify({'mensagem': 'Agendamento atualizado com sucesso'}), 200

    except Exception as e:
        con.rollback()
        print('Erro ao editar agendamento:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/agendamento/<int:id_agendamento>/confirmar', methods=['PUT'])
def confirmar_agendamento(id_agendamento):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_AGENDAMENTOS
            FROM AGENDAMENTOS
            WHERE ID_AGENDAMENTOS = ?
              AND (ID_USUARIOS_ADVOGADO_1 = ? OR ID_USUARIOS_ADVOGADO_2 = ?)
        """, (id_agendamento, id_advogado, id_advogado))

        if not cur.fetchone():
            return jsonify({'error': 'Agendamento não encontrado'}), 404

        cur.execute("""
            UPDATE AGENDAMENTOS
            SET STATUS = 'confirmado'
            WHERE ID_AGENDAMENTOS = ?
        """, (id_agendamento,))

        con.commit()

        return jsonify({'mensagem': 'Agendamento confirmado com sucesso'}), 200

    except Exception as e:
        con.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/agendamento/<int:id_agendamento>/cancelar', methods=['PUT'])
def cancelar_agendamento(id_agendamento):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json() or {}
    motivo = (dados.get('motivo') or '').strip()

    if not motivo:
        return jsonify({'error': 'Motivo é obrigatório'}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                a.ID_AGENDAMENTOS,
                a.CLIENTE,
                a.DATA,
                a.HORARIO,
                a.ASSUNTO,
                u.EMAIL,
                adv.NOME
            FROM AGENDAMENTOS a
            INNER JOIN USUARIOS u ON u.ID_USUARIOS = a.ID_USUARIOS_CLIENTE
            INNER JOIN USUARIOS adv ON adv.ID_USUARIOS = a.ID_USUARIOS_ADVOGADO_1
            WHERE a.ID_AGENDAMENTOS = ?
              AND (a.ID_USUARIOS_ADVOGADO_1 = ? OR a.ID_USUARIOS_ADVOGADO_2 = ?)
        """, (id_agendamento, id_advogado, id_advogado))

        agendamento = cur.fetchone()

        if not agendamento:
            return jsonify({'error': 'Agendamento não encontrado'}), 404

        nome_cliente = agendamento[1] or '--'
        data_ag = agendamento[2]
        horario_ag = agendamento[3]
        assunto_ag = agendamento[4] or '--'
        email_cliente = agendamento[5]
        nome_advogado = agendamento[6] or '--'

        if hasattr(data_ag, 'strftime'):
            data_formatada = data_ag.strftime('%d/%m/%Y')
        else:
            data_formatada = str(data_ag)

        if isinstance(horario_ag, datetime.time):
            horario_formatado = horario_ag.strftime('%H:%M')
        else:
            horario_formatado = str(horario_ag)[:5]

        cur.execute("""
            UPDATE AGENDAMENTOS
            SET STATUS = 'cancelado',
                MOTIVO = ?
            WHERE ID_AGENDAMENTOS = ?
        """, (motivo, id_agendamento))

        con.commit()

        if email_cliente:
            enviar_email_motivo(
                destinatario=email_cliente,
                assunto='Agendamento desmarcado - Constituere',
                nome_cliente=nome_cliente,
                nome_advogado=nome_advogado,
                data_agendamento=data_formatada,
                horario_agendamento=horario_formatado,
                assunto_agendamento=assunto_ag,
                motivo=motivo,
                tipo='desmarcado'
            )

        return jsonify({'mensagem': 'Agendamento cancelado com sucesso'}), 200

    except Exception as e:
        con.rollback()
        print('Erro ao cancelar agendamento:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/agendamento/<int:id_agendamento>/recusar', methods=['PUT'])
def recusar_agendamento(id_agendamento):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json() or {}
    motivo = (dados.get('motivo') or '').strip()

    if not motivo:
        return jsonify({'error': 'Motivo é obrigatório'}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                a.ID_AGENDAMENTOS,
                a.CLIENTE,
                a.DATA,
                a.HORARIO,
                a.ASSUNTO,
                u.EMAIL,
                adv.NOME
            FROM AGENDAMENTOS a
            INNER JOIN USUARIOS u ON u.ID_USUARIOS = a.ID_USUARIOS_CLIENTE
            INNER JOIN USUARIOS adv ON adv.ID_USUARIOS = a.ID_USUARIOS_ADVOGADO_1
            WHERE a.ID_AGENDAMENTOS = ?
              AND (a.ID_USUARIOS_ADVOGADO_1 = ? OR a.ID_USUARIOS_ADVOGADO_2 = ?)
        """, (id_agendamento, id_advogado, id_advogado))

        agendamento = cur.fetchone()

        if not agendamento:
            return jsonify({'error': 'Agendamento não encontrado'}), 404

        nome_cliente = agendamento[1] or '--'
        data_ag = agendamento[2]
        horario_ag = agendamento[3]
        assunto_ag = agendamento[4] or '--'
        email_cliente = agendamento[5]
        nome_advogado = agendamento[6] or '--'

        if hasattr(data_ag, 'strftime'):
            data_formatada = data_ag.strftime('%d/%m/%Y')
        else:
            data_formatada = str(data_ag)

        if isinstance(horario_ag, datetime.time):
            horario_formatado = horario_ag.strftime('%H:%M')
        else:
            horario_formatado = str(horario_ag)[:5]

        cur.execute("""
            UPDATE AGENDAMENTOS
            SET STATUS = 'recusado',
                MOTIVO = ?
            WHERE ID_AGENDAMENTOS = ?
        """, (motivo, id_agendamento))

        con.commit()

        if email_cliente:
            enviar_email_motivo(
                destinatario=email_cliente,
                assunto='Agendamento recusado - Constituere',
                nome_cliente=nome_cliente,
                nome_advogado=nome_advogado,
                data_agendamento=data_formatada,
                horario_agendamento=horario_formatado,
                assunto_agendamento=assunto_ag,
                motivo=motivo,
                tipo='recusado'
            )

        return jsonify({'mensagem': 'Agendamento recusado com sucesso'}), 200

    except Exception as e:
        con.rollback()
        print('Erro ao recusar agendamento:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()