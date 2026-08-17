from flask import jsonify, request, make_response
from funcao import senha_forte, verificar_existente, senha_correspondente, gerar_token, decodificar_token
from flask_bcrypt import generate_password_hash, check_password_hash
from main import app
from db import conexao
import os
import datetime
import concurrent.futures

@app.route('/criar_usuarios', methods=['POST'])
def criar_usuarios():
    nome = request.form.get('nome')
    email = request.form.get('email')
    cpf = request.form.get('cpf_cnpj')
    telefone = request.form.get('telefone')
    senha = request.form.get('senha')
    confirmar_senha = request.form.get('confirmar_senha')
    tipo = request.form.get('tipo')

    rg = request.form.get('rg')
    orgao_expedidor = request.form.get('orgao_expedidor')
    num_oab = request.form.get('num_oab')
    uf_oab = request.form.get('uf_oab')
    nacionalidade = request.form.get('nacionalidade')
    estado_civil = request.form.get('estado_civil')

    if not nome:
        return jsonify({"error": "Nome é obrigatório"}), 400

    if not cpf:
        return jsonify({"error": "CPF é obrigatório"}), 400

    if not email:
        return jsonify({"error": "E-mail é obrigatório"}), 400

    if not senha:
        return jsonify({"error": "Senha é obrigatória"}), 400

    if not confirmar_senha:
        return jsonify({"error": "Confirmar senha é obrigatório"}), 400

    if not telefone:
        return jsonify({"error": "Telefone é obrigatório"}), 400

    if tipo is None:
        return jsonify({"error": "Tipo de usuário é obrigatório"}), 400

    try:
        tipo = int(tipo)
    except ValueError:
        return jsonify({"error": "Tipo de usuário inválido"}), 400

    if tipo not in [0, 1, 2]:
        return jsonify({"error": "Tipo de usuário inválido"}), 400

    if verificar_existente(cpf, "CPF"):
        return jsonify({"error": "CPF já cadastrado"}), 400

    if verificar_existente(email, "EMAIL"):
        return jsonify({"error": "E-mail já cadastrado"}), 400

    if tipo == 0:
        if not num_oab:
            return jsonify({"error": "Número da OAB é obrigatório"}), 400

        if not uf_oab:
            return jsonify({"error": "UF da OAB é obrigatória"}), 400

        if verificar_existente(num_oab, "NUM_OAB"):
            return jsonify({"error": "Número da OAB já cadastrado"}), 400

    if senha_forte(senha) == False:
        return jsonify({
            "error": "Senha fraca. Use 8+ caracteres, maiúsculas, minúsculas, números e especiais"
        }), 400

    if senha_correspondente(senha, confirmar_senha) == False:
        return jsonify({"error": "Senhas não correspondem"}), 400

    if tipo == 0:
        from consulta_oab import consultar_oab

        try:
            print(f"Consultando OAB: {uf_oab}-{num_oab} | Nome: {nome}")

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

            print("Resultado da OAB:", resultado_oab)

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
            return jsonify({
                "error": resultado_oab.get(
                    "mensagem",
                    "OAB não encontrada ou não está regular."
                )
            }), 400

        advogado = items[0]

        nome_oab = advogado.get("nome", "")

        if nome.strip().upper() != nome_oab.strip().upper():
            return jsonify({
                "error": "O nome informado não corresponde ao nome cadastrado na OAB.",
                "nome_informado": nome,
                "nome_oab": nome_oab
            }), 400

        print(
            f"OAB validada com sucesso: "
            f"{uf_oab}-{num_oab} - {nome_oab}"
        )

    senha_cripto = generate_password_hash(senha).decode('utf-8')

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            INSERT INTO USUARIOS (
                NOME,
                EMAIL,
                SENHA,
                CPF,
                TELEFONE,
                TIPO,
                RG,
                ORGAO_EXPEDIDOR,
                NUM_OAB,
                UF_OAB,
                NACIONALIDADE,
                ESTADO_CIVIL,
                DATA_CADASTRO,
                ATIVO
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID_USUARIOS
        """, (
            nome,
            email,
            senha_cripto,
            cpf,
            telefone,
            tipo,
            rg,
            orgao_expedidor,
            num_oab,
            uf_oab,
            nacionalidade,
            estado_civil,
            datetime.datetime.now(),
            1
        ))

        id_usuario = cur.fetchone()[0]

        con.commit()

        foto_perfil = request.files.get('foto_perfil')

        if foto_perfil:
            try:
                nome_imagem = f'{id_usuario}.jpeg'

                caminho = os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    'Usuarios'
                )

                os.makedirs(caminho, exist_ok=True)

                foto_perfil.save(
                    os.path.join(caminho, nome_imagem)
                )

            except Exception as e:
                print(f"Erro ao salvar imagem: {e}")

        return jsonify({
            'message': 'Cadastro realizado com sucesso!'
        }), 201

    except Exception as e:
        con.rollback()

        return jsonify({
            'error': f'Erro interno: {e}'
        }), 500

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
    if not nacionalidade:
        return jsonify({"error": "Nacionalidade é obrigatória"}), 400
    if not estado_civil:
        return jsonify({"error": "Estado civil é obrigatório"}), 400

    con = conexao()
    cur = con.cursor()
    try:
        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE CPF = ? AND ID_USUARIOS != ?", (cpf, id_usuario))
        if cur.fetchone():
            return jsonify({"error": "CPF já cadastrado para outro usuário"}), 400

        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE EMAIL = ? AND ID_USUARIOS != ?", (email, id_usuario))
        if cur.fetchone():
            return jsonify({"error": "E-mail já cadastrado para outro usuário"}), 400

        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE NUM_OAB = ? AND UF_OAB = ? AND ID_USUARIOS != ?", (num_oab, uf_oab, id_usuario))
        if cur.fetchone():
            return jsonify({"error": "Número da OAB já cadastrado para outro usuário"}), 400

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
        mensagem_erro = (
            f"Esse número da OAB está cadastrado no sistema, informe o seu corretamente."
        )
        return jsonify({
            "error": mensagem_erro
        }), 400

    advogado = items[0]
    nome_oab = advogado.get("nome", "")

    if nome.strip().upper() != nome_oab.strip().upper():
        return jsonify({
            "error": "O nome informado não corresponde ao nome cadastrado na OAB.",
            "nome_informado": nome,
            "nome_oab": nome_oab
        }), 400

    print(f"OAB validada com sucesso na edição: {uf_oab}-{num_oab} - {nome_oab}")

    con = conexao()
    cur = con.cursor()

    try:
        if senha_cripto:
            cur.execute("""
                UPDATE USUARIOS SET
                    NOME = ?,
                    EMAIL = ?,
                    CPF = ?,
                    TELEFONE = ?,
                    RG = ?,
                    ORGAO_EXPEDIDOR = ?,
                    NUM_OAB = ?,
                    UF_OAB = ?,
                    NACIONALIDADE = ?,
                    ESTADO_CIVIL = ?,
                    SENHA = ?
                WHERE ID_USUARIOS = ?
            """, (
                nome,
                email,
                cpf,
                telefone,
                rg,
                orgao_expedidor,
                num_oab,
                uf_oab,
                nacionalidade,
                estado_civil,
                senha_cripto,
                id_usuario
            ))
        else:
            cur.execute("""
                UPDATE USUARIOS SET
                    NOME = ?,
                    EMAIL = ?,
                    CPF = ?,
                    TELEFONE = ?,
                    RG = ?,
                    ORGAO_EXPEDIDOR = ?,
                    NUM_OAB = ?,
                    UF_OAB = ?,
                    NACIONALIDADE = ?,
                    ESTADO_CIVIL = ?
                WHERE ID_USUARIOS = ?
            """, (
                nome,
                email,
                cpf,
                telefone,
                rg,
                orgao_expedidor,
                num_oab,
                uf_oab,
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

    if decodificar_token() != False:
        return jsonify({'error': 'Você já está logado'}), 400

    con = conexao()
    cur = con.cursor()
    try:
        cur.execute("""
            SELECT ID_USUARIOS, TIPO, NOME, SENHA, ATIVO
            FROM USUARIOS WHERE CPF = ?
        """, (cpf_cnpj,))

        usuario = cur.fetchone()

        if not usuario:
            return jsonify({"error": "Usuário não encontrado"}), 404

        id_usuario, tipo, nome, senha_hash, ativo = usuario

        if ativo == 0:
            return jsonify({"error": "Usuário inativado"}), 400

        if check_password_hash(senha_hash, senha):
            token = gerar_token(tipo, id_usuario, 1440)
            resp = make_response(jsonify({
                'message': f'Bem-vindo, {nome}!',
                'nome': nome,
                'token': token,
                'tipo': tipo,
                'foto_perfil': f'{id_usuario}.jpeg'
            }))
            resp.set_cookie('acess_token', token, httponly=True, secure=False, samesite='Lax', path="/", max_age=7600)
            return resp

        return jsonify({"error": "Senha incorreta"}), 400

    except Exception as e:
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