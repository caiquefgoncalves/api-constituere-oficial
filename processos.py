from funcao import decodificar_token, validar_numero_processo, limpar_documento, converter_decimal, criar_data_vencimento, adicionar_meses, dividir_valor
from main import app
from db import conexao
import datetime
from flask import jsonify, request



@app.route('/cadastrar_processo', methods=['POST'])
def cadastrar_processo():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({
            'error': 'Acesso não autorizado'
        }), 403

    dados = request.get_json()

    if not dados:
        return jsonify({
            'error': 'Dados não enviados'
        }), 400

    processo = dados.get('processo', {})
    parte = dados.get('parte_contraria', {})
    honorarios = dados.get('honorarios', {})

    numero_processo = (
        processo.get('numero_processo')
        or ''
    ).strip()

    tipo_processo = processo.get(
        'tipo_processo'
    )

    assunto = processo.get(
        'assunto'
    )

    area = processo.get(
        'area'
    )

    comarca = processo.get(
        'comarca'
    )

    vara = processo.get(
        'vara'
    )

    instancia = processo.get(
        'instancia'
    )

    data_inicio_recebida = processo.get(
        'data_inicio'
    )

    id_cliente = processo.get(
        'id_cliente'
    )

    if not validar_numero_processo(
        numero_processo
    ):
        return jsonify({
            'error': 'Número do processo inválido'
        }), 400

    if not id_cliente:
        return jsonify({
            'error': 'Cliente é obrigatório'
        }), 400

    if not tipo_processo:
        return jsonify({
            'error': 'Tipo do processo é obrigatório'
        }), 400

    if not assunto:
        return jsonify({
            'error': 'Assunto é obrigatório'
        }), 400

    if not area:
        return jsonify({
            'error': 'Área é obrigatória'
        }), 400

    if not comarca:
        return jsonify({
            'error': 'Comarca é obrigatória'
        }), 400

    if not vara:
        return jsonify({
            'error': 'Vara é obrigatória'
        }), 400

    try:
        instancia = int(
            instancia
        )
    except:
        return jsonify({
            'error': 'Instância inválida'
        }), 400

    if instancia not in [1, 2]:
        return jsonify({
            'error': 'Instância deve ser 1 ou 2'
        }), 400

    try:
        data_inicio = datetime.datetime.strptime(
            data_inicio_recebida,
            '%d/%m/%Y'
        ).date()

    except:
        return jsonify({
            'error': 'Data de início inválida'
        }), 400

    cpf = limpar_documento(
        parte.get('cpf')
    )

    cnpj = limpar_documento(
        parte.get('cnpj')
    )

    if cpf and cnpj:
        return jsonify({
            'error': 'Informe apenas CPF ou CNPJ da parte contrária'
        }), 400

    if not cpf and not cnpj:
        return jsonify({
            'error': 'Informe CPF ou CNPJ da parte contrária'
        }), 400

    if cpf:
        if len(cpf) != 11:
            return jsonify({
                'error': 'CPF da parte contrária inválido'
            }), 400

        if not parte.get('nome'):
            return jsonify({
                'error': 'Nome da parte contrária é obrigatório'
            }), 400

    if cnpj:
        if len(cnpj) != 14:
            return jsonify({
                'error': 'CNPJ da parte contrária inválido'
            }), 400

        if not parte.get('razao_social'):
            return jsonify({
                'error': 'Razão social da parte contrária é obrigatória'
            }), 400

    tipo_honorario = (
        honorarios.get('tipo_honorario')
        or 'NAO_HA'
    ).upper()

    if tipo_honorario not in [
        'NAO_HA',
        'SALARIOS',
        'REAIS'
    ]:
        return jsonify({
            'error': 'Tipo de honorário inválido'
        }), 400

    numero_salarios = honorarios.get(
        'numero_salarios'
    )

    valor_honorario = converter_decimal(
        honorarios.get(
            'valor_honorario'
        )
    )

    tipo_pagamento = honorarios.get(
        'tipo_pagamento'
    )

    valor_entrada = converter_decimal(
        honorarios.get(
            'valor_entrada'
        )
    )

    numero_parcelas = honorarios.get(
        'numero_parcelas'
    )

    dia_vencimento = honorarios.get(
        'dia_vencimento'
    )

    mes_inicio = honorarios.get(
        'mes_inicio'
    )

    forma_pagamento = honorarios.get(
        'forma_pagamento'
    )

    percentual_juros = converter_decimal(
        honorarios.get(
            'percentual_juros'
        )
    )

    tem_exito = honorarios.get(
        'tem_exito',
        False
    )

    tipo_exito = honorarios.get(
        'tipo_exito'
    )

    valor_exito = converter_decimal(
        honorarios.get(
            'valor_exito'
        )
    )

    distribuicao_exito = honorarios.get('distribuicao_exito')
    valor_entrada_exito = converter_decimal(honorarios.get('valor_entrada_exito'))
    numero_parcelas_exito = honorarios.get('numero_parcelas_exito')
    dia_vencimento_exito = honorarios.get('dia_vencimento_exito')
    mes_inicio_exito = honorarios.get('mes_inicio_exito')
    valor_salario_exito = converter_decimal(honorarios.get('valor_salario_exito'))
    valor_causa_exito = converter_decimal(honorarios.get('valor_causa_exito'))
    quantidade_exito = honorarios.get('quantidade_exito')

    valor_total = converter_decimal(0)

    if tipo_honorario == 'SALARIOS':
        try:
            numero_salarios = int(
                numero_salarios
            )
        except:
            return jsonify({
                'error': 'Número de salários inválido'
            }), 400

        if numero_salarios <= 0:
            return jsonify({
                'error': 'Número de salários deve ser maior que zero'
            }), 400

        if (
            valor_honorario is None
            or valor_honorario <= 0
        ):
            return jsonify({
                'error': 'Valor do salário é obrigatório'
            }), 400

        valor_total = (
            numero_salarios
            * valor_honorario
        )

    elif tipo_honorario == 'REAIS':
        numero_salarios = None

        if (
            valor_honorario is None
            or valor_honorario <= 0
        ):
            return jsonify({
                'error': 'Valor dos honorários é obrigatório'
            }), 400

        valor_total = valor_honorario

    else:
        numero_salarios = None
        valor_honorario = None
        tipo_pagamento = None
        valor_entrada = None
        numero_parcelas = None
        dia_vencimento = None
        mes_inicio = None
        forma_pagamento = None

    if tipo_honorario != 'NAO_HA':
        if not tipo_pagamento:
            return jsonify({
                'error': 'Tipo de pagamento é obrigatório'
            }), 400

        tipo_pagamento = tipo_pagamento.upper()

        if tipo_pagamento not in [
            'AVISTA',
            'PARCELADO',
            'ENTRADA_PARCELAS'
        ]:
            return jsonify({
                'error': 'Tipo de pagamento inválido'
            }), 400

        if not forma_pagamento:
            return jsonify({
                'error': 'Forma de pagamento é obrigatória'
            }), 400

        forma_pagamento = forma_pagamento.upper()

        if forma_pagamento not in [
            'CREDITO',
            'DEBITO',
            'PIX'
        ]:
            return jsonify({
                'error': 'Forma de pagamento inválida'
            }), 400

        try:
            dia_vencimento = int(
                dia_vencimento
            )

            mes_inicio = int(
                mes_inicio
            )

        except:
            return jsonify({
                'error': 'Dia ou mês de vencimento inválido'
            }), 400

        if (
            dia_vencimento < 1
            or dia_vencimento > 31
        ):
            return jsonify({
                'error': 'Dia de vencimento inválido'
            }), 400

        if (
            mes_inicio < 1
            or mes_inicio > 12
        ):
            return jsonify({
                'error': 'Mês de início inválido'
            }), 400

        if tipo_pagamento == 'AVISTA':
            numero_parcelas = 1
            valor_entrada = None

        if tipo_pagamento == 'PARCELADO':
            try:
                numero_parcelas = int(
                    numero_parcelas
                )
            except:
                return jsonify({
                    'error': 'Número de parcelas inválido'
                }), 400

            if numero_parcelas <= 0:
                return jsonify({
                    'error': 'Número de parcelas deve ser maior que zero'
                }), 400

            valor_entrada = None

        if tipo_pagamento == 'ENTRADA_PARCELAS':
            try:
                numero_parcelas = int(
                    numero_parcelas
                )
            except:
                return jsonify({
                    'error': 'Número de parcelas inválido'
                }), 400

            if numero_parcelas <= 0:
                return jsonify({
                    'error': 'Número de parcelas deve ser maior que zero'
                }), 400

            if (
                valor_entrada is None
                or valor_entrada <= 0
            ):
                return jsonify({
                    'error': 'Valor da entrada é obrigatório'
                }), 400

            if valor_entrada >= valor_total:
                return jsonify({
                    'error': 'Valor da entrada deve ser menor que o valor total'
                }), 400

    if tem_exito:
        if not tipo_exito:
            return jsonify({'error': 'Tipo do honorário de êxito é obrigatório'}), 400
        tipo_exito = tipo_exito.upper()
        if tipo_exito not in ['PERCENTUAL', 'SALARIOS_BENEFICIO']:
            return jsonify({'error': 'Tipo do honorário de êxito inválido'}), 400
        if valor_exito is None or valor_exito <= 0:
            return jsonify({'error': 'Valor do êxito é obrigatório'}), 400
        if tipo_exito == 'PERCENTUAL' and valor_exito > 100:
            return jsonify({'error': 'Percentual de êxito não pode ser maior que 100'}), 400

        if not distribuicao_exito:
            return jsonify({'error': 'Distribuição do êxito é obrigatória'}), 400
        distribuicao_exito = distribuicao_exito.upper()
        if distribuicao_exito not in ['AVISTA', 'PARCELADO', 'ENTRADA_PARCELAS']:
            return jsonify({'error': 'Distribuição do êxito inválida'}), 400

        if tipo_exito == 'SALARIOS_BENEFICIO':
            if not quantidade_exito or quantidade_exito <= 0:
                return jsonify({'error': 'Quantidade de salários do êxito é obrigatória'}), 400
            if not valor_salario_exito or valor_salario_exito <= 0:
                return jsonify({'error': 'Valor do salário do êxito é obrigatório'}), 400
            valor_total_exito = quantidade_exito * valor_salario_exito
        else:
            if not valor_causa_exito or valor_causa_exito <= 0:
                return jsonify({'error': 'Valor da causa para êxito percentual é obrigatório'}), 400
            valor_total_exito = (valor_exito / 100) * valor_causa_exito

        if distribuicao_exito == 'AVISTA':
            num_parcelas_exito = 1
            valor_entrada_exito = None
        elif distribuicao_exito == 'PARCELADO':
            try:
                num_parcelas_exito = int(numero_parcelas_exito)
            except:
                return jsonify({'error': 'Número de parcelas do êxito inválido'}), 400
            if num_parcelas_exito <= 0:
                return jsonify({'error': 'Número de parcelas do êxito deve ser maior que zero'}), 400
            valor_entrada_exito = None
        elif distribuicao_exito == 'ENTRADA_PARCELAS':
            try:
                num_parcelas_exito = int(numero_parcelas_exito)
            except:
                return jsonify({'error': 'Número de parcelas do êxito inválido'}), 400
            if num_parcelas_exito <= 0:
                return jsonify({'error': 'Número de parcelas do êxito deve ser maior que zero'}), 400
            if valor_entrada_exito is None or valor_entrada_exito <= 0:
                return jsonify({'error': 'Valor da entrada do êxito é obrigatório'}), 400
            if valor_entrada_exito >= valor_total_exito:
                return jsonify({'error': 'Valor da entrada do êxito deve ser menor que o valor total'}), 400

        try:
            dia_vencimento_exito = int(dia_vencimento_exito)
            mes_inicio_exito = int(mes_inicio_exito)
        except:
            return jsonify({'error': 'Dia ou mês de vencimento do êxito inválido'}), 400
        if dia_vencimento_exito < 1 or dia_vencimento_exito > 31:
            return jsonify({'error': 'Dia de vencimento do êxito inválido'}), 400
        if mes_inicio_exito < 1 or mes_inicio_exito > 12:
            return jsonify({'error': 'Mês de início do êxito inválido'}), 400

    else:
        tipo_exito = None
        valor_exito = None
        distribuicao_exito = None
        valor_entrada_exito = None
        num_parcelas_exito = None
        dia_vencimento_exito = None
        mes_inicio_exito = None
        valor_salario_exito = None
        valor_causa_exito = None
        quantidade_exito = None
        valor_total_exito = converter_decimal(0)

    data_nascimento = None

    if parte.get('data_nascimento'):
        try:
            data_nascimento = datetime.datetime.strptime(
                parte.get('data_nascimento'),
                '%d/%m/%Y'
            ).date()

        except:
            return jsonify({
                'error': 'Data de nascimento inválida'
            }), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_PROCESSOS
            FROM PROCESSOS
            WHERE NUM_PROCESSO = ?
        """, (
            numero_processo,
        ))

        if cur.fetchone():
            return jsonify({
                'error': 'Já existe um processo cadastrado com este número'
            }), 409

        cur.execute("""
            SELECT ID_USUARIOS
            FROM USUARIOS
            WHERE ID_USUARIOS = ?
              AND TIPO IN (2, 3)
              AND ATIVO = 1
              AND ID_USUARIO_RESPONSAVEL = ?
        """, (id_cliente, id_advogado))
        cliente = cur.fetchone()
        if not cliente:
            return jsonify({
                'error': 'Cliente não encontrado ou não pertence a este advogado'
            }), 403

        cur.execute("""
            INSERT INTO PROCESSOS (
                ID_USUARIOS_ADVOGADO,
                ID_USUARIOS_CLIENTE,
                NUM_PROCESSO,
                TIPO_PROCESSO,
                ASSUNTO,
                AREA,
                COMARCA,
                VARA,
                INSTANCIA,
                DATA_INICIO
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            RETURNING ID_PROCESSOS
        """, (
            id_advogado,
            id_cliente,
            numero_processo,
            tipo_processo,
            assunto,
            area,
            comarca,
            vara,
            instancia,
            data_inicio
        ))

        id_processo = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO PARTE_CONTRARIA (
                ID_PROCESSO,
                NOME,
                CPF,
                RG,
                ORGAO_EXPEDIDOR,
                NACIONALIDADE,
                ESTADO_CIVIL,
                DATA_NASCIMENTO,
                SEXO,
                CARTEIRA_TRABALHO,
                SERIE_CARTEIRA,
                PROFISSAO,
                CEP,
                LOGRADOURO,
                NUMERO,
                COMPLEMENTO,
                BAIRRO,
                CIDADE,
                ESTADO,
                TELEFONE,
                EMAIL,
                CNPJ,
                RAZAO_SOCIAL,
                NOME_FANTASIA
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
        """, (
            id_processo,
            parte.get('nome'),
            cpf,
            parte.get('rg'),
            parte.get('orgao_expedidor'),
            parte.get('nacionalidade'),
            parte.get('estado_civil'),
            data_nascimento,
            parte.get('sexo'),
            parte.get('carteira_trabalho'),
            parte.get('serie_carteira'),
            parte.get('profissao'),
            limpar_documento(
                parte.get('cep')
            ),
            parte.get('logradouro'),
            parte.get('numero'),
            parte.get('complemento'),
            parte.get('bairro'),
            parte.get('cidade'),
            parte.get('estado'),
            limpar_documento(
                parte.get('telefone')
            ),
            parte.get('email'),
            cnpj,
            parte.get('razao_social'),
            parte.get('nome_fantasia')
        ))

        cur.execute("""
            INSERT INTO PAGAMENTOS (
                ID_PROCESSO,
                TIPO_HONORARIO,
                NUM_SALARIOS,
                VALOR_HONORARIO,
                TIPO_PAGAMENTO,
                VALOR_ENTRADA,
                NUM_PARCELAS,
                DIA_VENCIMENTO,
                MES_INICIO,
                FORM_PAGAMENTO,
                TIPO_EXITO,
                VALOR_EXITO,
                PERCENTUAL_JUROS
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            RETURNING ID_PAGAMENTOS
        """, (
            id_processo,
            tipo_honorario,
            numero_salarios,
            valor_honorario,
            tipo_pagamento,
            valor_entrada,
            numero_parcelas,
            dia_vencimento,
            mes_inicio,
            forma_pagamento,
            tipo_exito,
            valor_exito,
            percentual_juros
        ))

        id_pagamento = cur.fetchone()[0]

        quantidade_parcelas_criadas = 0

        if tipo_honorario != 'NAO_HA':
            ano_inicio = data_inicio.year

            if mes_inicio < data_inicio.month:
                ano_inicio += 1

            if tipo_pagamento == 'AVISTA':
                vencimento = criar_data_vencimento(
                    ano_inicio,
                    mes_inicio,
                    dia_vencimento
                )

                cur.execute("""
                    INSERT INTO PARCELAS (
                        ID_PAGAMENTO,
                        NUMERO_PARCELA,
                        VALOR_PARCELA,
                        DATA_VENCIMENTO,
                        DATA_PAGAMENTO,
                        VALOR_PAGO,
                        STATUS
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    id_pagamento,
                    1,
                    valor_total,
                    vencimento,
                    None,
                    None,
                    'PENDENTE'
                ))

                quantidade_parcelas_criadas = 1

            elif tipo_pagamento == 'PARCELADO':
                valores = dividir_valor(
                    valor_total,
                    numero_parcelas
                )

                for indice in range(
                    numero_parcelas
                ):
                    ano, mes = adicionar_meses(
                        ano_inicio,
                        mes_inicio,
                        indice
                    )

                    vencimento = criar_data_vencimento(
                        ano,
                        mes,
                        dia_vencimento
                    )

                    cur.execute("""
                        INSERT INTO PARCELAS (
                            ID_PAGAMENTO,
                            NUMERO_PARCELA,
                            VALOR_PARCELA,
                            DATA_VENCIMENTO,
                            DATA_PAGAMENTO,
                            VALOR_PAGO,
                            STATUS
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?
                        )
                    """, (
                        id_pagamento,
                        indice + 1,
                        valores[indice],
                        vencimento,
                        None,
                        None,
                        'PENDENTE'
                    ))

                quantidade_parcelas_criadas = (
                    numero_parcelas
                )

            elif tipo_pagamento == 'ENTRADA_PARCELAS':
                cur.execute("""
                    INSERT INTO PARCELAS (
                        ID_PAGAMENTO,
                        NUMERO_PARCELA,
                        VALOR_PARCELA,
                        DATA_VENCIMENTO,
                        DATA_PAGAMENTO,
                        VALOR_PAGO,
                        STATUS
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?
                    )
                """, (
                    id_pagamento,
                    0,
                    valor_entrada,
                    data_inicio,
                    None,
                    None,
                    'PENDENTE'
                ))

                restante = (
                    valor_total
                    - valor_entrada
                )

                valores = dividir_valor(
                    restante,
                    numero_parcelas
                )

                for indice in range(
                    numero_parcelas
                ):
                    ano, mes = adicionar_meses(
                        ano_inicio,
                        mes_inicio,
                        indice
                    )

                    vencimento = criar_data_vencimento(
                        ano,
                        mes,
                        dia_vencimento
                    )

                    cur.execute("""
                        INSERT INTO PARCELAS (
                            ID_PAGAMENTO,
                            NUMERO_PARCELA,
                            VALOR_PARCELA,
                            DATA_VENCIMENTO,
                            DATA_PAGAMENTO,
                            VALOR_PAGO,
                            STATUS
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?
                        )
                    """, (
                        id_pagamento,
                        indice + 1,
                        valores[indice],
                        vencimento,
                        None,
                        None,
                        'PENDENTE'
                    ))

                quantidade_parcelas_criadas = (
                    numero_parcelas + 1
                )

        id_pagamento_exito = None
        if tem_exito:
            cur.execute("""
                INSERT INTO PAGAMENTO_EXITO (
                    ID_PAGAMENTO,
                    TIPO_PAGAMENTO,
                    VALOR_SALARIO,
                    VALOR_CAUSA,
                    QUANTIDADE,
                    DISTRIBUICAO,
                    VALOR_ENTRADA,
                    NUM_PARCELAS,
                    DIA_VENCIMENTO,
                    MES_INICIO
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING ID_PAGAMENTO_EXITO
            """, (
                id_pagamento,
                tipo_exito,
                valor_salario_exito,
                valor_causa_exito,
                quantidade_exito,
                distribuicao_exito,
                valor_entrada_exito,
                num_parcelas_exito,
                dia_vencimento_exito,
                mes_inicio_exito
            ))
            id_pagamento_exito = cur.fetchone()[0]

            ano_inicio_exito = data_inicio.year
            if mes_inicio_exito < data_inicio.month:
                ano_inicio_exito += 1

            if distribuicao_exito == 'AVISTA':
                vencimento = criar_data_vencimento(ano_inicio_exito, mes_inicio_exito, dia_vencimento_exito)
                cur.execute("""
                    INSERT INTO PARCELAS_EXITO (
                        ID_PAGAMENTO_EXITO, NUMERO_PARCELA, VALOR_PARCELA,
                        DATA_VENCIMENTO, DATA_PAGAMENTO, VALOR_PAGO, STATUS
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (id_pagamento_exito, 1, valor_total_exito, vencimento, None, None, 'PENDENTE'))
            elif distribuicao_exito == 'PARCELADO':
                valores_exito = dividir_valor(valor_total_exito, num_parcelas_exito)
                for indice in range(num_parcelas_exito):
                    ano, mes = adicionar_meses(ano_inicio_exito, mes_inicio_exito, indice)
                    vencimento = criar_data_vencimento(ano, mes, dia_vencimento_exito)
                    cur.execute("""
                        INSERT INTO PARCELAS_EXITO (
                            ID_PAGAMENTO_EXITO, NUMERO_PARCELA, VALOR_PARCELA,
                            DATA_VENCIMENTO, DATA_PAGAMENTO, VALOR_PAGO, STATUS
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (id_pagamento_exito, indice+1, valores_exito[indice], vencimento, None, None, 'PENDENTE'))
            elif distribuicao_exito == 'ENTRADA_PARCELAS':
                cur.execute("""
                    INSERT INTO PARCELAS_EXITO (
                        ID_PAGAMENTO_EXITO, NUMERO_PARCELA, VALOR_PARCELA,
                        DATA_VENCIMENTO, DATA_PAGAMENTO, VALOR_PAGO, STATUS
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (id_pagamento_exito, 0, valor_entrada_exito, data_inicio, None, None, 'PENDENTE'))
                restante_exito = valor_total_exito - valor_entrada_exito
                valores_exito = dividir_valor(restante_exito, num_parcelas_exito)
                for indice in range(num_parcelas_exito):
                    ano, mes = adicionar_meses(ano_inicio_exito, mes_inicio_exito, indice)
                    vencimento = criar_data_vencimento(ano, mes, dia_vencimento_exito)
                    cur.execute("""
                        INSERT INTO PARCELAS_EXITO (
                            ID_PAGAMENTO_EXITO, NUMERO_PARCELA, VALOR_PARCELA,
                            DATA_VENCIMENTO, DATA_PAGAMENTO, VALOR_PAGO, STATUS
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (id_pagamento_exito, indice+1, valores_exito[indice], vencimento, None, None, 'PENDENTE'))

        con.commit()

        return jsonify({
            'mensagem': 'Processo cadastrado com sucesso',
            'id_processo': id_processo,
            'id_pagamento': id_pagamento,
            'id_pagamento_exito': id_pagamento_exito,
            'numero_processo': numero_processo,
            'parcelas_criadas': quantidade_parcelas_criadas
        }), 201

    except Exception as e:
        con.rollback()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/processos', methods=['GET'])
def listar_processos():
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({
            'error': 'Token necessário'
        }), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({
            'error': 'Acesso não autorizado'
        }), 403

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                p.ID_PROCESSOS,
                p.NUM_PROCESSO,
                p.TIPO_PROCESSO,
                p.ASSUNTO,
                p.AREA,
                p.COMARCA,
                p.VARA,
                p.INSTANCIA,
                p.DATA_INICIO,

                cliente.ID_USUARIOS,
                cliente.NOME,
                cliente.RAZAO_SOCIAL,
                cliente.NOME_FANTASIA,

                advogado.ID_USUARIOS,
                advogado.NOME

            FROM PROCESSOS p

            INNER JOIN USUARIOS cliente
                ON cliente.ID_USUARIOS =
                   p.ID_USUARIOS_CLIENTE

            INNER JOIN USUARIOS advogado
                ON advogado.ID_USUARIOS =
                   p.ID_USUARIOS_ADVOGADO

            WHERE p.ID_USUARIOS_ADVOGADO = ?

            ORDER BY
                p.DATA_INICIO DESC,
                p.ID_PROCESSOS DESC
        """, (
            id_advogado,
        ))

        rows = cur.fetchall()

        processos = []

        for row in rows:
            nome_cliente = (
                row[10]
                or row[11]
                or row[12]
                or '--'
            )

            data_inicio = None

            if row[8]:
                data_inicio = row[8].strftime(
                    '%d/%m/%Y'
                )

            processos.append({
                'id': row[0],

                'numero': (
                    row[1]
                    or '--'
                ),

                'numero_processo': row[1],

                'tipo_processo': (
                    row[2]
                    or '--'
                ),

                'assunto': (
                    row[3]
                    or '--'
                ),

                'tipo': (
                    row[4]
                    or '--'
                ),

                'area': (
                    row[4]
                    or '--'
                ),

                'comarca': (
                    row[5]
                    or '--'
                ),

                'vara': (
                    row[6]
                    or '--'
                ),

                'instancia': row[7],

                'data_inicio': (
                    data_inicio
                    or '--'
                ),

                'id_cliente': row[9],

                'clientes': [
                    {
                        'id': row[9],
                        'nome': nome_cliente
                    }
                ],

                'id_advogado': row[13],

                'advogado_responsavel': (
                    row[14]
                    or '--'
                ),

                'status': 'em_andamento',
                'descricao': ''
            })

        return jsonify({
            'processos': processos,
            'quantidade': len(processos)
        }), 200

    except Exception as e:
        print(
            'Erro ao listar processos:',
            e
        )

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/pagamentos', methods=['GET'])
def listar_pagamentos():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    filtro_status = request.args.get('status')
    filtro_cliente = request.args.get('cliente')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 10))
    offset = (page - 1) * limit

    con = conexao()
    cur = con.cursor()

    def converter_data_firebird(valor):
        if valor is None:
            return None
        if isinstance(valor, datetime.date):
            return valor
        if isinstance(valor, str):
            for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                try:
                    return datetime.datetime.strptime(valor, fmt).date()
                except:
                    continue
            return None
        try:
            dias = int(valor)
            return datetime.date(1900, 1, 1) + datetime.timedelta(days=dias)
        except:
            return None

    try:
        sql_totais = """
            SELECT
                'prolabore' AS tipo,
                parc.ID_PARCELAS,
                parc.VALOR_PARCELA,
                parc.DATA_VENCIMENTO,
                parc.STATUS,
                u.NOME AS nome_cliente,
                u.RAZAO_SOCIAL,
                u.NOME_FANTASIA
            FROM PARCELAS parc
            INNER JOIN PAGAMENTOS pag ON parc.ID_PAGAMENTO = pag.ID_PAGAMENTOS
            INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
            INNER JOIN USUARIOS u ON p.ID_USUARIOS_CLIENTE = u.ID_USUARIOS
            WHERE p.ID_USUARIOS_ADVOGADO = ?

            UNION ALL

            SELECT
                'exito' AS tipo,
                pe.ID_PARCELA_EXITO,
                pe.VALOR_PARCELA,
                pe.DATA_VENCIMENTO,
                pe.STATUS,
                u.NOME AS nome_cliente,
                u.RAZAO_SOCIAL,
                u.NOME_FANTASIA
            FROM PARCELAS_EXITO pe
            INNER JOIN PAGAMENTO_EXITO pex ON pe.ID_PAGAMENTO_EXITO = pex.ID_PAGAMENTO_EXITO
            INNER JOIN PAGAMENTOS pag ON pex.ID_PAGAMENTO = pag.ID_PAGAMENTOS
            INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
            INNER JOIN USUARIOS u ON p.ID_USUARIOS_CLIENTE = u.ID_USUARIOS
            WHERE p.ID_USUARIOS_ADVOGADO = ?
        """

        params_totais = [id_advogado, id_advogado]

        if filtro_cliente:
            sql_totais += " AND (UPPER(nome_cliente) LIKE ? OR UPPER(RAZAO_SOCIAL) LIKE ? OR UPPER(NOME_FANTASIA) LIKE ?)"
            like = f"%{filtro_cliente.upper()}%"
            params_totais.extend([like, like, like])

        cur.execute(sql_totais, tuple(params_totais))
        rows_totais = cur.fetchall()

        total_recebido = 0.0
        total_a_pagar = 0.0
        total_atrasado = 0.0
        hoje = datetime.date.today()

        for row in rows_totais:
            valor = float(row[2]) if row[2] else 0.0
            status = row[4]
            data_venc_raw = row[3]
            data_venc = converter_data_firebird(data_venc_raw)

            if status == 'PAGA':
                total_recebido += valor
            else:  # PENDENTE ou outro
                if data_venc and data_venc < hoje:
                    total_atrasado += valor
                else:
                    total_a_pagar += valor


        sql_lista = """
            SELECT FIRST ? SKIP ?
                tipo,
                id,
                numero,
                valor,
                vencimento,
                pagamento,
                status,
                forma,
                nome_cliente,
                razao,
                fantasia,
                tipo_processo,
                num_processo
            FROM (
                SELECT
                    'prolabore' AS tipo,
                    parc.ID_PARCELAS AS id,
                    parc.NUMERO_PARCELA AS numero,
                    parc.VALOR_PARCELA AS valor,
                    parc.DATA_VENCIMENTO AS vencimento,
                    parc.DATA_PAGAMENTO AS pagamento,
                    parc.STATUS AS status,
                    pag.FORM_PAGAMENTO AS forma,
                    u.NOME AS nome_cliente,
                    u.RAZAO_SOCIAL AS razao,
                    u.NOME_FANTASIA AS fantasia,
                    p.TIPO_PROCESSO AS tipo_processo,
                    p.NUM_PROCESSO AS num_processo
                FROM PARCELAS parc
                INNER JOIN PAGAMENTOS pag ON parc.ID_PAGAMENTO = pag.ID_PAGAMENTOS
                INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
                INNER JOIN USUARIOS u ON p.ID_USUARIOS_CLIENTE = u.ID_USUARIOS
                WHERE p.ID_USUARIOS_ADVOGADO = ?

                UNION ALL

                SELECT
                    'exito' AS tipo,
                    pe.ID_PARCELA_EXITO AS id,
                    pe.NUMERO_PARCELA AS numero,
                    pe.VALOR_PARCELA AS valor,
                    pe.DATA_VENCIMENTO AS vencimento,
                    pe.DATA_PAGAMENTO AS pagamento,
                    pe.STATUS AS status,
                    '--' AS forma,
                    u.NOME AS nome_cliente,
                    u.RAZAO_SOCIAL AS razao,
                    u.NOME_FANTASIA AS fantasia,
                    p.TIPO_PROCESSO AS tipo_processo,
                    p.NUM_PROCESSO AS num_processo
                FROM PARCELAS_EXITO pe
                INNER JOIN PAGAMENTO_EXITO pex ON pe.ID_PAGAMENTO_EXITO = pex.ID_PAGAMENTO_EXITO
                INNER JOIN PAGAMENTOS pag ON pex.ID_PAGAMENTO = pag.ID_PAGAMENTOS
                INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
                INNER JOIN USUARIOS u ON p.ID_USUARIOS_CLIENTE = u.ID_USUARIOS
                WHERE p.ID_USUARIOS_ADVOGADO = ?
            ) AS combined
            ORDER BY vencimento ASC, id ASC
        """

        params_lista = [limit, offset, id_advogado, id_advogado]

        if filtro_cliente:
            sql_lista = sql_lista.replace(
                "ORDER BY vencimento ASC, id ASC",
                "WHERE (UPPER(nome_cliente) LIKE ? OR UPPER(razao) LIKE ? OR UPPER(fantasia) LIKE ?) ORDER BY vencimento ASC, id ASC"
            )
            like = f"%{filtro_cliente.upper()}%"
            params_lista.extend([like, like, like])

        cur.execute(sql_lista, tuple(params_lista))
        rows = cur.fetchall()

        pagamentos = []

        for row in rows:
            tipo = row[0]
            id_parcela = row[1]
            numero_parcela = row[2]
            valor = float(row[3])
            data_venc_raw = row[4]
            data_pag_raw = row[5]
            status_db = row[6]
            forma_pagamento = row[7] or '--'
            nome_cliente = row[8] or row[9] or row[10] or '--'
            tipo_processo = row[11] or 'Processo'

            data_venc = converter_data_firebird(data_venc_raw)
            data_pag = converter_data_firebird(data_pag_raw)

            if tipo == 'exito':
                nome_parcela = f"{tipo_processo} - Êxito - {numero_parcela}ª parcela"
            else:
                if numero_parcela == 0:
                    nome_parcela = f"{tipo_processo} - Entrada"
                else:
                    nome_parcela = f"{tipo_processo} - {numero_parcela}ª parcela"

            if status_db == 'PAGA':
                status_pt = 'Paga'
            else:
                if data_venc and data_venc < hoje:
                    status_pt = 'Atrasada'
                else:
                    status_pt = 'A pagar'

            pagamentos.append({
                'id': id_parcela,
                'nome': nome_parcela,
                'valor': valor,
                'cliente': nome_cliente,
                'status': status_pt,
                'pagamento': forma_pagamento,
                'vencimento': data_venc.strftime('%d/%m/%Y') if data_venc else '--',
                'data_pagamento': data_pag.strftime('%d/%m/%Y') if data_pag else None,
                'numero_parcela': numero_parcela,
                'tipo': tipo
            })

        if filtro_status and filtro_status != 'todos':
            pagamentos = [p for p in pagamentos if p['status'] == filtro_status]

        return jsonify({
            'pagamentos': pagamentos,
            'totais': {
                'recebido': round(total_recebido, 2),
                'a_pagar': round(total_a_pagar, 2),
                'atrasado': round(total_atrasado, 2)
            },
            'pagina': page,
            'limite': limit,
            'tem_mais': len(pagamentos) == limit
        }), 200

    except Exception as e:
        print("Erro ao listar pagamentos:", e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/pagamentos/<int:id_parcela>/baixar', methods=['PUT'])
def baixar_parcela(id_parcela):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT parc.ID_PARCELAS, parc.STATUS
            FROM PARCELAS parc
            INNER JOIN PAGAMENTOS pag ON parc.ID_PAGAMENTO = pag.ID_PAGAMENTOS
            INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
            WHERE parc.ID_PARCELAS = ? AND p.ID_USUARIOS_ADVOGADO = ?
        """, (id_parcela, id_advogado))

        parcela = cur.fetchone()

        if not parcela:
            return jsonify({'error': 'Parcela não encontrada'}), 404

        if parcela[1] == 'PAGA':
            return jsonify({'error': 'Esta parcela já foi paga'}), 400

        data_pagamento = datetime.date.today()
        cur.execute("""
            UPDATE PARCELAS
            SET STATUS = 'PAGA', DATA_PAGAMENTO = ?
            WHERE ID_PARCELAS = ?
        """, (data_pagamento, id_parcela))

        con.commit()

        return jsonify({
            'mensagem': 'Pagamento confirmado com sucesso!',
            'data_pagamento': data_pagamento.strftime('%d/%m/%Y')
        }), 200

    except Exception as e:
        con.rollback()
        print("Erro ao dar baixa na parcela:", e)
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()