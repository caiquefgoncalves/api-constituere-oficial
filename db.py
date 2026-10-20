import os
import struct
from pathlib import Path

import fdb
from flask import current_app


def _cliente_firebird():
    configurado = os.getenv('FIREBIRD_CLIENT_DLL')
    locais = ([Path(configurado)] if configurado else []) + [
        Path(os.getenv('PROGRAMFILES(X86)', r'C:\\Program Files (x86)')) / 'Firebird' / 'Firebird_4_0' / 'fbclient.dll',
        Path(os.getenv('LOCALAPPDATA', '')) / 'Firebird' / 'Firebird_4_0_Client' / 'fbclient.dll',
        Path(os.getenv('PROGRAMFILES', r'C:\\Program Files')) / 'Firebird' / 'Firebird_4_0' / 'fbclient.dll',
    ]
    arquitetura_python = 64 if struct.calcsize('P') == 8 else 32
    for caminho in locais:
        if caminho.is_file() and _dll_compativel(caminho, arquitetura_python):
            return str(caminho)
    return None


def _dll_compativel(caminho, arquitetura_python):
    try:
        with caminho.open('rb') as arquivo:
            arquivo.seek(0x3C)
            deslocamento_pe = struct.unpack('<I', arquivo.read(4))[0]
            arquivo.seek(deslocamento_pe + 4)
            maquina = struct.unpack('<H', arquivo.read(2))[0]
    except (OSError, struct.error):
        return False

    return (arquitetura_python == 32 and maquina == 0x014C) or (
        arquitetura_python == 64 and maquina == 0x8664
    )


def conexao():
    parametros = {
        'host': current_app.config['DB_HOST'],
        'database': current_app.config['DB_NAME'],
        'user': current_app.config['DB_USER'],
        'password': current_app.config['DB_PASSWORD'],
    }

    cliente_firebird = _cliente_firebird()

    if cliente_firebird:
        parametros['fb_library_name'] = cliente_firebird

    return fdb.connect(
        **parametros
    )
