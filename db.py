import fdb
from flask import current_app, has_request_context, g


def conexao():
    autor_id = None

    if has_request_context() and not getattr(g, 'lendo_token_auditoria', False):
        try:
            g.lendo_token_auditoria = True

            from funcao import decodificar_token

            token_data = decodificar_token()

            if isinstance(token_data, dict):
                autor_id = token_data.get('id_usuarios')

        except Exception as erro:
            current_app.logger.warning(
                'Não foi possível identificar o autor: %s', erro
            )

        finally:
            g.lendo_token_auditoria = False

    con = fdb.connect(
        host=current_app.config['DB_HOST'],
        database=current_app.config['DB_NAME'],
        user=current_app.config['DB_USER'],
        password=current_app.config['DB_PASSWORD']
    )

    try:
        cur = con.cursor()

        try:
            cur.execute("""
                SELECT
                    RDB$SET_CONTEXT('USER_SESSION', 'ORIGEM', 'APP'),
                    RDB$SET_CONTEXT('USER_SESSION', 'AUTOR_ID', ?)
                FROM RDB$DATABASE
            """, (
                str(autor_id) if autor_id is not None else None,
            ))

            cur.fetchone()

        finally:
            cur.close()

        return con

    except Exception:
        con.close()
        raise


def conexao_log():
    return fdb.connect(
        host=current_app.config['DB_HOST'],
        database=current_app.config['LOG_DB_NAME'],
        user=current_app.config['LOG_DB_USER'],
        password=current_app.config['LOG_DB_PASSWORD']
    )