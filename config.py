import os
from pathlib import Path

SECRET_KEY = 'chave_super_secreta_constituere_2026'
DEBUG = True

DB_HOST = 'localhost'
DB_USER = 'sysdba'
DB_PASSWORD = 'SYSDBA'

DB_NAME = str(Path(__file__).with_name('BANCO_CONSTITUERE.FDB'))

LOG_DB_NAME = str(Path(__file__).with_name('Log.FDB'))
LOG_DB_USER = 'sysdba'
LOG_DB_PASSWORD = 'SYSDBA'

UPLOAD_FOLDER = os.path.abspath(os.path.dirname(__file__))