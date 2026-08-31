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
import json


@app.route('/criar_usuarios', methods=['POST'])
def criar_usuarios():
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
    tipo = request.form.get('tipo')

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
    if tipo is None:
        return jsonify({"error": "Tipo de usuário é obrigatório"}), 400

    try:
        tipo = int(tipo)
    except ValueError:
        return jsonify({"error": "Tipo de usuário inválido"}), 400

    if tipo not in [0, 1, 2, 3]:
        return jsonify({"error": "Tipo de usuário inválido"}), 400

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
            data_limpa = data_nascimento.replace('/', '').replace('-', '')
            if len(data_limpa) == 8:
                dia, mes, ano = data_limpa[0:2], data_limpa[2:4], data_limpa[4:8]
                if 1 <= int(dia) <= 31 and 1 <= int(mes) <= 12 and 1900 <= int(ano) <= 2100:
                    data_nascimento_salvar = f"{ano}-{mes}-{dia}"
        except:
            pass

    senha_cripto = generate_password_hash(senha).decode('utf-8')
    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            INSERT INTO USUARIOS (
                NOME, EMAIL, SENHA, CPF, TELEFONE, TIPO,
                RG, ORGAO_EXPEDIDOR, NUM_OAB, UF_OAB,
                NACIONALIDADE, ESTADO_CIVIL, DATA_NASCIMENTO,
                SEXO, PROFISSAO, CNPJ, RAZAO_SOCIAL, NOME_FANTASIA,
                CEP, LOGRADOURO, NUMERO, COMPLEMENTO, BAIRRO,
                CIDADE, ESTADO, CARTERA_TRABALHO, SERIE_CARTERA,
                DATA_CADASTRO, ATIVO, ID_USUARIO_RESPONSAVEL
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING ID_USUARIOS
        """, (
            nome, email, senha_cripto, cpf, telefone, tipo,
            rg, orgao_expedidor, num_oab, uf_oab,
            nacionalidade, estado_civil, data_nascimento_salvar,
            sexo, profissao, cnpj, razao_social, nome_fantasia,
            cep, logradouro, numero, complemento, bairro,
            cidade, estado, carteira_trabalho, serie_carteira,
            datetime.datetime.now(), 1, id_usuario_logado
        ))

        id_usuario = cur.fetchone()[0]
        con.commit()

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
                "error": f"Sua situação é {situacao}. Apenas advogados regulares podem editar seu perfil."
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
                cpf_limpo,
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
                cpf_limpo,
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


    if not validar_cpf(cpf_cnpj):
        return jsonify({"error": "Usuário não encontrado"}), 404

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


        if not check_password_hash(senha_hash, senha):
            return jsonify({"error": "CPF/CNPJ ou senha incorretos"}), 400


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
            INNER JOIN ADVOGADO_ESCRITORIO ae ON e.ID_ESCRITORIOS = ae.ID_ESCRITORIOS
            WHERE e.ID_ESCRITORIOS = ? AND ae.ID_USUARIOS = ?
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
        print(f"Erro ao buscar detalhes do escritório: {e}")
        import traceback
        traceback.print_exc()
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

    dados = request.get_json()

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

    status = status.strip().upper()

    if status not in ['PROPRIETARIO', 'PARCEIRO', 'ASSOCIADO']:
        return jsonify({
            'sucesso': False,
            'mensagem': 'A posição deve ser PROPRIETARIO, PARCEIRO ou ASSOCIADO.'
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
            SELECT ID, STATUS
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
                'mensagem': 'Você não possui acesso a este escritório.'
            }), 403



        cursor.execute("""
            SELECT
                ID_ESCRITORIOS,
                NOME_FANTASIA
            FROM ESCRITORIOS
            WHERE ID_ESCRITORIOS = ?
        """, (id_escritorio,))

        escritorio_dados = cursor.fetchone()

        if not escritorio_dados:
            return jsonify({
                'sucesso': False,
                'mensagem': 'Escritório não encontrado.'
            }), 404

        nome_escritorio = escritorio_dados[1]



        cursor.execute("""
            SELECT
                ID_USUARIOS,
                NOME,
                EMAIL,
                TIPO
            FROM USUARIOS
            WHERE EMAIL = ?
        """, (email.strip(),))

        advogado = cursor.fetchone()

        if not advogado:
            return jsonify({
                'sucesso': False,
                'mensagem': 'Não foi encontrado nenhum usuário cadastrado com esse e-mail.'
            }), 404

        id_advogado = advogado[0]
        nome_advogado = advogado[1]
        email_advogado = advogado[2]
        tipo_usuario = advogado[3]



        if tipo_usuario != 0:
            return jsonify({
                'sucesso': False,
                'mensagem': 'O usuário informado não é um advogado.'
            }), 400



        if id_advogado == id_usuario_logado:
            return jsonify({
                'sucesso': False,
                'mensagem': 'Você não pode adicionar a si mesmo ao escritório.'
            }), 400



        cursor.execute("""
            SELECT
                ID,
                STATUS
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
            AND ID_ESCRITORIOS = ?
        """, (
            id_advogado,
            id_escritorio
        ))

        vinculo = cursor.fetchone()

        if vinculo:
            return jsonify({
                'sucesso': False,
                'mensagem': 'Este advogado já está vinculado a este escritório.'
            }), 400



        cursor.execute("""
            INSERT INTO ADVOGADO_ESCRITORIO
            (
                ID_USUARIOS,
                ID_ESCRITORIOS,
                STATUS
            )
            VALUES (?, ?, ?)
        """, (
            id_advogado,
            id_escritorio,
            status
        ))

        conexao_db.commit()



        enviar_email(
            email_advogado,
            'Convite para escritório - Constituere',
            nome_escritorio,
            nome_advogado
        )

        return jsonify({
            'sucesso': True,
            'mensagem': 'Advogado adicionado ao escritório com sucesso.'
        }), 200

    except Exception as e:

        if conexao_db:
            try:
                conexao_db.rollback()
            except:
                pass

        return jsonify({
            'sucesso': False,
            'mensagem': f'Erro ao adicionar advogado: {str(e)}'
        }), 500

    finally:

        if cursor:
            cursor.close()

        if conexao_db:
            conexao_db.close()


@app.route('/representante', methods=['POST'])
def criar_representante():
    """
    Rota para cadastrar um representante de um cliente jurídico
    """
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

        cur.execute("SELECT ID_REPRESENTANTE FROM REPRESENTANTES WHERE CPF = ? AND ID_CLIENTE_JURIDICO = ?", (cpf, id_cliente))
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
                ID_USUARIOS, NOME, CPF, EMAIL, TELEFONE,
                TIPO, ATIVO, RAZAO_SOCIAL, NOME_FANTASIA,
                CNPJ, DATA_CADASTRO
            FROM USUARIOS
            WHERE TIPO IN (2, 3)
            AND ID_USUARIO_RESPONSAVEL = ?
            ORDER BY DATA_CADASTRO DESC
        """, (id_usuario,))

        rows = cur.fetchall()
        clientes = []
        for row in rows:
            nome_exibicao = row[1] if row[1] else (row[7] or row[8] or '--')
            doc = row[2] if row[2] else (row[9] if row[9] else '--')
            if doc and doc != '--':
                if len(doc) == 11:
                    doc = f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
                elif len(doc) == 14:
                    doc = f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"
            status = 'ativo' if row[6] == 1 else 'inativo'
            data_cadastro = row[10].strftime('%d/%m/%Y') if row[10] else None

            clientes.append({
                'id': row[0],
                'nome': nome_exibicao,
                'cpf': doc,
                'email': row[3] or '--',
                'telefone': row[4] or '--',
                'tipo': 'fisico' if row[5] == 2 else 'juridico',
                'status': status,
                'data_cadastro': data_cadastro
            })

        return jsonify({'clientes': clientes}), 200

    except Exception as e:
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
                SEXO, DATA_NASCIMENTO,
                ID_USUARIO_RESPONSAVEL
            FROM USUARIOS
            WHERE ID_USUARIOS = ? AND TIPO IN (2, 3)
        """, (id_cliente,))

        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'Cliente não encontrado'}), 404

        if row[25] != id_usuario:
            return jsonify({'error': 'Você não tem permissão para acessar este cliente'}), 403

        cliente = {
            'id': row[0],
            'nome': row[1] if row[1] else (row[7] or row[8] or '--'),
            'cpf': row[2] if row[2] else (row[9] if row[9] else '--'),
            'email': row[3] or '--',
            'telefone': row[4] or '--',
            'tipo': 'fisico' if row[5] == 2 else 'juridico',
            'status': 'ativo' if row[6] == 1 else 'inativo',
            'data_cadastro': row[10].strftime('%d/%m/%Y') if row[10] else None,
            'rg': row[11] or '--',
            'orgao_expedidor': row[12] or '--',
            'nacionalidade': row[13] or '--',
            'estado_civil': row[14] or '--',
            'profissao': row[15] or '--',
            'cep': row[16] or '--',
            'logradouro': row[17] or '--',
            'numero': row[18] or '--',
            'complemento': row[19] or '--',
            'bairro': row[20] or '--',
            'cidade': row[21] or '--',
            'estado': row[22] or '--',
            'sexo': row[23] or '--',
            'data_nascimento': row[24].strftime('%d/%m/%Y') if row[24] else None,
            'razao_social': row[7] or '--',
            'nome_fantasia': row[8] or '--'
        }

        if cliente['tipo'] == 'juridico':
            cur.execute("""
                SELECT
                    NOME_COMPLETO, PROFISSAO, CPF, SEXO,
                    RG, ORGAO_EXPEDIDOR, NACIONALIDADE, ESTADO_CIVIL
                FROM REPRESENTANTES
                WHERE ID_CLIENTE_JURIDICO = ? AND ATIVO = 1
            """, (id_cliente,))
            rep = cur.fetchone()
            if rep:
                cliente['representante'] = {
                    'nome': rep[0] or '--',
                    'profissao': rep[1] or '--',
                    'cpf': rep[2] or '--',
                    'sexo': rep[3] or '--',
                    'rg': rep[4] or '--',
                    'orgao_expedidor': rep[5] or '--',
                    'nacionalidade': rep[6] or '--',
                    'estado_civil': rep[7] or '--'
                }

        return jsonify({'cliente': cliente}), 200

    except Exception as e:
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

    dados = request.get_json()

    nome = dados.get('nome')
    cpf = dados.get('cpf')
    email = dados.get('email')
    telefone = dados.get('telefone')

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("SELECT ID_USUARIOS FROM USUARIOS WHERE ID_USUARIOS = ?", (id_cliente,))
        if not cur.fetchone():
            return jsonify({'error': 'Cliente não encontrado'}), 404

        cur.execute("""
            UPDATE USUARIOS
            SET NOME = ?,
                CPF = ?,
                EMAIL = ?,
                TELEFONE = ?
            WHERE ID_USUARIOS = ?
        """, (nome, cpf, email, telefone, id_cliente))

        con.commit()
        return jsonify({'message': 'Cliente atualizado com sucesso!'}), 200

    except Exception as e:
        con.rollback()
        print(f"Erro ao atualizar cliente: {e}")
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
            WHERE ID_USUARIOS = ? AND STATUS = 'PROPRIETARIO'
        """, (id_usuario,))
        escritorio = cur.fetchone()
        if not escritorio:
            return jsonify({'error': 'Nenhum escritório encontrado para edição'}), 404

        id_escritorio = escritorio[0]

        cur.execute("SELECT ID_ESCRITORIOS FROM ESCRITORIOS WHERE CNPJ = ? AND ID_ESCRITORIOS != ?", (cnpj_numeros, id_escritorio))
        if cur.fetchone():
            return jsonify({"error": "CNPJ já cadastrado em outro escritório"}), 400

        cur.execute("SELECT ID_ESCRITORIOS FROM ESCRITORIOS WHERE EMAIL = ? AND ID_ESCRITORIOS != ?", (email, id_escritorio))
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
            SELECT ID_ESCRITORIOS
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ? AND STATUS = 'PROPRIETARIO'
        """, (id_usuario,))
        escritorio = cur.fetchone()
        if not escritorio:
            return jsonify({'error': 'Nenhum escritório encontrado'}), 404

        id_escritorio = escritorio[0]

        cur.execute("""
            SELECT
                ID_ESCRITORIOS,
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
            """, (
                id_usuario_logado,
                id_escritorio
            ))

            pertence = cur.fetchone()

            if not pertence:
                return jsonify({
                    'error': 'Você não possui acesso a este escritório'
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
                ae_logado.STATUS

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
                AND u.ATIVO = 1
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

        cur.execute(sql, tuple(parametros))

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
                    'oab': (
                        f'{row[3]}/{row[4]}'
                        if row[3] and row[4]
                        else row[3] or '--'
                    ),
                    'escritorios': []
                }

            status_logado = row[9]

            pode_gerenciar = (
                status_logado is not None
                and status_logado.upper() == 'PROPRIETARIO'
            )

            advogados_dict[id_advogado]['escritorios'].append({
                'id': row[5],
                'nome': (
                    row[6]
                    or row[7]
                    or '--'
                ),
                'status': row[8] or '--',
                'pode_gerenciar': pode_gerenciar
            })

        advogados = list(advogados_dict.values())

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

@app.route('/alterar_cargo_advogado/<int:id_advogado>/<int:id_escritorio>',methods=['PUT'])
def alterar_cargo_advogado(id_advogado, id_escritorio):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_usuario_logado = token_data['id_usuarios']

    # Apenas advogados
    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json()

    if not dados:
        return jsonify({'error': 'Dados não enviados'}), 400

    novo_status = dados.get('status')

    if not novo_status:
        return jsonify({'error': 'Status é obrigatório'}), 400

    novo_status = novo_status.upper()

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
            SELECT STATUS
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
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

        if (
            status_atual
            and status_atual.upper() == novo_status
        ):
            return jsonify({
                'error': f'Advogado já é {novo_status}'
            }), 400

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

        con.commit()

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