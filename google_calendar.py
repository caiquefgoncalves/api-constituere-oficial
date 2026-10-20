import os
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import jsonify, request, redirect
from google_auth_oauthlib.flow import Flow
from itsdangerous import (
    URLSafeTimedSerializer,
    BadSignature,
    SignatureExpired
)

from db import conexao
from funcao import decodificar_token
from main import app

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build


SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar.freebusy'
]




def configurar_http_local():
    redirect_uri = os.environ.get(
        'GOOGLE_REDIRECT_URI',
        ''
    )

    if (
        redirect_uri.startswith('http://localhost')
        or redirect_uri.startswith('http://127.0.0.1')
    ):
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


def configuracao_google():
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')

    if not client_id:
        raise Exception(
            'GOOGLE_CLIENT_ID não configurado no .env'
        )

    if not client_secret:
        raise Exception(
            'GOOGLE_CLIENT_SECRET não configurado no .env'
        )

    if not redirect_uri:
        raise Exception(
            'GOOGLE_REDIRECT_URI não configurado no .env'
        )

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


def criar_flow(
    state=None,
    code_verifier=None
):
    configurar_http_local()

    flow = Flow.from_client_config(
        configuracao_google(),
        scopes=SCOPES,
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False
    )

    flow.redirect_uri = os.environ.get(
        'GOOGLE_REDIRECT_URI'
    )

    return flow


def criar_serializer_google():
    return URLSafeTimedSerializer(
        app.config['SECRET_KEY'],
        salt='google-calendar-oauth'
    )




def buscar_conexao_google(id_usuario):
    con = conexao()
    cur = con.cursor()

    try:
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

        resultado = cur.fetchone()

        if not resultado:
            return None

        return {
            'google_email': resultado[0],
            'refresh_token': resultado[1],
            'ativo': resultado[2] == 1
        }

    finally:
        cur.close()
        con.close()


def salvar_conexao_google(
    id_usuario,
    google_email,
    refresh_token
):
    con = conexao()
    cur = con.cursor()

    try:
        cur.execute(
            """
            SELECT ID_USUARIOS
            FROM GOOGLE_CALENDAR
            WHERE ID_USUARIOS = ?
            """,
            (id_usuario,)
        )

        existente = cur.fetchone()

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

        con.commit()

    except Exception:
        con.rollback()
        raise

    finally:
        cur.close()
        con.close()


def desativar_conexao_google(id_usuario):
    con = conexao()
    cur = con.cursor()

    try:
        cur.execute(
            """
            UPDATE GOOGLE_CALENDAR
            SET ATIVO = 0
            WHERE ID_USUARIOS = ?
            """,
            (id_usuario,)
        )

        con.commit()

    except Exception:
        con.rollback()
        raise

    finally:
        cur.close()
        con.close()



@app.route(
    '/google/calendar/conectar',
    methods=['GET']
)
def conectar_google_calendar():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    if token_data['tipo'] != 0:
        return jsonify({
            'error': (
                'Apenas advogados podem '
                'conectar o Google Agenda'
            )
        }), 403

    try:
        id_usuario = token_data['id_usuarios']

        serializer = criar_serializer_google()


        code_verifier = secrets.token_urlsafe(64)

        state = serializer.dumps({
            'id_usuario': id_usuario,
            'code_verifier': code_verifier
        })

        flow = criar_flow(
            state=state,
            code_verifier=code_verifier
        )

        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )

        return jsonify({
            'authorization_url': authorization_url
        }), 200

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




@app.route(
    '/google/calendar/callback',
    methods=['GET']
)
def callback_google_calendar():
    try:
        erro_google = request.args.get('error')

        if erro_google:
            return jsonify({
                'error': (
                    'Autorização do Google cancelada'
                )
            }), 400

        state_recebido = request.args.get('state')

        if not state_recebido:
            return jsonify({
                'error': (
                    'State não informado pelo Google'
                )
            }), 400

        serializer = criar_serializer_google()

        try:
            dados_state = serializer.loads(
                state_recebido,
                max_age=600
            )

        except SignatureExpired:
            return jsonify({
                'error': (
                    'A autorização expirou. '
                    'Tente conectar o Google novamente.'
                )
            }), 400

        except BadSignature:
            return jsonify({
                'error': 'Autorização inválida'
            }), 400

        id_usuario = dados_state.get(
            'id_usuario'
        )

        code_verifier = dados_state.get(
            'code_verifier'
        )

        if not id_usuario:
            return jsonify({
                'error': (
                    'Usuário da autorização '
                    'não encontrado'
                )
            }), 400

        if not code_verifier:
            return jsonify({
                'error': (
                    'Code verifier não encontrado'
                )
            }), 400


        flow = criar_flow(
            state=state_recebido,
            code_verifier=code_verifier
        )

        flow.fetch_token(
            authorization_response=request.url
        )

        credentials = flow.credentials



        resposta_usuario = requests.get(
            (
                'https://www.googleapis.com/'
                'oauth2/v2/userinfo'
            ),
            headers={
                'Authorization': (
                    f'Bearer {credentials.token}'
                )
            },
            timeout=10
        )

        if not resposta_usuario.ok:
            return jsonify({
                'error': (
                    'Não foi possível identificar '
                    'a conta Google conectada'
                )
            }), 400

        dados_usuario = resposta_usuario.json()

        google_email = dados_usuario.get(
            'email'
        )

        if not google_email:
            return jsonify({
                'error': (
                    'O Google não informou '
                    'o e-mail da conta'
                )
            }), 400



        refresh_token = credentials.refresh_token


        if not refresh_token:
            conexao_existente = buscar_conexao_google(
                id_usuario
            )

            if (
                conexao_existente
                and conexao_existente['ativo']
            ):
                refresh_token = (
                    conexao_existente[
                        'refresh_token'
                    ]
                )

        if not refresh_token:
            return jsonify({
                'error': (
                    'O Google não retornou um '
                    'refresh token. '
                    'Tente autorizar novamente.'
                )
            }), 400



        salvar_conexao_google(
            id_usuario,
            google_email,
            refresh_token
        )

        frontend_url = os.environ.get(
            'FRONTEND_URL',
            'http://localhost:5173'
        )

        return redirect(
            (
                f'{frontend_url}/'
                'editar_perfil_advogado'
                '?google_calendar=conectado'
            )
        )

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




@app.route(
    '/google/calendar/status',
    methods=['GET']
)
def status_google_calendar():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    if token_data['tipo'] != 0:
        return jsonify({
            'error': 'Acesso não autorizado'
        }), 403

    try:
        id_usuario = token_data[
            'id_usuarios'
        ]

        conexao_google = buscar_conexao_google(
            id_usuario
        )

        if (
            not conexao_google
            or not conexao_google['ativo']
        ):
            return jsonify({
                'conectado': False,
                'google_email': None
            }), 200

        return jsonify({
            'conectado': True,
            'google_email': (
                conexao_google['google_email']
            )
        }), 200

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




@app.route(
    '/google/calendar/desconectar',
    methods=['DELETE']
)
def desconectar_google_calendar():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    if token_data['tipo'] != 0:
        return jsonify({
            'error': 'Acesso não autorizado'
        }), 403

    try:
        id_usuario = token_data[
            'id_usuarios'
        ]

        conexao_google = buscar_conexao_google(
            id_usuario
        )

        if (
            not conexao_google
            or not conexao_google['ativo']
        ):
            return jsonify({
                'error': (
                    'Google Agenda não está conectado'
                )
            }), 404

        refresh_token = conexao_google[
            'refresh_token'
        ]


        try:
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

            if not resposta_revogacao.ok:
                print(
                    'Google não confirmou '
                    'a revogação:',
                    resposta_revogacao.text
                )

        except Exception as erro_revogacao:
            print(
                'Erro ao revogar token '
                'no Google:',
                erro_revogacao
            )

        desativar_conexao_google(
            id_usuario
        )

        return jsonify({
            'mensagem': (
                'Google Agenda desconectado '
                'com sucesso'
            )
        }), 200

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




def obter_credenciais_google(id_usuario):
    conexao_google = buscar_conexao_google(
        id_usuario
    )

    if not conexao_google:
        raise Exception(
            'Google Agenda não conectado'
        )

    if not conexao_google['ativo']:
        raise Exception(
            'Conexão com Google Agenda está desativada'
        )

    refresh_token = conexao_google[
        'refresh_token'
    ]

    client_id = os.environ.get(
        'GOOGLE_CLIENT_ID'
    )

    client_secret = os.environ.get(
        'GOOGLE_CLIENT_SECRET'
    )

    if not client_id:
        raise Exception(
            'GOOGLE_CLIENT_ID não configurado'
        )

    if not client_secret:
        raise Exception(
            'GOOGLE_CLIENT_SECRET não configurado'
        )

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

    credenciais.refresh(
        GoogleRequest()
    )

    return credenciais


def obter_servico_calendar(id_usuario):
    credenciais = obter_credenciais_google(
        id_usuario
    )

    servico = build(
        'calendar',
        'v3',
        credentials=credenciais
    )

    return servico



@app.route(
    '/google/calendar/teste-evento',
    methods=['POST']
)
def teste_evento_google():
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

    try:
        id_usuario = token_data[
            'id_usuarios'
        ]

        fuso = ZoneInfo(
            'America/Sao_Paulo'
        )

        inicio = datetime.now(
            fuso
        ) + timedelta(
            minutes=10
        )

        fim = inicio + timedelta(
            minutes=30
        )

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



def criar_evento_google(
    id_usuario,
    titulo,
    descricao,
    inicio,
    fim,
    convidados=None
):
    servico = obter_servico_calendar(
        id_usuario
    )

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

    if convidados:
        evento['attendees'] = [
            {
                'email': email
            }
            for email in convidados
            if email
        ]

    evento_criado = (
        servico.events()
        .insert(
            calendarId='primary',
            body=evento,
            sendUpdates=(
                'all'
                if convidados
                else 'none'
            )
        )
        .execute()
    )

    return evento_criado

def atualizar_evento_google(
    id_usuario,
    google_event_id,
    titulo,
    descricao,
    inicio,
    fim,
    convidados=None
):
    servico = obter_servico_calendar(
        id_usuario
    )

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

    if convidados is not None:
        evento['attendees'] = [
            {
                'email': email
            }
            for email in convidados
            if email
        ]

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

    return evento_atualizado

def cancelar_evento_google(
    id_usuario,
    google_event_id
):
    servico = obter_servico_calendar(
        id_usuario
    )

    (
        servico.events()
        .delete(
            calendarId='primary',
            eventId=google_event_id,
            sendUpdates='all'
        )
        .execute()
    )

    return True