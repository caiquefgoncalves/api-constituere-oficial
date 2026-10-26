# os organiza caminhos e pastas no armazenamento do servidor.
import os

# Flask conecta as funções Python às requisições do site:
# request lê os dados recebidos; jsonify cria respostas em JSON;
# send_file envia arquivos para download.
from flask import (
    jsonify,
    request,
    send_file
)

# datetime permite obter a data atual para preencher os documentos.
from datetime import datetime

# werkzeug ajuda a limpar nomes de arquivos enviados por usuários de forma segura
from werkzeug.utils import secure_filename

# Importa a aplicação Flask, a conexão com o banco de dados e as
# funções de autenticação e permissão usadas nas rotas.
from main import app
from db import conexao

from funcao import decodificar_token

from permissoes import (
    verificar_acesso_escritorio_ativo
)

# Biblioteca utilizada para manipular templates de documentos Word (.docx) injetando dados neles
from docxtpl import DocxTemplate


# =========================================================
# CONFIGURAÇÕES
# =========================================================


# Pasta dos modelos de documentos
# dirname(__file__) identifica a pasta deste código; abspath cria
# o caminho absoluto e join monta o caminho da pasta de modelos.
PASTA_MODELOS = os.path.join(
    os.path.abspath(
        os.path.dirname(__file__)
    ),
    'arquivos',
    'ModelosDocumentos'
)


# Cria a pasta no servidor, caso ainda não exista.
# exist_ok=True evita erro se ela já tiver sido criada.
os.makedirs(
    PASTA_MODELOS,
    exist_ok=True
)

# Pasta dos documentos gerados
# Os documentos prontos ficam separados dos modelos originais.
PASTA_DOCUMENTOS_GERADOS = os.path.join(
    os.path.abspath(
        os.path.dirname(__file__)
    ),
    'arquivos',
    'DocumentosGerados'
)


# Garante que a pasta de saída esteja disponível antes dos downloads.
os.makedirs(
    PASTA_DOCUMENTOS_GERADOS,
    exist_ok=True
)


# Lista dos tipos de modelo aceitos ao cadastrar ou editar.
TIPOS_PERMITIDOS = [
    'CONTRATO',
    'PETICAO_INICIAL',
    'HIPOSSUFICIENCIA'
]

# Código padrão que avisa a internet que o arquivo sendo enviado é um Word (.docx)
# MIME type: identifica para o navegador o formato do arquivo enviado.
MIMETYPE_DOCX = (
    'application/'
    'vnd.openxmlformats-officedocument.'
    'wordprocessingml.document'
)


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

# Valida quem está fazendo a requisição antes de acessar documentos.
def verificar_usuario():

    # Decodifica o token de autenticação enviado pelo usuário.
    token_data = decodificar_token()

    # Sem um token válido, interrompe a operação (HTTP 401).
    if token_data == False:

        # Cada retorno combina uma resposta JSON com o código HTTP correspondente.
        return None, (
            jsonify({
                'error':
                    'Token necessário'
            }),
            401
        )

    # O tipo 0 é o perfil autorizado a usar essas rotas (HTTP 403 se não).
    if token_data['tipo'] != 0:

        return None, (
            jsonify({
                'error':
                    'Acesso não autorizado'
            }),
            403
        )

    # Retorna os dados do usuário e None para indicar ausência de erro.
    return token_data, None


# Confere o vínculo ativo do usuário com o escritório informado.
# somente_proprietario=True exige uma permissão adicional.
def verificar_escritorio(
    id_usuario,
    id_escritorio,
    somente_proprietario=False
):

    # A verificação de acesso é centralizada em outra função do projeto.
    acesso = (
        verificar_acesso_escritorio_ativo(
            id_usuario,
            id_escritorio
        )
    )

    # Se o vínculo ou a permissão forem inválidos, devolve o erro recebido.
    if not acesso['permitido']:

        return (
            jsonify({
                'error':
                    acesso['error']
            }),
            acesso['status_http']
        )

    # Bloqueia ações administrativas (como gerenciar templates) se não for proprietário
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

    # None significa que a operação pode continuar.
    return None


# Localiza a pasta de modelos exclusiva de cada escritório.
def pasta_escritorio(
    id_escritorio
):

    # str converte o ID numérico em texto para usá-lo como nome de pasta.
    pasta = os.path.join(
        PASTA_MODELOS,
        str(id_escritorio)
    )

    # Cria a subpasta do escritório apenas quando necessário.
    os.makedirs(
        pasta,
        exist_ok=True
    )

    return pasta


# Constrói o caminho do Word original usando o ID do modelo.
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


# Faz a validação básica do arquivo recebido no cadastro.
def arquivo_docx_valido(
    arquivo
):

    # Primeiro verifica se existe arquivo e se ele possui nome.
    if not arquivo:

        return False

    if not arquivo.filename:

        return False

    # lower ignora diferenças entre maiúsculas e minúsculas;
    # strip remove espaços antes/depois do nome.
    nome = (
        arquivo.filename
        .lower()
        .strip()
    )

    # endswith verifica se a extensão informada termina em .docx.
    return nome.endswith('.docx')


# Apresenta datas no formato brasileiro: dia/mês/ano.
def formatar_data(
    data
):

    # Uma data ausente permanece como None, evitando erro de formatação.
    if not data:

        return None

    # try executa a formatação; except usa o valor original se falhar.
    try:

        return data.strftime(
            '%d/%m/%Y'
        )

    except:

        return str(data)


# Transforma uma linha do banco em um dicionário identificado por campos.
def formatar_modelo(
    row
):

    # Os índices row[0], row[1] etc. seguem a ordem do SELECT no SQL.
    return {

        'id':
            row[0],

        'nome':
            row[1],

        'tipo':
            row[2],

        'descricao':
            # or "" fornece texto vazio quando a descrição vier nula.
            row[3] or '',

        'arquivo':
            row[4],

        'ativo':
            # Converte o 1/0 armazenado no banco para True/False da API.
            row[5] == 1,

        'atualizado_em':
            formatar_data(
                row[6]
            )
    }

# Define o nome físico do documento gerado a partir de seu ID.
def caminho_documento_gerado(
    id_documento
):

    return os.path.join(
        PASTA_DOCUMENTOS_GERADOS,
        f'{id_documento}.docx'
    )


# Converte qualquer valor para texto, sem escrever "None" no Word.
def valor_texto(
    valor
):

    # Se o banco não tiver informação, o campo no documento fica vazio.
    if valor is None:

        return ''

    return str(
        valor
    )


# Formata datas opcionais utilizadas durante o preenchimento.
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


# Prepara um nome de arquivo seguro, sem caracteres inadequados.
def limpar_nome_documento(
    nome
):

    # secure_filename remove ou adapta caracteres problemáticos do nome.
    nome = secure_filename(
        nome
    )

    # Usa um nome padrão caso a limpeza resulte em texto vazio.
    if not nome:

        return 'documento'

    # Remove a extensão original para adicioná-la uma única vez depois.
    if nome.lower().endswith(
        '.docx'
    ):

        nome = nome[:-5]

    return nome

# Extrai só os dígitos; serve de base para CPF, CNPJ, CEP e telefone.
def somente_numeros(
    valor
):

    if not valor:

        return ''

    # Percorre cada caractere e junta apenas os que são números.
    return ''.join(
        caractere
        for caractere in str(valor)
        if caractere.isdigit()
    )


# Insere pontos e hífen nos 11 dígitos de um CPF.
def formatar_cpf(
    valor
):

    # Normaliza o valor recebido antes de verificar seu tamanho.
    numero = somente_numeros(
        valor
    )

    # Se houver outra quantidade de dígitos, mantém o valor informado.
    if len(numero) != 11:

        return valor_texto(
            valor
        )

    # As fatias [início:fim] selecionam os grupos de dígitos.
    return (
        f'{numero[0:3]}.'
        f'{numero[3:6]}.'
        f'{numero[6:9]}-'
        f'{numero[9:11]}'
    )


# Aplica a máscara visual de CNPJ quando há exatamente 14 dígitos.
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


# Formata telefones brasileiros com DDD e hífen.
def formatar_telefone(
    valor
):

    numero = somente_numeros(
        valor
    )

    # Onze dígitos indicam o padrão usado para celulares com nono dígito.
    if len(numero) == 11:

        return (
            f'({numero[0:2]}) '
            f'{numero[2:7]}-'
            f'{numero[7:11]}'
        )


    # Dez dígitos seguem a máscara de telefone fixo.
    if len(numero) == 10:

        return (
            f'({numero[0:2]}) '
            f'{numero[2:6]}-'
            f'{numero[6:10]}'
        )


    # Se nenhum dos formatos se aplicar, conserva o texto original.
    return valor_texto(
        valor
    )


# Insere hífen no CEP de oito dígitos.
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


# Formata o número de processo no padrão de 20 dígitos.
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

# Cria os campos de data que podem aparecer no modelo Word.
def formatar_data_atual():

    # datetime.now() consulta a data e a hora atuais do servidor.
    hoje = datetime.now()

    # Lista os meses por extenso, na ordem de janeiro a dezembro.
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

    # Retorna dia, mês, ano e uma versão completa para o documento.
    # O índice do mês subtrai 1 porque listas começam em zero.
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

# GET: fornece ao site todos os modelos cadastrados em um escritório.
# <int:id_escritorio> captura o ID diretamente do endereço da rota.
@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos',
    methods=['GET']
)
def listar_modelos_documentos(
    id_escritorio
):

    # A consulta só prossegue após validar o usuário.
    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro

    # Confirma também que esse usuário tem acesso ao escritório solicitado.
    erro_acesso = verificar_escritorio(
        token_data['id_usuarios'],
        id_escritorio
    )

    if erro_acesso:

        return erro_acesso

    # Abre a conexão e o cursor que executará os comandos SQL.
    con = conexao()
    cur = con.cursor()

    # A consulta é protegida por try/except/finally para tratar falhas.
    try:

        # SELECT escolhe as colunas; FROM indica a tabela pesquisada.
        # WHERE filtra pelo escritório; ORDER BY traz ativos e mais recentes
        # primeiro. O ? recebe id_escritorio sem concatenar texto ao SQL.
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

        # fetchall() devolve todas as linhas encontradas pela consulta.
        rows = cur.fetchall()

        # Cria a lista que será devolvida ao frontend.
        modelos = []

        # Percorre as linhas e padroniza cada modelo com formatar_modelo().
        for row in rows:

            modelos.append(
                formatar_modelo(
                    row
                )
            )

        # jsonify converte o dicionário em JSON; HTTP 200 indica sucesso.
        return jsonify({
            'modelos':
                modelos
        }), 200

    # Em caso de erro inesperado, registra o motivo no terminal e
    # devolve uma mensagem genérica (HTTP 500).
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

    # finally executa a limpeza mesmo com return ou erro;
    # fecha cursor e conexão para liberar recursos.
    finally:

        cur.close()
        con.close()


# =========================================================
# CADASTRAR MODELO
# =========================================================

# POST: recebe informações e o arquivo .docx de um novo modelo.
@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos',
    methods=['POST']
)
def cadastrar_modelo_documento(
    id_escritorio
):

    # Obtém a identidade de quem está cadastrando o modelo.
    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro

    # Gerenciar modelos é uma operação reservada ao proprietário.
    erro_acesso = verificar_escritorio(
        token_data['id_usuarios'],
        id_escritorio,
        somente_proprietario=True
    )

    if erro_acesso:

        return erro_acesso

    # request.form lê campos enviados junto ao arquivo (multipart/form-data).
    # or "" trata campo ausente; strip elimina espaços extras.
    nome = (
        request.form.get(
            'nome'
        )
        or ''
    ).strip()

    # upper padroniza o tipo em letras maiúsculas para a validação.
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

    # request.files acessa o arquivo anexado no formulário.
    arquivo = request.files.get(
        'arquivo'
    )

    # -----------------------------------------------------
    # VALIDAÇÕES
    # -----------------------------------------------------

    # A API valida os dados antes de gravar qualquer informação.
    if not nome:

        return jsonify({
            'error':
                'Nome do modelo '
                'é obrigatório.'
        }), 400

    # Limita o tamanho do nome a 150 caracteres.
    if len(nome) > 150:

        return jsonify({
            'error':
                'Nome do modelo '
                'muito longo.'
        }), 400

    # Exige a categoria do documento.
    if not tipo:

        return jsonify({
            'error':
                'Tipo do documento '
                'é obrigatório.'
        }), 400

    # Aceita apenas os tipos definidos em TIPOS_PERMITIDOS.
    if tipo not in TIPOS_PERMITIDOS:

        return jsonify({
            'error':
                'Tipo de documento '
                'inválido.'
        }), 400

    # A descrição tem limite de 500 caracteres.
    if len(descricao) > 500:

        return jsonify({
            'error':
                'Descrição muito longa.'
        }), 400

    # Recusa arquivos que não tenham nome e extensão .docx.
    if not arquivo_docx_valido(
        arquivo
    ):

        return jsonify({
            'error':
                'O arquivo precisa '
                'estar no formato .docx.'
        }), 400

    # Normaliza o nome informado para evitar caminhos inseguros.
    nome_arquivo = secure_filename(
        arquivo.filename
    )

    if not nome_arquivo:

        nome_arquivo = (
            'modelo.docx'
        )

    # Só abre a conexão com o banco após todas as validações.
    con = conexao()
    cur = con.cursor()

    # Guarda o caminho do arquivo para poder removê-lo caso haja erro.
    caminho_salvo = None

    try:

        # Primeiro cria o registro
        # para obter o ID do modelo.

        # INSERT cria o registro do modelo no banco.
        # CURRENT_TIMESTAMP salva a data; RETURNING devolve o ID criado.
        # Os sinais ? recebem os valores na mesma ordem da lista abaixo.
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

        # fetchone()[0] lê o ID retornado na primeira coluna da consulta.
        id_modelo = (
            cur.fetchone()[0]
        )

        # Agora salva fisicamente
        # usando o ID do modelo.

        # Cada arquivo é guardado pelo ID do modelo, evitando nomes repetidos.
        caminho_salvo = caminho_modelo(
            id_escritorio,
            id_modelo
        )

        # save grava no servidor o arquivo Word enviado pelo navegador.
        arquivo.save(
            caminho_salvo
        )

        # commit confirma a inclusão no banco após salvar o arquivo.
        con.commit()

        # HTTP 201 informa que o modelo foi criado e envia seus dados.
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

    # Se algum passo falhar, desfaz as alterações pendentes no banco.
    except Exception as erro:

        con.rollback()

        # Se o banco falhar depois
        # de o arquivo ter sido salvo,
        # removemos o arquivo.

        # A verificação evita tentar excluir um arquivo que não foi salvo.
        if (
            caminho_salvo
            and
            os.path.exists(
                caminho_salvo
            )
        ):

            try:

                # Remove também o .docx que tenha sido salvo parcialmente.
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

    # Encerra cursor e conexão, independentemente do resultado.
    finally:

        cur.close()
        con.close()


# =========================================================
# EDITAR INFORMAÇÕES DO MODELO
# =========================================================

# PUT: altera nome, tipo e descrição de um modelo já cadastrado.
@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos/<int:id_modelo>',
    methods=['PUT']
)
def editar_modelo_documento(
    id_escritorio,
    id_modelo
):

    # Exige usuário autenticado e, a seguir, permissão de proprietário.
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

    # request.get_json lê o JSON recebido; silent=True não lança erro
    # caso o corpo não seja JSON e or {} evita trabalhar com None.
    dados = (
        request.get_json(
            silent=True
        )
        or {}
    )

    # get busca a chave no dicionário; strip limpa espaços no início/fim.
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

    # Repete as validações essenciais antes de atualizar o registro.
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

    # Prepara a conexão para localizar e alterar o modelo.
    con = conexao()
    cur = con.cursor()

    try:

        # Verifica se o modelo existe e pertence ao escritório indicado.
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

        # fetchone devolve a primeira linha, ou None se não houver resultado.
        modelo = cur.fetchone()

        # HTTP 404 é usado quando o registro solicitado não existe.
        if not modelo:

            return jsonify({
                'error':
                    'Modelo não encontrado.'
            }), 404

        # UPDATE modifica os campos do modelo e registra a data da edição.
        # O WHERE impede que um modelo de outro escritório seja alterado.
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

        # Persiste as alterações realizadas pelo UPDATE.
        con.commit()

        return jsonify({
            'mensagem':
                'Modelo atualizado '
                'com sucesso!'
        }), 200

    # rollback cancela a alteração caso a consulta apresente falha.
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

    # A limpeza da conexão ocorre em qualquer resultado.
    finally:

        cur.close()
        con.close()


# =========================================================
# ATIVAR / INATIVAR MODELO
# =========================================================

# PUT: alterna a disponibilidade de um modelo sem apagá-lo.
@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos/<int:id_modelo>/status',
    methods=['PUT']
)
def alterar_status_modelo_documento(
    id_escritorio,
    id_modelo
):

    # Somente usuários autenticados e proprietários podem alterar o status.
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

    # Lê o JSON que contém o campo "ativo" enviado pelo frontend.
    dados = (
        request.get_json(
            silent=True
        )
        or {}
    )

    # Obtém o status solicitado, que pode ser booleano ou 0/1.
    ativo = dados.get(
        'ativo'
    )

    # Sem o campo "ativo", não é possível decidir o novo estado.
    if ativo is None:

        return jsonify({
            'error':
                'Informe o status '
                'do modelo.'
        }), 400

    # isinstance(ativo, bool) identifica True ou False.
    # A expressão condicional transforma True em 1 e False em 0.
    if isinstance(
        ativo,
        bool
    ):

        ativo_banco = (
            1
            if ativo
            else 0
        )

    # Também aceita diretamente 0 ou 1, como usados no banco.
    elif ativo in [0, 1]:

        ativo_banco = ativo

    # Outros valores são rejeitados para preservar um status consistente.
    else:

        return jsonify({
            'error':
                'Status inválido.'
        }), 400

    con = conexao()
    cur = con.cursor()

    try:

        # Procura o modelo dentro do escritório antes de modificá-lo.
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

        # Atualiza ATIVO e registra quando ocorreu a mudança.
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

        # Confirma a mudança no banco de dados.
        con.commit()

        # Escolhe a mensagem conforme o novo status do modelo.
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

        # Devolve o resultado com "ativo" como verdadeiro ou falso.
        return jsonify({
            'mensagem':
                mensagem,

            'ativo':
                ativo_banco == 1

        }), 200

    # Em caso de falha, desfaz a operação e sinaliza erro interno.
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

    # Libera os recursos usados na consulta.
    finally:

        cur.close()
        con.close()


# GET: disponibiliza o arquivo Word original do modelo.
@app.route(
    '/escritorio/<int:id_escritorio>/modelos-documentos/<int:id_modelo>/download',
    methods=['GET']
)
def baixar_modelo_documento(
    id_escritorio,
    id_modelo
):

    # Valida a identidade e o vínculo do usuário com o escritório.
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

        # Busca o nome original do arquivo para apresentá-lo no download.
        # Os dois filtros garantem ID do modelo e ID do escritório.
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

        # Sem registro correspondente, retorna que o modelo não existe.
        modelo = cur.fetchone()

        if not modelo:

            return jsonify({
                'error':
                    'Modelo não encontrado.'
            }), 404

        nome_arquivo = modelo[0]

        # Monta o caminho físico a partir do escritório e do ID do modelo.
        caminho = caminho_modelo(
            id_escritorio,
            id_modelo
        )

        # isfile confirma que o Word ainda existe no armazenamento.
        if not os.path.isfile(
            caminho
        ):

            return jsonify({
                'error':
                    'Arquivo do modelo '
                    'não encontrado.'
            }), 404

        # send_file transmite o documento; as_attachment=True solicita
        # o download e download_name define como o arquivo será nomeado.
        return send_file(

            caminho,

            mimetype=
                MIMETYPE_DOCX,

            as_attachment=True,

            download_name=
                nome_arquivo
        )

    # Trata falhas ao localizar ou enviar o arquivo.
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

    # Fecha os acessos ao banco ao finalizar a requisição.
    finally:

        cur.close()
        con.close()

# =========================================================
# MODELOS DISPONÍVEIS PARA O PROCESSO
# =========================================================

# GET: lista somente os modelos ativos compatíveis com o escritório
# ao qual o processo informado está vinculado.
@app.route(
    '/processo/<int:id_processo>/modelos-documentos',
    methods=['GET']
)
def listar_modelos_processo(
    id_processo
):

    # Confirma que a chamada parte de um usuário autorizado.
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

        # Primeiro identifica o escritório associado ao processo no banco.
        cur.execute("""
            SELECT
                ID_ESCRITORIOS
            FROM PROCESSOS
            WHERE ID_PROCESSOS = ?
        """, (
            id_processo,
        ))


        # fetchone captura a linha do processo, se ela existir.
        processo = cur.fetchone()


        # Processos inexistentes não podem receber modelos.
        if not processo:

            return jsonify({
                'error':
                    'Processo não encontrado.'
            }), 404


        # A primeira coluna consultada contém o ID do escritório.
        id_escritorio = (
            processo[0]
        )


        # Também impede a operação se não existir vínculo com escritório.
        if not id_escritorio:

            return jsonify({
                'error':
                    'O processo não está '
                    'vinculado a um escritório.'
            }), 400


        # -------------------------------------------------
        # VERIFICA ACESSO
        # -------------------------------------------------

        # A checagem de permissão usa o escritório encontrado na consulta.
        erro_acesso = verificar_escritorio(
            token_data['id_usuarios'],
            id_escritorio
        )


        if erro_acesso:

            return erro_acesso


        # -------------------------------------------------
        # MODELOS ATIVOS DO ESCRITÓRIO
        # -------------------------------------------------

        # O SELECT busca apenas modelos com ATIVO = 1 e os ordena por nome.
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


        # Prepara a lista de modelos disponíveis para escolha no site.
        modelos = []


        # Converte cada resultado para o formato esperado pelo frontend.
        for row in cur.fetchall():

            modelos.append(
                formatar_modelo(
                    row
                )
            )


        # Retorna o escritório localizado e os modelos que podem ser usados.
        return jsonify({

            'id_escritorio':
                id_escritorio,

            'modelos':
                modelos

        }), 200


    # Registra possíveis falhas sem expor detalhes internos na resposta.
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


    # Finaliza a consulta liberando cursor e conexão.
    finally:

        cur.close()
        con.close()

# =========================================================
# GERAR DOCUMENTO
# =========================================================

# POST: gera um .docx preenchido a partir de um modelo e de um processo.
# Esta rota reúne autenticação, consulta de dados, preenchimento e download.
@app.route(
    '/processo/<int:id_processo>/documentos/gerar',
    methods=['POST']
)
def gerar_documento(
    id_processo
):

    # Bloqueia a geração se o usuário não estiver autenticado.
    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro


    # Identifica quem solicitou a geração para registrar a autoria.
    id_usuario_logado = (
        token_data['id_usuarios']
    )


    # O frontend envia o ID do modelo em um corpo JSON.
    # Tenta pegar os dados enviados. O 'silent=True' impede o sistema de travar
    # caso o envio venha vazio ou com erro, devolvendo um dicionário vazio {} como plano B.
    dados = (
        request.get_json(
            silent=True
        )
        or {}
    )


    # Lê qual modelo foi escolhido pelo usuário.
    id_modelo = dados.get(
        'id_modelo'
    )


    # Sem modelo selecionado, devolve erro de requisição (HTTP 400).
    if not id_modelo:

        return jsonify({
            'error':
                'Selecione um modelo.'
        }), 400


    # int converte o ID para número inteiro; se não for possível,
    # a exceção é tratada e a operação é interrompida.
    try:

        id_modelo = int(
            id_modelo
        )

    except:

        return jsonify({
            'error':
                'Modelo inválido.'
        }), 400


    # Abre o acesso ao banco para reunir informações e registrar o resultado.
    con = conexao()
    cur = con.cursor()

    # Inicializa o caminho para permitir limpeza segura em caso de falha.
    caminho_salvo = None


    try:

        # =================================================
        # PROCESSO + CLIENTE + ADVOGADO + ESCRITÓRIO
        # =================================================

        # Esta consulta reúne em uma linha tudo que será usado no Word:
        # dados do processo, do cliente, do advogado e do escritório.
        # INNER JOIN combina tabelas pelos IDs relacionados; os apelidos
        # p, cliente, advogado e escritorio distinguem as colunas.
        # Relaciona ao processo o usuário cadastrado como cliente.
        # Relaciona ao processo o usuário cadastrado como advogado.
        # Associa o processo ao escritório responsável.
        # O filtro ? seleciona apenas o processo solicitado na URL.
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


        # Obtém a primeira linha resultante, com os dados consolidados.
        processo = cur.fetchone()


        # Sem essa associação completa, o documento não é gerado.
        if not processo:

            return jsonify({
                'error':
                    'Processo não encontrado.'
            }), 404


        # Lê o escritório encontrado para validar a permissão de acesso.
        id_escritorio = (
            processo[0]
        )


        # =================================================
        # ACESSO AO ESCRITÓRIO
        # =================================================

        # A geração só continua se o usuário pertencer ao escritório.
        erro_acesso = verificar_escritorio(
            id_usuario_logado,
            id_escritorio
        )


        if erro_acesso:

            return erro_acesso


        # =================================================
        # MODELO
        # =================================================

        # Busca o modelo solicitado e garante que ele seja do mesmo escritório.
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


        # Lê o nome original e o status do modelo escolhido.
        modelo = cur.fetchone()


        if not modelo:

            return jsonify({
                'error':
                    'Modelo não encontrado '
                    'neste escritório.'
            }), 404


        # Usa "Documento" como nome alternativo se faltar nome ao modelo.
        nome_modelo = (
            modelo[0]
            or 'Documento'
        )


        # Um modelo inativo não deve ser oferecido para gerar novos arquivos.
        if modelo[2] != 1:

            return jsonify({
                'error':
                    'Este modelo está inativo.'
            }), 400


        # Localiza o arquivo .docx que será preenchido.
        caminho_modelo_docx = (
            caminho_modelo(
                id_escritorio,
                id_modelo
            )
        )


        # Confirma que o arquivo modelo está presente no servidor.
        if not os.path.isfile(
            caminho_modelo_docx
        ):

            return jsonify({
                'error':
                    'Arquivo do modelo '
                    'não encontrado.'
            }), 404

        # Prepara a data de hoje para inseri-la no documento.
        data_atual = formatar_data_atual()

        # =================================================
        # DADOS DO DOCUMENTO
        # =================================================

        # O contexto é um dicionário de dicionários: agrupa os dados
        # nas categorias cliente, processo, advogado, escritório e data.
        # No Word, os campos podem usar, por exemplo, {{ cliente.nome }}.
        contexto = {

            # Campos do cliente: dados pessoais, contatos, endereço e empresa.
            'cliente': {

                # Cada índice do resultado corresponde a uma coluna do SELECT;
                # as funções auxiliares padronizam texto, CPF, telefone etc.
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


            # Campos do processo: identificação, assunto e informações judiciais.
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


            # Campos do advogado: nome, inscrição na OAB e contatos.
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


            # Campos do escritório: razão social, CNPJ, endereço e contatos.
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

            # A data também é enviada ao template como um grupo de campos.
            'data': data_atual
        }


        # =================================================
        # PREENCHE O MODELO
        # =================================================

        # Abre o .docx base por meio da biblioteca docxtpl.
        documento = DocxTemplate(
            caminho_modelo_docx
        )


        # render substitui as variáveis do Word pelos valores do contexto;
        # autoescape=True protege caracteres especiais no texto inserido.
        documento.render(
            contexto,
            autoescape=True
        )


        # =================================================
        # NOME DO ARQUIVO
        # =================================================

        # Normaliza o nome do modelo para formar o nome do novo arquivo.
        nome_base = limpar_nome_documento(
            nome_modelo
        )


        # Limpa também o número do processo usado como parte do nome.
        numero_processo = secure_filename(
            valor_texto(
                processo[1]
            )
        )


        # Na falta do número oficial, usa o ID do processo como alternativa.
        if not numero_processo:

            numero_processo = str(
                id_processo
            )


        # Combina o nome do modelo com o número do processo e .docx.
        nome_saida = (
            f'{nome_base}_'
            f'{numero_processo}.docx'
        )


        # =================================================
        # REGISTRA NO BANCO
        # =================================================

        # Grava um histórico do documento gerado: modelo, processo,
        # usuário responsável, nome do arquivo e data da geração.
        # RETURNING devolve o novo identificador do documento.
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


        # Recupera o ID criado para identificar o arquivo no armazenamento.
        id_documento = (
            cur.fetchone()[0]
        )


        # =================================================
        # SALVA O DOCX
        # =================================================

        # Cada documento é salvo usando o próprio ID, evitando conflitos.
        caminho_salvo = (
            caminho_documento_gerado(
                id_documento
            )
        )


        # save grava a versão preenchida, sem modificar o modelo original.
        documento.save(
            caminho_salvo
        )


        # commit confirma o registro somente após salvar o .docx com sucesso.
        con.commit()


        # =================================================
        # DEVOLVE O ARQUIVO
        # =================================================

        # Envia o Word pronto para download logo após a geração.
        return send_file(

            caminho_salvo,

            mimetype=
                MIMETYPE_DOCX,

            as_attachment=True,

            download_name=
                nome_saida
        )


    # Se surgir uma falha, cancela a operação pendente no banco.
    except Exception as erro:

        con.rollback()

# Remove eventual arquivo de saída para não deixar conteúdo órfão.

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


        # Registra o problema no terminal para auxiliar o diagnóstico.
        print(
            'Erro ao gerar documento:',
            erro
        )


        # traceback imprime a sequência das chamadas que levou ao erro.
        import traceback

        traceback.print_exc()


        # Para o usuário, retorna um erro genérico HTTP 500.
        return jsonify({
            'error':
                'Erro ao gerar documento.'
        }), 500


    # Fecha a conexão mesmo se alguma etapa não for concluída.
    finally:

        cur.close()
        con.close()

# =========================================================
# LISTAR DOCUMENTOS GERADOS
# =========================================================

# GET: apresenta o histórico de documentos gerados pelo usuário.
@app.route(
    '/documentos-gerados',
    methods=['GET']
)
def listar_documentos_gerados():

    # Confirma a identidade antes de consultar o histórico.
    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro


    # O ID do usuário será usado para filtrar seus próprios documentos.
    id_usuario = (
        token_data['id_usuarios']
    )


    con = conexao()
    cur = con.cursor()


    try:

        # Consulta registros de documentos e reúne informações dos modelos,
        # processos, clientes e escritórios por meio dos INNER JOINs.
        # O filtro exige que o usuário tenha gerado o documento e mantenha
        # um vínculo ativo com o escritório associado.
        # Esta associação representa o vínculo ativo com o escritório.
        # A condição seleciona documentos criados pelo usuário logado.
        # Mostra primeiro as gerações mais recentes.
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


        # Lista onde serão reunidos os documentos encontrados.
        documentos = []


        # Percorre todos os resultados retornados pela consulta SQL.
        for row in cur.fetchall():

            # Prioriza nome, razão social ou nome fantasia do cliente;
            # or escolhe a primeira informação disponível.
            nome_cliente = (
                row[8]
                or row[9]
                or row[10]
                or '--'
            )


            # Faz o mesmo para selecionar um nome legível do escritório.
            nome_escritorio = (
                row[12]
                or row[13]
                or '--'
            )


            # Inicia a data como ausente antes de tentar formatá-la.
            data_geracao = None


            # Se a data existe, converte para dia/mês/ano hora:minuto.
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


            # Monta um dicionário com os dados que o frontend exibirá na lista.
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


        # Devolve a lista e a quantidade total de registros encontrados.
        return jsonify({

            'documentos':
                documentos,

            'quantidade':
                len(documentos)

        }), 200


    # Registra no servidor uma possível falha da consulta.
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


    # Libera cursor e conexão independentemente do resultado.
    finally:

        cur.close()
        con.close()

# =========================================================
# BAIXAR DOCUMENTO GERADO
# =========================================================

# GET: baixa novamente um documento anteriormente gerado.
@app.route(
    '/documentos-gerados/<int:id_documento>/download',
    methods=['GET']
)
def baixar_documento_gerado(
    id_documento
):

    # Valida quem está tentando acessar o arquivo.
    token_data, erro = (
        verificar_usuario()
    )

    if erro:

        return erro


    # Recupera o usuário logado para filtrar a consulta.
    id_usuario = (
        token_data['id_usuarios']
    )


    con = conexao()
    cur = con.cursor()


    try:

        # A consulta só encontra documentos gerados pelo próprio usuário;
        # também recupera o escritório do processo relacionado.
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


        # Obtém o documento encontrado ou None quando não houver acesso.
        documento = cur.fetchone()


        # Para IDs não encontrados, responde HTTP 404.
        if not documento:

            return jsonify({
                'error':
                    'Documento não encontrado.'
            }), 404


        # Recupera o nome de download guardado no banco.
        nome_arquivo = (
            documento[0]
        )

        # Recupera o escritório para uma segunda verificação de permissão.
        id_escritorio = (
            documento[1]
        )


        # -------------------------------------------------
        # CONFIRMA QUE AINDA TEM ACESSO AO ESCRITÓRIO
        # -------------------------------------------------

        # Mesmo que tenha gerado o documento, o usuário precisa manter
        # acesso ativo ao escritório para poder baixá-lo.
        erro_acesso = verificar_escritorio(
            id_usuario,
            id_escritorio
        )


        if erro_acesso:

            return erro_acesso


        # Localiza no disco o .docx identificado pelo ID do documento.
        caminho = (
            caminho_documento_gerado(
                id_documento
            )
        )


        # Se o arquivo não existir mais no servidor, informa HTTP 404.
        if not os.path.isfile(
            caminho
        ):

            return jsonify({
                'error':
                    'Arquivo não encontrado.'
            }), 404


        # Envia o arquivo em formato Word como anexo para download.
        return send_file(

            caminho,

            mimetype=
                MIMETYPE_DOCX,

            as_attachment=True,

            download_name=
                nome_arquivo
        )


    # Qualquer erro inesperado vira uma resposta HTTP 500.
    except Exception as erro:

        print(
            'Erro ao baixar documento:',
            erro
        )


        return jsonify({
            'error':
                'Erro ao baixar documento.'
        }), 500


    # Garante o fechamento do cursor e da conexão.
    finally:

        cur.close()
        con.close()