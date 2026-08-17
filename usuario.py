from flask import jsonify, request, make_response
from funcao import *
from flask_bcrypt import generate_password_hash, check_password_hash
from main import app
from db import conexao
import os
import datetime
import concurrent.futures
import time
from consulta_cnsa import consultar_cnsa
from consulta_oab import consultar_oab

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

    if not validar_cpf(cpf):
        return jsonify({"error": "CPF inválido"}), 400

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
            mensagem = resultado_oab.get("mensagem", "")
            if mensagem and "Advogado encontrado, mas a situação é" in mensagem:
                return jsonify({"error": mensagem}), 400
            return jsonify({
                "error": f"OAB {uf_oab}-{num_oab} não encontrada no cadastro da OAB. Verifique se o número e a UF estão corretos."
            }), 400

        advogado = items[0]
        nome_oab = advogado.get("nome", "")
        situacao = advogado.get("situacao", "")

        if situacao.upper() != "REGULAR":
            return jsonify({
                "error": f"Sua situação é {situacao}. Apenas advogados regulares podem se cadastrar."
            }), 400

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

        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE NUM_OAB = ? AND UF_OAB = ? AND ID_USUARIOS != ?",
                    (num_oab, uf_oab, id_usuario))
        if cur.fetchone():
            return jsonify(
                {"error": f"Este número de OAB ({uf_oab}-{num_oab}) já está cadastrado para outro usuário."}), 400

        cur.execute("""
            SELECT NUM_OAB, UF_OAB
            FROM USUARIOS
            WHERE ID_USUARIOS = ?
        """, (id_usuario,))
        usuario_atual = cur.fetchone()

        oab_atual = usuario_atual[0] if usuario_atual else None
        uf_oab_atual = usuario_atual[1] if usuario_atual else None

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

    oab_alterada = (num_oab != oab_atual) or (uf_oab != uf_oab_atual)

    if oab_alterada:
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

        advogado = items[0]
        nome_oab = advogado.get("nome", "")
        situacao = advogado.get("situacao", "")

        if situacao.upper() != "REGULAR":
            return jsonify({
                "error": f"Sua situação é cancelada/suspensa. Apenas advogados regulares podem editar seu perfil."
            }), 400

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
                UPDATE USUARIOS
                SET NOME            = ?,
                    EMAIL           = ?,
                    CPF             = ?,
                    TELEFONE        = ?,
                    RG              = ?,
                    ORGAO_EXPEDIDOR = ?,
                    NUM_OAB         = ?,
                    UF_OAB          = ?,
                    NACIONALIDADE   = ?,
                    ESTADO_CIVIL    = ?,
                    SENHA           = ?
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
                UPDATE USUARIOS
                SET NOME            = ?,
                    EMAIL           = ?,
                    CPF             = ?,
                    TELEFONE        = ?,
                    RG              = ?,
                    ORGAO_EXPEDIDOR = ?,
                    NUM_OAB         = ?,
                    UF_OAB          = ?,
                    NACIONALIDADE   = ?,
                    ESTADO_CIVIL    = ?
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
                'id_usuario': id_usuario,
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








@app.route('/escritorio/<int:id_escritorio>', methods=['GET'])
def detalhes_escritorio(id_escritorio):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

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
                ae.STATUS
            FROM ESCRITORIOS e
            INNER JOIN ADVOGADO_ESCRITORIO ae ON e.ID_ESCRITORIOS = ae.ID_ESCRITORIO
            WHERE e.ID_ESCRITORIOS = ? AND ae.ID_USUARIO = ?
        """, (id_escritorio, id_usuario))

        escritorio = cur.fetchone()

        if not escritorio:
            return jsonify({'error': 'Escritório não encontrado'}), 404

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
                'data_cadastro': escritorio[15].strftime('%d/%m/%Y %H:%M') if escritorio[15] else None,
                'status': escritorio[16]
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()





@app.route('/meus_escritorios', methods=['GET'])
def meus_escritorios():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

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
                ae.STATUS
            FROM ESCRITORIOS e
            INNER JOIN ADVOGADO_ESCRITORIO ae ON e.ID_ESCRITORIOS = ae.ID_ESCRITORIOS
            WHERE ae.ID_USUARIOS = ?
            ORDER BY e.ID_ESCRITORIOS DESC
        """, (id_usuario,))

        escritorios = cur.fetchall()

        resultado = []
        for escritorio in escritorios:
            resultado.append({
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
                'data_cadastro': escritorio[15].strftime('%d/%m/%Y %H:%M') if escritorio[15] else None,
                'status': escritorio[16]
            })

        return jsonify({
            'escritorios': resultado
        }), 200

    except Exception as e:
        print(f"Erro ao buscar escritórios: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
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

        cur.execute("SELECT ID_ESCRITORIOS FROM ESCRITORIOS WHERE CNPJ = ?", (cnpj_numeros,))
        if cur.fetchone():
            return jsonify({"error": "CNPJ já cadastrado"}), 400


        cur.execute("SELECT ID_ESCRITORIOS FROM ESCRITORIOS WHERE EMAIL = ?", (email,))
        if cur.fetchone():
            return jsonify({"error": "E-mail já cadastrado"}), 400


        cur.execute("""
            INSERT INTO ESCRITORIOS (
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
                SENHA,
                DATA_CADASTRO
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID_ESCRITORIOS
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
            INSERT INTO ADVOGADO_ESCRITORIO (
                ID_USUARIOS,
                ID_ESCRITORIOS,
                STATUS
            )
            VALUES (?, ?, ?)
        """, (
            id_usuario,
            id_escritorio,
            'PROPRIETARIO'
        ))

        con.commit()

        print(f"Escritório cadastrado. ID: {id_escritorio}")
        print(f"Advogado {id_usuario} vinculado como PROPRIETARIO")

        # Salva a foto se existir
        foto_perfil = request.files.get('foto_perfil')
        if foto_perfil:
            try:
                nome_imagem = f'escritorio_{id_escritorio}.jpeg'
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'Escritorios')
                os.makedirs(caminho, exist_ok=True)
                foto_perfil.save(os.path.join(caminho, nome_imagem))
                print(f"Imagem salva: {nome_imagem}")
            except Exception as e:
                print(f"Erro ao salvar imagem: {e}")

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