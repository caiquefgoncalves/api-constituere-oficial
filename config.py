import os.path

SECRET_KEY = 'chave_super_secreta_constituere_2026'
DEBUG = True


DB_HOST = 'localhost'
DB_NAME = r'C:\Users\Usuario\Desktop\api-constituere-oficial-main\BANCO_CONSTITUERE.FDB'
DB_USER = 'sysdba'
DB_PASSWORD = 'SYSDBA'

UPLOAD_FOLDER = os.path.abspath(os.path.dirname(__file__))
