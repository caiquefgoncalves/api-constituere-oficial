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
    options.add_argument("--window-position=-2000,-2000")
    options.add_argument("--window-size=800,600")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Network.enable", {})
    return driver


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
        dados_api["totalCount"] = dados_api.pop("TotalCount", len(dados_api["items"]))
        dados_api["limitExceeded"] = bool(dados_api.pop("LimitExceeded", False))
        return dados_api

    if "currentPage" in dados_api and "pageSize" in dados_api:
        return {
            "items": [],
            "totalCount": 0,
            "limitExceeded": False,
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

    return str(dados_api.get("situacao", "")).strip().upper() == "REGULAR"


def _situacao_do_detalhe(detalhe):
    dados_api = _dados_api(detalhe)

    if not isinstance(dados_api, dict):
        return ""

    return str(dados_api.get("situacao", "")).strip().upper()


def _limpar_dados_detalhe(dados_detalhe):
    if not isinstance(dados_detalhe, dict):
        return {}

    dados_limpos = dict(dados_detalhe)

    if not INCLUIR_FOTO_NO_RETORNO:
        dados_limpos.pop("foto", None)

    return dados_limpos


def _ler_respostas_api(driver, requisicoes_api, requisicoes_lidas):
    for entrada in driver.get_log("performance"):
        try:
            mensagem = json.loads(entrada["message"])["message"]
        except (KeyError, json.JSONDecodeError):
            continue

        metodo = mensagem.get("method")
        params = mensagem.get("params", {})

        if metodo == "Network.responseReceived":
            resposta = params.get("response", {})
            url = resposta.get("url", "")

            if API_SEARCH_PATH in url:
                requisicoes_api[params["requestId"]] = url

        if metodo != "Network.loadingFinished":
            continue

        request_id = params.get("requestId")

        if request_id not in requisicoes_api or request_id in requisicoes_lidas:
            continue

        try:
            corpo = driver.execute_cdp_cmd(
                "Network.getResponseBody",
                {"requestId": request_id},
            )
        except WebDriverException:
            continue

        requisicoes_lidas.add(request_id)
        texto = corpo.get("body", "")

        if corpo.get("base64Encoded"):
            texto = base64.b64decode(texto).decode("utf-8", errors="replace")

        dados = _json_do_corpo(texto)
        resultado = _normalizar_resposta(dados)

        if resultado is not None:
            return resultado

    return None


def _mostrar_captcha(driver):
    print("CAPTCHA solicitado. Abrindo navegador...")
    driver.set_window_position(100, 100)
    driver.set_window_size(800, 600)


def _buscar_detalhe_advogado(driver, parametro):
    script = """
        const parametro = arguments[0];
        const siteKey = arguments[1];
        const done = arguments[arguments.length - 1];

        if (!window.grecaptcha) {
            done({error: "grecaptcha_indisponivel"});
            return;
        }

        window.grecaptcha.ready(() => {
            window.grecaptcha.execute(siteKey, {action: "lawyer_detail"})
                .then((token) => {
                    return fetch(
                        `/cna-interno/api/advogado/detail?parametro=${encodeURIComponent(parametro)}`,
                        {
                            headers: {
                                "X-Recaptcha-Token": token,
                                "X-Recaptcha-Action": "lawyer_detail",
                            },
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
                            body: text,
                        });
                    }
                })
                .catch((error) => done({error: String(error)}));
        });
    """

    return driver.execute_async_script(script, parametro, RECAPTCHA_SITE_KEY)


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

        detalhe = _buscar_detalhe_advogado(driver, parametro)
        dados_detalhe = _dados_api(detalhe)

        situacao = _situacao_do_detalhe(detalhe)

        if situacao:
            situacoes_encontradas.append(
                {
                    "nome": item.get("nome"),
                    "num_oab": item.get("num_oab"),
                    "uf_oab_oab": item.get("uf_oab"),
                    "situacao": situacao,
                }
            )

        if situacao != "REGULAR":
            continue

        item_regular = dict(item)

        if isinstance(dados_detalhe, dict):
            item_regular.update(_limpar_dados_detalhe(dados_detalhe))

        regulares.append(item_regular)

    resultado_filtrado = dict(resultado)
    resultado_filtrado["items"] = regulares
    resultado_filtrado["totalCount"] = len(regulares)
    resultado_filtrado["limitExceeded"] = False
    resultado_filtrado["situacoes"] = situacoes_encontradas

    if regulares:
        resultado_filtrado["mensagem"] = "Advogado encontrado com situacao REGULAR."
    elif situacoes_encontradas:
        situacao = situacoes_encontradas[0]["situacao"]
        resultado_filtrado["mensagem"] = (
            f"Advogado encontrado, mas a situação é {situacao.lower()}. "
            "Apenas advogados regulares podem se cadastrar"
        )
    else:
        resultado_filtrado["mensagem"] = "Nenhum advogado encontrado."

    return resultado_filtrado


class ConsultorOAB:
    def __init__(self):
        self.driver = _criar_driver()
        self.wait = WebDriverWait(self.driver, 30)
        self.pagina_carregada = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.fechar()

    def fechar(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _abrir_pagina(self):
        if self.pagina_carregada:
            return

        self.driver.get(URL_OAB)
        self.wait.until(EC.presence_of_element_located((By.NAME, "name")))
        self.pagina_carregada = True

    def consultar(self, uf_oab, num_oab, nome, apenas_regular=True):
        resultado = None
        captcha_precisa = False
        requisicoes_api = {}
        requisicoes_lidas = set()

        self._abrir_pagina()

        campo_nome = self.driver.find_element(By.NAME, "name")
        campo_nome.clear()
        campo_nome.send_keys(nome)

        campo_num_oab = self.driver.find_element(By.NAME, "registration")
        campo_num_oab.clear()
        campo_num_oab.send_keys(str(num_oab))

        if uf_oab:
            Select(self.driver.find_element(By.NAME, "sectional")).select_by_value(uf_oab)

        Select(self.driver.find_element(By.NAME, "registrationType")).select_by_value("1")

        self.driver.get_log("performance")

        self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
        )
        self.driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()

        inicio = time.time()

        while resultado is None and time.time() - inicio < TEMPO_MAXIMO_CONSULTA:
            resposta = _ler_respostas_api(
                self.driver,
                requisicoes_api,
                requisicoes_lidas,
            )

            if resposta == {"captcha": True}:
                if not captcha_precisa:
                    captcha_precisa = True
                    _mostrar_captcha(self.driver)
            elif resposta is not None:
                resultado = resposta

            time.sleep(INTERVALO_VERIFICACAO)

        if apenas_regular:
            return _filtrar_advogados_regulares(self.driver, resultado)

        return resultado


def consultar_oab(uf_oab, num_oab, nome, apenas_regular=True):
    with ConsultorOAB() as consultor:
        return consultor.consultar(uf_oab, num_oab, nome, apenas_regular=apenas_regular)