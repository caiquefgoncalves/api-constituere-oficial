import datetime
import json
import os
import re
import unicodedata

import jwt
from flask import jsonify, request

from db import conexao
from main import app


ASSISTANT_NAME = "Veritas"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
DEFAULT_OPENROUTER_MODELS = (
  "inclusionai/ling-3.0-flash-sante:free",
  "thinkingmachines/inkling-small:free",
  "qwen/qwen3.8-27b:free",
  "nvidia/nemotron-3.5-lightning:free",
)

PROGRAMMING_KEYWORDS = (
    "codigo", "programacao", "programar", "python", "javascript", "typescript",
    "html", "css", "sql", "script", "função", "funcao", "classe", "class ",
    "algoritmo", "api ", "endpoint", "react", "flask", "node.js", "nodejs",
)

OUT_OF_SCOPE_MESSAGE = (
    "Posso ajudar somente com perguntas jurídicas e com os serviços autorizados "
    "do Constituere, como consultar e administrar agendamentos, clientes e parceiros."
)

SCHEDULE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "criar_agendamento",
            "description": "Propõe a criação de um agendamento. Só use quando todos os dados estiverem claros.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_cliente": {"type": "integer"},
                    "id_advogado_2": {"type": "integer"},
                    "assunto": {"type": "string"},
                    "data": {"type": "string", "description": "Data no formato YYYY-MM-DD"},
                    "horario": {"type": "string", "description": "Horário no formato HH:MM"},
                    "duracao": {"type": "string", "description": "Duração em minutos ou HH:MM"},
                },
                "required": ["id_cliente", "assunto", "data", "horario", "duracao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editar_agendamento",
            "description": "Propõe a alteração de data, horário, duração ou assunto de um agendamento existente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_agendamento": {"type": "integer"},
                    "id_cliente": {"type": "integer"},
                    "id_advogado_2": {"type": "integer"},
                    "assunto": {"type": "string"},
                    "data": {"type": "string", "description": "YYYY-MM-DD"},
                    "horario": {"type": "string", "description": "HH:MM"},
                    "duracao": {"type": "string"},
                },
                "required": ["id_agendamento", "assunto", "data", "horario", "duracao"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirmar_agendamento",
            "description": "Propõe a confirmação do advogado logado para um agendamento existente.",
            "parameters": {
                "type": "object",
                "properties": {"id_agendamento": {"type": "integer"}},
                "required": ["id_agendamento"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recusar_agendamento",
            "description": "Propõe a recusa do advogado logado para um agendamento existente.",
            "parameters": {
                "type": "object",
                "properties": {"id_agendamento": {"type": "integer"}, "motivo": {"type": "string"}},
                "required": ["id_agendamento", "motivo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancelar_agendamento",
            "description": "Propõe o desmarque do advogado logado para um agendamento existente.",
            "parameters": {
                "type": "object",
                "properties": {"id_agendamento": {"type": "integer"}, "motivo": {"type": "string"}},
                "required": ["id_agendamento", "motivo"],
            },
        },
    },
]


def _decode_request_token():
    token = request.headers.get("X-Access-Token")

    if not token:
        token = request.cookies.get("acess_token")

    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    if not token:
        return False

    try:
        payload = jwt.decode(
            token,
            app.config["SECRET_KEY"],
            algorithms=["HS256"],
        )
        return {
            "tipo": payload["tipo"],
            "id_usuarios": payload["id_usuarios"],
        }
    except jwt.PyJWTError:
        return False


def _as_date(value):
    if value is None:
        return None

    if isinstance(value, datetime.datetime):
        return value.date()

    if isinstance(value, datetime.date):
        return value

    text = str(value).strip()

    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass

    return None


def _format_date(value):
    date_value = _as_date(value)
    if not date_value:
        return "--"
    return date_value.strftime("%d/%m/%Y")


def _format_time(value):
    if value is None:
        return "--"

    if isinstance(value, datetime.time):
        return value.strftime("%H:%M")

    return str(value)[:5]


def _format_duration(value):
    if value is None:
        return "--"

    if isinstance(value, int):
        return f"{value // 60:02d}:{value % 60:02d}"

    return str(value)


def _format_document(value):
    digits = re.sub(r"\D", "", str(value or ""))

    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"

    return ""


def _normalize_text(value):
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return without_accents.lower()


def _contains_any_word(text, keywords):
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", text)
        for keyword in keywords
    )


def _is_programming_request(question):
    normalized = _normalize_text(question)
    return any(keyword in normalized for keyword in PROGRAMMING_KEYWORDS)


def _resolve_period(question):
    today = datetime.date.today()
    normalized = _normalize_text(question)

    if "amanha" in normalized:
        tomorrow = today + datetime.timedelta(days=1)
        return tomorrow, tomorrow, "amanha"

    if "hoje" in normalized:
        return today, today, "hoje"

    if "proxima semana" in normalized:
        start = today + datetime.timedelta(days=(7 - today.weekday()))
        end = start + datetime.timedelta(days=6)
        return start, end, "proxima_semana"

    if "semana" in normalized:
        start = today - datetime.timedelta(days=today.weekday())
        end = start + datetime.timedelta(days=6)
        return start, end, "semana_atual"

    if "mes" in normalized:
        start = today.replace(day=1)
        if start.month == 12:
            next_month = start.replace(year=start.year + 1, month=1)
        else:
            next_month = start.replace(month=start.month + 1)
        return start, next_month - datetime.timedelta(days=1), "mes_atual"

    return today, today + datetime.timedelta(days=7), "proximos_7_dias"


def _question_mentions_schedule(question):
    normalized = _normalize_text(question)
    keywords = (
        "agenda",
        "agendamento",
        "agendamentos",
        "compromisso",
        "reuniao",
    )
    return _contains_any_word(normalized, keywords)


def _question_requests_schedule_mutation(question):
    return _contains_any_word(
        _normalize_text(question),
        ("crie", "criar", "agende", "agendar", "marque", "editar", "edite", "reagende", "recuse", "recusar", "desmarque", "desmarcar", "cancele", "cancelar"),
    )


def _is_own_agenda_request(question):
    normalized = _normalize_text(question)
    return (
        _question_mentions_schedule(question)
        and _contains_any_word(normalized, ("minha", "meus", "toda", "todos"))
    )


def _question_mentions_cases(question):
    normalized = _normalize_text(question)
    keywords = (
        "processo",
        "processos",
        "acao",
        "acoes",
        "causa",
        "causas",
    )
    return _contains_any_word(normalized, keywords)


def _question_mentions_contacts(question):
    return _contains_any_word(
        _normalize_text(question),
        ("cliente", "clientes", "advogado", "advogados", "parceiro", "parceiros"),
    )


def _fetch_lawyer_appointments(id_lawyer, question):
    start, end, period = _resolve_period(question)

    if _question_requests_schedule_mutation(question) and not _extract_dates_from_question(question):
        end = datetime.date.today() + datetime.timedelta(days=365)
        period = "proximos_12_meses"

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute(
            """
            SELECT FIRST 30
                a.ID_AGENDAMENTOS,
                a.ID_USUARIOS_ADVOGADO_1,
                a.ID_USUARIOS_ADVOGADO_2,
                a.ID_USUARIOS_CLIENTE,
                a.CLIENTE,
                a.ASSUNTO,
                a.DATA,
                a.HORARIO,
                a.DURACAO,
                a.STATUS,
                a.MOTIVO
            FROM AGENDAMENTOS a
            WHERE (a.ID_USUARIOS_ADVOGADO_1 = ? OR a.ID_USUARIOS_ADVOGADO_2 = ?)
              AND a.DATA >= ?
              AND a.DATA <= ?
            ORDER BY a.DATA ASC, a.HORARIO ASC
            """,
            (id_lawyer, id_lawyer, start, end),
        )

        rows = cur.fetchall()

        return {
            "periodo": period,
            "data_inicio": start.isoformat(),
            "data_fim": end.isoformat(),
            "quantidade": len(rows),
            "agendamentos": [
                {
                    "id": row[0],
                    "id_advogado_2": row[2],
                    "id_cliente": row[3],
                    "cliente": row[4] or "--",
                    "assunto": row[5] or "--",
                    "data": _format_date(row[6]),
                    "data_iso": _as_date(row[6]).isoformat() if _as_date(row[6]) else None,
                    "horario": _format_time(row[7]),
                    "duracao": _format_duration(row[8]),
                    "status": row[9] or "--",
                    "motivo": row[10] or "",
                }
                for row in rows
            ],
        }
    finally:
        cur.close()
        con.close()


def _extract_dates_from_question(question):
    dates = []
    normalized = _normalize_text(question)

    if "hoje" in normalized:
        dates.append(datetime.date.today())
    if "amanha" in normalized:
        dates.append(datetime.date.today() + datetime.timedelta(days=1))

    for raw_date, formats in (
        (re.findall(r"\b\d{2}/\d{2}/\d{4}\b", question), ("%d/%m/%Y",)),
        (re.findall(r"\b\d{4}-\d{2}-\d{2}\b", question), ("%Y-%m-%d",)),
    ):
        for value in raw_date:
            for date_format in formats:
                try:
                    dates.append(datetime.datetime.strptime(value, date_format).date())
                    break
                except ValueError:
                    continue

    return list(dict.fromkeys(dates))


def _find_appointments_by_client_and_date(question, id_lawyer):
    dates = _extract_dates_from_question(question)
    if not dates:
        return []

    con = conexao()
    cur = con.cursor()
    matches = []
    normalized_question = _normalize_text(question)
    request_is_for_own_agenda = _is_own_agenda_request(question)

    try:
        for appointment_date in dates:
            cur.execute(
                """
                SELECT
                    ID_AGENDAMENTOS,
                    ID_USUARIOS_ADVOGADO_2,
                    ID_USUARIOS_CLIENTE,
                    CLIENTE,
                    ASSUNTO,
                    DATA,
                    HORARIO,
                    DURACAO,
                    STATUS,
                    MOTIVO
                FROM AGENDAMENTOS
                WHERE DATA = ?
                  AND (ID_USUARIOS_ADVOGADO_1 = ? OR ID_USUARIOS_ADVOGADO_2 = ?)
                """,
                (appointment_date, id_lawyer, id_lawyer),
            )

            for row in cur.fetchall():
                client_name = row[3] or "--"
                name_tokens = [
                    token for token in _normalize_text(client_name).split()
                    if len(token) >= 3
                ]
                if (
                    not request_is_for_own_agenda
                    and (
                        not name_tokens
                        or not any(token in normalized_question for token in name_tokens)
                    )
                ):
                    continue

                matches.append({
                    "id": row[0],
                    "id_advogado_2": row[1],
                    "id_cliente": row[2],
                    "cliente": client_name,
                    "assunto": row[4] or "--",
                    "data": _format_date(row[5]),
                    "data_iso": _as_date(row[5]).isoformat() if _as_date(row[5]) else None,
                    "horario": _format_time(row[6]),
                    "duracao": _format_duration(row[7]),
                    "status": row[8] or "--",
                    "motivo": row[9] or "",
                })

        return matches
    finally:
        cur.close()
        con.close()


def _fetch_lawyer_clients(id_lawyer):
    con = conexao()
    cur = con.cursor()

    try:
        cur.execute(
            """
            SELECT FIRST 100
                ID_USUARIOS,
                COALESCE(NULLIF(NOME, ''), RAZAO_SOCIAL, NOME_FANTASIA, '--'),
                COALESCE(NULLIF(CPF, ''), NULLIF(CNPJ, ''))
            FROM USUARIOS
            WHERE ID_USUARIO_RESPONSAVEL = ?
              AND TIPO IN (2, 3)
              AND ATIVO = 1
            ORDER BY NOME
            """,
            (id_lawyer,),
        )
        return [
            {"id": row[0], "nome": row[1], "documento": _format_document(row[2])}
            for row in cur.fetchall()
        ]
    finally:
        cur.close()
        con.close()


def _fetch_active_lawyers():
    con = conexao()
    cur = con.cursor()

    try:
        cur.execute(
            """
            SELECT FIRST 100 ID_USUARIOS, COALESCE(NULLIF(NOME, ''), '--')
            FROM USUARIOS
            WHERE TIPO = 0 AND ATIVO = 1
            ORDER BY NOME
            """
        )
        return [{"id": row[0], "nome": row[1]} for row in cur.fetchall()]
    finally:
        cur.close()
        con.close()


def _fetch_lawyer_partners(id_lawyer):
    con = conexao()
    cur = con.cursor()

    try:
        cur.execute(
            """
            SELECT
                u.ID_USUARIOS,
                COALESCE(NULLIF(u.NOME, ''), '--')
            FROM ADVOGADO_ESCRITORIO parceiro
            INNER JOIN USUARIOS u
                ON u.ID_USUARIOS = parceiro.ID_USUARIOS
            INNER JOIN ADVOGADO_ESCRITORIO vinculo_logado
                ON vinculo_logado.ID_ESCRITORIOS = parceiro.ID_ESCRITORIOS
            WHERE vinculo_logado.ID_USUARIOS = ?
              AND vinculo_logado.ATIVO = 1
              AND parceiro.ATIVO = 1
              AND parceiro.ID_USUARIOS <> ?
              AND u.TIPO = 0
              AND u.ATIVO = 1
            ORDER BY u.NOME
            """,
            (id_lawyer, id_lawyer),
        )
        return list({row[0]: {"id": row[0], "nome": row[1]} for row in cur.fetchall()}.values())
    finally:
        cur.close()
        con.close()


def _find_schedule_parties(question, id_lawyer):
    emails = set(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", question))
    documents = {
        re.sub(r"\D", "", value)
        for value in re.findall(r"\d[\d.\-/ ]{8,}\d", question)
    }
    documents = {value for value in documents if len(value) in (11, 14)}

    if not emails and not documents:
        return {"clientes": [], "advogados": []}

    con = conexao()
    cur = con.cursor()
    clients = []
    lawyers = []

    try:
        for email in emails:
            cur.execute(
                """
                SELECT ID_USUARIOS, COALESCE(NULLIF(NOME, ''), RAZAO_SOCIAL, NOME_FANTASIA, '--')
                FROM USUARIOS
                WHERE ID_USUARIO_RESPONSAVEL = ? AND TIPO IN (2, 3) AND ATIVO = 1
                  AND LOWER(EMAIL) = LOWER(?)
                """,
                (id_lawyer, email),
            )
            clients.extend({"id": row[0], "nome": row[1]} for row in cur.fetchall())

            cur.execute(
                """
                SELECT ID_USUARIOS, COALESCE(NULLIF(NOME, ''), '--')
                FROM USUARIOS
                WHERE TIPO = 0 AND ATIVO = 1 AND LOWER(EMAIL) = LOWER(?)
                """,
                (email,),
            )
            lawyers.extend({"id": row[0], "nome": row[1]} for row in cur.fetchall())

        for document in documents:
            cur.execute(
                """
                SELECT ID_USUARIOS, COALESCE(NULLIF(NOME, ''), RAZAO_SOCIAL, NOME_FANTASIA, '--')
                FROM USUARIOS
                WHERE ID_USUARIO_RESPONSAVEL = ? AND TIPO IN (2, 3) AND ATIVO = 1
                  AND (CPF = ? OR CNPJ = ?)
                """,
                (id_lawyer, document, document),
            )
            clients.extend({"id": row[0], "nome": row[1]} for row in cur.fetchall())

            cur.execute(
                """
                SELECT ID_USUARIOS, COALESCE(NULLIF(NOME, ''), '--')
                FROM USUARIOS
                WHERE TIPO = 0 AND ATIVO = 1 AND CPF = ?
                """,
                (document,),
            )
            lawyers.extend({"id": row[0], "nome": row[1]} for row in cur.fetchall())

        return {
            "clientes": list({item["id"]: item for item in clients}.values()),
            "advogados": list({item["id"]: item for item in lawyers}.values()),
        }
    finally:
        cur.close()
        con.close()


def _fetch_lawyer_case_summary(id_lawyer):
    con = conexao()
    cur = con.cursor()

    try:
        cur.execute(
            """
            SELECT
                COALESCE(NULLIF(TRIM(STATUS), ''), 'Sem status') AS STATUS,
                COUNT(*)
            FROM PROCESSOS
            WHERE ID_USUARIOS_ADVOGADO = ?
            GROUP BY COALESCE(NULLIF(TRIM(STATUS), ''), 'Sem status')
            ORDER BY COUNT(*) DESC
            """,
            (id_lawyer,),
        )
        status_rows = cur.fetchall()

        cur.execute(
            """
            SELECT FIRST 10
                p.ID_PROCESSOS,
                p.NUM_PROCESSO,
                p.TIPO_PROCESSO,
                p.ASSUNTO,
                p.AREA,
                p.STATUS,
                u.NOME,
                u.RAZAO_SOCIAL,
                u.NOME_FANTASIA
            FROM PROCESSOS p
            INNER JOIN USUARIOS u
                ON u.ID_USUARIOS = p.ID_USUARIOS_CLIENTE
            WHERE p.ID_USUARIOS_ADVOGADO = ?
            ORDER BY p.DATA_INICIO DESC
            """,
            (id_lawyer,),
        )
        process_rows = cur.fetchall()

        return {
            "por_status": [
                {
                    "status": row[0],
                    "quantidade": row[1],
                }
                for row in status_rows
            ],
            "processos_recentes": [
                {
                    "id": row[0],
                    "numero": row[1] or "--",
                    "tipo": row[2] or "--",
                    "assunto": row[3] or "--",
                    "area": row[4] or "--",
                    "status": row[5] or "--",
                    "cliente": row[6] or row[7] or row[8] or "--",
                }
                for row in process_rows
            ],
        }
    finally:
        cur.close()
        con.close()


def _build_authorized_context(question, token_data, contextual_question=None):
    """Builds data for the current intent, using history only to complete it.

    Assistant messages in the history can contain words such as "clientes".  They
    must not turn an agenda request into a request to list contacts.
    """
    contextual_question = contextual_question or question
    user_type = token_data["tipo"]
    user_id = token_data["id_usuarios"]
    context = {
        "usuario_logado": {
            "id": user_id,
            "tipo": user_type,
        },
        "dados": {},
        "restricoes": [],
    }

    if _question_mentions_schedule(question) or _question_requests_schedule_mutation(question):
        if user_type == 0:
            context["dados"]["agendamentos"] = _fetch_lawyer_appointments(
                user_id,
                contextual_question,
            )
            if _question_requests_schedule_mutation(question):
                context["dados"]["clientes"] = _fetch_lawyer_clients(user_id)
                context["dados"]["advogados"] = _fetch_active_lawyers()
                parties = _find_schedule_parties(contextual_question, user_id)
                context["dados"]["clientes_identificados"] = parties["clientes"]
                context["dados"]["advogados_identificados"] = parties["advogados"]
                context["dados"]["agendamentos_alvo"] = (
                    _find_appointments_by_client_and_date(contextual_question, user_id)
                )
        else:
            context["restricoes"].append(
                "Agendamentos so podem ser consultados por advogado autenticado."
            )

    if _question_mentions_contacts(question):
        if user_type == 0:
            context["dados"]["clientes_vinculados"] = _fetch_lawyer_clients(user_id)
            context["dados"]["advogados_parceiros"] = _fetch_lawyer_partners(user_id)
        else:
            context["restricoes"].append(
                "Clientes e parceiros so podem ser consultados por advogado autenticado."
            )

    if _question_mentions_cases(question):
        if user_type == 0:
            context["dados"]["processos"] = _fetch_lawyer_case_summary(user_id)
        else:
            context["restricoes"].append(
                "Processos internos so podem ser consultados por advogado autenticado."
            )

    return context


def _fallback_answer(question, authorized_context):
    appointments = authorized_context.get("dados", {}).get("agendamentos")
    target_appointments = authorized_context.get("dados", {}).get("agendamentos_alvo", [])
    clients = authorized_context.get("dados", {}).get("clientes_vinculados")
    partners = authorized_context.get("dados", {}).get("advogados_parceiros")

    if (
        _question_requests_schedule_mutation(question)
        and _is_own_agenda_request(question)
    ):
        if not target_appointments:
            return "Não encontrei agendamentos na data informada."

        lines = ["Encontrei estes agendamentos na sua agenda:"]
        for index, item in enumerate(target_appointments, start=1):
            lines.append(
                f"{index}. {item['data']} às {item['horario']}: "
                f"{item['assunto']} com {item['cliente']}."
            )

        if len(target_appointments) == 1:
            lines.append("Confirme o cancelamento deste agendamento para continuar.")
        else:
            lines.append("Informe qual deles deseja cancelar ou diga se deseja cancelar todos.")
        return "\n".join(lines)

    if clients is not None or partners is not None:
        lines = []
        if clients is not None:
            lines.append(f"Clientes ativos vinculados: {len(clients)}")
            for index, client in enumerate(clients, start=1):
                document = client.get("documento")
                suffix = f" — CPF/CNPJ: {document}" if document else ""
                lines.append(f"{index}. {client['nome']}{suffix}")
        if partners is not None:
            if lines:
                lines.append("")
            lines.append(f"Advogados parceiros ativos: {len(partners)}")
            lines.extend(
                f"{index}. {partner['nome']}"
                for index, partner in enumerate(partners, start=1)
            )
        return "\n".join(lines)

    if appointments is not None:
        if appointments["quantidade"] == 0:
            return (
                f"Voce nao tem agendamentos entre "
                f"{_format_date(appointments['data_inicio'])} e "
                f"{_format_date(appointments['data_fim'])}."
            )

        lines = [
            (
                f"Encontrei {appointments['quantidade']} agendamento(s) entre "
                f"{_format_date(appointments['data_inicio'])} e "
                f"{_format_date(appointments['data_fim'])}:"
            )
        ]

        for item in appointments["agendamentos"]:
            lines.append(
                f"- {item['data']} as {item['horario']}: "
                f"{item['assunto']} com {item['cliente']} "
                f"({item['status']})."
            )

        return "\n".join(lines)

    if authorized_context.get("restricoes"):
        return "Nao posso acessar esses dados para o usuario logado."

    return (
        "A Veritas esta configurada, mas nenhuma chave de IA foi definida. "
        "Configure NVIDIA_API_KEY ou OPENROUTER_API_KEY para respostas juridicas em linguagem natural."
    )


def _sanitize_history(history):
    if not isinstance(history, list):
        return []

    sanitized = []
    for item in history[-12:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = str(item.get("content") or "").strip()

        if role not in ("user", "assistant") or not content:
            continue

        sanitized.append({"role": role, "content": content[:4000]})

    return sanitized


def _question_with_history(question, history):
    recent_messages = [item["content"] for item in history[-6:]]
    return "\n".join(recent_messages + [question])


def _hide_internal_ids(answer):
    return re.sub(
        r"\bID(?:\s+(?:do|da)\s+\w+)?\s*[:#]?\s*\d+\b",
        "",
        answer,
        flags=re.IGNORECASE,
    ).replace("  ", " ").strip()


def _get_openrouter_models():
    configured_models = os.getenv("VERITAS_OPENROUTER_MODELS", "").strip()

    if configured_models:
        return tuple(
            model.strip()
            for model in configured_models.split(",")
            if model.strip()
        )

    return DEFAULT_OPENROUTER_MODELS


def _proposal_from_tool_call(tool_call, authorized_context):
    try:
        arguments = json.loads(tool_call.function.arguments)
    except (AttributeError, TypeError, json.JSONDecodeError):
        return None

    name = tool_call.function.name
    target_appointments = authorized_context.get("dados", {}).get(
        "agendamentos_alvo", []
    )
    appointments = {
        item["id"]: item for item in target_appointments
    }

    if name == "criar_agendamento":
        clients = {
            item["id"]: item for item in authorized_context.get("dados", {}).get("clientes", [])
        }
        client = clients.get(arguments.get("id_cliente"))
        required = ("assunto", "data", "horario", "duracao")
        if not client or not all(str(arguments.get(field, "")).strip() for field in required):
            return None

        data = {
            "id_cliente": client["id"],
            "cliente": client["nome"],
            "assunto": arguments["assunto"].strip(),
            "data": arguments["data"].strip(),
            "horario": arguments["horario"].strip(),
            "duracao": str(arguments["duracao"]).strip(),
        }
        second_lawyer_id = arguments.get("id_advogado_2")
        if second_lawyer_id:
            lawyers = {
                item["id"]: item
                for item in authorized_context.get("dados", {}).get("advogados", [])
            }
            if second_lawyer_id not in lawyers:
                return None
            data["id_advogado_2"] = second_lawyer_id
        return {
            "tipo": "criar",
            "descricao": f"Criar agendamento com {client['nome']} em {data['data']} às {data['horario']}.",
            "endpoint": "/agendamentos",
            "metodo": "POST",
            "dados": data,
        }

    appointment_id = arguments.get("id_agendamento")
    appointment = appointments.get(appointment_id)
    if not appointment:
        return None

    if name == "editar_agendamento":
        required = ("assunto", "data", "horario", "duracao")
        if not all(str(arguments.get(field, "")).strip() for field in required):
            return None

        clients = {
            item["id"]: item for item in authorized_context.get("dados", {}).get("clientes", [])
        }
        client_id = arguments.get("id_cliente") or appointment["id_cliente"]
        client = clients.get(client_id)
        if not client:
            return None

        data = {
            "id_cliente": client_id,
            "cliente": client["nome"],
            "assunto": arguments["assunto"].strip(),
            "data": arguments["data"].strip(),
            "horario": arguments["horario"].strip(),
            "duracao": str(arguments["duracao"]).strip(),
        }
        second_lawyer_id = arguments.get("id_advogado_2", appointment["id_advogado_2"])
        if second_lawyer_id:
            lawyers = {
                item["id"]: item
                for item in authorized_context.get("dados", {}).get("advogados", [])
            }
            if second_lawyer_id not in lawyers and second_lawyer_id != appointment["id_advogado_2"]:
                return None
            data["id_advogado_2"] = second_lawyer_id
        return {
            "tipo": "editar",
            "descricao": f"Editar o agendamento com {appointment['cliente']} para {data['data']} às {data['horario']}.",
            "endpoint": f"/agendamento/{appointment_id}",
            "metodo": "PUT",
            "dados": data,
        }

    if name == "confirmar_agendamento":
        return {
            "tipo": "confirmar",
            "descricao": f"Confirmar o agendamento com {appointment['cliente']} em {appointment['data']} às {appointment['horario']}.",
            "endpoint": f"/agendamento/{appointment_id}/confirmar",
            "metodo": "PUT",
            "dados": {},
        }

    if name in ("recusar_agendamento", "cancelar_agendamento"):
        reason = str(arguments.get("motivo", "")).strip()
        if not reason:
            return None
        action = "recusar" if name == "recusar_agendamento" else "cancelar"
        verb = "Recusar" if action == "recusar" else "Desmarcar"
        return {
            "tipo": action,
            "descricao": f"{verb} o agendamento com {appointment['cliente']} em {appointment['data']} às {appointment['horario']}.",
            "endpoint": f"/agendamento/{appointment_id}/{action}",
            "metodo": "PUT",
            "dados": {"motivo": reason},
        }

    return None


def _call_openrouter(question, authorized_context, history, force_nvidia=False):
    nvidia_api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    if not nvidia_api_key and not openrouter_api_key:
        return None, None

    from openai import OpenAI

    use_nvidia = force_nvidia or not bool(openrouter_api_key)
    if not use_nvidia:
        client = OpenAI(
            api_key=openrouter_api_key,
            base_url=OPENROUTER_BASE_URL,
            timeout=60.0,
            max_retries=1,
            default_headers={
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173"),
                "X-OpenRouter-Title": "Constituere Veritas",
            },
        )
        models = _get_openrouter_models()
    else:
        client = OpenAI(
            api_key=nvidia_api_key,
            base_url=NVIDIA_BASE_URL,
            timeout=60.0,
            max_retries=1,
        )
        models = (os.getenv("VERITAS_NVIDIA_MODEL", DEFAULT_NVIDIA_MODEL),)

    instructions = """
Voce e Veritas, uma assistente juridica do sistema Constituere.
Responda em portugues brasileiro, com linguagem clara e objetiva.
Use texto simples e linhas numeradas em listas. Você pode usar **texto** para dar ênfase; os asteriscos duplos serão exibidos em negrito. Não use parênteses vazios. Ao listar clientes, escreva o nome seguido de “— CPF/CNPJ: ” e o documento formatado, se disponível.
Seu escopo é exclusivamente responder perguntas jurídicas e operar os serviços autorizados do Constituere.
Nunca forneça código, trechos de programação, scripts, SQL, HTML, CSS, configurações técnicas ou instruções de desenvolvimento, mesmo que o usuário insista. Para esses pedidos, informe brevemente que estão fora do seu escopo.
Voce pode explicar conceitos juridicos, organizar raciocinios e apontar proximos passos.
Nao se apresente como advogada e nao garanta resultado juridico.
Quando faltar informacao ou houver risco relevante, recomende validacao por um profissional responsavel.
Use os dados internos somente quando eles estiverem no CONTEXTO AUTORIZADO.
Nunca revele, deduza ou invente dados de outro usuario, escritorio, cliente, processo ou agendamento.
Nao diga que acessou tabelas, SQL ou banco de dados; apenas responda ao usuario.
Se o contexto indicar restricao de acesso, informe que nao pode acessar aqueles dados para o usuario logado.
Nunca mencione IDs internos de usuario, cliente, advogado ou agendamento nas respostas. Use apenas nomes e detalhes relevantes.
Para criar, editar, recusar ou desmarcar um agendamento, use a ferramenta correspondente somente se o usuario pediu a acao e todos os dados obrigatorios estiverem claros no CONTEXTO AUTORIZADO.
Para editar, recusar, desmarcar ou confirmar um agendamento, localize-o em agendamentos_alvo pela data e, quando informados, pelo nome do cliente. Se o usuário pedir uma ação sobre "minha agenda" em uma data, considere todos os agendamentos daquele dia: se houver somente um, você pode preparar a proposta; se houver mais de um, apresente-os sem IDs e pergunte qual deles ou se deseja aplicar a ação a todos. Nunca liste clientes ou advogados quando o pedido atual for sobre agenda.
Use o HISTÓRICO RECENTE para completar dados que o usuário já forneceu na conversa, como cliente, data, horário e ação. Não peça novamente uma informação que esteja clara no histórico.
Quando a pergunta tiver CPF, CNPJ ou e-mail, use apenas os IDs presentes em clientes_identificados ou advogados_identificados para relacionar o cliente ou o segundo advogado. Se não houver correspondência, peça outro identificador.
Ao criar agendamento, um único nome informado pelo usuário é o cliente. Se houver dois nomes, identifique o cliente pela lista clientes e o advogado secundário pela lista advogados; se o mesmo nome puder ser ambos, peça esclarecimento.
A ferramenta apenas cria uma proposta que o usuario precisara confirmar na interface. Nunca afirme que a acao foi executada antes da confirmacao.
""".strip()

    user_input = f"""
PERGUNTA:
{question}

CONTEXTO AUTORIZADO:
{json.dumps(authorized_context, ensure_ascii=False, default=str)}
""".strip()

    system_role = "system" if use_nvidia else "developer"
    messages = [{"role": system_role, "content": instructions}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=SCHEDULE_TOOLS,
                tool_choice="auto",
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []

            for tool_call in tool_calls:
                proposal = _proposal_from_tool_call(tool_call, authorized_context)
                if proposal:
                    return _hide_internal_ids(
                        message.content or "Revise a ação proposta antes de confirmar."
                    ), proposal

            answer = message.content

            if answer:
                return _hide_internal_ids(answer), None
        except Exception as exc:
            print(f"Modelo de IA indisponivel ({model}): {exc}")

    if not use_nvidia and nvidia_api_key:
        print("OpenRouter indisponível; tentando a API NVIDIA.")
        return _call_openrouter(
            question,
            authorized_context,
            history,
            force_nvidia=True,
        )

    return None, None


@app.route("/ai/veritas", methods=["POST"])
def perguntar_veritas():
    token_data = _decode_request_token()

    if token_data == False:
        return jsonify({"error": "Token necessario"}), 401

    payload = request.get_json(silent=True) or {}
    question = (payload.get("pergunta") or payload.get("question") or "").strip()

    if not question:
        return jsonify({"error": "Pergunta obrigatoria"}), 400

    if len(question) > 4000:
        return jsonify({"error": "Pergunta ultrapassa o limite permitido"}), 400

    if _is_programming_request(question):
        return jsonify({"assistant": ASSISTANT_NAME, "resposta": OUT_OF_SCOPE_MESSAGE}), 200

    try:
        history = _sanitize_history(payload.get("historico"))
        context_question = _question_with_history(question, history)
        authorized_context = _build_authorized_context(
            question,
            token_data,
            contextual_question=context_question,
        )
        answer, proposal = _call_openrouter(question, authorized_context, history)

        if not answer:
            answer = _fallback_answer(question, authorized_context)

        return jsonify(
            {
                "assistant": ASSISTANT_NAME,
                "resposta": answer,
                "dados_utilizados": list(authorized_context["dados"].keys()),
                "restricoes": authorized_context["restricoes"],
                "acao_proposta": proposal,
            }
        ), 200

    except Exception as exc:
        print("Erro na Veritas:", exc)
        import traceback

        traceback.print_exc()
        return jsonify({"error": "Erro ao consultar a Veritas"}), 500
