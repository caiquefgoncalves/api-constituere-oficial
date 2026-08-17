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


def decodificar_token():
    """
    Decodifica o token JWT - Tenta várias fontes
    Prioridade: 1. Header X-Access-Token, 2. Cookie, 3. Outras fontes
    """
    try:
        token = None

        # 1. PRIORIDADE: Tenta do header X-Access-Token (enviado pelo front-end)
        token = request.headers.get('X-Access-Token')
        if token:
            print("✅ Token encontrado no header X-Access-Token")

        # 2. Tenta do cookie
        if not token:
            token = request.cookies.get('acess_token')
            if token:
                print("✅ Token encontrado no cookie")

        # 3. Tenta do header Authorization (fallback)
        if not token:
            auth_header = request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                if token:
                    print("✅ Token encontrado no header Authorization")

        if not token:
            print("❌ Token não encontrado em nenhuma fonte")
            return False

        senha_secreta = current_app.config['SECRET_KEY']
        payload = jwt.decode(token, senha_secreta, algorithms=['HS256'])

        print(f"✅ Token decodificado - ID: {payload['id_usuarios']}, Tipo: {payload['tipo']}")
        return {'tipo': payload['tipo'], 'id_usuarios': payload['id_usuarios']}

    except jwt.ExpiredSignatureError:
        print("❌ Token expirado")
        return False
    except jwt.InvalidTokenError as e:
        print(f"❌ Token inválido: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro ao decodificar token: {e}")
        return False


def validar_cpf(cpf):
    cpf = ''.join(filter(str.isdigit, str(cpf)))

    if len(cpf) != 11:
        return False

    if cpf == cpf[0] * 11:
        return False

    soma = 0

    for i in range(9):
        soma += int(cpf[i]) * (10 - i)

    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto

    if int(cpf[9]) != digito1:
        return False

    soma = 0

    for i in range(10):
        soma += int(cpf[i]) * (11 - i)

    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto

    if int(cpf[10]) != digito2:
        return False

    return True