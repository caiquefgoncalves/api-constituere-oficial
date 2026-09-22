from db import conexao


def verificar_acesso_escritorio_ativo(
    id_usuario,
    id_escritorio
):
    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                STATUS,
                ATIVO
            FROM ADVOGADO_ESCRITORIO
            WHERE ID_USUARIOS = ?
              AND ID_ESCRITORIOS = ?
        """, (
            id_usuario,
            id_escritorio
        ))

        vinculo = cur.fetchone()

        if not vinculo:
            return {
                'permitido': False,
                'status_http': 403,
                'error': 'Você não pertence a este escritório.'
            }

        status = vinculo[0]
        ativo = vinculo[1]

        if ativo != 1:
            return {
                'permitido': False,
                'status_http': 403,
                'error': 'Seu acesso a este escritório está inativo.',
                'escritorio_inativo': True
            }

        return {
            'permitido': True,
            'status': status,
            'ativo': True
        }

    finally:
        cur.close()
        con.close()