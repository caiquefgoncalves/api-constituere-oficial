# os lê configurações do ambiente; secrets cria códigos aleatórios seguros.
import os
import secrets
# datetime trabalha com datas e horários; timedelta calcula intervalos,
# como adicionar 10 minutos ao horário atual.
from datetime import datetime, timedelta
# ZoneInfo identifica o fuso horário para não depender do horário
# configurado na máquina que executa a API.
from zoneinfo import ZoneInfo

# requests faz chamadas HTTP a serviços externos, como as APIs do Google.
import requests
# Flask transforma funções Python em endpoints da aplicação.
# jsonify monta respostas em JSON; request lê dados recebidos;
# redirect encaminha o navegador para outra página.
from flask import jsonify, request, redirect
# Flow organiza as etapas de autorização OAuth 2.0 com o Google.
# O usuário autoriza o acesso sem compartilhar sua senha com o Constituere.
from google_auth_oauthlib.flow import Flow
# O serializer assina os dados temporários usados na autorização.
# BadSignature identifica dados alterados/inválidos; SignatureExpired,
# autorizações que passaram do tempo permitido.
from itsdangerous import (
    URLSafeTimedSerializer,
    BadSignature,
    SignatureExpired
)

# Recursos próprios do sistema: conexão com o banco, autenticação
# de usuário e a aplicação Flask que registra as rotas.
from db import conexao
from funcao import decodificar_token
from main import app

# Bibliotecas oficiais do Google: Credentials representa as credenciais;
# GoogleRequest permite renová-las; build prepara o acesso à API Calendar.
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build


# PERMISSÕES SOLICITADAS AO GOOGLE
# SCOPES define quais operações o usuário será convidado a autorizar:
# identificação da conta, leitura do e-mail, gerenciamento de eventos
# e consulta de disponibilidade. Nem toda permissão é usada neste arquivo.
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar.freebusy'
]




# CONFIGURAÇÃO DO AMBIENTE E DA AUTORIZAÇÃO
# Durante testes locais, a biblioteca OAuth precisa aceitar o endereço HTTP
# usado pelo desenvolvimento. Essa exceção não vale para servidores públicos.
def configurar_http_local():
    # os.environ.get lê uma variável de ambiente. O segundo argumento ('')
    # é o valor usado caso a configuração não exista.
    redirect_uri = os.environ.get(
        'GOOGLE_REDIRECT_URI',
        ''
    )

    # startswith verifica o começo do endereço: a exceção é liberada
    # apenas quando o retorno está configurado para localhost/127.0.0.1.
    if (
        redirect_uri.startswith('http://localhost')
        or redirect_uri.startswith('http://127.0.0.1')
    ):
        # Ativa a exceção de HTTP inseguro somente nesse cenário local.
        # Em produção, o fluxo de autorização deve utilizar HTTPS.
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


# Reúne as informações necessárias para o Google reconhecer
# a aplicação: identificador, segredo e endereço de retorno.
def configuracao_google():
    # Esses dados vêm do ambiente (.env carregado na aplicação),
    # evita colocá-los diretamente no código-fonte.
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')

    # raise interrompe a função com um erro descritivo caso falte
    # o identificador exigido para iniciar a integração.
    if not client_id:
        raise Exception(
            'GOOGLE_CLIENT_ID não configurado no .env'
        )

    # Sem o segredo do cliente, não é possível concluir a troca
    # do código de autorização por credenciais.
    if not client_secret:
        raise Exception(
            'GOOGLE_CLIENT_SECRET não configurado no .env'
        )

    # O redirect URI informa a página da API para a qual o Google
    # retornará depois que o usuário permitir ou recusar o acesso.
    if not redirect_uri:
        raise Exception(
            'GOOGLE_REDIRECT_URI não configurado no .env'
        )

    # Retorna um dicionário Python no formato aceito pelo Flow.
    # auth_uri abre o consentimento; token_uri troca/renova credenciais.
    return {
        'web': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': (
                'https://accounts.google.com/o/oauth2/auth'
            ),
            'token_uri': (
                'https://oauth2.googleapis.com/token'
            ),
            'redirect_uris': [
                redirect_uri
            ]
        }
    }


# Constrói o fluxo OAuth utilizado tanto para conectar a conta
# quanto para concluir a autorização quando o Google retornar.
def criar_flow(
    state=None,
    code_verifier=None
):
    # Executa a configuração de teste antes de iniciar a comunicação.
    configurar_http_local()

    # Flow.from_client_config cria a configuração do OAuth.
    # state identifica a solicitação; code_verifier participa da validação PKCE - Proof Key for Code Exchange (Chave de Prova para Troca de Código)
    # O PKCE é um protocolo de segurança criado para impedir que um hacker intercepte e roube o código de autorização que o Google devolve para a sua aplicação.;
    # a geração automática é desligada porque o código é criado pela aplicação.
    flow = Flow.from_client_config(
        configuracao_google(),
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,  # Passa a senha que você gerou manualmente
        autogenerate_code_verifier=False  # Avisa a biblioteca para não gerar outra sozinha
    )

    # Indica para qual rota o Google deve redirecionar o navegador
    # ao fim da autorização.
    flow.redirect_uri = os.environ.get(
        'GOOGLE_REDIRECT_URI'
    )

    # Devolve o objeto Flow pronto para ser usado pela etapa chamadora.
    return flow


# Cria um assinador para os dados temporários da autorização.
# A chave secreta da aplicação protege a assinatura; salt separa este uso
# de outros tokens assinados pelo mesmo sistema.
def criar_serializer_google():
    return URLSafeTimedSerializer(
        app.config['SECRET_KEY'],
        salt='google-calendar-oauth'
    )




# CONEXÃO COM O BANCO DE DADOS
# Consulta se um advogado já vinculou uma conta Google ao Constituere.
def buscar_conexao_google(id_usuario):
    # conexao abre o banco de dados; cursor executa comandos SQL
    # e permite ler os resultados.
    con = conexao()
    cur = con.cursor()

    # try/finally garante o fechamento da conexão, mesmo se ocorrer
    # erro ou se a função terminar antes do previsto.
    try:
        # SELECT escolhe as colunas desejadas; WHERE limita a busca
        # ao usuário informado. O '?' representa um parâmetro passado à consulta,
        # sem concatenar o valor diretamente no SQL.
        cur.execute(
            """
            SELECT
                GOOGLE_EMAIL,
                REFRESH_TOKEN,
                ATIVO
            FROM GOOGLE_CALENDAR
            WHERE ID_USUARIOS = ?
            """,
            (id_usuario,)
        )

        # fetchone lê o primeiro registro da consulta, ou None se não houver.
        resultado = cur.fetchone()

        # Se nenhuma conexão foi cadastrada, devolve None.
        if not resultado:
            return None

        # Converte a linha do banco em um dicionário com nomes claros.
        # No campo ativo, '== 1' transforma o indicador numérico em True/False.
        return {
            'google_email': resultado[0],
            'refresh_token': resultado[1],
            'ativo': resultado[2] == 1
        }

    # finally sempre libera o cursor e a conexão depois da leitura.
    finally:
        cur.close()
        con.close()


# Salva uma nova conexão ou atualiza a já existente.
# Assim, o mesmo advogado não precisa ganhar uma nova linha a cada vínculo.
def salvar_conexao_google(
    id_usuario,
    google_email,
    refresh_token
):
    con = conexao()
    cur = con.cursor()

    # Tudo ocorre dentro de uma transação: as mudanças só são
    # confirmadas após o comando commit.
    try:
        # Primeiro verifica se já existe cadastro com o ID deste usuário.
        cur.execute(
            """
            SELECT ID_USUARIOS
            FROM GOOGLE_CALENDAR
            WHERE ID_USUARIOS = ?
            """,
            (id_usuario,)
        )

        # O resultado define qual operação SQL deve ser usada.
        existente = cur.fetchone()

        # Caso já exista um registro, UPDATE substitui e-mail e token
        # e reativa a conexão.
        if existente:
            cur.execute(
                """
                UPDATE GOOGLE_CALENDAR
                SET GOOGLE_EMAIL = ?,
                    REFRESH_TOKEN = ?,
                    ATIVO = 1
                WHERE ID_USUARIOS = ?
                """,
                (
                    google_email,
                    refresh_token,
                    id_usuario
                )
            )

        # Se for a primeira conexão, INSERT cria o registro e associa
        # o e-mail e o token de renovação ao advogado.
        else:
            cur.execute(
                """
                INSERT INTO GOOGLE_CALENDAR (
                    ID_USUARIOS,
                    GOOGLE_EMAIL,
                    REFRESH_TOKEN,
                    ATIVO
                )
                VALUES (?, ?, ?, 1)
                """,
                (
                    id_usuario,
                    google_email,
                    refresh_token
                )
            )

        # commit confirma definitivamente a inclusão ou alteração no banco.
        con.commit()

    # Se houver falha, rollback desfaz alterações ainda não confirmadas;
    # raise repassa o erro para quem chamou a função.
    except Exception:
        con.rollback()
        raise

    # Fecha recursos do banco independentemente do resultado.
    finally:
        cur.close()
        con.close()


# Desativa a integração no banco quando o usuário desconecta a agenda.
# O registro permanece salvo, mas ATIVO passa para 0.
def desativar_conexao_google(id_usuario):
    con = conexao()
    cur = con.cursor()

    try:
        # UPDATE altera apenas a conexão que pertence ao ID informado.
        cur.execute(
            """
            UPDATE GOOGLE_CALENDAR
            SET ATIVO = 0
            WHERE ID_USUARIOS = ?
            """,
            (id_usuario,)
        )

        # Registra a desativação; em caso de erro, rollback impede
        # que a operação fique parcialmente confirmada.
        con.commit()

    except Exception:
        con.rollback()
        raise

    # Fecha as estruturas utilizadas para acessar o banco.
    finally:
        cur.close()
        con.close()



# ROTA 1 | INICIAR A CONEXÃO
# @app.route vincula o endereço HTTP abaixo à função Python.
# GET inicia a autorização e retorna a URL de consentimento do Google.
@app.route(
    '/google/calendar/conectar',
    methods=['GET']
)
def conectar_google_calendar():
    # Identifica o usuário autenticado a partir do token enviado na requisição.
    token_data = decodificar_token()

    # HTTP 401 indica que faltou autenticação válida.
    # jsonify transforma o dicionário em uma resposta JSON.
    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    # HTTP 403 indica que o usuário existe, mas não tem o perfil
    # permitido: aqui, somente advogados (tipo 0) podem conectar a agenda.
    if token_data['tipo'] != 0:
        return jsonify({
            'error': (
                'Apenas advogados podem '
                'conectar o Google Agenda'
            )
        }), 403

    # A partir daqui, a API prepara uma solicitação individual
    # de autorização para o usuário identificado.
    try:
        id_usuario = token_data['id_usuarios']

        # Prepara o assinador dos dados de controle desta autorização.
        serializer = criar_serializer_google()


        # Gera um código aleatório e imprevisível, chamado code_verifier.
        # Ele é utilizado no PKCE para vincular o início e o fim da autorização.
        code_verifier = secrets.token_urlsafe(64)

        # dumps transforma os dados em um state assinado: identifica
        # qual usuário iniciou o pedido e guarda o code_verifier para o retorno.
        # A assinatura detecta alterações; não criptografa o conteúdo.
        state = serializer.dumps({
            'id_usuario': id_usuario,
            'code_verifier': code_verifier
        })

        # Inicia o fluxo OAuth com o mesmo state e code_verifier criados.
        flow = criar_flow(
            state=state,
            code_verifier=code_verifier
        )

        # Monta a URL que abrirá a tela de consentimento do Google.
        # offline solicita capacidade de renovar acesso depois; prompt='consent'
        # pede uma nova confirmação. O '_' ignora o segundo valor retornado.
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )

        # Envia a URL ao frontend (HTTP 200), que pode redirecionar
        # o navegador do advogado para autorizar a integração.
        return jsonify({
            'authorization_url': authorization_url
        }), 200

    # Captura falhas inesperadas; print/traceback exibem detalhes
    # no servidor e HTTP 500 informa o erro sem expor o fluxo inteiro ao cliente.
    except Exception as erro:
        print(
            'Erro ao iniciar conexão com Google:',
            erro
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': (
                'Não foi possível iniciar '
                'a conexão com o Google Agenda'
            )
        }), 500




# ROTA 2 | RETORNO DA AUTORIZAÇÃO (CALLBACK)
# Após o consentimento, o Google redireciona o navegador para esta rota.
# Aqui são verificados os dados da solicitação e obtidos os tokens de acesso.
@app.route(
    '/google/calendar/callback',
    methods=['GET']
)
def callback_google_calendar():
    # Inicia o tratamento do retorno, inclusive a possibilidade
    # de o usuário ter recusado a autorização.
    try:
        # request.args.get lê parâmetros presentes na URL do retorno.
        erro_google = request.args.get('error')

        # Se o Google devolveu 'error', o consentimento não foi concluído.
        # HTTP 400 indica que a solicitação não pode continuar.
        if erro_google:
            return jsonify({
                'error': (
                    'Autorização do Google cancelada'
                )
            }), 400

        # Recupera o state para conferir a qual autorização este retorno pertence.
        state_recebido = request.args.get('state')

        # Sem state, não é possível conferir a origem da solicitação.
        if not state_recebido:
            return jsonify({
                'error': (
                    'State não informado pelo Google'
                )
            }), 400

        # Recria o assinador para validar os dados enviados na primeira etapa.
        serializer = criar_serializer_google()

        # loads verifica a assinatura e recupera os valores do state.
        # max_age=600 limita a validade a 600 segundos (10 minutos).
        try:
            dados_state = serializer.loads(
                state_recebido,
                max_age=600
            )

        # Trata especificamente o retorno tardio: o usuário precisa
        # iniciar uma nova autorização.
        except SignatureExpired:
            return jsonify({
                'error': (
                    'A autorização expirou. '
                    'Tente conectar o Google novamente.'
                )
            }), 400

        # Se a assinatura for inválida, os dados recebidos não são aceitos.
        except BadSignature:
            return jsonify({
                'error': 'Autorização inválida'
            }), 400

        # get recupera valores de um dicionário sem gerar erro se a chave
        # não existir; neste caso, obtém o ID associado à solicitação.
        id_usuario = dados_state.get(
            'id_usuario'
        )

        # Recupera o mesmo code_verifier que será exigido pelo PKCE.
        code_verifier = dados_state.get(
            'code_verifier'
        )

        # Sem usuário associado, a aplicação não sabe onde salvar a conexão.
        if not id_usuario:
            return jsonify({
                'error': (
                    'Usuário da autorização '
                    'não encontrado'
                )
            }), 400

        # Sem o verificador, a etapa de troca do código não pode prosseguir.
        if not code_verifier:
            return jsonify({
                'error': (
                    'Code verifier não encontrado'
                )
            }), 400


        # Reconstrói o fluxo de autorização com os parâmetros validados.
        flow = criar_flow(
            state=state_recebido,
            code_verifier=code_verifier
        )

        # fetch_token lê a resposta de autorização e solicita ao Google
        # os tokens correspondentes. request.url contém a URL completa recebida.
        flow.fetch_token(
            authorization_response=request.url
        )

        # As credenciais resultantes guardam o token de acesso e,
        # quando fornecido pelo Google, o token de renovação (refresh token).
        credentials = flow.credentials



        # Consulta o serviço de identificação do Google para descobrir
        # o e-mail da conta que acabou de ser autorizada.
        resposta_usuario = requests.get(
            (
                'https://www.googleapis.com/'
                'oauth2/v2/userinfo'
            ),
            # O cabeçalho Authorization envia o access token como Bearer.
            # timeout=10 limita a espera por resposta a até 10 segundos.
            headers={
                'Authorization': (
                    f'Bearer {credentials.token}'
                )
            },
            timeout=10
        )

        # A propriedade ok informa se a requisição HTTP ao Google
        # foi considerada bem-sucedida.
        if not resposta_usuario.ok:
            return jsonify({
                'error': (
                    'Não foi possível identificar '
                    'a conta Google conectada'
                )
            }), 400

        # json() converte a resposta recebida em um dicionário Python.
        dados_usuario = resposta_usuario.json()

        # Busca o campo 'email' retornado pelo serviço do Google.
        google_email = dados_usuario.get(
            'email'
        )

        # Evita salvar uma conexão cuja conta não pôde ser identificada.
        if not google_email:
            return jsonify({
                'error': (
                    'O Google não informou '
                    'o e-mail da conta'
                )
            }), 400



        # O refresh token permite solicitar novos access tokens sem pedir
        # que o advogado autorize novamente a cada chamada.
        refresh_token = credentials.refresh_token


        # Nem toda autorização devolve um refresh token novo.
        # Se isso acontecer, tenta reaproveitar o de uma conexão ativa existente.
        if not refresh_token:
            conexao_existente = buscar_conexao_google(
                id_usuario
            )

            # A verificação evita usar token de um cadastro ausente ou inativo.
            if (
                conexao_existente
                and conexao_existente['ativo']
            ):
                refresh_token = (
                    conexao_existente[
                        'refresh_token'
                    ]
                )

        # Sem um refresh token disponível, a integração não pode ser
        # mantida pelo mecanismo utilizado neste módulo.
        if not refresh_token:
            return jsonify({
                'error': (
                    'O Google não retornou um '
                    'refresh token. '
                    'Tente autorizar novamente.'
                )
            }), 400



        # Grava no banco o e-mail vinculado e o refresh token recuperado.
        salvar_conexao_google(
            id_usuario,
            google_email,
            refresh_token
        )

        # Lê o endereço do site; localhost:5173 é o valor alternativo
        # utilizado quando FRONTEND_URL não foi definido.
        frontend_url = os.environ.get(
            'FRONTEND_URL',
            'http://localhost:5173'
        )

        # redirect retorna o navegador à edição de perfil, com um parâmetro
        # na URL que informa ao frontend que a conta foi conectada.
        return redirect(
            (
                f'{frontend_url}/'
                'editar_perfil_advogado'
                '?google_calendar=conectado'
            )
        )

    # Em falhas inesperadas, registra os detalhes no servidor e
    # retorna uma resposta HTTP 500 para facilitar a identificação do problema.
    except Exception as erro:
        print(
            'Erro no callback do Google:',
            erro
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': (
                'Não foi possível concluir '
                'a conexão com o Google Agenda'
            ),
            'detalhe': str(erro)
        }), 500




# ROTA 3 | CONSULTAR O STATUS DA INTEGRAÇÃO
# GET permite ao frontend mostrar se a agenda está ou não conectada.
@app.route(
    '/google/calendar/status',
    methods=['GET']
)
def status_google_calendar():
    # Decodifica o token para saber qual advogado fez a consulta.
    token_data = decodificar_token()

    # Sem autenticação válida, a rota responde HTTP 401.
    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    # Confirma que a solicitação veio de um perfil de advogado.
    if token_data['tipo'] != 0:
        return jsonify({
            'error': 'Acesso não autorizado'
        }), 403

    # Busca no banco apenas a conexão do usuário autenticado.
    try:
        id_usuario = token_data[
            'id_usuarios'
        ]

        conexao_google = buscar_conexao_google(
            id_usuario
        )

        # Se não existe conexão ou ela está inativa, devolve conectado=False
        # e nenhum e-mail. É uma resposta válida (HTTP 200), não um erro.
        if (
            not conexao_google
            or not conexao_google['ativo']
        ):
            return jsonify({
                'conectado': False,
                'google_email': None
            }), 200

        # Caso a conexão esteja ativa, informa o e-mail Google vinculado.
        # O frontend pode usar esses campos para atualizar os botões da interface.
        return jsonify({
            'conectado': True,
            'google_email': (
                conexao_google['google_email']
            )
        }), 200

    # Mantém erros internos separados das respostas normais de status.
    except Exception as erro:
        print(
            'Erro ao consultar Google Agenda:',
            erro
        )

        return jsonify({
            'error': (
                'Não foi possível consultar '
                'a conexão com o Google Agenda'
            )
        }), 500




# ROTA 4 | DESCONECTAR UMA CONTA GOOGLE
# DELETE desativa o vínculo no Constituere e tenta revogar no Google
# a credencial utilizada para renovar o acesso.
@app.route(
    '/google/calendar/desconectar',
    methods=['DELETE']
)
def desconectar_google_calendar():
    # Verifica autenticação antes de permitir a desconexão.
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    # Limita a ação aos perfis autorizados.
    if token_data['tipo'] != 0:
        return jsonify({
            'error': 'Acesso não autorizado'
        }), 403

    # Localiza a conexão ativa que pertence ao advogado autenticado.
    try:
        id_usuario = token_data[
            'id_usuarios'
        ]

        conexao_google = buscar_conexao_google(
            id_usuario
        )

        # Se a conta não está conectada, não há integração a desativar.
        if (
            not conexao_google
            or not conexao_google['ativo']
        ):
            return jsonify({
                'error': (
                    'Google Agenda não está conectado'
                )
            }), 404

        # Obtém o refresh token que será enviado ao Google para revogação.
        refresh_token = conexao_google[
            'refresh_token'
        ]


        # Executa a revogação em um try separado: mesmo se o Google
        # não responder, a desativação local ainda será tentada.
        try:
            # requests.post envia uma requisição HTTP ao endpoint de revogação.
            # O token vai nos parâmetros; o cabeçalho informa o formato esperado.
            resposta_revogacao = requests.post(
                (
                    'https://oauth2.googleapis.com/'
                    'revoke'
                ),
                params={
                    'token': refresh_token
                },
                headers={
                    'Content-Type': (
                        'application/'
                        'x-www-form-urlencoded'
                    )
                },
                timeout=10
            )

            # Se o Google não confirmar a operação, o sistema registra o aviso.
            # Isso não comprova que a credencial tenha sido revogada remotamente.
            if not resposta_revogacao.ok:
                print(
                    'Google não confirmou '
                    'a revogação:',
                    resposta_revogacao.text
                )

        # Problemas de rede na revogação são registrados sem impedir
        # o desligamento do vínculo no banco do Constituere.
        except Exception as erro_revogacao:
            print(
                'Erro ao revogar token '
                'no Google:',
                erro_revogacao
            )

        # Marca a conexão como inativa no banco, impedindo que o próprio
        # sistema continue a utilizá-la.
        desativar_conexao_google(
            id_usuario
        )

        # Retorna confirmação de desconexão local ao frontend (HTTP 200).
        return jsonify({
            'mensagem': (
                'Google Agenda desconectado '
                'com sucesso'
            )
        }), 200

    # Captura erros que impeçam a conclusão da operação local.
    except Exception as erro:
        print(
            'Erro ao desconectar '
            'Google Agenda:',
            erro
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': (
                'Não foi possível desconectar '
                'o Google Agenda'
            )
        }), 500




# CREDENCIAIS E COMUNICAÇÃO COM A API DO CALENDAR
# Esta função prepara credenciais válidas a partir da conta que o advogado
# já autorizou, sem exigir novo login na interface.
def obter_credenciais_google(id_usuario):
    # Recupera os dados salvos para o usuário informado.
    conexao_google = buscar_conexao_google(
        id_usuario
    )

    # Se a conexão não existe, raise sinaliza que a operação
    # não pode prosseguir.
    if not conexao_google:
        raise Exception(
            'Google Agenda não conectado'
        )

    # Uma conexão desativada também não pode acessar os eventos.
    if not conexao_google['ativo']:
        raise Exception(
            'Conexão com Google Agenda está desativada'
        )

    # Lê o refresh token armazenado para aquela conta.
    refresh_token = conexao_google[
        'refresh_token'
    ]

    # Recupera as identificações da aplicação configuradas no servidor.
    client_id = os.environ.get(
        'GOOGLE_CLIENT_ID'
    )

    client_secret = os.environ.get(
        'GOOGLE_CLIENT_SECRET'
    )

    # Valida configurações necessárias para renovar o token de acesso.
    if not client_id:
        raise Exception(
            'GOOGLE_CLIENT_ID não configurado'
        )

    if not client_secret:
        raise Exception(
            'GOOGLE_CLIENT_SECRET não configurado'
        )

    # Credentials reúne o refresh token, o endereço de renovação,
    # as credenciais da aplicação e as permissões OAuth autorizadas.
    # token=None indica que um access token atualizado será solicitado.
    credenciais = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=(
            'https://oauth2.googleapis.com/token'
        ),
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES
    )

    # refresh faz a solicitação ao Google para obter um access token
    # válido; GoogleRequest é o transporte HTTP usado pela biblioteca.
    credenciais.refresh(
        GoogleRequest()
    )

    # Retorna o objeto com as credenciais prontas para uso.
    return credenciais


# Cria o cliente da API Google Calendar para realizar operações
# sobre os eventos da agenda autorizada.
def obter_servico_calendar(id_usuario):
    credenciais = obter_credenciais_google(
        id_usuario
    )

    # build('calendar', 'v3') inicializa a versão 3 da API,
    # associando ao serviço as credenciais renovadas do advogado.
    servico = build(
        'calendar',
        'v3',
        credentials=credenciais
    )

    return servico



# ROTA 5 | CRIAR UM EVENTO DE TESTE
# POST executa um teste real da integração na agenda do advogado.
# O compromisso é agendado para começar daqui a 10 minutos.
@app.route(
    '/google/calendar/teste-evento',
    methods=['POST']
)
def teste_evento_google():
    # A rota exige autenticação e permite a criação apenas a advogados.
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    if token_data['tipo'] != 0:
        return jsonify({
            'error': (
                'Apenas advogados podem '
                'criar eventos de teste'
            )
        }), 403

    # Dentro do try, calcula os horários e cria o evento.
    try:
        id_usuario = token_data[
            'id_usuarios'
        ]

        # Define o fuso de São Paulo para interpretar a data e a hora.
        fuso = ZoneInfo(
            'America/Sao_Paulo'
        )

        # datetime.now(fuso) obtém o horário atual nesse fuso;
        # timedelta(minutes=10) acrescenta 10 minutos.
        inicio = datetime.now(
            fuso
        ) + timedelta(
            minutes=10
        )

        # Define que o teste terá 30 minutos de duração.
        fim = inicio + timedelta(
            minutes=30
        )

        # Reaproveita a função principal de criação de eventos, evitando
        # duplicar a comunicação com o Google.
        evento = criar_evento_google(
            id_usuario=id_usuario,
            titulo='Teste Constituere',
            descricao=(
                'Evento criado automaticamente '
                'pelo Constituere.'
            ),
            inicio=inicio,
            fim=fim
        )

        # A resposta inclui ID, link e início do evento criado.
        # .get oferece acesso seguro aos campos da resposta do Google;
        # HTTP 201 indica que um recurso foi criado.
        return jsonify({
            'mensagem': (
                'Evento criado com sucesso!'
            ),
            'event_id': evento.get('id'),
            'link': evento.get('htmlLink'),
            'inicio': evento.get(
                'start',
                {}
            ).get('dateTime')
        }), 201

    # Mostra o erro técnico no servidor e informa falha HTTP 500
    # caso a API não consiga criar o evento de teste.
    except Exception as erro:
        print(
            'Erro ao criar evento teste:',
            erro
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': (
                'Não foi possível criar '
                'o evento no Google Agenda'
            ),
            'detalhe': str(erro)
        }), 500



# OPERAÇÕES DE EVENTOS | CRIAR
# Função reutilizável pelas partes do Constituere que agendam reuniões.
# Recebe usuário, título, descrição, horários e convidados opcionais.
def criar_evento_google(
    id_usuario,
    titulo,
    descricao,
    inicio,
    fim,
    convidados=None
):
    # Obtém o serviço Calendar autenticado com a conta do advogado.
    servico = obter_servico_calendar(
        id_usuario
    )

    # Monta o dicionário de dados exigido pela API do Google:
    # summary é o título; description é a descrição; start e end são horários.
    evento = {
        'summary': titulo,
        'description': descricao,
        'start': {
            # isoformat converte datetime em texto no padrão de data/hora ISO.
            # timeZone informa explicitamente o fuso horário do compromisso.
            'dateTime': inicio.isoformat(),
            'timeZone': 'America/Sao_Paulo'
        },
        'end': {
            'dateTime': fim.isoformat(),
            'timeZone': 'America/Sao_Paulo'
        }
    }

    # Se foi enviada uma lista de convidados, inclui seus e-mails no evento.
    if convidados:
        # A compreensão de lista percorre 'convidados', transforma cada e-mail
        # em {'email': ...} e descarta valores vazios com if email.
        evento['attendees'] = [
            {
                'email': email
            }
            for email in convidados
            if email
        ]

    # Encadeamento da API: events() seleciona os eventos;
    # insert() prepara a criação na agenda principal (primary);
    # execute() envia a requisição ao Google de fato.
    evento_criado = (
        servico.events()
        .insert(
            calendarId='primary',
            body=evento,
            # sendUpdates='all' solicita notificações aos convidados;
            # 'none' evita essas notificações quando não há convidados.
            sendUpdates=(
                'all'
                if convidados
                else 'none'
            )
        )
        .execute()
    )

    # Devolve os detalhes do compromisso realmente criado pelo Google,
    # como seu identificador e link.
    return evento_criado

# OPERAÇÕES DE EVENTOS | ATUALIZAR
# Altera informações de um compromisso existente, identificado pelo
# ID retornado quando o evento foi criado.
def atualizar_evento_google(
    id_usuario,
    google_event_id,
    titulo,
    descricao,
    inicio,
    fim,
    convidados=None
):
    # Primeiro obtém acesso à agenda correspondente ao usuário.
    servico = obter_servico_calendar(
        id_usuario
    )

    # Constrói apenas os campos que serão enviados na atualização:
    # título, descrição e os horários do compromisso.
    evento = {
        'summary': titulo,
        'description': descricao,
        'start': {
            'dateTime': inicio.isoformat(),
            'timeZone': 'America/Sao_Paulo'
        },
        'end': {
            'dateTime': fim.isoformat(),
            'timeZone': 'America/Sao_Paulo'
        }
    }

    # 'is not None' diferencia lista omitida de lista vazia:
    # None mantém convidados atuais sem alteração explícita;
    # [] envia uma lista vazia para retirar todos os convidados.
    if convidados is not None:
        evento['attendees'] = [
            {
                'email': email
            }
            for email in convidados
            if email
        ]

    # patch atualiza campos específicos, em vez de substituir o evento
    # inteiro. eventId identifica o evento e sendUpdates='all' solicita avisos.
    evento_atualizado = (
        servico.events()
        .patch(
            calendarId='primary',
            eventId=google_event_id,
            body=evento,
            sendUpdates='all'
        )
        .execute()
    )

    # Devolve os dados do evento depois da alteração.
    return evento_atualizado

# OPERAÇÕES DE EVENTOS | CANCELAR
# Remove o evento da agenda do usuário, recebendo seu identificador Google.
def cancelar_evento_google(
    id_usuario,
    google_event_id
):
    # Recupera acesso autenticado à agenda em que o evento será excluído.
    servico = obter_servico_calendar(
        id_usuario
    )

    # delete seleciona o evento pelo ID e prepara sua exclusão;
    # execute() envia a operação ao Google; sendUpdates='all' solicita
    # o envio de atualizações aos convidados.
    (
        servico.events()
        .delete(
            calendarId='primary',
            eventId=google_event_id,
            sendUpdates='all'
        )
        .execute()
    )

    # Se nenhuma exceção foi lançada, sinaliza conclusão ao código chamador.
    return True