import os
from pathlib import Path


def carregar_env_local():
    arquivo_env = Path(__file__).with_name('.env')

    if not arquivo_env.is_file():
        return

    for linha in arquivo_env.read_text(encoding='utf-8').splitlines():
        linha = linha.strip()

        if not linha or linha.startswith('#') or '=' not in linha:
            continue

        chave, valor = linha.split('=', 1)
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")


        if chave and not os.environ.get(chave):
            os.environ[chave] = valor


carregar_env_local()

SECRET_KEY = 'chave_super_secreta_constituere_2026'
DEBUG = True


DB_HOST = 'localhost'
DB_NAME = r'C:\Users\Aluno\Desktop\api-constituere-oficial-main\BANCO_CONSTITUERE.FDB'
DB_USER = 'sysdba'
DB_PASSWORD = 'sysdba'

UPLOAD_FOLDER = os.path.abspath(os.path.dirname(__file__))
