import base64
import json
import os
import time

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait


URL_CNSA = "https://cnsa.oab.org.br/"

TEMPO_MAXIMO_CONSULTA = 60
INTERVALO_VERIFICACAO = 0.05


def mostrar_tempo(inicio, mensagem):
    tempo = time.perf_counter() - inicio
    print(f"[TEMPO] {mensagem}: {tempo:.2f} segundos")


def normalizar_uf(uf):

    if not uf:
        return ""

    uf = uf.strip().upper()

    estados = {
        "ACRE": "AC",
        "ALAGOAS": "AL",
        "AMAPÁ": "AP",
        "AMAPA": "AP",
        "AMAZONAS": "AM",
        "BAHIA": "BA",
        "CEARÁ": "CE",
        "CEARA": "CE",
        "DISTRITO FEDERAL": "DF",
        "ESPÍRITO SANTO": "ES",
        "ESPIRITO SANTO": "ES",
        "GOIÁS": "GO",
        "GOIAS": "GO",
        "MARANHÃO": "MA",
        "MARANHAO": "MA",
        "MATO GROSSO": "MT",
        "MATO GROSSO DO SUL": "MS",
        "MINAS GERAIS": "MG",
        "PARÁ": "PA",
        "PARA": "PA",
        "PARAÍBA": "PB",
        "PARAIBA": "PB",
        "PARANÁ": "PR",
        "PARANA": "PR",
        "PERNAMBUCO": "PE",
        "PIAUÍ": "PI",
        "PIAUI": "PI",
        "RIO DE JANEIRO": "RJ",
        "RIO GRANDE DO NORTE": "RN",
        "RIO GRANDE DO SUL": "RS",
        "RONDÔNIA": "RO",
        "RONDONIA": "RO",
        "RORAIMA": "RR",
        "SANTA CATARINA": "SC",
        "SÃO PAULO": "SP",
        "SAO PAULO": "SP",
        "SERGIPE": "SE",
        "TOCANTINS": "TO"
    }

    return estados.get(uf, uf)


def criar_driver():

    inicio = time.perf_counter()

    options = Options()

    options.page_load_strategy = "eager"

    options.add_argument(
        "--window-position=-2000,-2000"
    )

    options.add_argument(
        "--window-size=900,700"
    )

    options.add_argument(
        "--disable-extensions"
    )

    options.add_argument(
        "--disable-notifications"
    )

    options.add_argument(
        "--disable-popup-blocking"
    )

    options.add_argument(
        "--disable-gpu"
    )

    options.add_argument(
        "--disable-blink-features=AutomationControlled"
    )

    options.set_capability(
        "goog:loggingPrefs",
        {
            "performance": "ALL"
        }
    )

    caminho_driver = os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)
        ),
        "chromedriver.exe"
    )

    if os.path.exists(caminho_driver):

        print(
            "[DRIVER] ChromeDriver encontrado."
        )

        service = Service(
            caminho_driver
        )

        driver = webdriver.Chrome(
            service=service,
            options=options
        )

    else:

        print(
            "[DRIVER] chromedriver.exe não encontrado."
        )

        print(
            "[DRIVER] Tentando Selenium Manager..."
        )

        driver = webdriver.Chrome(
            options=options
        )

    driver.execute_cdp_cmd(
        "Network.enable",
        {}
    )

    mostrar_tempo(
        inicio,
        "Driver criado"
    )

    return driver


def json_do_corpo(corpo):

    if not corpo:
        return None

    try:
        return json.loads(corpo)

    except Exception:
        return None


def mostrar_navegador(driver):

    print()
    print(
        ">>> CAPTCHA ou interação manual necessária."
    )

    try:

        driver.set_window_position(
            100,
            100
        )

        driver.set_window_size(
            1000,
            800
        )

    except Exception:
        pass


def ler_rede(
    driver,
    requisicoes,
    requisicoes_lidas
):

    try:

        logs = driver.get_log(
            "performance"
        )

    except Exception:

        return None

    for entrada in logs:

        try:

            mensagem = json.loads(
                entrada["message"]
            )["message"]

        except Exception:

            continue

        metodo = mensagem.get(
            "method"
        )

        params = mensagem.get(
            "params",
            {}
        )

        if metodo == "Network.responseReceived":

            response = params.get(
                "response",
                {}
            )

            url = response.get(
                "url",
                ""
            )

            status = response.get(
                "status",
                ""
            )

            tipo = params.get(
                "type",
                ""
            )

            if tipo not in (
                "XHR",
                "Fetch"
            ):
                continue

            if "cnsa.oab.org.br" not in url:
                continue

            request_id = params.get(
                "requestId"
            )

            if not request_id:
                continue

            print()
            print(
                ">>> API CNSA DETECTADA"
            )

            print(
                f">>> STATUS: {status}"
            )

            print(
                f">>> URL: {url}"
            )

            requisicoes[
                request_id
            ] = {
                "url": url,
                "status": status
            }

        if metodo != "Network.loadingFinished":
            continue

        request_id = params.get(
            "requestId"
        )

        if not request_id:
            continue

        if request_id not in requisicoes:
            continue

        if request_id in requisicoes_lidas:
            continue

        requisicoes_lidas.add(
            request_id
        )

        info = requisicoes[
            request_id
        ]

        print()
        print(
            ">>> TENTANDO LER RESPOSTA"
        )

        print(
            f">>> REQUEST ID: {request_id}"
        )

        try:

            corpo = driver.execute_cdp_cmd(
                "Network.getResponseBody",
                {
                    "requestId": request_id
                }
            )

        except WebDriverException as e:

            print(
                f">>> Erro ao ler resposta: {e}"
            )

            continue

        texto = corpo.get(
            "body",
            ""
        )

        if corpo.get(
            "base64Encoded"
        ):

            try:

                texto = base64.b64decode(
                    texto
                ).decode(
                    "utf-8",
                    errors="replace"
                )

            except Exception:
                pass

        print()
        print(
            ">>> CORPO RECEBIDO:"
        )

        print(
            texto[:5000]
        )

        dados = json_do_corpo(
            texto
        )

        if dados is not None:

            return {
                "url": info["url"],
                "status": info["status"],
                "dados": dados
            }

        return {
            "url": info["url"],
            "status": info["status"],
            "dados": texto
        }

    return None


class ConsultorCNSA:

    def __init__(self):

        inicio = time.perf_counter()

        self.driver = criar_driver()

        self.wait = WebDriverWait(
            self.driver,
            15
        )

        self.pagina_carregada = False

        mostrar_tempo(
            inicio,
            "ConsultorCNSA inicializado"
        )

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

            inicio = time.perf_counter()

            try:
                self.driver.quit()
            except Exception:
                pass

            self.driver = None

            mostrar_tempo(
                inicio,
                "Navegador fechado"
            )

    def abrir_pagina(self):

        if self.pagina_carregada:
            return

        inicio = time.perf_counter()

        self.driver.get(
            URL_CNSA
        )

        self.wait.until(
            EC.presence_of_element_located(
                (
                    By.NAME,
                    "registration"
                )
            )
        )

        self.wait.until(
            EC.presence_of_element_located(
                (
                    By.NAME,
                    "sectional"
                )
            )
        )

        self.pagina_carregada = True

        mostrar_tempo(
            inicio,
            "Página carregada"
        )

    def consultar(
        self,
        uf,
        inscricao
    ):

        inicio_total = time.perf_counter()

        print()
        print(
            "========================================"
        )

        print(
            "INICIANDO CONSULTA CNSA"
        )

        print(
            f"UF: {uf}"
        )

        print(
            f"Inscrição: {inscricao}"
        )

        print(
            "========================================"
        )

        self.abrir_pagina()

        inicio_formulario = time.perf_counter()

        uf = normalizar_uf(
            uf
        )

        campo_inscricao = (
            self.driver.find_element(
                By.NAME,
                "registration"
            )
        )

        campo_inscricao.clear()

        campo_inscricao.send_keys(
            str(inscricao)
        )

        campo_uf = (
            self.driver.find_element(
                By.NAME,
                "sectional"
            )
        )

        Select(
            campo_uf
        ).select_by_value(
            uf
        )

        mostrar_tempo(
            inicio_formulario,
            "Formulário preenchido"
        )

        print(
            f">>> UF utilizada: {uf}"
        )

        self.driver.get_log(
            "performance"
        )

        inicio_botao = time.perf_counter()

        try:

            botao = self.wait.until(
                EC.element_to_be_clickable(
                    (
                        By.CSS_SELECTOR,
                        'button[type="submit"]'
                    )
                )
            )

        except Exception:

            print(
                ">>> Botão submit não encontrado."
            )

            return {
                "sucesso": False,
                "mensagem": (
                    "Botão de pesquisa não encontrado."
                )
            }

        mostrar_tempo(
            inicio_botao,
            "Botão encontrado"
        )

        inicio_pesquisa = time.perf_counter()

        try:

            botao.click()

        except Exception:

            self.driver.execute_script(
                "arguments[0].click();",
                botao
            )

        mostrar_tempo(
            inicio_pesquisa,
            "Pesquisa enviada"
        )

        requisicoes = {}

        requisicoes_lidas = set()

        inicio_resposta = time.perf_counter()

        while (
            time.perf_counter()
            -
            inicio_resposta
            <
            TEMPO_MAXIMO_CONSULTA
        ):

            resposta = ler_rede(
                self.driver,
                requisicoes,
                requisicoes_lidas
            )

            if resposta is not None:

                mostrar_tempo(
                    inicio_resposta,
                    "Resposta da API recebida"
                )

                mostrar_tempo(
                    inicio_total,
                    "CONSULTA FINALIZADA"
                )

                print()
                print(
                    "========================================"
                )

                print(
                    "RESULTADO:"
                )

                print(
                    resposta
                )

                print(
                    "========================================"
                )

                return resposta

            time.sleep(
                INTERVALO_VERIFICACAO
            )

        mostrar_tempo(
            inicio_total,
            "TEMPO LIMITE ATINGIDO"
        )

        print()
        print(
            "========================================"
        )

        print(
            "NENHUMA RESPOSTA FINAL RECEBIDA"
        )

        print(
            "========================================"
        )

        return {
            "sucesso": False,
            "timeout": True,
            "mensagem": (
                "Tempo limite atingido."
            )
        }


def consultar_cnsa(
    uf,
    inscricao
):

    with ConsultorCNSA() as consultor:

        return consultor.consultar(
            uf,
            inscricao
        )


