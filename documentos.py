import os

from flask import (
    jsonify,
    request,
    send_file
)

from datetime import datetime

from werkzeug.utils import secure_filename

from main import app
from db import conexao

from funcao import decodificar_token

from permissoes import (
    verificar_acesso_escritorio_ativo
)

from docxtpl import DocxTemplate


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

PASTA_DOCUMENTOS_GERADOS = os.path.join(
    os.path.abspath(
        os.path.dirname(__file__)
    ),
    'arquivos',
    'DocumentosGerados'
)


os.makedirs(
    PASTA_DOCUMENTOS_GERADOS,
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

def caminho_documento_gerado(
    id_documento
):

    return os.path.join(
        PASTA_DOCUMENTOS_GERADOS,
        f'{id_documento}.docx'
    )


def valor_texto(
    valor
):

    if valor is None:

        return ''

    return str(
        valor
    )


def valor_data(
    valor
):

    if not valor:

        return ''

    try:

        return valor.strftime(
            '%d/%m/%Y'
        )

    except:

        return str(
            valor
        )


def limpar_nome_documento(
    nome
):

    nome = secure_filename(
        nome
    )

    if not nome:

        return 'documento'

    if nome.lower().endswith(
        '.docx'
    ):

        nome = nome[:-5]

    return nome

def somente_numeros(
    valor
):

    if not valor:

        return ''

    return ''.join(
        caractere
        for caractere in str(valor)
        if caractere.isdigit()
    )


def formatar_cpf(
    valor
):

    numero = somente_numeros(
        valor
    )

    if len(numero) != 11:

        return valor_texto(
            valor
        )

    return (
        f'{numero[0:3]}.'
        f'{numero[3:6]}.'
        f'{numero[6:9]}-'
        f'{numero[9:11]}'
    )


def formatar_cnpj(
    valor
):

    numero = somente_numeros(
        valor
    )

    if len(numero) != 14:

        return valor_texto(
            valor
        )

    return (
        f'{numero[0:2]}.'
        f'{numero[2:5]}.'
        f'{numero[5:8]}/'
        f'{numero[8:12]}-'
        f'{numero[12:14]}'
    )


def formatar_telefone(
    valor
):

    numero = somente_numeros(
        valor
    )

    if len(numero) == 11:

        return (
            f'({numero[0:2]}) '
            f'{numero[2:7]}-'
            f'{numero[7:11]}'
        )


    if len(numero) == 10:

        return (
            f'({numero[0:2]}) '
            f'{numero[2:6]}-'
            f'{numero[6:10]}'
        )


    return valor_texto(
        valor
    )


def formatar_cep(
    valor
):

    numero = somente_numeros(
        valor
    )

    if len(numero) != 8:

        return valor_texto(
            valor
        )

    return (
        f'{numero[0:5]}-'
        f'{numero[5:8]}'
    )


def formatar_numero_processo(
    valor
):

    numero = somente_numeros(
        valor
    )

    if len(numero) != 20:

        return valor_texto(
            valor
        )

    return (
        f'{numero[0:7]}-'
        f'{numero[7:9]}.'
        f'{numero[9:13]}.'
        f'{numero[13]}.'
        f'{numero[14:16]}.'
        f'{numero[16:20]}'
    )

def formatar_data_atual():

    hoje = datetime.now()

    meses = [
        'janeiro',
        'fevereiro',
        'março',
        'abril',
        'maio',
        'junho',
        'julho',
        'agosto',
        'setembro',
        'outubro',
        'novembro',
        'dezembro'
    ]

    return {
        'dia': hoje.day,
        'mes': meses[hoje.month - 1],
        'ano': hoje.year,
        'completa':
            f'{hoje.day} de '
            f'{meses[hoje.month - 1]} de '
            f'{hoje.year}'
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
                ID_MODELOS_DOCUMENTOS
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

# =========================================================
# MODELOS DISPONÍVEIS PARA O PROCESSO
# =========================================================

@app.route(
    '/processo/<int:id_processo>/modelos-documentos',
    methods=['GET']
)
def listar_modelos_processo(
    id_processo
):

    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro


    con = conexao()
    cur = con.cursor()


    try:

        # -------------------------------------------------
        # BUSCA O ESCRITÓRIO DO PROCESSO
        # -------------------------------------------------

        cur.execute("""
            SELECT
                ID_ESCRITORIOS
            FROM PROCESSOS
            WHERE ID_PROCESSOS = ?
        """, (
            id_processo,
        ))


        processo = cur.fetchone()


        if not processo:

            return jsonify({
                'error':
                    'Processo não encontrado.'
            }), 404


        id_escritorio = (
            processo[0]
        )


        if not id_escritorio:

            return jsonify({
                'error':
                    'O processo não está '
                    'vinculado a um escritório.'
            }), 400


        # -------------------------------------------------
        # VERIFICA ACESSO
        # -------------------------------------------------

        erro_acesso = verificar_escritorio(
            token_data['id_usuarios'],
            id_escritorio
        )


        if erro_acesso:

            return erro_acesso


        # -------------------------------------------------
        # MODELOS ATIVOS DO ESCRITÓRIO
        # -------------------------------------------------

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
              AND ATIVO = 1
            ORDER BY NOME
        """, (
            id_escritorio,
        ))


        modelos = []


        for row in cur.fetchall():

            modelos.append(
                formatar_modelo(
                    row
                )
            )


        return jsonify({

            'id_escritorio':
                id_escritorio,

            'modelos':
                modelos

        }), 200


    except Exception as erro:

        print(
            'Erro ao buscar modelos '
            'do processo:',
            erro
        )


        return jsonify({
            'error':
                'Erro ao carregar modelos.'
        }), 500


    finally:

        cur.close()
        con.close()

# =========================================================
# GERAR DOCUMENTO
# =========================================================

@app.route(
    '/processo/<int:id_processo>/documentos/gerar',
    methods=['POST']
)
def gerar_documento(
    id_processo
):

    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro


    id_usuario_logado = (
        token_data['id_usuarios']
    )


    dados = (
        request.get_json(
            silent=True
        )
        or {}
    )


    id_modelo = dados.get(
        'id_modelo'
    )


    if not id_modelo:

        return jsonify({
            'error':
                'Selecione um modelo.'
        }), 400


    try:

        id_modelo = int(
            id_modelo
        )

    except:

        return jsonify({
            'error':
                'Modelo inválido.'
        }), 400


    con = conexao()
    cur = con.cursor()

    caminho_salvo = None


    try:

        # =================================================
        # PROCESSO + CLIENTE + ADVOGADO + ESCRITÓRIO
        # =================================================

        cur.execute("""
            SELECT
                p.ID_ESCRITORIOS,
                p.NUM_PROCESSO,
                p.TIPO_PROCESSO,
                p.ASSUNTO,
                p.AREA,
                p.COMARCA,
                p.VARA,
                p.INSTANCIA,
                p.DATA_INICIO,

                cliente.NOME,
                cliente.CPF,
                cliente.CNPJ,
                cliente.RG,
                cliente.ORGAO_EXPEDIDOR,
                cliente.NACIONALIDADE,
                cliente.ESTADO_CIVIL,
                cliente.PROFISSAO,
                cliente.EMAIL,
                cliente.TELEFONE,
                cliente.CEP,
                cliente.LOGRADOURO,
                cliente.NUMERO,
                cliente.COMPLEMENTO,
                cliente.BAIRRO,
                cliente.CIDADE,
                cliente.ESTADO,
                cliente.RAZAO_SOCIAL,
                cliente.NOME_FANTASIA,

                advogado.NOME,
                advogado.NUM_OAB,
                advogado.EMAIL,
                advogado.TELEFONE,

                escritorio.NOME_FANTASIA,
                escritorio.RAZAO_SOCIAL,
                escritorio.CNPJ,
                escritorio.TELEFONE,
                escritorio.EMAIL,
                escritorio.CEP,
                escritorio.CIDADE,
                escritorio.ESTADO

            FROM PROCESSOS p

            INNER JOIN USUARIOS cliente
                ON cliente.ID_USUARIOS =
                   p.ID_USUARIOS_CLIENTE

            INNER JOIN USUARIOS advogado
                ON advogado.ID_USUARIOS =
                   p.ID_USUARIOS_ADVOGADO

            INNER JOIN ESCRITORIOS escritorio
                ON escritorio.ID_ESCRITORIOS =
                   p.ID_ESCRITORIOS

            WHERE p.ID_PROCESSOS = ?
        """, (
            id_processo,
        ))


        processo = cur.fetchone()


        if not processo:

            return jsonify({
                'error':
                    'Processo não encontrado.'
            }), 404


        id_escritorio = (
            processo[0]
        )


        # =================================================
        # ACESSO AO ESCRITÓRIO
        # =================================================

        erro_acesso = verificar_escritorio(
            id_usuario_logado,
            id_escritorio
        )


        if erro_acesso:

            return erro_acesso


        # =================================================
        # MODELO
        # =================================================

        cur.execute("""
            SELECT
                NOME,
                NOME_ARQUIVO,
                ATIVO
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
                    'Modelo não encontrado '
                    'neste escritório.'
            }), 404


        nome_modelo = (
            modelo[0]
            or 'Documento'
        )


        if modelo[2] != 1:

            return jsonify({
                'error':
                    'Este modelo está inativo.'
            }), 400


        caminho_modelo_docx = (
            caminho_modelo(
                id_escritorio,
                id_modelo
            )
        )


        if not os.path.isfile(
            caminho_modelo_docx
        ):

            return jsonify({
                'error':
                    'Arquivo do modelo '
                    'não encontrado.'
            }), 404

        data_atual = formatar_data_atual()

        # =================================================
        # DADOS DO DOCUMENTO
        # =================================================

        contexto = {

            'cliente': {

                'nome':
                    valor_texto(
                        processo[9]
                    ),

                'cpf':
                    formatar_cpf(
                        processo[10]
                    ),

                'cnpj':
                    formatar_cnpj(
                        processo[11]
                    ),

                'rg':
                    valor_texto(
                        processo[12]
                    ),

                'orgao_expedidor':
                    valor_texto(
                        processo[13]
                    ),

                'nacionalidade':
                    valor_texto(
                        processo[14]
                    ),

                'estado_civil':
                    valor_texto(
                        processo[15]
                    ),

                'profissao':
                    valor_texto(
                        processo[16]
                    ),

                'email':
                    valor_texto(
                        processo[17]
                    ),

                'telefone':
                    formatar_telefone(
                        processo[18]
                    ),

                'cep':
                    formatar_cep(
                        processo[19]
                    ),

                'logradouro':
                    valor_texto(
                        processo[20]
                    ),

                'numero':
                    valor_texto(
                        processo[21]
                    ),

                'complemento':
                    valor_texto(
                        processo[22]
                    ),

                'bairro':
                    valor_texto(
                        processo[23]
                    ),

                'cidade':
                    valor_texto(
                        processo[24]
                    ),

                'estado':
                    valor_texto(
                        processo[25]
                    ),

                'razao_social':
                    valor_texto(
                        processo[26]
                    ),

                'nome_fantasia':
                    valor_texto(
                        processo[27]
                    )
            },


            'processo': {

                'numero':
                    formatar_numero_processo(
                        processo[1]
                    ),

                'tipo':
                    valor_texto(
                        processo[2]
                    ),

                'assunto':
                    valor_texto(
                        processo[3]
                    ),

                'area':
                    valor_texto(
                        processo[4]
                    ),

                'comarca':
                    valor_texto(
                        processo[5]
                    ),

                'vara':
                    valor_texto(
                        processo[6]
                    ),

                'instancia':
                    valor_texto(
                        processo[7]
                    ),

                'data_inicio':
                    formatar_data(
                        processo[8]
                    )
            },


            'advogado': {

                'nome':
                    valor_texto(
                        processo[28]
                    ),

                'oab':
                    valor_texto(
                        processo[29]
                    ),

                'email':
                    valor_texto(
                        processo[30]
                    ),

                'telefone':
                    formatar_telefone(
                        processo[31]
                    )
            },


            'escritorio': {

                'nome_fantasia':
                    valor_texto(
                        processo[32]
                    ),

                'razao_social':
                    valor_texto(
                        processo[33]
                    ),

                'cnpj':
                    formatar_cnpj(
                        processo[34]
                    ),

                'telefone':
                    formatar_telefone(
                        processo[35]
                    ),

                'email':
                    valor_texto(
                        processo[36]
                    ),
                'cep':
                    formatar_cep(
                        processo[37]
                    ),

                'cidade':
                    valor_texto(
                        processo[38]
                    ),

                'estado':
                    valor_texto(
                        processo[39]
                    )
            },

            'data': data_atual
        }


        # =================================================
        # PREENCHE O MODELO
        # =================================================

        documento = DocxTemplate(
            caminho_modelo_docx
        )


        documento.render(
            contexto,
            autoescape=True
        )


        # =================================================
        # NOME DO ARQUIVO
        # =================================================

        nome_base = limpar_nome_documento(
            nome_modelo
        )


        numero_processo = secure_filename(
            valor_texto(
                processo[1]
            )
        )


        if not numero_processo:

            numero_processo = str(
                id_processo
            )


        nome_saida = (
            f'{nome_base}_'
            f'{numero_processo}.docx'
        )


        # =================================================
        # REGISTRA NO BANCO
        # =================================================

        cur.execute("""
            INSERT INTO DOCUMENTOS_GERADOS (
                ID_MODELOS_DOCUMENTOS,
                ID_PROCESSOS,
                ID_USUARIOS_GERADOR,
                NOME_ARQUIVO,
                NOME_MODELO,
                DATA_GERACAO
            )
            VALUES (
                ?, ?, ?, ?, ?,
                CURRENT_TIMESTAMP
            )
            RETURNING ID_DOCUMENTOS_GERADOS
        """, (
            id_modelo,
            id_processo,
            id_usuario_logado,
            nome_saida,
            nome_modelo
        ))


        id_documento = (
            cur.fetchone()[0]
        )


        # =================================================
        # SALVA O DOCX
        # =================================================

        caminho_salvo = (
            caminho_documento_gerado(
                id_documento
            )
        )


        documento.save(
            caminho_salvo
        )


        con.commit()


        # =================================================
        # DEVOLVE O ARQUIVO
        # =================================================

        return send_file(

            caminho_salvo,

            mimetype=
                MIMETYPE_DOCX,

            as_attachment=True,

            download_name=
                nome_saida
        )


    except Exception as erro:

        con.rollback()


        if (
            caminho_salvo
            and
            os.path.isfile(
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
            'Erro ao gerar documento:',
            erro
        )


        import traceback

        traceback.print_exc()


        return jsonify({
            'error':
                'Erro ao gerar documento.'
        }), 500


    finally:

        cur.close()
        con.close()

# =========================================================
# LISTAR DOCUMENTOS GERADOS
# =========================================================

@app.route(
    '/documentos-gerados',
    methods=['GET']
)
def listar_documentos_gerados():

    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro


    id_usuario = (
        token_data['id_usuarios']
    )


    con = conexao()
    cur = con.cursor()


    try:

        cur.execute("""
            SELECT
                dg.ID_DOCUMENTOS_GERADOS,
                dg.NOME_ARQUIVO,
                dg.NOME_MODELO,
                dg.DATA_GERACAO,

                m.TIPO,

                p.ID_PROCESSOS,
                p.NUM_PROCESSO,

                cliente.ID_USUARIOS,
                cliente.NOME,
                cliente.RAZAO_SOCIAL,
                cliente.NOME_FANTASIA,

                e.ID_ESCRITORIOS,
                e.NOME_FANTASIA,
                e.RAZAO_SOCIAL

            FROM DOCUMENTOS_GERADOS dg

            INNER JOIN MODELOS_DOCUMENTOS m
                ON m.ID_MODELOS_DOCUMENTOS =
                   dg.ID_MODELOS_DOCUMENTOS

            INNER JOIN PROCESSOS p
                ON p.ID_PROCESSOS =
                   dg.ID_PROCESSOS

            INNER JOIN USUARIOS cliente
                ON cliente.ID_USUARIOS =
                   p.ID_USUARIOS_CLIENTE

            INNER JOIN ESCRITORIOS e
                ON e.ID_ESCRITORIOS =
                   p.ID_ESCRITORIOS

            INNER JOIN ADVOGADO_ESCRITORIO acesso
                ON acesso.ID_ESCRITORIOS =
                   p.ID_ESCRITORIOS

               AND acesso.ID_USUARIOS = ?

               AND acesso.ATIVO = 1

            WHERE
                dg.ID_USUARIOS_GERADOR = ?

            ORDER BY
                dg.DATA_GERACAO DESC,
                dg.ID_DOCUMENTOS_GERADOS DESC
        """, (
            id_usuario,
            id_usuario
        ))


        documentos = []


        for row in cur.fetchall():

            nome_cliente = (
                row[8]
                or row[9]
                or row[10]
                or '--'
            )


            nome_escritorio = (
                row[12]
                or row[13]
                or '--'
            )


            data_geracao = None


            if row[3]:

                try:

                    data_geracao = (
                        row[3].strftime(
                            '%d/%m/%Y %H:%M'
                        )
                    )

                except:

                    data_geracao = str(
                        row[3]
                    )


            documentos.append({

                'id':
                    row[0],

                'nome_arquivo':
                    row[1],

                'nome_modelo':
                    row[2],

                'data_geracao':
                    data_geracao,

                'tipo':
                    row[4],

                'id_processo':
                    row[5],

                'numero_processo':
                    row[6] or '--',

                'id_cliente':
                    row[7],

                'cliente':
                    nome_cliente,

                'id_escritorio':
                    row[11],

                'escritorio':
                    nome_escritorio
            })


        return jsonify({

            'documentos':
                documentos,

            'quantidade':
                len(documentos)

        }), 200


    except Exception as erro:

        print(
            'Erro ao listar documentos:',
            erro
        )


        return jsonify({
            'error':
                'Erro ao carregar '
                'os documentos.'
        }), 500


    finally:

        cur.close()
        con.close()

# =========================================================
# BAIXAR DOCUMENTO GERADO
# =========================================================

@app.route(
    '/documentos-gerados/<int:id_documento>/download',
    methods=['GET']
)
def baixar_documento_gerado(
    id_documento
):

    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro


    id_usuario = (
        token_data['id_usuarios']
    )


    con = conexao()
    cur = con.cursor()


    try:

        cur.execute("""
            SELECT
                dg.NOME_ARQUIVO,
                p.ID_ESCRITORIOS

            FROM DOCUMENTOS_GERADOS dg

            INNER JOIN PROCESSOS p
                ON p.ID_PROCESSOS =
                   dg.ID_PROCESSOS

            WHERE
                dg.ID_DOCUMENTOS_GERADOS = ?

              AND dg.ID_USUARIOS_GERADOR = ?
        """, (
            id_documento,
            id_usuario
        ))


        documento = cur.fetchone()


        if not documento:

            return jsonify({
                'error':
                    'Documento não encontrado.'
            }), 404


        nome_arquivo = (
            documento[0]
        )

        id_escritorio = (
            documento[1]
        )


        # -------------------------------------------------
        # CONFIRMA QUE AINDA TEM ACESSO AO ESCRITÓRIO
        # -------------------------------------------------

        erro_acesso = verificar_escritorio(
            id_usuario,
            id_escritorio
        )


        if erro_acesso:

            return erro_acesso


        caminho = (
            caminho_documento_gerado(
                id_documento
            )
        )


        if not os.path.isfile(
            caminho
        ):

            return jsonify({
                'error':
                    'Arquivo não encontrado.'
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
            'Erro ao baixar documento:',
            erro
        )


        return jsonify({
            'error':
                'Erro ao baixar documento.'
        }), 500


    finally:

        cur.close()
        con.close()