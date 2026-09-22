from flask import jsonify, request
from funcao import (
    decodificar_token,
    enviar_email_agendamento_criado,
    enviar_email_agendamento_reagendado,
    enviar_email_um_advogado_confirmado,
    enviar_email_dois_advogados,
    enviar_email_um_advogado,
    enviar_email_agendamento_cancelado
)
from db import conexao
from main import app, socketio
import datetime
import concurrent.futures


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


def buscar_conflito(cur, id_advogado, data_agendamento, horario_min, duracao_min, ignorar_id=None):
    data_anterior = data_agendamento - datetime.timedelta(days=1)
    data_posterior = data_agendamento + datetime.timedelta(days=1)

    sql = """
          SELECT ID_AGENDAMENTOS, DATA, HORARIO, DURACAO
          FROM AGENDAMENTOS
          WHERE DATA BETWEEN ? AND ?
            AND (ID_USUARIOS_ADVOGADO_1 = ? OR ID_USUARIOS_ADVOGADO_2 = ?)
            AND UPPER(STATUS) NOT IN ('CANCELADO', 'RECUSADO') \
          """

    params = [data_anterior, data_posterior, id_advogado, id_advogado]

    if ignorar_id:
        sql += " AND ID_AGENDAMENTOS != ?"
        params.append(ignorar_id)

    cur.execute(sql, tuple(params))
    existentes = cur.fetchall()

    inicio_novo = (
            datetime.datetime.combine(data_agendamento, datetime.time(0, 0))
            + datetime.timedelta(minutes=horario_min)
    )
    fim_novo = inicio_novo + datetime.timedelta(minutes=duracao_min)

    for existente in existentes:
        id_existente = existente[0]
        data_existente = existente[1]
        horario_existente = existente[2]
        duracao_existente = existente[3]

        inicio_existente_min = horario_para_minutos(horario_existente)

        if inicio_existente_min is None:
            continue

        if isinstance(duracao_existente, int):
            duracao_existente_min = duracao_existente
        else:
            duracao_existente_min = converter_duracao(duracao_existente)

        if duracao_existente_min is None:
            continue

        inicio_existente = (
                datetime.datetime.combine(data_existente, datetime.time(0, 0))
                + datetime.timedelta(minutes=inicio_existente_min)
        )
        fim_existente = inicio_existente + datetime.timedelta(minutes=duracao_existente_min)

        if (inicio_novo < fim_existente) and (fim_novo > inicio_existente):
            if hasattr(data_existente, 'strftime'):
                data_fmt = data_existente.strftime('%d/%m/%Y')
            else:
                data_fmt = str(data_existente)

            if isinstance(horario_existente, datetime.time):
                horario_fmt = horario_existente.strftime('%H:%M')
            else:
                horario_fmt = str(horario_existente)[:5]

            return {
                'id': id_existente,
                'data': data_fmt,
                'horario': horario_fmt,
                'duracao_minutos': duracao_existente_min,
                'duracao_formatada': f"{duracao_existente_min // 60:02d}:{duracao_existente_min % 60:02d}"
            }

    return None


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

    if id_advogado_2:
        try:
            id_advogado_2 = int(id_advogado_2)
        except (ValueError, TypeError):
            return jsonify({'error': 'Advogado 2 inválido'}), 400

        if id_advogado_2 == id_advogado_logado:
            return jsonify({'error': 'O segundo advogado não pode ser o mesmo advogado logado'}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
                    SELECT ID_USUARIOS, NOME
                    FROM USUARIOS
                    WHERE ID_USUARIOS = ?
                      AND TIPO IN (2, 3)
                      AND ATIVO = 1
                      AND ID_USUARIO_RESPONSAVEL = ?
                    """, (id_cliente, id_advogado_logado))

        cliente = cur.fetchone()

        if not cliente:
            return jsonify({'error': 'Cliente não encontrado ou não pertence a este advogado'}), 403

        if not nome_cliente:
            nome_cliente = cliente[1] or '--'

        nome_advogado_2 = None

        if id_advogado_2:
            cur.execute("""
                        SELECT ID_USUARIOS, NOME
                        FROM USUARIOS
                        WHERE ID_USUARIOS = ?
                          AND TIPO = 0
                          AND ATIVO = 1
                        """, (id_advogado_2,))

            advogado_2 = cur.fetchone()

            if not advogado_2:
                return jsonify({'error': 'Advogado 2 não encontrado'}), 400

            nome_advogado_2 = advogado_2[1] or 'Advogado'

        conflito = buscar_conflito(
            cur,
            id_advogado_logado,
            data_agendamento,
            horario_min,
            duracao_min
        )

        if conflito:
            return jsonify({
                'error': f'Já existe um agendamento neste período: {conflito["data"]} às {conflito["horario"]} (duração {conflito["duracao_formatada"]}). Escolha outro horário ou ajuste a duração.',
                'conflito': conflito
            }), 409

        if id_advogado_2:
            conflito_2 = buscar_conflito(
                cur,
                id_advogado_2,
                data_agendamento,
                horario_min,
                duracao_min
            )

            if conflito_2:
                return jsonify({
                    'error': f'O advogado 2 já possui agendamento neste período: {conflito_2["data"]} às {conflito_2["horario"]} (duração {conflito_2["duracao_formatada"]}).',
                    'conflito': conflito_2
                }), 409

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
                        DATA_CADASTRO,
                        CONFIRMADO_ADVOGADO_1,
                        CONFIRMADO_ADVOGADO_2,
                        RECUSADO_ADVOGADO_1,
                        RECUSADO_ADVOGADO_2
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        RETURNING ID_AGENDAMENTOS
                    """, (
                        id_advogado_logado,
                        id_advogado_2 if id_advogado_2 else None,
                        id_cliente,
                        nome_cliente,
                        assunto,
                        data_agendamento,
                        horario_obj,
                        duracao_min,
                        'a_confirmar',
                        datetime.datetime.now(),
                        0,
                        0,
                        0,
                        0
                    ))

        id_agendamento = cur.fetchone()[0]

        id_notificacao = None
        titulo_notificacao = None
        mensagem_notificacao = None

        if id_advogado_2:
            cur.execute("""
                        SELECT NOME
                        FROM USUARIOS
                        WHERE ID_USUARIOS = ?
                        """, (id_advogado_logado,))

            resultado_advogado_1 = cur.fetchone()
            nome_advogado_1 = resultado_advogado_1[0] if resultado_advogado_1 else 'Outro advogado'

            data_formatada = data_agendamento.strftime('%d/%m/%Y')
            horario_formatado = horario_obj.strftime('%H:%M')

            titulo_notificacao = 'Novo agendamento'

            mensagem_notificacao = (
                f'{nome_advogado_1} adicionou você '
                f'a um agendamento com {nome_cliente} '
                f'para o dia {data_formatada} às {horario_formatado}.'
            )

            cur.execute("""
                        INSERT INTO NOTIFICACOES (ID_USUARIOS, TIPO, TITULO, MENSAGEM)
                        VALUES (?, ?, ?, ?)
                            RETURNING ID_NOTIFICACAO
                        """, (id_advogado_2, 'NOVO_AGENDAMENTO', titulo_notificacao, mensagem_notificacao))

            id_notificacao = cur.fetchone()[0]

        con.commit()

        if id_notificacao and id_advogado_2:
            agora = datetime.datetime.now()

            socketio.emit(
                'nova_notificacao',
                {
                    'id': id_notificacao,
                    'tipo': 'NOVO_AGENDAMENTO',
                    'titulo': titulo_notificacao,
                    'mensagem': mensagem_notificacao,
                    'lida': False,
                    'data_criacao': agora.strftime('%d/%m/%Y'),
                    'hora_criacao': agora.strftime('%H:%M'),
                    'data_leitura': None,
                    'id_agendamento': id_agendamento
                },
                room=f'usuario_{id_advogado_2}'
            )

        try:
            cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado_logado,))
            row_adv_1 = cur.fetchone()
            nome_adv_1_email = row_adv_1[0] if row_adv_1 else 'Advogado'

            cur.execute("SELECT EMAIL FROM USUARIOS WHERE ID_USUARIOS = ?", (id_cliente,))
            row_email_cliente = cur.fetchone()

            if row_email_cliente and row_email_cliente[0]:
                email_cliente = row_email_cliente[0]
                data_fmt_email = data_agendamento.strftime('%d/%m/%Y')
                horario_fmt_email = horario_obj.strftime('%H:%M')

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    executor.submit(
                        enviar_email_agendamento_criado,
                        email_cliente,
                        nome_cliente,
                        nome_adv_1_email,
                        data_fmt_email,
                        horario_fmt_email,
                        assunto
                    )

                print(f"Solicitação de e-mail (novo agendamento) criada para {email_cliente}")
        except Exception as e:
            print(f"Erro ao agendar e-mail (novo agendamento): {e}")

        return jsonify({
            'mensagem': 'Agendamento cadastrado com sucesso',
            'id_agendamento': id_agendamento,
            'status': 'a_confirmar',
            'advogado_1': {'id': id_advogado_logado, 'confirmado': False, 'recusado': False},
            'advogado_2': (
                {'id': id_advogado_2, 'nome': nome_advogado_2, 'confirmado': False, 'recusado': False}
                if id_advogado_2
                else None
            ),
            'respostas': {
                'respondidos': 0,
                'necessarios': 2 if id_advogado_2 else 1,
                'confirmados': 0,
                'recusados': 0,
                'texto': '0/2' if id_advogado_2 else '0/1'
            }
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
    limite_recebido = request.args.get('limite')

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
                  a.MOTIVO,
                  a.CONFIRMADO_ADVOGADO_1,
                  a.CONFIRMADO_ADVOGADO_2,
                  a.RECUSADO_ADVOGADO_1,
                  a.RECUSADO_ADVOGADO_2
              FROM AGENDAMENTOS a
              WHERE (a.ID_USUARIOS_ADVOGADO_1 = ? OR a.ID_USUARIOS_ADVOGADO_2 = ?) \
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

        if limite_recebido:
            try:
                limite = int(limite_recebido)
                if limite > 0:
                    sql = sql.replace("SELECT", f"SELECT FIRST {limite}", 1)
            except:
                pass

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
                duracao_formatada = f'{horas:02d}:{minutos:02d}'
            else:
                duracao_formatada = str(duracao)

            confirmado_advogado_1 = row[11] == 1
            confirmado_advogado_2 = row[12] == 1
            recusado_advogado_1 = row[13] == 1
            recusado_advogado_2 = row[14] == 1

            tem_segundo_advogado = row[2] is not None
            total_advogados = 2 if tem_segundo_advogado else 1

            total_confirmados = int(confirmado_advogado_1) + (int(confirmado_advogado_2) if tem_segundo_advogado else 0)
            total_recusados = int(recusado_advogado_1) + (int(recusado_advogado_2) if tem_segundo_advogado else 0)
            total_respostas = total_confirmados + total_recusados

            total_necessario_confirmacao = total_advogados - total_recusados
            if total_necessario_confirmacao < 0:
                total_necessario_confirmacao = 0

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
                'motivo': row[10] or '',
                'confirmado_advogado_1': confirmado_advogado_1,
                'confirmado_advogado_2': (confirmado_advogado_2 if tem_segundo_advogado else None),
                'recusado_advogado_1': recusado_advogado_1,
                'recusado_advogado_2': (recusado_advogado_2 if tem_segundo_advogado else None),
                'confirmacoes': {
                    'confirmados': total_confirmados,
                    'necessarios': total_necessario_confirmacao,
                    'texto': f'{total_confirmados}/{total_necessario_confirmacao}'
                },
                'respostas': {
                    'respondidos': total_respostas,
                    'necessarios': total_advogados,
                    'confirmados': total_confirmados,
                    'recusados': total_recusados,
                    'texto': f'{total_respostas}/{total_advogados}'
                }
            })

        return jsonify({'agendamentos': agendamentos, 'quantidade': len(agendamentos)}), 200

    except Exception as e:
        print('Erro ao listar agendamentos:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/escritorio/<int:id_escritorio>/agendamentos', methods=['GET'])
def listar_agendamentos_escritorio(id_escritorio):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_usuario_logado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    limite_recebido = request.args.get('limite')

    con = conexao()
    cur = con.cursor()

    meses_pt = {
        1: 'JAN', 2: 'FEV', 3: 'MAR', 4: 'ABR',
        5: 'MAI', 6: 'JUN', 7: 'JUL', 8: 'AGO',
        9: 'SET', 10: 'OUT', 11: 'NOV', 12: 'DEZ'
    }

    try:
        cur.execute("""
                    SELECT 1 FROM ADVOGADO_ESCRITORIO
                    WHERE ID_USUARIOS = ? AND ID_ESCRITORIOS = ?
                    """, (id_usuario_logado, id_escritorio))

        if not cur.fetchone():
            return jsonify({'error': 'Você não possui acesso a este escritório'}), 403

        cur.execute("""
                    SELECT ID_USUARIOS FROM ADVOGADO_ESCRITORIO
                    WHERE ID_ESCRITORIOS = ?
                    """, (id_escritorio,))

        ids_advogados = [row[0] for row in cur.fetchall()]

        if not ids_advogados:
            return jsonify({'agendamentos': [], 'quantidade': 0}), 200

        placeholders = ','.join(['?'] * len(ids_advogados))

        sql = f"""
            SELECT
                a.ID_AGENDAMENTOS, a.CLIENTE, a.ASSUNTO,
                a.DATA, a.HORARIO, a.DURACAO, a.STATUS
            FROM AGENDAMENTOS a
            WHERE (a.ID_USUARIOS_ADVOGADO_1 IN ({placeholders})
                OR a.ID_USUARIOS_ADVOGADO_2 IN ({placeholders}))
              AND a.DATA >= ?
              AND UPPER(a.STATUS) NOT IN ('CANCELADO', 'RECUSADO')
            ORDER BY a.DATA ASC, a.HORARIO ASC
        """

        params = list(ids_advogados) + list(ids_advogados) + [datetime.date.today()]

        if limite_recebido:
            try:
                limite = int(limite_recebido)
                if limite > 0:
                    sql = sql.replace("SELECT", f"SELECT FIRST {limite}", 1)
            except:
                pass

        cur.execute(sql, tuple(params))
        rows = cur.fetchall()

        agendamentos = []

        for row in rows:
            data_agendamento = row[3]
            horario = row[4]
            duracao = row[5]

            if hasattr(data_agendamento, 'strftime'):
                data_formatada = data_agendamento.strftime('%d/%m/%Y')
                dia = data_agendamento.strftime('%d')
                mes = meses_pt.get(data_agendamento.month, data_agendamento.strftime('%b').upper())
            else:
                data_formatada = str(data_agendamento)
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
                'cliente': row[1] or '--',
                'assunto': row[2] or '--',
                'data': data_formatada,
                'dia': dia,
                'mes': mes,
                'horario': horario_formatado,
                'duracao': duracao_formatada,
                'status': row[6] or '--'
            })

        return jsonify({'agendamentos': agendamentos, 'quantidade': len(agendamentos)}), 200

    except Exception as e:
        print('Erro ao listar agendamentos do escritório:', e)
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
                        SELECT ID_USUARIOS FROM USUARIOS
                        WHERE ID_USUARIOS = ?
                          AND TIPO IN (2, 3)
                          AND ATIVO = 1
                          AND ID_USUARIO_RESPONSAVEL = ?
                        """, (id_cliente, id_advogado))

            if not cur.fetchone():
                return jsonify({'error': 'Cliente não encontrado ou não pertence a este advogado'}), 403

        if id_advogado_2:
            cur.execute("""
                        SELECT ID_USUARIOS FROM USUARIOS
                        WHERE ID_USUARIOS = ? AND TIPO = 0 AND ATIVO = 1
                        """, (id_advogado_2,))

            if not cur.fetchone():
                return jsonify({'error': 'Advogado 2 não encontrado'}), 400

        conflito = buscar_conflito(cur, id_advogado, data_agendamento, horario_min, duracao_min, ignorar_id=id_agendamento)

        if conflito:
            return jsonify({
                'error': f'Já existe um agendamento neste período: {conflito["data"]} às {conflito["horario"]} (duração {conflito["duracao_formatada"]}). Escolha outro horário ou ajuste a duração.',
                'conflito': conflito
            }), 409

        if id_advogado_2:
            conflito_2 = buscar_conflito(cur, id_advogado_2, data_agendamento, horario_min, duracao_min, ignorar_id=id_agendamento)

            if conflito_2:
                return jsonify({
                    'error': f'O advogado 2 já possui agendamento neste período: {conflito_2["data"]} às {conflito_2["horario"]} (duração {conflito_2["duracao_formatada"]}).',
                    'conflito': conflito_2
                }), 409

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

        try:
            eh_um_advogado = not id_advogado_2

            cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado,))
            row_adv = cur.fetchone()
            nome_adv = row_adv[0] if row_adv else 'Advogado'

            cur.execute("""
                        SELECT u.EMAIL, a.ASSUNTO
                        FROM AGENDAMENTOS a
                                 INNER JOIN USUARIOS u ON u.ID_USUARIOS = a.ID_USUARIOS_CLIENTE
                        WHERE a.ID_AGENDAMENTOS = ?
                        """, (id_agendamento,))

            info = cur.fetchone()

            if info and info[0]:
                email_cliente = info[0]
                assunto_ag = info[1] or 'Consulta'

                data_fmt = data_agendamento.strftime('%d/%m/%Y')
                horario_fmt = horario_obj.strftime('%H:%M')

                if eh_um_advogado:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        executor.submit(
                            enviar_email_agendamento_reagendado,
                            email_cliente,
                            nome_cliente,
                            nome_adv,
                            data_fmt,
                            horario_fmt,
                            assunto_ag
                        )
                    print(f"Solicitação de e-mail (reagendado - único) criada para {email_cliente}")
                else:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        executor.submit(
                            enviar_email_agendamento_criado,
                            email_cliente,
                            nome_cliente,
                            nome_adv,
                            data_fmt,
                            horario_fmt,
                            assunto_ag
                        )
                    print(f"Solicitação de e-mail (agendamento editado - com advogado 2) criada para {email_cliente}")
        except Exception as e:
            print(f"Erro ao agendar e-mail (editar): {e}")

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
                    SELECT
                        ID_USUARIOS_ADVOGADO_1,
                        ID_USUARIOS_ADVOGADO_2,
                        CLIENTE,
                        DATA,
                        HORARIO,
                        CONFIRMADO_ADVOGADO_1,
                        CONFIRMADO_ADVOGADO_2,
                        RECUSADO_ADVOGADO_1,
                        RECUSADO_ADVOGADO_2,
                        STATUS
                    FROM AGENDAMENTOS
                    WHERE ID_AGENDAMENTOS = ?
                      AND (ID_USUARIOS_ADVOGADO_1 = ? OR ID_USUARIOS_ADVOGADO_2 = ?)
                    """, (id_agendamento, id_advogado, id_advogado))

        agendamento = cur.fetchone()

        if not agendamento:
            return jsonify({'error': 'Agendamento não encontrado'}), 404

        id_advogado_1 = agendamento[0]
        id_advogado_2 = agendamento[1]
        nome_cliente = agendamento[2] or '--'
        data_agendamento = agendamento[3]
        horario_agendamento = agendamento[4]

        confirmado_1 = agendamento[5] or 0
        confirmado_2 = agendamento[6] or 0
        recusado_1 = agendamento[7] or 0
        recusado_2 = agendamento[8] or 0
        status_atual = agendamento[9]

        if hasattr(data_agendamento, 'strftime'):
            data_formatada = data_agendamento.strftime('%d/%m/%Y')
        else:
            data_formatada = str(data_agendamento)

        if isinstance(horario_agendamento, datetime.time):
            horario_formatado = horario_agendamento.strftime('%H:%M')
        else:
            horario_formatado = str(horario_agendamento)[:5]

        if status_atual == 'cancelado':
            return jsonify({'error': 'Este agendamento está cancelado'}), 400

        if id_advogado == id_advogado_1:
            if confirmado_1 == 1:
                return jsonify({'error': 'Você já confirmou este agendamento'}), 400

            if recusado_1 == 1:
                return jsonify({'error': 'Você já recusou este agendamento'}), 400

            cur.execute("""
                        UPDATE AGENDAMENTOS SET CONFIRMADO_ADVOGADO_1 = 1
                        WHERE ID_AGENDAMENTOS = ?
                        """, (id_agendamento,))

            confirmado_1 = 1

        elif id_advogado_2 and id_advogado == id_advogado_2:
            if confirmado_2 == 1:
                return jsonify({'error': 'Você já confirmou este agendamento'}), 400

            if recusado_2 == 1:
                return jsonify({'error': 'Você já recusou este agendamento'}), 400

            cur.execute("""
                        UPDATE AGENDAMENTOS SET CONFIRMADO_ADVOGADO_2 = 1
                        WHERE ID_AGENDAMENTOS = ?
                        """, (id_agendamento,))

            confirmado_2 = 1

        total_advogados = 2 if id_advogado_2 else 1

        total_confirmados = int(confirmado_1 == 1) + (int(confirmado_2 == 1) if id_advogado_2 else 0)
        total_recusados = int(recusado_1 == 1) + (int(recusado_2 == 1) if id_advogado_2 else 0)
        total_respostas = total_confirmados + total_recusados

        if total_respostas < total_advogados:
            novo_status = 'a_confirmar'
        elif total_confirmados >= 1:
            novo_status = 'confirmado'
        else:
            novo_status = 'cancelado'

        cur.execute("""
                    UPDATE AGENDAMENTOS SET STATUS = ?
                    WHERE ID_AGENDAMENTOS = ?
                    """, (novo_status, id_agendamento))

        id_outro_advogado = None

        if id_advogado_2:
            if id_advogado == id_advogado_1:
                id_outro_advogado = id_advogado_2
            else:
                id_outro_advogado = id_advogado_1

        id_notificacao = None
        titulo_notificacao = None
        mensagem_notificacao = None

        if id_outro_advogado and total_respostas < total_advogados:
            cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado,))
            resultado = cur.fetchone()
            nome_advogado = resultado[0] if resultado else 'O outro advogado'

            titulo_notificacao = 'Advogado confirmou o agendamento'

            mensagem_notificacao = (
                f'{nome_advogado} confirmou o agendamento com '
                f'{nome_cliente} para o dia {data_formatada} '
                f'às {horario_formatado}. Falta a sua resposta.'
            )

            cur.execute("""
                        INSERT INTO NOTIFICACOES (ID_USUARIOS, TIPO, TITULO, MENSAGEM)
                        VALUES (?, ?, ?, ?)
                            RETURNING ID_NOTIFICACAO
                        """, (id_outro_advogado, 'AGENDAMENTO_CONFIRMADO_ADVOGADO', titulo_notificacao, mensagem_notificacao))

            id_notificacao = cur.fetchone()[0]

        con.commit()

        if id_notificacao:
            agora = datetime.datetime.now()

            socketio.emit(
                'nova_notificacao',
                {
                    'id': id_notificacao,
                    'tipo': 'AGENDAMENTO_CONFIRMADO_ADVOGADO',
                    'titulo': titulo_notificacao,
                    'mensagem': mensagem_notificacao,
                    'lida': False,
                    'data_criacao': agora.strftime('%d/%m/%Y'),
                    'hora_criacao': agora.strftime('%H:%M'),
                    'data_leitura': None,
                    'id_agendamento': id_agendamento
                },
                room=f'usuario_{id_outro_advogado}'
            )

        try:
            if (
                    total_respostas == total_advogados
                    and total_confirmados == total_advogados
            ):
                cur.execute("""
                            SELECT u.EMAIL, a.ASSUNTO
                            FROM AGENDAMENTOS a
                                     INNER JOIN USUARIOS u ON u.ID_USUARIOS = a.ID_USUARIOS_CLIENTE
                            WHERE a.ID_AGENDAMENTOS = ?
                            """, (id_agendamento,))

                info = cur.fetchone()

                if info and info[0]:
                    email_cliente = info[0]
                    assunto_ag = info[1] or 'Consulta'

                    if not id_advogado_2:
                        cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado_1,))
                        adv = cur.fetchone()
                        nome_adv = adv[0] if adv else 'Advogado'

                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            executor.submit(
                                enviar_email_um_advogado_confirmado,
                                email_cliente,
                                nome_cliente,
                                nome_adv,
                                data_formatada,
                                horario_formatado,
                                assunto_ag
                            )
                        print(f"Solicitação de e-mail (1 advogado confirmou) criada para {email_cliente}")

                    else:
                        cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado_1,))
                        adv1 = cur.fetchone()

                        cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado_2,))
                        adv2 = cur.fetchone()

                        nome_adv1 = adv1[0] if adv1 else 'Advogado'
                        nome_adv2 = adv2[0] if adv2 else 'Advogado'

                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            executor.submit(
                                enviar_email_dois_advogados,
                                email_cliente,
                                nome_cliente,
                                nome_adv1,
                                nome_adv2,
                                data_formatada,
                                horario_formatado,
                                assunto_ag
                            )
                        print(f"Solicitação de e-mail (dois advogados) criada para {email_cliente}")
        except Exception as e:
            print(f"Erro ao agendar e-mail (confirmar): {e}")

        return jsonify({
            'mensagem': 'Resposta registrada com sucesso',
            'status': novo_status,
            'respostas': {
                'respondidos': total_respostas,
                'necessarios': total_advogados,
                'confirmados': total_confirmados,
                'recusados': total_recusados,
                'texto': f'{total_respostas}/{total_advogados}'
            }
        }), 200

    except Exception as e:
        con.rollback()
        print('Erro ao confirmar agendamento:', e)
        import traceback
        traceback.print_exc()
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
                        ID_USUARIOS_ADVOGADO_1,
                        ID_USUARIOS_ADVOGADO_2,
                        CLIENTE,
                        DATA,
                        HORARIO,
                        CONFIRMADO_ADVOGADO_1,
                        CONFIRMADO_ADVOGADO_2,
                        RECUSADO_ADVOGADO_1,
                        RECUSADO_ADVOGADO_2,
                        STATUS
                    FROM AGENDAMENTOS
                    WHERE ID_AGENDAMENTOS = ?
                      AND (ID_USUARIOS_ADVOGADO_1 = ? OR ID_USUARIOS_ADVOGADO_2 = ?)
                    """, (id_agendamento, id_advogado, id_advogado))

        agendamento = cur.fetchone()

        if not agendamento:
            return jsonify({'error': 'Agendamento não encontrado'}), 404

        id_advogado_1 = agendamento[0]
        id_advogado_2 = agendamento[1]
        nome_cliente = agendamento[2] or '--'
        data_agendamento = agendamento[3]
        horario_agendamento = agendamento[4]

        confirmado_1 = agendamento[5] or 0
        confirmado_2 = agendamento[6] or 0
        recusado_1 = agendamento[7] or 0
        recusado_2 = agendamento[8] or 0
        status_atual = agendamento[9]

        if hasattr(data_agendamento, 'strftime'):
            data_formatada = data_agendamento.strftime('%d/%m/%Y')
        else:
            data_formatada = str(data_agendamento)

        if isinstance(horario_agendamento, datetime.time):
            horario_formatado = horario_agendamento.strftime('%H:%M')
        else:
            horario_formatado = str(horario_agendamento)[:5]

        if status_atual == 'cancelado':
            return jsonify({'error': 'Este agendamento já está cancelado'}), 400

        if id_advogado == id_advogado_1:
            if recusado_1 == 1:
                return jsonify({'error': 'Você já desmarcou este agendamento'}), 400

            cur.execute("""
                        UPDATE AGENDAMENTOS
                        SET RECUSADO_ADVOGADO_1 = 1,
                            CONFIRMADO_ADVOGADO_1 = 0
                        WHERE ID_AGENDAMENTOS = ?
                        """, (id_agendamento,))

            recusado_1 = 1
            confirmado_1 = 0

        elif id_advogado_2 and id_advogado == id_advogado_2:
            if recusado_2 == 1:
                return jsonify({'error': 'Você já desmarcou este agendamento'}), 400

            cur.execute("""
                        UPDATE AGENDAMENTOS
                        SET RECUSADO_ADVOGADO_2 = 1,
                            CONFIRMADO_ADVOGADO_2 = 0
                        WHERE ID_AGENDAMENTOS = ?
                        """, (id_agendamento,))

            recusado_2 = 1
            confirmado_2 = 0

        total_advogados = 2 if id_advogado_2 else 1

        total_confirmados = int(confirmado_1 == 1) + (int(confirmado_2 == 1) if id_advogado_2 else 0)
        total_recusados = int(recusado_1 == 1) + (int(recusado_2 == 1) if id_advogado_2 else 0)
        total_respostas = total_confirmados + total_recusados

        if total_respostas < total_advogados:
            novo_status = 'a_confirmar'
        elif total_confirmados >= 1:
            novo_status = 'confirmado'
        else:
            novo_status = 'cancelado'

        cur.execute("""
                    UPDATE AGENDAMENTOS SET STATUS = ?, MOTIVO = ?
                    WHERE ID_AGENDAMENTOS = ?
                    """, (novo_status, motivo, id_agendamento))

        id_outro_advogado = None

        if id_advogado_2:
            if id_advogado == id_advogado_1:
                id_outro_advogado = id_advogado_2
            else:
                id_outro_advogado = id_advogado_1

        id_notificacao = None
        titulo_notificacao = None
        mensagem_notificacao = None

        if id_outro_advogado and total_respostas < total_advogados:
            cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado,))
            resultado = cur.fetchone()
            nome_advogado = resultado[0] if resultado else 'O outro advogado'

            titulo_notificacao = 'Advogado desmarcou o agendamento'

            mensagem_notificacao = (
                f'{nome_advogado} desmarcou o agendamento com '
                f'{nome_cliente}, marcado para {data_formatada} '
                f'às {horario_formatado}. Motivo: {motivo}'
            )

            cur.execute("""
                        INSERT INTO NOTIFICACOES (ID_USUARIOS, TIPO, TITULO, MENSAGEM)
                        VALUES (?, ?, ?, ?)
                            RETURNING ID_NOTIFICACAO
                        """, (id_outro_advogado, 'AGENDAMENTO_DESMARCADO_ADVOGADO', titulo_notificacao, mensagem_notificacao))

            id_notificacao = cur.fetchone()[0]

        con.commit()

        if id_notificacao:
            agora = datetime.datetime.now()

            socketio.emit(
                'nova_notificacao',
                {
                    'id': id_notificacao,
                    'tipo': 'AGENDAMENTO_DESMARCADO_ADVOGADO',
                    'titulo': titulo_notificacao,
                    'mensagem': mensagem_notificacao,
                    'lida': False,
                    'data_criacao': agora.strftime('%d/%m/%Y'),
                    'hora_criacao': agora.strftime('%H:%M'),
                    'data_leitura': None,
                    'id_agendamento': id_agendamento
                },
                room=f'usuario_{id_outro_advogado}'
            )

        try:
            cur.execute("""
                        SELECT u.EMAIL, a.ASSUNTO
                        FROM AGENDAMENTOS a
                                 INNER JOIN USUARIOS u ON u.ID_USUARIOS = a.ID_USUARIOS_CLIENTE
                        WHERE a.ID_AGENDAMENTOS = ?
                        """, (id_agendamento,))

            info = cur.fetchone()

            if info and info[0]:
                email_cliente = info[0]
                assunto_ag = info[1] or 'Consulta'

                if not id_advogado_2:
                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado,))
                    adv = cur.fetchone()
                    nome_adv = adv[0] if adv else 'Advogado'

                    motivos = [
                        {'nome': nome_adv, 'motivo': motivo}
                    ]

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        executor.submit(
                            enviar_email_agendamento_cancelado,
                            email_cliente,
                            nome_cliente,
                            None,
                            nome_adv,
                            data_formatada,
                            horario_formatado,
                            assunto_ag,
                            motivos,
                            'desmarcado',
                            'unico'
                        )
                    print(f"Solicitação de e-mail (desmarcado - único) criada para {email_cliente}")

                elif (
                        total_respostas == total_advogados
                        and total_confirmados == 0
                        and total_recusados == 2
                ):
                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado_1,))
                    adv_1 = cur.fetchone()

                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado_2,))
                    adv_2 = cur.fetchone()

                    nome_1 = adv_1[0] if adv_1 else 'Advogado 1'
                    nome_2 = adv_2[0] if adv_2 else 'Advogado 2'

                    motivos = [
                        {'nome': nome_1, 'motivo': motivo},
                        {'nome': nome_2, 'motivo': motivo}
                    ]

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        executor.submit(
                            enviar_email_agendamento_cancelado,
                            email_cliente,
                            nome_cliente,
                            None,
                            None,
                            data_formatada,
                            horario_formatado,
                            assunto_ag,
                            motivos,
                            'desmarcado',
                            'dois'
                        )
                    print(f"Solicitação de e-mail (desmarcado - dois) criada para {email_cliente}")

                elif (
                        total_respostas == total_advogados
                        and total_confirmados == 1
                        and total_recusados == 1
                ):
                    if id_advogado == id_advogado_1:
                        id_presente = id_advogado_2
                        id_ausente = id_advogado_1
                    else:
                        id_presente = id_advogado_1
                        id_ausente = id_advogado

                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_presente,))
                    presente = cur.fetchone()

                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_ausente,))
                    ausente = cur.fetchone()

                    nome_presente = presente[0] if presente else 'Advogado'
                    nome_ausente = ausente[0] if ausente else 'Advogado'

                    motivos = [
                        {'nome': nome_ausente, 'motivo': motivo}
                    ]

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        executor.submit(
                            enviar_email_agendamento_cancelado,
                            email_cliente,
                            nome_cliente,
                            nome_presente,
                            nome_ausente,
                            data_formatada,
                            horario_formatado,
                            assunto_ag,
                            motivos,
                            'desmarcado',
                            'um_de_dois'
                        )
                    print(f"Solicitação de e-mail (desmarcado - um de dois) criada para {email_cliente}")
        except Exception as e:
            print(f"Erro ao agendar e-mail (cancelar): {e}")

        return jsonify({
            'mensagem': 'Resposta registrada com sucesso',
            'status': novo_status,
            'respostas': {
                'respondidos': total_respostas,
                'necessarios': total_advogados,
                'confirmados': total_confirmados,
                'recusados': total_recusados,
                'texto': f'{total_respostas}/{total_advogados}'
            }
        }), 200

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
                        ID_USUARIOS_ADVOGADO_1,
                        ID_USUARIOS_ADVOGADO_2,
                        CLIENTE,
                        DATA,
                        HORARIO,
                        CONFIRMADO_ADVOGADO_1,
                        CONFIRMADO_ADVOGADO_2,
                        RECUSADO_ADVOGADO_1,
                        RECUSADO_ADVOGADO_2,
                        STATUS
                    FROM AGENDAMENTOS
                    WHERE ID_AGENDAMENTOS = ?
                      AND (ID_USUARIOS_ADVOGADO_1 = ? OR ID_USUARIOS_ADVOGADO_2 = ?)
                    """, (id_agendamento, id_advogado, id_advogado))

        agendamento = cur.fetchone()

        if not agendamento:
            return jsonify({'error': 'Agendamento não encontrado'}), 404

        id_advogado_1 = agendamento[0]
        id_advogado_2 = agendamento[1]
        nome_cliente = agendamento[2] or '--'
        data_agendamento = agendamento[3]
        horario_agendamento = agendamento[4]

        confirmado_1 = agendamento[5] or 0
        confirmado_2 = agendamento[6] or 0
        recusado_1 = agendamento[7] or 0
        recusado_2 = agendamento[8] or 0
        status_atual = agendamento[9]

        if hasattr(data_agendamento, 'strftime'):
            data_formatada = data_agendamento.strftime('%d/%m/%Y')
        else:
            data_formatada = str(data_agendamento)

        if isinstance(horario_agendamento, datetime.time):
            horario_formatado = horario_agendamento.strftime('%H:%M')
        else:
            horario_formatado = str(horario_agendamento)[:5]

        if status_atual == 'cancelado':
            return jsonify({'error': 'Este agendamento está cancelado'}), 400

        if id_advogado == id_advogado_1:
            if confirmado_1 == 1:
                return jsonify({'error': 'Você já confirmou este agendamento'}), 400

            if recusado_1 == 1:
                return jsonify({'error': 'Você já recusou este agendamento'}), 400

            cur.execute("""
                        UPDATE AGENDAMENTOS SET RECUSADO_ADVOGADO_1 = 1
                        WHERE ID_AGENDAMENTOS = ?
                        """, (id_agendamento,))

            recusado_1 = 1

        elif id_advogado_2 and id_advogado == id_advogado_2:
            if confirmado_2 == 1:
                return jsonify({'error': 'Você já confirmou este agendamento'}), 400

            if recusado_2 == 1:
                return jsonify({'error': 'Você já recusou este agendamento'}), 400

            cur.execute("""
                        UPDATE AGENDAMENTOS SET RECUSADO_ADVOGADO_2 = 1
                        WHERE ID_AGENDAMENTOS = ?
                        """, (id_agendamento,))

            recusado_2 = 1

        total_advogados = 2 if id_advogado_2 else 1

        total_confirmados = int(confirmado_1 == 1) + (int(confirmado_2 == 1) if id_advogado_2 else 0)
        total_recusados = int(recusado_1 == 1) + (int(recusado_2 == 1) if id_advogado_2 else 0)
        total_respostas = total_confirmados + total_recusados

        if total_respostas < total_advogados:
            novo_status = 'a_confirmar'
        elif total_confirmados >= 1:
            novo_status = 'confirmado'
        else:
            novo_status = 'cancelado'

        cur.execute("""
                    UPDATE AGENDAMENTOS SET STATUS = ?, MOTIVO = ?
                    WHERE ID_AGENDAMENTOS = ?
                    """, (novo_status, motivo, id_agendamento))

        id_outro_advogado = None

        if id_advogado_2:
            if id_advogado == id_advogado_1:
                id_outro_advogado = id_advogado_2
            else:
                id_outro_advogado = id_advogado_1

        id_notificacao = None
        titulo_notificacao = None
        mensagem_notificacao = None

        if id_outro_advogado:
            cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado,))
            resultado = cur.fetchone()
            nome_advogado = resultado[0] if resultado else 'O outro advogado'

            titulo_notificacao = 'Advogado recusou o agendamento'

            mensagem_notificacao = (
                f'{nome_advogado} recusou o agendamento com '
                f'{nome_cliente}, marcado para {data_formatada} '
                f'às {horario_formatado}. Motivo: {motivo}'
            )

            cur.execute("""
                        INSERT INTO NOTIFICACOES (ID_USUARIOS, TIPO, TITULO, MENSAGEM)
                        VALUES (?, ?, ?, ?)
                            RETURNING ID_NOTIFICACAO
                        """, (id_outro_advogado, 'AGENDAMENTO_RECUSADO_ADVOGADO', titulo_notificacao, mensagem_notificacao))

            id_notificacao = cur.fetchone()[0]

        con.commit()

        if id_notificacao:
            agora = datetime.datetime.now()

            socketio.emit(
                'nova_notificacao',
                {
                    'id': id_notificacao,
                    'tipo': 'AGENDAMENTO_RECUSADO_ADVOGADO',
                    'titulo': titulo_notificacao,
                    'mensagem': mensagem_notificacao,
                    'lida': False,
                    'data_criacao': agora.strftime('%d/%m/%Y'),
                    'hora_criacao': agora.strftime('%H:%M'),
                    'data_leitura': None,
                    'id_agendamento': id_agendamento
                },
                room=f'usuario_{id_outro_advogado}'
            )

        try:
            cur.execute("""
                        SELECT u.EMAIL, a.ASSUNTO
                        FROM AGENDAMENTOS a
                                 INNER JOIN USUARIOS u ON u.ID_USUARIOS = a.ID_USUARIOS_CLIENTE
                        WHERE a.ID_AGENDAMENTOS = ?
                        """, (id_agendamento,))

            info = cur.fetchone()

            if info and info[0]:
                email_cliente = info[0]
                assunto_ag = info[1] or 'Consulta'

                if not id_advogado_2:
                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado,))
                    adv = cur.fetchone()
                    nome_adv = adv[0] if adv else 'Advogado'

                    motivos = [
                        {'nome': nome_adv, 'motivo': motivo}
                    ]

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        executor.submit(
                            enviar_email_agendamento_cancelado,
                            email_cliente,
                            nome_cliente,
                            None,
                            nome_adv,
                            data_formatada,
                            horario_formatado,
                            assunto_ag,
                            motivos,
                            'recusado',
                            'unico'
                        )
                    print(f"Solicitação de e-mail (recusado - único) criada para {email_cliente}")

                elif (
                        total_respostas == total_advogados
                        and total_confirmados == 0
                        and total_recusados == 2
                ):
                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado_1,))
                    adv_1 = cur.fetchone()

                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_advogado_2,))
                    adv_2 = cur.fetchone()

                    nome_1 = adv_1[0] if adv_1 else 'Advogado 1'
                    nome_2 = adv_2[0] if adv_2 else 'Advogado 2'

                    motivos = [
                        {'nome': nome_1, 'motivo': motivo},
                        {'nome': nome_2, 'motivo': motivo}
                    ]

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        executor.submit(
                            enviar_email_agendamento_cancelado,
                            email_cliente,
                            nome_cliente,
                            None,
                            None,
                            data_formatada,
                            horario_formatado,
                            assunto_ag,
                            motivos,
                            'recusado',
                            'dois'
                        )
                    print(f"Solicitação de e-mail (recusado - dois) criada para {email_cliente}")

                elif (
                        total_respostas == total_advogados
                        and total_confirmados == 1
                        and total_recusados == 1
                ):
                    if id_advogado == id_advogado_1:
                        id_presente = id_advogado_2
                        id_ausente = id_advogado_1
                    else:
                        id_presente = id_advogado_1
                        id_ausente = id_advogado

                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_presente,))
                    presente = cur.fetchone()

                    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_ausente,))
                    ausente = cur.fetchone()

                    nome_presente = presente[0] if presente else 'Advogado'
                    nome_ausente = ausente[0] if ausente else 'Advogado'

                    motivos = [
                        {'nome': nome_ausente, 'motivo': motivo}
                    ]

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        executor.submit(
                            enviar_email_agendamento_cancelado,
                            email_cliente,
                            nome_cliente,
                            nome_presente,
                            nome_ausente,
                            data_formatada,
                            horario_formatado,
                            assunto_ag,
                            motivos,
                            'recusado',
                            'um_de_dois'
                        )
                    print(f"Solicitação de e-mail (recusado - um de dois) criada para {email_cliente}")
        except Exception as e:
            print(f"Erro ao agendar e-mail (recusar): {e}")

        return jsonify({
            'mensagem': 'Resposta registrada com sucesso',
            'status': novo_status,
            'respostas': {
                'respondidos': total_respostas,
                'necessarios': total_advogados,
                'confirmados': total_confirmados,
                'recusados': total_recusados,
                'texto': f'{total_respostas}/{total_advogados}'
            }
        }), 200

    except Exception as e:
        con.rollback()
        print('Erro ao recusar agendamento:', e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()