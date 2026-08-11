from flask_bcrypt import generate_password_hash, check_password_hash
from flask import jsonify, request
from db import conexao
from flask import current_app
import jwt
import datetime



def verificar_existente(valor, campo, id_usuarios=None):
    con = conexao()
    cur = con.cursor()

    try:
        campos_permitidos = {
            "CPF": "CPF",
            "EMAIL": "EMAIL",
            "NUM_OAB": "NUM_OAB"
        }

        if campo not in campos_permitidos:
            return False

        coluna = campos_permitidos[campo]

        if id_usuarios:
            cur.execute(
                f"""
                SELECT 1
                FROM USUARIOS
                WHERE {coluna} = ?
                AND ID_USUARIOS != ?
                """,
                (valor, id_usuarios)
            )
        else:
            cur.execute(
                f"""
                SELECT 1
                FROM USUARIOS
                WHERE {coluna} = ?
                """,
                (valor,)
            )

        return cur.fetchone() is not None

    except Exception as e:
        print(f"Erro ao verificar existência: {e}")
        return False

    finally:
        cur.close()
        con.close()



def senha_correspondente(senha, confirmar_senha):
    return senha == confirmar_senha



def senha_forte(senha):
    if len(senha) < 8: return False
    criterios = {"maiuscula": False, "minuscula": False, "numero": False, "especial": False}
    for s in senha:
        if s.isupper():
            criterios["maiuscula"] = True
        elif s.islower():
            criterios["minuscula"] = True
        elif s.isdigit():
            criterios["numero"] = True
        elif not s.isalnum():
            criterios["especial"] = True
    return all(criterios.values())



def gerar_token(tipo, id_usuarios, tempo):
    payload = {
        'tipo': tipo,
        'id_usuarios': id_usuarios,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=tempo)
    }
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def decodificar_token(token_recebido=None):
    try:
        token = token_recebido


        if not token:
            token = request.cookies.get('acess_token')
        if not token:
            token = request.form.get('token')
        if not token:
            token = request.args.get('token')


        if not token:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]

        if not token:
            return False

        senha_secreta = current_app.config['SECRET_KEY']
        payload = jwt.decode(token, senha_secreta, algorithms=['HS256'])

        return {'tipo': payload['tipo'], 'id_usuarios': payload['id_usuarios']}

    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False
    except Exception:
        return False