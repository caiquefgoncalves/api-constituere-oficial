import base64
import json
import time

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait


URL_OAB = "https://cna.oab.org.br/"
API_SEARCH_PATH = "/cna-interno/api/advogado/search"
API_DETAIL_PATH = "/cna-interno/api/advogado/detail"
CAPTCHA_FALLBACK_CODE = "recaptcha_fallback_required"
RECAPTCHA_SITE_KEY = "6LecMcgsAAAAAPZLGrS_nBBb3IzfpDFQykLZbKQ6"
TEMPO_MAXIMO_CONSULTA = 300
INTERVALO_VERIFICACAO = 0.1
INCLUIR_FOTO_NO_RETORNO = False


def _criar_driver():
    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--start-minimized")
    options.set_capability(
        "goog:loggingPrefs",
        {"performance": "ALL"}
    )

    driver = webdriver.Chrome(options=options)

    driver.execute_cdp_cmd(
        "Network.enable",
        {}
    )

    try:
        driver.minimize_window()
    except Exception:
        pass

    return driver


def _elemento_visivel(driver, by, valor):
    elementos = driver.find_elements(by, valor)

    for elemento in elementos:
        try:
            if elemento.is_displayed() and elemento.is_enabled():
                return elemento
        except WebDriverException:
            continue

    raise Exception(
        f"Elemento visível não encontrado: {by}={valor}"
    )


def _json_do_corpo(corpo):
    if not corpo:
        return None

    try:
        return json.loads(corpo)
    except json.JSONDecodeError:
        return None


def _normalizar_resposta(dados):
    if not isinstance(dados, dict):
        return None

    dados_api = dados.get("data", dados)

    if not isinstance(dados_api, dict):
        return None

    if dados_api.get("code") == CAPTCHA_FALLBACK_CODE:
        return {"captcha": True}

    if "items" in dados_api:
        return dados_api

    if "Items" in dados_api:
        dados_api["items"] = dados_api.pop("Items")
        dados_api["totalCount"] = dados_api.pop(
            "TotalCount",
            len(dados_api["items"])
        )
        dados_api["limitExceeded"] = bool(
            dados_api.pop(
                "LimitExceeded",
                False
            )
        )
        return dados_api

    if (
        "currentPage" in dados_api
        and "pageSize" in dados_api
    ):
        return {
            "items": [],
            "totalCount": 0,
            "limitExceeded": False
        }

    return dados_api


def _dados_api(dados):
    if isinstance(dados, dict):
        return dados.get("data", dados)

    return dados


def _situacao_regular(detalhe):
    dados_api = _dados_api(detalhe)

    if not isinstance(dados_api, dict):
        return False

    return (
        str(
            dados_api.get(
                "situacao",
                ""
            )
        )
        .strip()
        .upper()
        == "REGULAR"
    )


def _situacao_do_detalhe(detalhe):
    dados_api = _dados_api(detalhe)

    if not isinstance(dados_api, dict):
        return ""

    return (
        str(
            dados_api.get(
                "situacao",
                ""
            )
        )
        .strip()
        .upper()
    )


def _limpar_dados_detalhe(dados_detalhe):
    if not isinstance(dados_detalhe, dict):
        return {}

    dados_limpos = dict(dados_detalhe)

    if not INCLUIR_FOTO_NO_RETORNO:
        dados_limpos.pop("foto", None)

    return dados_limpos


def _ler_respostas_api(
    driver,
    requisicoes_api,
    requisicoes_lidas
):
    try:
        logs = driver.get_log("performance")
    except Exception:
        return None

    for entrada in logs:
        try:
            mensagem = json.loads(
                entrada["message"]
            )["message"]
        except (
            KeyError,
            json.JSONDecodeError
        ):
            continue

        metodo = mensagem.get("method")
        params = mensagem.get("params", {})

        if metodo == "Network.responseReceived":
            resposta = params.get("response", {})
            url = resposta.get("url", "")

            if API_SEARCH_PATH in url:
                request_id = params.get("requestId")

                if request_id:
                    requisicoes_api[request_id] = url

        if metodo != "Network.loadingFinished":
            continue

        request_id = params.get("requestId")

        if (
            request_id not in requisicoes_api
            or request_id in requisicoes_lidas
        ):
            continue

        try:
            corpo = driver.execute_cdp_cmd(
                "Network.getResponseBody",
                {"requestId": request_id}
            )
        except WebDriverException:
            continue

        requisicoes_lidas.add(request_id)

        texto = corpo.get("body", "")

        if corpo.get("base64Encoded", False):
            try:
                texto = base64.b64decode(
                    texto
                ).decode(
                    "utf-8",
                    errors="replace"
                )
            except Exception:
                continue

        dados = _json_do_corpo(texto)
        resultado = _normalizar_resposta(dados)

        if resultado is not None:
            return resultado

    return None


def _mostrar_captcha(driver):
    print()
    print("=" * 60)
    print("CAPTCHA SOLICITADO")
    print("=" * 60)
    print("Abrindo navegador...")
    print("Resolva o CAPTCHA manualmente.")
    print("=" * 60)
    print()

    try:
        driver.maximize_window()
    except Exception:
        try:
            driver.set_window_position(100, 100)
            driver.set_window_size(1200, 900)
        except Exception:
            pass


def _buscar_detalhe_advogado(driver, parametro):
    script = """
    const parametro = arguments[0];
    const siteKey = arguments[1];
    const done = arguments[arguments.length - 1];

    if (!window.grecaptcha) {
        done({
            error: "grecaptcha_indisponivel"
        });
        return;
    }

    window.grecaptcha.ready(() => {
        window.grecaptcha.execute(
            siteKey,
            {
                action: "lawyer_detail"
            }
        )
        .then((token) => {
            return fetch(
                `/cna-interno/api/advogado/detail?parametro=${encodeURIComponent(parametro)}`,
                {
                    headers: {
                        "X-Recaptcha-Token": token,
                        "X-Recaptcha-Action": "lawyer_detail"
                    }
                }
            );
        })
        .then(async (response) => {
            const text = await response.text();

            try {
                done(JSON.parse(text));
            } catch (error) {
                done({
                    error: "json_invalido",
                    status: response.status,
                    body: text
                });
            }
        })
        .catch((error) => {
            done({
                error: String(error)
            });
        });
    });
    """

    return driver.execute_async_script(
        script,
        parametro,
        RECAPTCHA_SITE_KEY
    )


def _filtrar_advogados_regulares(driver, resultado):
    if not isinstance(resultado, dict):
        return resultado

    items = resultado.get("items", [])

    if not items:
        return resultado

    regulares = []
    situacoes_encontradas = []

    for item in items:
        parametro = item.get("parametro")

        if not parametro:
            continue

        try:
            detalhe = _buscar_detalhe_advogado(
                driver,
                parametro
            )
        except Exception as erro:
            print(
                f"Erro ao consultar detalhe: {erro}"
            )
            continue

        dados_detalhe = _dados_api(detalhe)
        situacao = _situacao_do_detalhe(detalhe)

        if situacao:
            situacoes_encontradas.append(
                {
                    "nome": item.get("nome"),
                    "num_oab": item.get("num_oab"),
                    "uf_oab_oab": item.get("uf_oab"),
                    "situacao": situacao
                }
            )

        if situacao != "REGULAR":
            continue

        item_regular = dict(item)

        if isinstance(dados_detalhe, dict):
            item_regular.update(
                _limpar_dados_detalhe(
                    dados_detalhe
                )
            )

        regulares.append(item_regular)

    resultado_filtrado = dict(resultado)

    resultado_filtrado["items"] = regulares
    resultado_filtrado["totalCount"] = len(regulares)
    resultado_filtrado["limitExceeded"] = False
    resultado_filtrado["situacoes"] = situacoes_encontradas

    if regulares:
        resultado_filtrado["mensagem"] = (
            "Advogado encontrado com "
            "situacao REGULAR."
        )
    elif situacoes_encontradas:
        situacao = (
            situacoes_encontradas[0]["situacao"]
        )

        resultado_filtrado["mensagem"] = (
            f"Advogado encontrado, mas "
            f"a situação é {situacao.lower()}. "
            "Apenas advogados regulares "
            "podem se cadastrar."
        )
    else:
        resultado_filtrado["mensagem"] = (
            "Nenhum advogado encontrado."
        )

    return resultado_filtrado


class ConsultorOAB:

    def __init__(self):
        self.driver = _criar_driver()
        self.wait = WebDriverWait(
            self.driver,
            30
        )
        self.pagina_carregada = False

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback
    ):
        self.fechar()

    def fechar(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

            self.driver = None

    def _abrir_pagina(self):
        if self.pagina_carregada:
            return

        print("Abrindo CNA da OAB...")

        self.driver.get(URL_OAB)

        self.wait.until(
            EC.visibility_of_element_located(
                (
                    By.NAME,
                    "name"
                )
            )
        )

        try:
            self.driver.minimize_window()
        except Exception:
            pass

        self.pagina_carregada = True

        print(
            "Página carregada em segundo plano."
        )

    def consultar(
        self,
        uf_oab,
        num_oab,
        nome,
        apenas_regular=True
    ):
        tempo_inicio = time.perf_counter()

        resultado = None
        captcha_precisa = False

        requisicoes_api = {}
        requisicoes_lidas = set()

        try:
            self._abrir_pagina()

            campo_nome = self.wait.until(
                EC.visibility_of_element_located(
                    (
                        By.NAME,
                        "name"
                    )
                )
            )

            self.driver.execute_script(
                """
                arguments[0].scrollIntoView({
                    block: 'center'
                });
                """,
                campo_nome
            )

            campo_nome.click()
            campo_nome.clear()
            campo_nome.send_keys(nome)

            campo_num_oab = self.wait.until(
                EC.visibility_of_element_located(
                    (
                        By.NAME,
                        "registration"
                    )
                )
            )

            self.driver.execute_script(
                """
                arguments[0].scrollIntoView({
                    block: 'center'
                });
                """,
                campo_num_oab
            )

            campo_num_oab.click()
            campo_num_oab.clear()
            campo_num_oab.send_keys(
                str(num_oab)
            )

            if uf_oab:
                select_sectional = self.wait.until(
                    EC.visibility_of_element_located(
                        (
                            By.NAME,
                            "sectional"
                        )
                    )
                )

                self.driver.execute_script(
                    """
                    arguments[0].scrollIntoView({
                        block: 'center'
                    });
                    """,
                    select_sectional
                )

                self.wait.until(
                    lambda d:
                    select_sectional.is_enabled()
                )

                Select(
                    select_sectional
                ).select_by_value(
                    uf_oab.upper()
                )

            select_tipo = self.wait.until(
                EC.visibility_of_element_located(
                    (
                        By.NAME,
                        "registrationType"
                    )
                )
            )

            self.driver.execute_script(
                """
                arguments[0].scrollIntoView({
                    block: 'center'
                });
                """,
                select_tipo
            )

            self.wait.until(
                lambda d:
                select_tipo.is_enabled()
            )

            Select(
                select_tipo
            ).select_by_value("1")

            try:
                self.driver.get_log(
                    "performance"
                )
            except Exception:
                pass

            botoes = self.driver.find_elements(
                By.CSS_SELECTOR,
                'button[type="submit"]'
            )

            botao_pesquisa = None

            for botao in botoes:
                try:
                    if (
                        botao.is_displayed()
                        and botao.is_enabled()
                    ):
                        botao_pesquisa = botao
                        break
                except WebDriverException:
                    continue

            if botao_pesquisa is None:
                raise Exception(
                    "Botão de pesquisa visível "
                    "não encontrado."
                )

            self.driver.execute_script(
                """
                arguments[0].scrollIntoView({
                    block: 'center'
                });
                """,
                botao_pesquisa
            )

            self.wait.until(
                lambda d:
                botao_pesquisa.is_displayed()
                and botao_pesquisa.is_enabled()
            )

            print()
            print("=" * 60)
            print(
                f"Consultando OAB: "
                f"{uf_oab}-{num_oab}"
            )
            print(
                f"Nome: {nome}"
            )
            print("=" * 60)

            botao_pesquisa.click()

            print(
                "Pesquisa enviada..."
            )

            inicio_api = time.perf_counter()

            while (
                resultado is None
                and (
                    time.perf_counter()
                    - inicio_api
                    < TEMPO_MAXIMO_CONSULTA
                )
            ):
                resposta = _ler_respostas_api(
                    self.driver,
                    requisicoes_api,
                    requisicoes_lidas
                )

                if resposta == {
                    "captcha": True
                }:
                    if not captcha_precisa:
                        captcha_precisa = True
                        _mostrar_captcha(
                            self.driver
                        )

                elif resposta is not None:
                    resultado = resposta

                    print(
                        "Resposta da API recebida."
                    )

                    break

                time.sleep(
                    INTERVALO_VERIFICACAO
                )

            tempo_busca = (
                time.perf_counter()
                - tempo_inicio
            )

            if resultado is None:
                print()
                print("=" * 60)
                print(
                    f"BUSCA FINALIZADA EM "
                    f"{tempo_busca:.2f} SEGUNDOS"
                )
                print("=" * 60)

                return {
                    "items": [],
                    "totalCount": 0,
                    "limitExceeded": False,
                    "tempo_consulta_segundos": round(
                        tempo_busca,
                        2
                    ),
                    "captcha_solicitado": captcha_precisa,
                    "mensagem": (
                        "Tempo limite atingido "
                        "sem resposta da API."
                    )
                }

            if apenas_regular:
                resultado = (
                    _filtrar_advogados_regulares(
                        self.driver,
                        resultado
                    )
                )

            tempo_total = (
                time.perf_counter()
                - tempo_inicio
            )

            if isinstance(
                resultado,
                dict
            ):
                resultado[
                    "tempo_consulta_segundos"
                ] = round(
                    tempo_total,
                    2
                )

                resultado[
                    "captcha_solicitado"
                ] = captcha_precisa

            print()
            print("=" * 60)
            print(
                f"BUSCA CONCLUÍDA EM "
                f"{tempo_total:.2f} SEGUNDOS"
            )

            if captcha_precisa:
                print(
                    "CAPTCHA foi necessário."
                )
            else:
                print(
                    "CAPTCHA não foi necessário."
                )

            print("=" * 60)
            print()

            return resultado

        except Exception:
            tempo_total = (
                time.perf_counter()
                - tempo_inicio
            )

            print()
            print(
                f"Consulta interrompida após "
                f"{tempo_total:.2f} segundos."
            )

            raise


def consultar_oab(
    uf_oab,
    num_oab,
    nome,
    apenas_regular=True
):
    with ConsultorOAB() as consultor:
        return consultor.consultar(
            uf_oab,
            num_oab,
            nome,
            apenas_regular=apenas_regular
        )


if __name__ == "__main__":

    resultado = consultar_oab(
        uf_oab="PE",
        num_oab="25087",
        nome="Andrea Carla Cardoso Poroca",
        apenas_regular=True
    )

    print()
    print("=" * 60)
    print("RESULTADO FINAL")
    print("=" * 60)

    print(
        json.dumps(
            resultado,
            indent=4,
            ensure_ascii=False
        )
    )