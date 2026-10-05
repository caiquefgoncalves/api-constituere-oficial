import os

from flask import (
    jsonify,
    request,
    send_file
)

from werkzeug.utils import secure_filename

from main import app
from db import conexao

from funcao import decodificar_token

from permissoes import (
    verificar_acesso_escritorio_ativo
)


# =========================================================
# CONFIGURAÇÕES
# =========================================================

PASTA_MODELOS = os.path.join(
    os.path.abspath(
        os.path.dirname(__file__)
    ),
    'arquivos',
    'ModelosDocumentos'
)


os.makedirs(
    PASTA_MODELOS,
    exist_ok=True
)


TIPOS_PERMITIDOS = [
    'CONTRATO',
    'PETICAO_INICIAL',
    'HIPOSSUFICIENCIA'
]


MIMETYPE_DOCX = (
    'application/'
    'vnd.openxmlformats-officedocument.'
    'wordprocessingml.document'
)


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def verificar_usuario():

    token_data = decodificar_token()

    if token_data == False:

        return None, (
            jsonify({
                'error':
                    'Token necessário'
            }),
            401
        )

    if token_data['tipo'] != 0:

        return None, (
            jsonify({
                'error':
                    'Acesso não autorizado'
            }),
            403
        )

    return token_data, None


def verificar_escritorio(
    id_usuario,
    id_escritorio,
    somente_proprietario=False
):

    acesso = (
        verificar_acesso_escritorio_ativo(
            id_usuario,
            id_escritorio
        )
    )

    if not acesso['permitido']:

        return (
            jsonify({
                'error':
                    acesso['error']
            }),
            acesso['status_http']
        )

    if (
        somente_proprietario
        and
        acesso['status'] != 'PROPRIETARIO'
    ):

        return (
            jsonify({
                'error':
                    'Apenas o proprietário '
                    'pode realizar esta ação.'
            }),
            403
        )

    return None


def pasta_escritorio(
    id_escritorio
):

    pasta = os.path.join(
        PASTA_MODELOS,
        str(id_escritorio)
    )

    os.makedirs(
        pasta,
        exist_ok=True
    )

    return pasta


def caminho_modelo(
    id_escritorio,
    id_modelo
):

    return os.path.join(
        pasta_escritorio(
            id_escritorio
        ),
        f'{id_modelo}.docx'
    )


def arquivo_docx_valido(
    arquivo
):

    if not arquivo:

        return False

    if not arquivo.filename:

        return False

    nome = (
        arquivo.filename
        .lower()
        .strip()
    )

    return nome.endswith('.docx')


def formatar_data(
    data
):

    if not data:

        return None

    try:

        return data.strftime(
            '%d/%m/%Y'
        )

    except:

        return str(data)


def formatar_modelo(
    row
):

    return {

        'id':
            row[0],

        'nome':
            row[1],

        'tipo':
            row[2],

        'descricao':
            row[3] or '',

        'arquivo':
            row[4],

        'ativo':
            row[5] == 1,

        'atualizado_em':
            formatar_data(
                row[6]
            )
    }


# =========================================================
# LISTAR MODELOS
# =========================================================

@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos',
    methods=['GET']
)
def listar_modelos_documentos(
    id_escritorio
):

    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro

    erro_acesso = verificar_escritorio(
        token_data['id_usuarios'],
        id_escritorio
    )

    if erro_acesso:

        return erro_acesso

    con = conexao()
    cur = con.cursor()

    try:

        cur.execute("""
            SELECT
                ID_MODELOS_DOCUMENTOS,
                NOME,
                TIPO,
                DESCRICAO,
                NOME_ARQUIVO,
                ATIVO,
                DATA_ATUALIZACAO
            FROM MODELOS_DOCUMENTOS
            WHERE ID_ESCRITORIOS = ?
            ORDER BY
                ATIVO DESC,
                DATA_ATUALIZACAO DESC,
                ID_MODELOS_DOCUMENTOS DESC
        """, (
            id_escritorio,
        ))

        rows = cur.fetchall()

        modelos = []

        for row in rows:

            modelos.append(
                formatar_modelo(
                    row
                )
            )

        return jsonify({
            'modelos':
                modelos
        }), 200

    except Exception as erro:

        print(
            'Erro ao listar modelos:',
            erro
        )

        return jsonify({
            'error':
                'Erro ao carregar '
                'os modelos de documentos.'
        }), 500

    finally:

        cur.close()
        con.close()


# =========================================================
# CADASTRAR MODELO
# =========================================================

@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos',
    methods=['POST']
)
def cadastrar_modelo_documento(
    id_escritorio
):

    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro

    erro_acesso = verificar_escritorio(
        token_data['id_usuarios'],
        id_escritorio,
        somente_proprietario=True
    )

    if erro_acesso:

        return erro_acesso

    nome = (
        request.form.get(
            'nome'
        )
        or ''
    ).strip()

    tipo = (
        request.form.get(
            'tipo'
        )
        or ''
    ).strip().upper()

    descricao = (
        request.form.get(
            'descricao'
        )
        or ''
    ).strip()

    arquivo = request.files.get(
        'arquivo'
    )

    # -----------------------------------------------------
    # VALIDAÇÕES
    # -----------------------------------------------------

    if not nome:

        return jsonify({
            'error':
                'Nome do modelo '
                'é obrigatório.'
        }), 400

    if len(nome) > 150:

        return jsonify({
            'error':
                'Nome do modelo '
                'muito longo.'
        }), 400

    if not tipo:

        return jsonify({
            'error':
                'Tipo do documento '
                'é obrigatório.'
        }), 400

    if tipo not in TIPOS_PERMITIDOS:

        return jsonify({
            'error':
                'Tipo de documento '
                'inválido.'
        }), 400

    if len(descricao) > 500:

        return jsonify({
            'error':
                'Descrição muito longa.'
        }), 400

    if not arquivo_docx_valido(
        arquivo
    ):

        return jsonify({
            'error':
                'O arquivo precisa '
                'estar no formato .docx.'
        }), 400

    nome_arquivo = secure_filename(
        arquivo.filename
    )

    if not nome_arquivo:

        nome_arquivo = (
            'modelo.docx'
        )

    con = conexao()
    cur = con.cursor()

    caminho_salvo = None

    try:

        # Primeiro cria o registro
        # para obter o ID do modelo.

        cur.execute("""
            INSERT INTO MODELOS_DOCUMENTOS (
                ID_ESCRITORIOS,
                NOME,
                TIPO,
                DESCRICAO,
                NOME_ARQUIVO,
                ATIVO,
                DATA_ATUALIZACAO
            )
            VALUES (
                ?, ?, ?, ?, ?, 1,
                CURRENT_TIMESTAMP
            )
            RETURNING ID_MODELOS_DOCUMENTOS
        """, (
            id_escritorio,
            nome,
            tipo,
            descricao
                if descricao
                else None,
            nome_arquivo
        ))

        id_modelo = (
            cur.fetchone()[0]
        )

        # Agora salva fisicamente
        # usando o ID do modelo.

        caminho_salvo = caminho_modelo(
            id_escritorio,
            id_modelo
        )

        arquivo.save(
            caminho_salvo
        )

        con.commit()

        return jsonify({

            'mensagem':
                'Modelo cadastrado '
                'com sucesso!',

            'modelo': {

                'id':
                    id_modelo,

                'nome':
                    nome,

                'tipo':
                    tipo,

                'descricao':
                    descricao,

                'arquivo':
                    nome_arquivo,

                'ativo':
                    True,

                'atualizado_em':
                    None
            }

        }), 201

    except Exception as erro:

        con.rollback()

        # Se o banco falhar depois
        # de o arquivo ter sido salvo,
        # removemos o arquivo.

        if (
            caminho_salvo
            and
            os.path.exists(
                caminho_salvo
            )
        ):

            try:

                os.remove(
                    caminho_salvo
                )

            except:

                pass

        print(
            'Erro ao cadastrar modelo:',
            erro
        )

        return jsonify({
            'error':
                'Erro ao cadastrar '
                'o modelo de documento.'
        }), 500

    finally:

        cur.close()
        con.close()


# =========================================================
# EDITAR INFORMAÇÕES DO MODELO
# =========================================================

@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos/<int:id_modelo>',
    methods=['PUT']
)
def editar_modelo_documento(
    id_escritorio,
    id_modelo
):

    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro

    erro_acesso = verificar_escritorio(
        token_data['id_usuarios'],
        id_escritorio,
        somente_proprietario=True
    )

    if erro_acesso:

        return erro_acesso

    dados = (
        request.get_json(
            silent=True
        )
        or {}
    )

    nome = (
        dados.get('nome')
        or ''
    ).strip()

    tipo = (
        dados.get('tipo')
        or ''
    ).strip().upper()

    descricao = (
        dados.get('descricao')
        or ''
    ).strip()

    if not nome:

        return jsonify({
            'error':
                'Nome do modelo '
                'é obrigatório.'
        }), 400

    if len(nome) > 150:

        return jsonify({
            'error':
                'Nome do modelo '
                'muito longo.'
        }), 400

    if tipo not in TIPOS_PERMITIDOS:

        return jsonify({
            'error':
                'Tipo de documento '
                'inválido.'
        }), 400

    if len(descricao) > 500:

        return jsonify({
            'error':
                'Descrição muito longa.'
        }), 400

    con = conexao()
    cur = con.cursor()

    try:

        cur.execute("""
            SELECT
                ID_MODELO
            FROM MODELOS_DOCUMENTOS
            WHERE ID_MODELOS_DOCUMENTOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_modelo,
            id_escritorio
        ))

        modelo = cur.fetchone()

        if not modelo:

            return jsonify({
                'error':
                    'Modelo não encontrado.'
            }), 404

        cur.execute("""
            UPDATE MODELOS_DOCUMENTOS
            SET
                NOME = ?,
                TIPO = ?,
                DESCRICAO = ?,
                DATA_ATUALIZACAO =
                    CURRENT_TIMESTAMP
            WHERE ID_MODELOS_DOCUMENTOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            nome,
            tipo,
            descricao
                if descricao
                else None,
            id_modelo,
            id_escritorio
        ))

        con.commit()

        return jsonify({
            'mensagem':
                'Modelo atualizado '
                'com sucesso!'
        }), 200

    except Exception as erro:

        con.rollback()

        print(
            'Erro ao editar modelo:',
            erro
        )

        return jsonify({
            'error':
                'Erro ao atualizar '
                'o modelo.'
        }), 500

    finally:

        cur.close()
        con.close()


# =========================================================
# ATIVAR / INATIVAR MODELO
# =========================================================

@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos/<int:id_modelo>/status',
    methods=['PUT']
)
def alterar_status_modelo_documento(
    id_escritorio,
    id_modelo
):

    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro

    erro_acesso = verificar_escritorio(
        token_data['id_usuarios'],
        id_escritorio,
        somente_proprietario=True
    )

    if erro_acesso:

        return erro_acesso

    dados = (
        request.get_json(
            silent=True
        )
        or {}
    )

    ativo = dados.get(
        'ativo'
    )

    if ativo is None:

        return jsonify({
            'error':
                'Informe o status '
                'do modelo.'
        }), 400

    if isinstance(
        ativo,
        bool
    ):

        ativo_banco = (
            1
            if ativo
            else 0
        )

    elif ativo in [0, 1]:

        ativo_banco = ativo

    else:

        return jsonify({
            'error':
                'Status inválido.'
        }), 400

    con = conexao()
    cur = con.cursor()

    try:

        cur.execute("""
            SELECT
                ID_MODELOS_DOCUMENTOS
            FROM MODELOS_DOCUMENTOS
            WHERE ID_MODELOS_DOCUMENTOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_modelo,
            id_escritorio
        ))

        if not cur.fetchone():

            return jsonify({
                'error':
                    'Modelo não encontrado.'
            }), 404

        cur.execute("""
            UPDATE MODELOS_DOCUMENTOS
            SET
                ATIVO = ?,
                DATA_ATUALIZACAO =
                    CURRENT_TIMESTAMP
            WHERE ID_MODELOS_DOCUMENTOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            ativo_banco,
            id_modelo,
            id_escritorio
        ))

        con.commit()

        if ativo_banco == 1:

            mensagem = (
                'Modelo ativado '
                'com sucesso!'
            )

        else:

            mensagem = (
                'Modelo inativado '
                'com sucesso!'
            )

        return jsonify({
            'mensagem':
                mensagem,

            'ativo':
                ativo_banco == 1

        }), 200

    except Exception as erro:

        con.rollback()

        print(
            'Erro ao alterar status:',
            erro
        )

        return jsonify({
            'error':
                'Erro ao alterar '
                'o status do modelo.'
        }), 500

    finally:

        cur.close()
        con.close()


@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos/<int:id_modelo>/download',
    methods=['GET']
)
def baixar_modelo_documento(
    id_escritorio,
    id_modelo
):

    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro

    erro_acesso = verificar_escritorio(
        token_data['id_usuarios'],
        id_escritorio
    )

    if erro_acesso:

        return erro_acesso

    con = conexao()
    cur = con.cursor()

    try:

        cur.execute("""
            SELECT
                NOME_ARQUIVO
            FROM MODELOS_DOCUMENTOS
            WHERE ID_MODELOS_DOCUMENTOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_modelo,
            id_escritorio
        ))

        modelo = cur.fetchone()

        if not modelo:

            return jsonify({
                'error':
                    'Modelo não encontrado.'
            }), 404

        nome_arquivo = modelo[0]

        caminho = caminho_modelo(
            id_escritorio,
            id_modelo
        )

        if not os.path.isfile(
            caminho
        ):

            return jsonify({
                'error':
                    'Arquivo do modelo '
                    'não encontrado.'
            }), 404

        return send_file(

            caminho,

            mimetype=
                MIMETYPE_DOCX,

            as_attachment=True,

            download_name=
                nome_arquivo
        )

    except Exception as erro:

        print(
            'Erro ao baixar modelo:',
            erro
        )

        return jsonify({
            'error':
                'Erro ao baixar '
                'o modelo.'
        }), 500

    finally:

        cur.close()
        con.close()