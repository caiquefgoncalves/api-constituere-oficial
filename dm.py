from flask import jsonify, request
from main import app, socketio
from db import conexao
from funcao import decodificar_token
from datetime import datetime
from flask_socketio import emit, join_room, leave_room

conexoes_usuarios = {}


def _nome_usuario(cur, id_usuario):
    cur.execute("SELECT NOME FROM USUARIOS WHERE ID_USUARIOS = ?", (id_usuario,))
    linha = cur.fetchone()
    return linha[0] if linha else 'Usuário'


def _escritorio_do_usuario(cur, id_usuario, tipo_usuario):
    if tipo_usuario == 0:
        cur.execute("""
            SELECT FIRST 1 ID_ESCRITORIOS
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ? AND ATIVO = 1
            ORDER BY CASE WHEN STATUS = 'PROPRIETARIO' THEN 0 ELSE 1 END
        """, (id_usuario,))
    else:
        cur.execute("""
            SELECT FIRST 1 vinculo.ID_ESCRITORIOS
            FROM USUARIOS cliente
            INNER JOIN ADVOGADO_ESCRITORIO vinculo
                ON vinculo.ID_USUARIOS = cliente.ID_USUARIO_RESPONSAVEL
            WHERE cliente.ID_USUARIOS = ?
              AND cliente.ATIVO = 1
              AND vinculo.ATIVO = 1
        """, (id_usuario,))

    linha = cur.fetchone()
    return linha[0] if linha else None


@app.route('/dm/advogados_disponiveis', methods=['GET'])
def advogados_disponiveis():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuario = token_data['id_usuarios']
    tipo_usuario = token_data['tipo']

    con = conexao()
    cur = con.cursor()

    try:
        if tipo_usuario == 0:
            cur.execute("""
                SELECT DISTINCT
                    u.ID_USUARIOS,
                    u.NOME
                FROM ADVOGADO_ESCRITORIO ae_logado
                INNER JOIN ADVOGADO_ESCRITORIO ae_alvo
                    ON ae_alvo.ID_ESCRITORIOS = ae_logado.ID_ESCRITORIOS
                   AND ae_alvo.ATIVO = 1
                INNER JOIN USUARIOS u
                    ON u.ID_USUARIOS = ae_alvo.ID_USUARIOS
                   AND u.ATIVO = 1
                WHERE ae_logado.ID_USUARIOS = ?
                  AND ae_logado.ATIVO = 1
                  AND u.ID_USUARIOS <> ?
                ORDER BY u.NOME
            """, (id_usuario, id_usuario))

            advogados = []
            for row in cur.fetchall():
                advogados.append({
                    'id': row[0],
                    'nome': row[1] or '--',
                    'cargo': 'Advogado',
                    'foto': f'{row[0]}.jpeg'
                })

            return jsonify({'advogados': advogados}), 200

        cur.execute("""
            SELECT ID_USUARIO_RESPONSAVEL
            FROM USUARIOS
            WHERE ID_USUARIOS = ?
        """, (id_usuario,))

        row_cliente = cur.fetchone()

        if not row_cliente or not row_cliente[0]:
            return jsonify({'advogados': []}), 200

        id_advogado_responsavel = row_cliente[0]

        cur.execute("""
            SELECT DISTINCT
                u.ID_USUARIOS,
                u.NOME
            FROM ADVOGADO_ESCRITORIO ae_resp
            INNER JOIN ADVOGADO_ESCRITORIO ae_alvo
                ON ae_alvo.ID_ESCRITORIOS = ae_resp.ID_ESCRITORIOS
               AND ae_alvo.ATIVO = 1
               AND UPPER(ae_alvo.STATUS) IN ('PROPRIETARIO', 'PARCEIRO')
            INNER JOIN USUARIOS u
                ON u.ID_USUARIOS = ae_alvo.ID_USUARIOS
               AND u.TIPO = 0
               AND u.ATIVO = 1
            WHERE ae_resp.ID_USUARIOS = ?
              AND ae_resp.ATIVO = 1
            ORDER BY u.NOME
        """, (id_advogado_responsavel,))

        advogados = []
        ids_adicionados = set()

        for row in cur.fetchall():
            if row[0] in ids_adicionados:
                continue
            ids_adicionados.add(row[0])

            advogados.append({
                'id': row[0],
                'nome': row[1] or '--',
                'cargo': 'Advogado',
                'foto': f'{row[0]}.jpeg'
            })

        if not advogados:
            cur.execute("""
                SELECT ID_USUARIOS, NOME
                FROM USUARIOS
                WHERE ID_USUARIOS = ?
                  AND TIPO = 0
                  AND ATIVO = 1
            """, (id_advogado_responsavel,))

            row = cur.fetchone()
            if row:
                advogados.append({
                    'id': row[0],
                    'nome': row[1] or '--',
                    'cargo': 'Advogado',
                    'foto': f'{row[0]}.jpeg'
                })

        return jsonify({'advogados': advogados}), 200

    except Exception as e:
        print(f"ERRO advogados_disponiveis: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/dm/iniciar_conversa/<int:id_contato>', methods=['POST'])
def iniciar_conversa(id_contato):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuario = token_data['id_usuarios']
    tipo_usuario = token_data['tipo']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_USUARIOS, TIPO FROM USUARIOS
            WHERE ID_USUARIOS = ? AND ATIVO = 1
        """, (id_contato,))
        contato = cur.fetchone()

        if not contato:
            return jsonify({'error': 'Contato não encontrado'}), 404

        if tipo_usuario == 0:
            id_advogado = id_usuario
            id_cliente = id_contato

            cur.execute("""
                SELECT 1 FROM USUARIOS
                WHERE ID_USUARIOS = ?
                  AND TIPO IN (2, 3)
                  AND ATIVO = 1
                  AND ID_USUARIO_RESPONSAVEL = ?
            """, (id_contato, id_usuario))

            if not cur.fetchone():
                return jsonify({'error': 'Cliente não pertence a você'}), 403
        else:
            id_advogado = id_contato
            id_cliente = id_usuario

            cur.execute("""
                SELECT 1 FROM USUARIOS
                WHERE ID_USUARIOS = ?
                  AND TIPO = 0
                  AND ATIVO = 1
            """, (id_contato,))

            if not cur.fetchone():
                return jsonify({'error': 'Advogado não encontrado'}), 404

        cur.execute("""
            SELECT ID_CONVERSA FROM CONVERSAS
            WHERE ID_ADVOGADO = ? AND ID_CLIENTE = ?
        """, (id_advogado, id_cliente))
        conversa = cur.fetchone()

        if conversa:
            return jsonify({
                'message': 'Conversa já existe',
                'conversa_id': conversa[0]
            }), 200

        cur.execute("""
            INSERT INTO CONVERSAS (ID_ADVOGADO, ID_CLIENTE, ULTIMA_MENSAGEM)
            VALUES (?, ?, ?) RETURNING ID_CONVERSA
        """, (id_advogado, id_cliente, datetime.now()))

        novo_id = cur.fetchone()[0]
        con.commit()

        return jsonify({
            'message': 'Conversa iniciada com sucesso',
            'conversa_id': novo_id
        }), 201

    except Exception as e:
        con.rollback()
        print(f'Erro: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/dm/enviar_mensagem/<int:id_conversa>', methods=['POST'])
def enviar_mensagem(id_conversa):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_remetente = token_data['id_usuarios']

    data = request.get_json()
    mensagem_texto = (data.get('mensagem') or '').strip()

    if not mensagem_texto:
        return jsonify({'error': 'Mensagem não pode estar vazia'}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_ADVOGADO, ID_CLIENTE FROM CONVERSAS WHERE ID_CONVERSA = ?
        """, (id_conversa,))
        conversa = cur.fetchone()

        if not conversa:
            return jsonify({'error': 'Conversa não encontrada'}), 404

        id_advogado, id_cliente = conversa[0], conversa[1]

        if id_remetente != id_advogado and id_remetente != id_cliente:
            return jsonify({'error': 'Você não participa desta conversa'}), 403

        cur.execute("""
            INSERT INTO MENSAGENS (ID_CONVERSA, ID_REMETENTE, MENSAGEM, DATA_ENVIO)
            VALUES (?, ?, ?, ?) RETURNING ID_MENSAGEM
        """, (id_conversa, id_remetente, mensagem_texto, datetime.now()))

        novo_id = cur.fetchone()[0]

        cur.execute("""
            UPDATE CONVERSAS SET ULTIMA_MENSAGEM = ? WHERE ID_CONVERSA = ?
        """, (datetime.now(), id_conversa))

        con.commit()

        nome_remetente = _nome_usuario(cur, id_remetente)
        data_envio = datetime.now().strftime('%d/%m/%Y %H:%M')

        mensagem_data = {
            'id': novo_id,
            'conversa_id': id_conversa,
            'remetente_id': id_remetente,
            'remetente_nome': nome_remetente,
            'mensagem': mensagem_texto,
            'data': data_envio
        }

        sala = f"conversa_{id_conversa}"
        socketio.emit('new_message', mensagem_data, room=sala)

        return jsonify({
            'message': 'Mensagem enviada com sucesso',
            'mensagem_id': novo_id
        }), 201

    except Exception as e:
        con.rollback()
        print(f'Erro: {e}')
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/dm/listar_conversas', methods=['GET'])
def listar_conversas():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuario = token_data['id_usuarios']
    tipo_usuario = token_data['tipo']

    con = conexao()
    cur = con.cursor()

    try:
        if tipo_usuario == 0:
            cur.execute("""
                SELECT c.ID_CONVERSA, c.ID_CLIENTE, u.NOME, c.ULTIMA_MENSAGEM
                FROM CONVERSAS c
                INNER JOIN USUARIOS u ON u.ID_USUARIOS = c.ID_CLIENTE
                WHERE c.ID_ADVOGADO = ?
                ORDER BY c.ULTIMA_MENSAGEM DESC
            """, (id_usuario,))
        else:
            cur.execute("""
                SELECT c.ID_CONVERSA, c.ID_ADVOGADO, u.NOME, c.ULTIMA_MENSAGEM
                FROM CONVERSAS c
                INNER JOIN USUARIOS u ON u.ID_USUARIOS = c.ID_ADVOGADO
                WHERE c.ID_CLIENTE = ?
                ORDER BY c.ULTIMA_MENSAGEM DESC
            """, (id_usuario,))

        conversas = cur.fetchall()
        lista_conversas = []

        for conv in conversas:
            data_ultima = ''
            if conv[3]:
                try:
                    data_ultima = conv[3].strftime('%d/%m/%Y %H:%M')
                except:
                    data_ultima = str(conv[3])

            cur.execute("""
                SELECT FIRST 1 MENSAGEM FROM MENSAGENS
                WHERE ID_CONVERSA = ?
                ORDER BY DATA_ENVIO DESC
            """, (conv[0],))
            ultima_msg = cur.fetchone()

            lista_conversas.append({
                'conversa_id': conv[0],
                'usuario_id': conv[1],
                'usuario_nome': conv[2],
                'usuario_foto': f'{conv[1]}.jpeg',
                'ultima_mensagem': data_ultima,
                'ultimo_texto': ultima_msg[0] if ultima_msg else ''
            })

        return jsonify({'conversas': lista_conversas}), 200

    except Exception as e:
        print(f"ERRO listar_conversas: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/dm/mensagens/<int:id_conversa>', methods=['GET'])
def buscar_mensagens(id_conversa):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    id_usuario = token_data['id_usuarios']

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_ADVOGADO, ID_CLIENTE FROM CONVERSAS WHERE ID_CONVERSA = ?
        """, (id_conversa,))
        conversa = cur.fetchone()

        if not conversa:
            return jsonify({'error': 'Conversa não encontrada'}), 404

        if id_usuario != conversa[0] and id_usuario != conversa[1]:
            return jsonify({'error': 'Acesso negado'}), 403

        cur.execute("""
            SELECT ID_MENSAGEM, ID_REMETENTE, MENSAGEM, DATA_ENVIO
            FROM MENSAGENS
            WHERE ID_CONVERSA = ?
            ORDER BY DATA_ENVIO ASC
        """, (id_conversa,))

        mensagens = cur.fetchall()
        lista_mensagens = []

        for msg in mensagens:
            data_envio = ''
            if msg[3]:
                try:
                    data_envio = msg[3].strftime('%d/%m/%Y %H:%M')
                except:
                    data_envio = str(msg[3])

            lista_mensagens.append({
                'id': msg[0],
                'remetente_id': msg[1],
                'mensagem': msg[2],
                'data': data_envio,
                'is_meu_envio': msg[1] == id_usuario
            })

        return jsonify({'mensagens': lista_mensagens}), 200

    except Exception as e:
        print(f"ERRO buscar_mensagens: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@socketio.on('connect')
def handle_connect():
    print(f'Cliente conectado: {request.sid}')


@socketio.on('disconnect')
def handle_disconnect():
    usuario_id = None
    for uid, sid in conexoes_usuarios.items():
        if sid == request.sid:
            usuario_id = uid
            break

    if usuario_id:
        del conexoes_usuarios[usuario_id]


@socketio.on('authenticate')
def handle_authenticate(data):
    token = data.get('token')
    if not token:
        emit('error', {'error': 'Token não fornecido'})
        return

    token_data = decodificar_token(token)
    if token_data == False:
        emit('error', {'error': 'Token inválido'})
        return

    usuario_id = token_data['id_usuarios']
    conexoes_usuarios[usuario_id] = request.sid

    con = conexao()
    cur = con.cursor()

    try:
        tipo = token_data['tipo']
        if tipo == 0:
            cur.execute("SELECT ID_CONVERSA FROM CONVERSAS WHERE ID_ADVOGADO = ?", (usuario_id,))
        else:
            cur.execute("SELECT ID_CONVERSA FROM CONVERSAS WHERE ID_CLIENTE = ?", (usuario_id,))

        conversas = cur.fetchall()
        for conv in conversas:
            join_room(f"conversa_{conv[0]}")
    except Exception as e:
        print(f'Erro ao entrar nas salas: {e}')
    finally:
        cur.close()
        con.close()

    emit('authenticated', {'status': 'ok', 'usuario_id': usuario_id})


@socketio.on('join_conversa')
def handle_join_conversa(data):
    conversa_id = data.get('conversa_id')
    if conversa_id:
        join_room(f"conversa_{conversa_id}")
        emit('joined_conversa', {'conversa_id': conversa_id})


@socketio.on('leave_conversa')
def handle_leave_conversa(data):
    conversa_id = data.get('conversa_id')
    if conversa_id:
        leave_room(f"conversa_{conversa_id}")