import os
from pathlib import Path

import fdb
from flask import current_app

def conexao():
    parametros = {
        'host': current_app.config['DB_HOST'],
        'database': current_app.config['DB_NAME'],
        'user': current_app.config['DB_USER'],
        'password': current_app.config['DB_PASSWORD'],
    }

    cliente_firebird = os.getenv('FIREBIRD_CLIENT_DLL')
    if not cliente_firebird:
        cliente_local = (
            Path(os.getenv('LOCALAPPDATA', ''))
            / 'Firebird'
            / 'Firebird_4_0_Client'
            / 'fbclient.dll'
        )
        if cliente_local.is_file():
            cliente_firebird = str(cliente_local)

    if cliente_firebird:
        parametros['fb_library_name'] = cliente_firebird

    return fdb.connect(
        **parametros
    )
