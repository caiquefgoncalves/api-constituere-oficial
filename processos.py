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

    if numero_processo:
        if not validar_numero_processo(numero_processo):
            return jsonify({
                'error': 'Número do processo inválido'
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

    if data_inicio_recebida:
        try:
            data_inicio = datetime.datetime.strptime(
                data_inicio_recebida,
                '%d/%m/%Y'
            ).date()
        except:
            return jsonify({
                'error': 'Data de início inválida'
            }), 400
    else:
        data_inicio = datetime.date.today()

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
                if valor_honorario and valor_honorario > 0:
                    valor_salario_exito = valor_honorario
                else:
                    return jsonify({'error': 'Valor do salário do êxito é obrigatório'}), 400
            valor_total_exito = quantidade_exito * valor_salario_exito
        else:
            if not valor_causa_exito or valor_causa_exito <= 0:
                valor_causa_exito = 45000.00
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
            if mes_inicio_exito is None:
                mes_inicio_exito = mes_inicio if mes_inicio else 1
            else:
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
                DATA_INICIO,
                STATUS
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            RETURNING ID_PROCESSOS
        """, (
            id_advogado,
            id_cliente,
            numero_processo if numero_processo else None,
            tipo_processo,
            assunto,
            area,
            comarca,
            vara if vara else None,
            instancia,
            data_inicio,
            'em_andamento'
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
            if not valor_causa_exito or valor_causa_exito <= 0:
                valor_causa_exito = 45000.00

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
            'numero_processo': numero_processo if numero_processo else '--',
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

    filtro_numero = (
        request.args.get('numero')
        or ''
    ).strip()

    filtro_status = (
        request.args.get('status')
        or ''
    ).strip()

    filtro_tipo = (
        request.args.get('tipo')
        or ''
    ).strip()

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT DISTINCT
                TRIM(p.TIPO_PROCESSO)
            FROM PROCESSOS p
            WHERE p.ID_USUARIOS_ADVOGADO = ?
              AND p.TIPO_PROCESSO IS NOT NULL
              AND TRIM(p.TIPO_PROCESSO) <> ''
            ORDER BY TRIM(p.TIPO_PROCESSO)
        """, (
            id_advogado,
        ))

        rows_tipos = cur.fetchall()

        tipos_processos = []

        for row in rows_tipos:
            if row[0]:
                tipos_processos.append(
                    row[0].strip()
                )

        sql = """
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
                p.STATUS,
                cliente.ID_USUARIOS,
                cliente.NOME,
                cliente.RAZAO_SOCIAL,
                cliente.NOME_FANTASIA,
                advogado.ID_USUARIOS,
                advogado.NOME
            FROM PROCESSOS p
            INNER JOIN USUARIOS cliente
                ON cliente.ID_USUARIOS = p.ID_USUARIOS_CLIENTE
            INNER JOIN USUARIOS advogado
                ON advogado.ID_USUARIOS = p.ID_USUARIOS_ADVOGADO
            WHERE p.ID_USUARIOS_ADVOGADO = ?
        """

        parametros = [
            id_advogado
        ]

        if filtro_numero:
            sql += """
                AND UPPER(
                    COALESCE(
                        p.NUM_PROCESSO,
                        ''
                    )
                ) LIKE ?
            """

            parametros.append(
                f'%{filtro_numero.upper()}%'
            )

        if (
            filtro_status
            and filtro_status.lower() != 'todos'
        ):
            sql += """
                AND UPPER(
                    COALESCE(
                        p.STATUS,
                        ''
                    )
                ) = ?
            """

            parametros.append(
                filtro_status.upper()
            )

        if (
            filtro_tipo
            and filtro_tipo.lower() != 'todos'
        ):
            sql += """
                AND UPPER(
                    TRIM(
                        COALESCE(
                            p.TIPO_PROCESSO,
                            ''
                        )
                    )
                ) = UPPER(TRIM(?))
            """

            parametros.append(
                filtro_tipo
            )

        sql += """
            ORDER BY
                p.DATA_INICIO DESC,
                p.ID_PROCESSOS DESC
        """

        cur.execute(
            sql,
            tuple(parametros)
        )

        rows = cur.fetchall()

        processos = []

        for row in rows:
            nome_cliente = (
                row[11]
                or row[12]
                or row[13]
                or '--'
            )

            data_inicio = None

            if row[8]:
                try:
                    data_inicio = row[8].strftime(
                        '%d/%m/%Y'
                    )
                except:
                    data_inicio = str(
                        row[8]
                    )

            status = (
                row[9]
                or 'em_andamento'
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

                'status': status,

                'id_cliente': row[10],

                'clientes': [
                    {
                        'id': row[10],
                        'nome': nome_cliente
                    }
                ],

                'id_advogado': row[14],

                'advogado_responsavel': (
                    row[15]
                    or '--'
                ),

                'descricao': ''
            })

        return jsonify({
            'processos': processos,
            'quantidade': len(processos),
            'tipos_processos': tipos_processos,
            'filtros': {
                'numero': (
                    filtro_numero
                    if filtro_numero
                    else None
                ),

                'status': (
                    filtro_status
                    if (
                        filtro_status
                        and filtro_status.lower() != 'todos'
                    )
                    else None
                ),

                'tipo': (
                    filtro_tipo
                    if (
                        filtro_tipo
                        and filtro_tipo.lower() != 'todos'
                    )
                    else None
                )
            }
        }), 200

    except Exception as e:
        print(
            'Erro ao listar processos:',
            e
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/tipos_processos', methods=['GET'])
def listar_tipos_processos():
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
            SELECT DISTINCT
                TRIM(p.TIPO_PROCESSO)

            FROM PROCESSOS p

            WHERE p.ID_USUARIOS_ADVOGADO = ?
              AND p.TIPO_PROCESSO IS NOT NULL
              AND TRIM(p.TIPO_PROCESSO) <> ''

            ORDER BY TRIM(p.TIPO_PROCESSO)
        """, (
            id_advogado,
        ))

        rows = cur.fetchall()

        tipos = []

        for row in rows:
            if row[0]:
                tipos.append(
                    row[0].strip()
                )

        return jsonify({
            'tipos': tipos,
            'quantidade': len(tipos)
        }), 200

    except Exception as e:
        print(
            'Erro ao listar tipos de processos:',
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
              AND p.STATUS = 'concluido'
        """

        params_totais = [id_advogado, id_advogado]

        if filtro_cliente:
            sql_totais += " AND (UPPER(u.NOME) LIKE ? OR UPPER(u.RAZAO_SOCIAL) LIKE ? OR UPPER(u.NOME_FANTASIA) LIKE ?)"
            like = f"%{filtro_cliente.upper()}%"
            params_totais.extend([like, like, like])

        cur.execute(sql_totais, tuple(params_totais))
        rows_totais = cur.fetchall()

        total_recebido = 0.0
        total_a_pagar = 0.0
        total_atrasado = 0.0
        hoje = datetime.date.today()

        for row in rows_totais:
            valor = float(row[1]) if row[1] else 0.0
            status = row[3]
            data_venc_raw = row[2]
            data_venc = converter_data_firebird(data_venc_raw)

            if status == 'PAGA':
                total_recebido += valor
            else:
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
                    pag.FORM_PAGAMENTO AS forma,
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
                  AND p.STATUS = 'concluido'
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

        total_registros = len(rows_totais)
        tem_mais = (page * limit) < total_registros

        return jsonify({
            'pagamentos': pagamentos,
            'totais': {
                'recebido': round(total_recebido, 2),
                'a_pagar': round(total_a_pagar, 2),
                'atrasado': round(total_atrasado, 2)
            },
            'pagina': page,
            'limite': limit,
            'tem_mais': tem_mais
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
            cur.execute("""
                SELECT pe.ID_PARCELA_EXITO, pe.STATUS
                FROM PARCELAS_EXITO pe
                INNER JOIN PAGAMENTO_EXITO pex ON pe.ID_PAGAMENTO_EXITO = pex.ID_PAGAMENTO_EXITO
                INNER JOIN PAGAMENTOS pag ON pex.ID_PAGAMENTO = pag.ID_PAGAMENTOS
                INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
                WHERE pe.ID_PARCELA_EXITO = ? AND p.ID_USUARIOS_ADVOGADO = ?
            """, (id_parcela, id_advogado))

            parcela = cur.fetchone()

            if not parcela:
                return jsonify({'error': 'Parcela não encontrada'}), 404

            if parcela[1] == 'PAGA':
                return jsonify({'error': 'Esta parcela já foi paga'}), 400

            data_pagamento = datetime.date.today()
            cur.execute("""
                UPDATE PARCELAS_EXITO
                SET STATUS = 'PAGA', DATA_PAGAMENTO = ?
                WHERE ID_PARCELA_EXITO = ?
            """, (data_pagamento, id_parcela))

            con.commit()

            return jsonify({
                'mensagem': 'Pagamento de êxito confirmado com sucesso!',
                'data_pagamento': data_pagamento.strftime('%d/%m/%Y')
            }), 200

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





@app.route('/processo/<int:id_processo>/pagamento', methods=['PUT'])
def atualizar_pagamento_processo(id_processo):
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json()
    if not dados:
        return jsonify({'error': 'Dados não enviados'}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT ID_USUARIOS_ADVOGADO, ID_PAGAMENTOS
            FROM PROCESSOS p
            LEFT JOIN PAGAMENTOS pag ON p.ID_PROCESSOS = pag.ID_PROCESSO
            WHERE p.ID_PROCESSOS = ?
        """, (id_processo,))
        result = cur.fetchone()
        if not result:
            return jsonify({'error': 'Processo não encontrado'}), 404
        if result[0] != id_advogado:
            return jsonify({'error': 'Acesso não autorizado'}), 403

        id_pagamento = result[1]

        tipo_honorario = dados.get('tipo_honorario', 'NAO_HA').upper()
        valor_honorario = dados.get('valor_honorario')
        tipo_pagamento = dados.get('tipo_pagamento')
        valor_entrada = dados.get('valor_entrada')
        numero_parcelas = dados.get('numero_parcelas')
        dia_vencimento = dados.get('dia_vencimento')
        mes_inicio = dados.get('mes_inicio')
        forma_pagamento = dados.get('forma_pagamento')
        percentual_juros = dados.get('percentual_juros')

        tem_exito = dados.get('tem_exito', False)
        tipo_exito = dados.get('tipo_exito')
        valor_exito = dados.get('valor_exito')

        distribuicao_exito = dados.get('distribuicao_exito')
        valor_entrada_exito = dados.get('valor_entrada_exito')
        numero_parcelas_exito = dados.get('numero_parcelas_exito')
        dia_vencimento_exito = dados.get('dia_vencimento_exito')
        mes_inicio_exito = dados.get('mes_inicio_exito')
        valor_causa_exito = dados.get('valor_causa_exito')
        valor_salario_exito = dados.get('valor_salario_exito')
        quantidade_exito = dados.get('quantidade_exito')

        if id_pagamento:
            cur.execute("""
                UPDATE PAGAMENTOS
                SET TIPO_HONORARIO = ?,
                    NUM_SALARIOS = ?,
                    VALOR_HONORARIO = ?,
                    TIPO_PAGAMENTO = ?,
                    VALOR_ENTRADA = ?,
                    NUM_PARCELAS = ?,
                    DIA_VENCIMENTO = ?,
                    MES_INICIO = ?,
                    FORM_PAGAMENTO = ?,
                    TIPO_EXITO = ?,
                    VALOR_EXITO = ?,
                    PERCENTUAL_JUROS = ?
                WHERE ID_PAGAMENTOS = ?
            """, (
                tipo_honorario,
                dados.get('numero_salarios'),
                valor_honorario,
                tipo_pagamento,
                valor_entrada,
                numero_parcelas,
                dia_vencimento,
                mes_inicio,
                forma_pagamento,
                tipo_exito if tem_exito else None,
                valor_exito if tem_exito else None,
                percentual_juros,
                id_pagamento
            ))

            if tem_exito:
                cur.execute("""
                    SELECT ID_PAGAMENTO_EXITO
                    FROM PAGAMENTO_EXITO
                    WHERE ID_PAGAMENTO = ?
                """, (id_pagamento,))
                id_pagamento_exito = cur.fetchone()

                if not valor_causa_exito or valor_causa_exito <= 0:
                    valor_causa_exito = 45000.00

                if id_pagamento_exito:
                    cur.execute("""
                        UPDATE PAGAMENTO_EXITO
                        SET TIPO_PAGAMENTO = ?,
                            VALOR_SALARIO = ?,
                            VALOR_CAUSA = ?,
                            QUANTIDADE = ?,
                            DISTRIBUICAO = ?,
                            VALOR_ENTRADA = ?,
                            NUM_PARCELAS = ?,
                            DIA_VENCIMENTO = ?,
                            MES_INICIO = ?
                        WHERE ID_PAGAMENTO_EXITO = ?
                    """, (
                        tipo_exito,
                        valor_salario_exito,
                        valor_causa_exito,
                        quantidade_exito,
                        distribuicao_exito,
                        valor_entrada_exito,
                        numero_parcelas_exito,
                        dia_vencimento_exito,
                        mes_inicio_exito,
                        id_pagamento_exito[0]
                    ))
                    id_pagamento_exito = id_pagamento_exito[0]
                else:
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
                        numero_parcelas_exito,
                        dia_vencimento_exito,
                        mes_inicio_exito
                    ))
                    id_pagamento_exito = cur.fetchone()[0]

                cur.execute("""
                    DELETE FROM PARCELAS_EXITO
                    WHERE ID_PAGAMENTO_EXITO = ?
                """, (id_pagamento_exito,))

                if tipo_exito == 'SALARIOS_BENEFICIO':
                    valor_total_exito = quantidade_exito * valor_salario_exito
                else:
                    valor_total_exito = (valor_exito / 100) * valor_causa_exito

                is_retido_fonte = distribuicao_exito == 'RETIDO_FONTE'

                if is_retido_fonte:
                    status_parcela = 'PAGA'
                    data_pagamento = datetime.date.today()
                    distribuicao_real = 'AVISTA'
                else:
                    status_parcela = 'PENDENTE'
                    data_pagamento = None
                    distribuicao_real = distribuicao_exito

                data_inicio_processo = None
                cur.execute("""
                    SELECT DATA_INICIO
                    FROM PROCESSOS
                    WHERE ID_PROCESSOS = ?
                """, (id_processo,))
                row_processo = cur.fetchone()
                if row_processo:
                    data_inicio_processo = row_processo[0]

                if not data_inicio_processo:
                    data_inicio_processo = datetime.date.today()

                ano_inicio_exito = data_inicio_processo.year
                if mes_inicio_exito < data_inicio_processo.month:
                    ano_inicio_exito += 1

                if distribuicao_real == 'AVISTA':
                    vencimento = criar_data_vencimento(ano_inicio_exito, mes_inicio_exito, dia_vencimento_exito)
                    cur.execute("""
                        INSERT INTO PARCELAS_EXITO (
                            ID_PAGAMENTO_EXITO, NUMERO_PARCELA, VALOR_PARCELA,
                            DATA_VENCIMENTO, DATA_PAGAMENTO, VALOR_PAGO, STATUS
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (id_pagamento_exito, 1, valor_total_exito, vencimento, data_pagamento, None, status_parcela))

                elif distribuicao_real == 'PARCELADO':
                    valores_exito = dividir_valor(valor_total_exito, numero_parcelas_exito)
                    for indice in range(numero_parcelas_exito):
                        ano, mes = adicionar_meses(ano_inicio_exito, mes_inicio_exito, indice)
                        vencimento = criar_data_vencimento(ano, mes, dia_vencimento_exito)
                        cur.execute("""
                            INSERT INTO PARCELAS_EXITO (
                                ID_PAGAMENTO_EXITO, NUMERO_PARCELA, VALOR_PARCELA,
                                DATA_VENCIMENTO, DATA_PAGAMENTO, VALOR_PAGO, STATUS
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (id_pagamento_exito, indice + 1, valores_exito[indice], vencimento, data_pagamento, None, status_parcela))

                elif distribuicao_real == 'ENTRADA_PARCELAS':
                    cur.execute("""
                        INSERT INTO PARCELAS_EXITO (
                            ID_PAGAMENTO_EXITO, NUMERO_PARCELA, VALOR_PARCELA,
                            DATA_VENCIMENTO, DATA_PAGAMENTO, VALOR_PAGO, STATUS
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (id_pagamento_exito, 0, valor_entrada_exito, data_inicio_processo, data_pagamento, None, status_parcela))
                    restante_exito = valor_total_exito - valor_entrada_exito
                    valores_exito = dividir_valor(restante_exito, numero_parcelas_exito)
                    for indice in range(numero_parcelas_exito):
                        ano, mes = adicionar_meses(ano_inicio_exito, mes_inicio_exito, indice)
                        vencimento = criar_data_vencimento(ano, mes, dia_vencimento_exito)
                        cur.execute("""
                            INSERT INTO PARCELAS_EXITO (
                                ID_PAGAMENTO_EXITO, NUMERO_PARCELA, VALOR_PARCELA,
                                DATA_VENCIMENTO, DATA_PAGAMENTO, VALOR_PAGO, STATUS
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (id_pagamento_exito, indice + 1, valores_exito[indice], vencimento, data_pagamento, None, status_parcela))

                if is_retido_fonte:
                    cur.execute("""
                        UPDATE PROCESSOS
                        SET STATUS = 'concluido'
                        WHERE ID_PROCESSOS = ?
                    """, (id_processo,))

            else:
                cur.execute("""
                    DELETE FROM PAGAMENTO_EXITO
                    WHERE ID_PAGAMENTO = ?
                """, (id_pagamento,))

        con.commit()
        return jsonify({'mensagem': 'Pagamento atualizado com sucesso'}), 200

    except Exception as e:
        con.rollback()
        print("Erro ao atualizar pagamento:", e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()



@app.route('/dashboard/rendimentos', methods=['GET'])
def dashboard_rendimentos():
    token_data = decodificar_token()
    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    periodo = request.args.get('periodo', 'mes')
    hoje = datetime.date.today()
    ano_atual = hoje.year
    mes_atual = hoje.month

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
        sql = """
            SELECT
                parc.VALOR_PARCELA,
                parc.DATA_VENCIMENTO,
                parc.STATUS
            FROM PARCELAS parc
            INNER JOIN PAGAMENTOS pag ON parc.ID_PAGAMENTO = pag.ID_PAGAMENTOS
            INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
            WHERE p.ID_USUARIOS_ADVOGADO = ?

            UNION ALL

            SELECT
                pe.VALOR_PARCELA,
                pe.DATA_VENCIMENTO,
                pe.STATUS
            FROM PARCELAS_EXITO pe
            INNER JOIN PAGAMENTO_EXITO pex ON pe.ID_PAGAMENTO_EXITO = pex.ID_PAGAMENTO_EXITO
            INNER JOIN PAGAMENTOS pag ON pex.ID_PAGAMENTO = pag.ID_PAGAMENTOS
            INNER JOIN PROCESSOS p ON pag.ID_PROCESSO = p.ID_PROCESSOS
            WHERE p.ID_USUARIOS_ADVOGADO = ?
        """

        cur.execute(sql, (id_advogado, id_advogado))
        rows = cur.fetchall()

        dados = {}
        total_recebido = 0.0
        total_a_receber = 0.0

        for row in rows:
            valor = float(row[0]) if row[0] else 0.0
            data_venc = converter_data_firebird(row[1])
            status = row[2]

            if not data_venc:
                continue

            ano = data_venc.year
            mes = data_venc.month
            dia = data_venc.day

            if periodo == 'mes':
                if ano != ano_atual or mes != mes_atual:
                    continue
                if dia <= 7:
                    label = '01-07'
                elif dia <= 14:
                    label = '08-14'
                elif dia <= 21:
                    label = '15-21'
                else:
                    label = '22-31'
                key = f"{ano}-{mes}-{label}"
            else:
                if str(ano) != periodo:
                    continue
                label = f"{mes:02d}/{ano}"
                key = f"{ano}-{mes:02d}"

            if key not in dados:
                dados[key] = {
                    'label': label,
                    'recebido': 0.0,
                    'a_receber': 0.0
                }

            if status == 'PAGA':
                dados[key]['recebido'] += valor
                total_recebido += valor
            else:
                dados[key]['a_receber'] += valor
                total_a_receber += valor

        dados_ordenados = [dados[key] for key in sorted(dados.keys())]

        return jsonify({
            'dados': dados_ordenados,
            'totais': {
                'recebido': round(total_recebido, 2),
                'a_receber': round(total_a_receber, 2)
            }
        }), 200

    except Exception as e:
        print("Erro ao buscar dados do gráfico:", e)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/processo/<int:id_processo>/atualizacoes', methods=['POST'])
def cadastrar_atualizacao_processo(id_processo):
    token_data = decodificar_token()

    if token_data == False:
        return jsonify({'error': 'Token necessário'}), 401

    tipo_usuario = token_data['tipo']
    id_advogado = token_data['id_usuarios']

    if tipo_usuario != 0:
        return jsonify({'error': 'Acesso não autorizado'}), 403

    dados = request.get_json()

    if not dados:
        return jsonify({'error': 'Dados não enviados'}), 400

    titulo = (dados.get('titulo') or '').strip()
    descricao = (dados.get('descricao') or '').strip()
    processo_concluido = dados.get('processo_concluido', 0)

    if not titulo:
        return jsonify({'error': 'Título é obrigatório'}), 400

    if len(titulo) > 254:
        return jsonify({'error': 'Título deve ter no máximo 254 caracteres'}), 400

    if descricao and len(descricao) > 254:
        return jsonify({'error': 'Descrição deve ter no máximo 254 caracteres'}), 400

    try:
        processo_concluido = int(processo_concluido)
    except:
        return jsonify({'error': 'Valor de processo concluído inválido'}), 400

    if processo_concluido not in [0, 1]:
        return jsonify({'error': 'Processo concluído deve ser 0 ou 1'}), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                ID_PROCESSOS,
                STATUS
            FROM PROCESSOS
            WHERE ID_PROCESSOS = ?
              AND ID_USUARIOS_ADVOGADO = ?
        """, (id_processo, id_advogado))

        processo = cur.fetchone()

        if not processo:
            return jsonify({'error': 'Processo não encontrado'}), 404

        cur.execute("""
            INSERT INTO ATUALIZACOES (
                ID_PROCESSOS,
                TITULO,
                DESCRICAO,
                PROCESSO_CONCLUIDO
            )
            VALUES (?, ?, ?, ?)
            RETURNING ID_ATUALIZACOES, "DATA"
        """, (id_processo, titulo, descricao if descricao else None, processo_concluido))

        resultado = cur.fetchone()
        id_atualizacao = resultado[0]
        data_atualizacao = resultado[1]


        con.commit()

        return jsonify({
            'mensagem': 'Atualização cadastrada com sucesso',
            'atualizacao': {
                'id': id_atualizacao,
                'id_processo': id_processo,
                'data': data_atualizacao.strftime('%d/%m/%Y %H:%M') if data_atualizacao else None,
                'titulo': titulo,
                'descricao': descricao if descricao else None,
                'processo_concluido': processo_concluido
            }
        }), 201

    except Exception as e:
        con.rollback()
        print('Erro ao cadastrar atualização:', e)
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        con.close()


@app.route('/processo/<int:id_processo>/atualizacoes', methods=['GET'])
def listar_atualizacoes_processo(id_processo):
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
                ID_PROCESSOS
            FROM PROCESSOS
            WHERE ID_PROCESSOS = ?
              AND ID_USUARIOS_ADVOGADO = ?
        """, (
            id_processo,
            id_advogado
        ))

        processo = cur.fetchone()

        if not processo:
            return jsonify({
                'error': 'Processo não encontrado'
            }), 404

        cur.execute("""
            SELECT
                ID_ATUALIZACOES,
                ID_PROCESSOS,
                "DATA",
                TITULO,
                DESCRICAO,
                PROCESSO_CONCLUIDO
            FROM ATUALIZACOES
            WHERE ID_PROCESSOS = ?
            ORDER BY
                "DATA" DESC,
                ID_ATUALIZACOES DESC
        """, (
            id_processo,
        ))

        rows = cur.fetchall()

        atualizacoes = []

        for row in rows:
            data_atualizacao = row[2]

            atualizacoes.append({
                'id': row[0],
                'id_processo': row[1],
                'data': (
                    data_atualizacao.strftime(
                        '%d/%m/%Y %H:%M'
                    )
                    if data_atualizacao
                    else None
                ),
                'titulo': (
                    row[3]
                    or '--'
                ),
                'descricao': (
                    row[4]
                    or ''
                ),
                'processo_concluido': bool(
                    row[5]
                )
            })

        return jsonify({
            'atualizacoes': atualizacoes,
            'quantidade': len(atualizacoes)
        }), 200

    except Exception as e:
        print(
            'Erro ao listar atualizações:',
            e
        )

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/processo/<int:id_processo>/atualizacoes/<int:id_atualizacao>', methods=['PUT'])
def editar_atualizacao_processo(id_processo, id_atualizacao):
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

    titulo = (
        dados.get('titulo')
        or ''
    ).strip()

    descricao = (
        dados.get('descricao')
        or ''
    ).strip()

    processo_concluido = dados.get(
        'processo_concluido',
        0
    )

    if not titulo:
        return jsonify({
            'error': 'Título é obrigatório'
        }), 400

    if len(titulo) > 254:
        return jsonify({
            'error': 'Título deve ter no máximo 254 caracteres'
        }), 400

    if descricao and len(descricao) > 254:
        return jsonify({
            'error': 'Descrição deve ter no máximo 254 caracteres'
        }), 400

    try:
        processo_concluido = int(
            processo_concluido
        )
    except:
        return jsonify({
            'error': 'Valor de processo concluído inválido'
        }), 400

    if processo_concluido not in [0, 1]:
        return jsonify({
            'error': 'Processo concluído deve ser 0 ou 1'
        }), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                p.ID_PROCESSOS,
                p.STATUS
            FROM PROCESSOS p
            WHERE p.ID_PROCESSOS = ?
              AND p.ID_USUARIOS_ADVOGADO = ?
        """, (
            id_processo,
            id_advogado
        ))

        processo = cur.fetchone()

        if not processo:
            return jsonify({
                'error': 'Processo não encontrado'
            }), 404

        cur.execute("""
            SELECT
                ID_ATUALIZACOES,
                PROCESSO_CONCLUIDO
            FROM ATUALIZACOES
            WHERE ID_ATUALIZACOES = ?
              AND ID_PROCESSOS = ?
        """, (
            id_atualizacao,
            id_processo
        ))

        atualizacao = cur.fetchone()

        if not atualizacao:
            return jsonify({
                'error': 'Atualização não encontrada'
            }), 404

        cur.execute("""
            UPDATE ATUALIZACOES
            SET
                TITULO = ?,
                DESCRICAO = ?,
                PROCESSO_CONCLUIDO = ?
            WHERE ID_ATUALIZACOES = ?
              AND ID_PROCESSOS = ?
        """, (
            titulo,
            descricao if descricao else None,
            processo_concluido,
            id_atualizacao,
            id_processo
        ))

        if processo_concluido == 1:
            cur.execute("""
                UPDATE PROCESSOS
                SET STATUS = ?
                WHERE ID_PROCESSOS = ?
                  AND ID_USUARIOS_ADVOGADO = ?
            """, (
                'concluido',
                id_processo,
                id_advogado
            ))
        else:
            cur.execute("""
                SELECT COUNT(*)
                FROM ATUALIZACOES
                WHERE ID_PROCESSOS = ?
                  AND PROCESSO_CONCLUIDO = 1
            """, (
                id_processo,
            ))

            quantidade_concluidas = (
                cur.fetchone()[0]
            )

            if quantidade_concluidas == 0:
                cur.execute("""
                    UPDATE PROCESSOS
                    SET STATUS = ?
                    WHERE ID_PROCESSOS = ?
                      AND ID_USUARIOS_ADVOGADO = ?
                      AND STATUS = ?
                """, (
                    'em_andamento',
                    id_processo,
                    id_advogado,
                    'concluido'
                ))

        con.commit()

        return jsonify({
            'mensagem': 'Atualização editada com sucesso',
            'atualizacao': {
                'id': id_atualizacao,
                'id_processo': id_processo,
                'titulo': titulo,
                'descricao': (
                    descricao
                    if descricao
                    else None
                ),
                'processo_concluido': bool(
                    processo_concluido
                )
            }
        }), 200

    except Exception as e:
        con.rollback()

        print(
            'Erro ao editar atualização:',
            e
        )

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/processo/<int:id_processo>/atualizacoes/<int:id_atualizacao>', methods=['DELETE'])
def excluir_atualizacao_processo(id_processo, id_atualizacao):
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
                p.STATUS
            FROM PROCESSOS p
            WHERE p.ID_PROCESSOS = ?
              AND p.ID_USUARIOS_ADVOGADO = ?
        """, (
            id_processo,
            id_advogado
        ))

        processo = cur.fetchone()

        if not processo:
            return jsonify({
                'error': 'Processo não encontrado'
            }), 404

        cur.execute("""
            SELECT
                ID_ATUALIZACOES,
                PROCESSO_CONCLUIDO
            FROM ATUALIZACOES
            WHERE ID_ATUALIZACOES = ?
              AND ID_PROCESSOS = ?
        """, (
            id_atualizacao,
            id_processo
        ))

        atualizacao = cur.fetchone()

        if not atualizacao:
            return jsonify({
                'error': 'Atualização não encontrada'
            }), 404

        era_conclusao = bool(
            atualizacao[1]
        )

        cur.execute("""
            DELETE FROM ATUALIZACOES
            WHERE ID_ATUALIZACOES = ?
              AND ID_PROCESSOS = ?
        """, (
            id_atualizacao,
            id_processo
        ))

        if era_conclusao:
            cur.execute("""
                SELECT COUNT(*)
                FROM ATUALIZACOES
                WHERE ID_PROCESSOS = ?
                  AND PROCESSO_CONCLUIDO = 1
            """, (
                id_processo,
            ))

            quantidade_concluidas = (
                cur.fetchone()[0]
            )

            if quantidade_concluidas == 0:
                cur.execute("""
                    UPDATE PROCESSOS
                    SET STATUS = ?
                    WHERE ID_PROCESSOS = ?
                      AND ID_USUARIOS_ADVOGADO = ?
                      AND STATUS = ?
                """, (
                    'em_andamento',
                    id_processo,
                    id_advogado,
                    'concluido'
                ))

        con.commit()

        return jsonify({
            'mensagem': 'Atualização excluída com sucesso'
        }), 200

    except Exception as e:
        con.rollback()

        print(
            'Erro ao excluir atualização:',
            e
        )

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/processo/<int:id_processo>/pagamento/exito', methods=['GET'])
def buscar_pagamento_exito_processo(id_processo):
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
                p.ID_USUARIOS_ADVOGADO,
                pag.ID_PAGAMENTOS,
                pag.TIPO_HONORARIO,
                pag.NUM_SALARIOS,
                pag.VALOR_HONORARIO,
                pag.FORM_PAGAMENTO,
                pag.TIPO_EXITO,
                pag.VALOR_EXITO,
                pag.PERCENTUAL_JUROS,
                pex.ID_PAGAMENTO_EXITO,
                pex.TIPO_PAGAMENTO,
                pex.VALOR_SALARIO,
                pex.VALOR_CAUSA,
                pex.QUANTIDADE,
                pex.DISTRIBUICAO,
                pex.VALOR_ENTRADA,
                pex.NUM_PARCELAS,
                pex.DIA_VENCIMENTO,
                pex.MES_INICIO
            FROM PROCESSOS p
            INNER JOIN PAGAMENTOS pag
                ON pag.ID_PROCESSO = p.ID_PROCESSOS
            LEFT JOIN PAGAMENTO_EXITO pex
                ON pex.ID_PAGAMENTO = pag.ID_PAGAMENTOS
            WHERE p.ID_PROCESSOS = ?
        """, (
            id_processo,
        ))

        row = cur.fetchone()

        if not row:
            return jsonify({
                'error': 'Processo ou pagamento não encontrado'
            }), 404

        if row[0] != id_advogado:
            return jsonify({
                'error': 'Acesso não autorizado'
            }), 403

        tipo_honorario = row[2]
        valor_honorario = row[4]
        tipo_exito_pagamento = row[6]
        valor_exito_pagamento = row[7]

        tipo_exito = (
            row[10]
            or tipo_exito_pagamento
            or ''
        )

        valor_salario = row[11]

        if (
            valor_salario is None
            and tipo_exito == 'SALARIOS_BENEFICIO'
            and tipo_honorario == 'SALARIOS'
            and valor_honorario is not None
        ):
            valor_salario = valor_honorario

        quantidade = row[13]

        if (
            quantidade is None
            and tipo_exito == 'SALARIOS_BENEFICIO'
            and valor_exito_pagamento is not None
        ):
            quantidade = valor_exito_pagamento

        valor_causa = row[12]

        dados = {
            'id_pagamento': row[1],

            'id_pagamento_exito': (
                row[9]
                if row[9] is not None
                else None
            ),

            'tipo_pagamento': tipo_exito,

            'tipo_exito': tipo_exito,

            'valor_exito': (
                float(valor_exito_pagamento)
                if valor_exito_pagamento is not None
                else None
            ),

            'quantidade': (
                float(quantidade)
                if quantidade is not None
                else None
            ),

            'valor_salario': (
                float(valor_salario)
                if valor_salario is not None
                else None
            ),

            'valor_causa': (
                float(valor_causa)
                if valor_causa is not None
                else None
            ),

            'distribuicao': (
                row[14]
                or ''
            ),

            'valor_entrada': (
                float(row[15])
                if row[15] is not None
                else None
            ),

            'num_parcelas': (
                row[16]
                if row[16] is not None
                else ''
            ),

            'dia_vencimento': (
                row[17]
                if row[17] is not None
                else ''
            ),

            'mes_inicio': (
                row[18]
                if row[18] is not None
                else ''
            ),

            'forma_pagamento': (
                row[5]
                or ''
            ),

            'percentual_juros': (
                float(row[8])
                if row[8] is not None
                else None
            ),

            'configurado': (
                row[9] is not None
            )
        }

        return jsonify({
            'dados': dados
        }), 200

    except Exception as e:
        print(
            'Erro ao buscar pagamento de êxito:',
            e
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()

@app.route('/processo/<int:id_processo>/pagamento/exito', methods=['PUT'])
def atualizar_pagamento_exito_processo(id_processo):
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

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                pag.ID_PAGAMENTOS,
                pag.TIPO_EXITO,
                pag.VALOR_EXITO,
                p.DATA_INICIO
            FROM PROCESSOS p
            INNER JOIN PAGAMENTOS pag
                ON pag.ID_PROCESSO = p.ID_PROCESSOS
            WHERE p.ID_PROCESSOS = ?
              AND p.ID_USUARIOS_ADVOGADO = ?
        """, (
            id_processo,
            id_advogado
        ))

        pagamento = cur.fetchone()

        if not pagamento:
            return jsonify({
                'error': 'Processo ou pagamento não encontrado'
            }), 404

        id_pagamento = pagamento[0]

        tipo_exito = (
            dados.get('tipo_exito')
            or pagamento[1]
            or ''
        ).upper()

        valor_exito = converter_decimal(
            dados.get('valor_exito')
        )

        if valor_exito is None:
            valor_exito = converter_decimal(
                pagamento[2]
            )

        if tipo_exito not in [
            'PERCENTUAL',
            'SALARIOS_BENEFICIO'
        ]:
            return jsonify({
                'error': 'Tipo do êxito inválido'
            }), 400

        if (
            valor_exito is None
            or valor_exito <= 0
        ):
            return jsonify({
                'error': 'Valor do êxito é obrigatório'
            }), 400

        distribuicao = (
            dados.get(
                'distribuicao_exito'
            )
            or ''
        ).upper()

        if distribuicao not in [
            'AVISTA',
            'PARCELADO',
            'ENTRADA_PARCELAS',
            'RETIDO_FONTE'
        ]:
            return jsonify({
                'error': 'Distribuição do êxito inválida'
            }), 400

        valor_salario = converter_decimal(
            dados.get(
                'valor_salario_exito'
            )
        )

        valor_causa = converter_decimal(
            dados.get(
                'valor_causa_exito'
            )
        )

        quantidade = dados.get(
            'quantidade_exito'
        )

        valor_entrada = converter_decimal(
            dados.get(
                'valor_entrada_exito'
            )
        )

        numero_parcelas = dados.get(
            'numero_parcelas_exito'
        )

        dia_vencimento = dados.get(
            'dia_vencimento_exito'
        )

        mes_inicio = dados.get(
            'mes_inicio_exito'
        )

        if (
            tipo_exito ==
            'SALARIOS_BENEFICIO'
        ):
            try:
                quantidade = int(
                    quantidade
                )
            except:
                return jsonify({
                    'error': 'Quantidade de salários inválida'
                }), 400

            if quantidade <= 0:
                return jsonify({
                    'error': 'Quantidade deve ser maior que zero'
                }), 400

            if (
                valor_salario is None
                or valor_salario <= 0
            ):
                return jsonify({
                    'error': 'Valor do salário é obrigatório'
                }), 400

            valor_total = (
                quantidade
                * valor_salario
            )

        else:
            if valor_exito > 100:
                return jsonify({
                    'error': 'Percentual não pode ser maior que 100'
                }), 400

            if (
                valor_causa is None
                or valor_causa <= 0
            ):
                return jsonify({
                    'error': 'Valor da causa é obrigatório'
                }), 400

            valor_total = (
                valor_exito
                / 100
            ) * valor_causa

        if distribuicao in [
            'PARCELADO',
            'ENTRADA_PARCELAS'
        ]:
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
            distribuicao ==
            'ENTRADA_PARCELAS'
        ):
            if (
                valor_entrada is None
                or valor_entrada <= 0
            ):
                return jsonify({
                    'error': 'Valor da entrada é obrigatório'
                }), 400

            if (
                valor_entrada >=
                valor_total
            ):
                return jsonify({
                    'error': 'Valor da entrada deve ser menor que o valor total'
                }), 400
        else:
            valor_entrada = None

        if (
            distribuicao !=
            'RETIDO_FONTE'
        ):
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

            if not (
                1 <=
                dia_vencimento <=
                31
            ):
                return jsonify({
                    'error': 'Dia de vencimento inválido'
                }), 400

            if not (
                1 <=
                mes_inicio <=
                12
            ):
                return jsonify({
                    'error': 'Mês de início inválido'
                }), 400

        cur.execute("""
            UPDATE PAGAMENTOS
            SET
                TIPO_EXITO = ?,
                VALOR_EXITO = ?
            WHERE ID_PAGAMENTOS = ?
        """, (
            tipo_exito,
            valor_exito,
            id_pagamento
        ))

        cur.execute("""
            SELECT
                ID_PAGAMENTO_EXITO
            FROM PAGAMENTO_EXITO
            WHERE ID_PAGAMENTO = ?
        """, (
            id_pagamento,
        ))

        existente = cur.fetchone()

        if existente:
            id_pagamento_exito = (
                existente[0]
            )

            cur.execute("""
                UPDATE PAGAMENTO_EXITO
                SET
                    TIPO_PAGAMENTO = ?,
                    VALOR_SALARIO = ?,
                    VALOR_CAUSA = ?,
                    QUANTIDADE = ?,
                    DISTRIBUICAO = ?,
                    VALOR_ENTRADA = ?,
                    NUM_PARCELAS = ?,
                    DIA_VENCIMENTO = ?,
                    MES_INICIO = ?
                WHERE ID_PAGAMENTO_EXITO = ?
            """, (
                tipo_exito,
                valor_salario,
                valor_causa,
                quantidade,
                distribuicao,
                valor_entrada,
                numero_parcelas,
                dia_vencimento,
                mes_inicio,
                id_pagamento_exito
            ))

        else:
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
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                RETURNING ID_PAGAMENTO_EXITO
            """, (
                id_pagamento,
                tipo_exito,
                valor_salario,
                valor_causa,
                quantidade,
                distribuicao,
                valor_entrada,
                numero_parcelas,
                dia_vencimento,
                mes_inicio
            ))

            id_pagamento_exito = (
                cur.fetchone()[0]
            )

        cur.execute("""
            DELETE FROM PARCELAS_EXITO
            WHERE ID_PAGAMENTO_EXITO = ?
        """, (
            id_pagamento_exito,
        ))

        data_inicio = (
            pagamento[3]
            or datetime.date.today()
        )

        if (
            isinstance(
                data_inicio,
                datetime.datetime
            )
        ):
            data_inicio = (
                data_inicio.date()
            )

        if (
            distribuicao ==
            'RETIDO_FONTE'
        ):
            cur.execute("""
                INSERT INTO PARCELAS_EXITO (
                    ID_PAGAMENTO_EXITO,
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
                id_pagamento_exito,
                1,
                valor_total,
                data_inicio,
                datetime.date.today(),
                valor_total,
                'PAGA'
            ))

        else:
            ano_inicio = (
                data_inicio.year
            )

            if (
                mes_inicio <
                data_inicio.month
            ):
                ano_inicio += 1

            if (
                distribuicao ==
                'AVISTA'
            ):
                vencimento = (
                    criar_data_vencimento(
                        ano_inicio,
                        mes_inicio,
                        dia_vencimento
                    )
                )

                cur.execute("""
                    INSERT INTO PARCELAS_EXITO (
                        ID_PAGAMENTO_EXITO,
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
                    id_pagamento_exito,
                    1,
                    valor_total,
                    vencimento,
                    None,
                    None,
                    'PENDENTE'
                ))

            elif (
                distribuicao ==
                'PARCELADO'
            ):
                valores = dividir_valor(
                    valor_total,
                    numero_parcelas
                )

                for indice in range(
                    numero_parcelas
                ):
                    ano, mes = (
                        adicionar_meses(
                            ano_inicio,
                            mes_inicio,
                            indice
                        )
                    )

                    vencimento = (
                        criar_data_vencimento(
                            ano,
                            mes,
                            dia_vencimento
                        )
                    )

                    cur.execute("""
                        INSERT INTO PARCELAS_EXITO (
                            ID_PAGAMENTO_EXITO,
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
                        id_pagamento_exito,
                        indice + 1,
                        valores[indice],
                        vencimento,
                        None,
                        None,
                        'PENDENTE'
                    ))

            elif (
                distribuicao ==
                'ENTRADA_PARCELAS'
            ):
                cur.execute("""
                    INSERT INTO PARCELAS_EXITO (
                        ID_PAGAMENTO_EXITO,
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
                    id_pagamento_exito,
                    0,
                    valor_entrada,
                    data_inicio,
                    None,
                    None,
                    'PENDENTE'
                ))

                restante = (
                    valor_total -
                    valor_entrada
                )

                valores = dividir_valor(
                    restante,
                    numero_parcelas
                )

                for indice in range(
                    numero_parcelas
                ):
                    ano, mes = (
                        adicionar_meses(
                            ano_inicio,
                            mes_inicio,
                            indice
                        )
                    )

                    vencimento = (
                        criar_data_vencimento(
                            ano,
                            mes,
                            dia_vencimento
                        )
                    )

                    cur.execute("""
                        INSERT INTO PARCELAS_EXITO (
                            ID_PAGAMENTO_EXITO,
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
                        id_pagamento_exito,
                        indice + 1,
                        valores[indice],
                        vencimento,
                        None,
                        None,
                        'PENDENTE'
                    ))

        con.commit()

        return jsonify({
            'mensagem': 'Pagamento de êxito configurado com sucesso',
            'id_pagamento_exito': id_pagamento_exito
        }), 200

    except Exception as e:
        con.rollback()

        print(
            'Erro ao atualizar pagamento de êxito:',
            e
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()


@app.route('/processo/<int:id_processo>/concluir', methods=['POST'])
def concluir_processo(id_processo):
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

    atualizacao = dados.get(
        'atualizacao',
        {}
    )

    exito = dados.get(
        'exito',
        {}
    )

    id_atualizacao = atualizacao.get(
        'id_atualizacao'
    )

    titulo = (
        atualizacao.get('titulo')
        or ''
    ).strip()

    descricao = (
        atualizacao.get('descricao')
        or ''
    ).strip()

    if not titulo:
        return jsonify({
            'error': 'Título da atualização é obrigatório'
        }), 400

    tipo_exito = (
        exito.get('tipo_exito')
        or ''
    ).upper()

    if tipo_exito not in [
        'PERCENTUAL',
        'SALARIOS_BENEFICIO'
    ]:
        return jsonify({
            'error': 'Tipo de êxito inválido'
        }), 400

    valor_exito = converter_decimal(
        exito.get(
            'valor_exito'
        )
    )

    valor_salario = converter_decimal(
        exito.get(
            'valor_salario_exito'
        )
    )

    valor_causa = converter_decimal(
        exito.get(
            'valor_causa_exito'
        )
    )

    quantidade = exito.get(
        'quantidade_exito'
    )

    distribuicao = (
        exito.get(
            'distribuicao_exito'
        )
        or ''
    ).upper()

    valor_entrada = converter_decimal(
        exito.get(
            'valor_entrada_exito'
        )
    )

    numero_parcelas = exito.get(
        'numero_parcelas_exito'
    )

    dia_vencimento = exito.get(
        'dia_vencimento_exito'
    )

    mes_inicio = exito.get(
        'mes_inicio_exito'
    )

    if distribuicao not in [
        'AVISTA',
        'PARCELADO',
        'ENTRADA_PARCELAS',
        'RETIDO_FONTE'
    ]:
        return jsonify({
            'error': 'Distribuição do êxito inválida'
        }), 400

    con = conexao()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT
                pag.ID_PAGAMENTOS,
                pag.TIPO_HONORARIO,
                pag.VALOR_HONORARIO,
                pag.TIPO_EXITO,
                pag.VALOR_EXITO,
                p.DATA_INICIO
            FROM PROCESSOS p
            INNER JOIN PAGAMENTOS pag
                ON pag.ID_PROCESSO = p.ID_PROCESSOS
            WHERE p.ID_PROCESSOS = ?
              AND p.ID_USUARIOS_ADVOGADO = ?
        """, (
            id_processo,
            id_advogado
        ))

        pagamento = cur.fetchone()

        if not pagamento:
            return jsonify({
                'error': 'Processo ou pagamento não encontrado'
            }), 404

        id_pagamento = pagamento[0]
        tipo_honorario = pagamento[1]
        valor_honorario = pagamento[2]

        cur.execute("""
            SELECT
                ID_PAGAMENTO_EXITO,
                TIPO_PAGAMENTO,
                VALOR_SALARIO,
                VALOR_CAUSA,
                QUANTIDADE,
                DISTRIBUICAO,
                VALOR_ENTRADA,
                NUM_PARCELAS,
                DIA_VENCIMENTO,
                MES_INICIO
            FROM PAGAMENTO_EXITO
            WHERE ID_PAGAMENTO = ?
        """, (
            id_pagamento,
        ))

        exito_existente = cur.fetchone()

        if (
            valor_exito is None
            or valor_exito <= 0
        ):
            valor_exito = converter_decimal(
                pagamento[4]
            )

        if (
            tipo_exito == 'SALARIOS_BENEFICIO'
        ):
            if (
                quantidade is None
                or quantidade == ''
            ):
                if (
                    exito_existente
                    and exito_existente[4] is not None
                ):
                    quantidade = exito_existente[4]
                else:
                    quantidade = valor_exito

            try:
                quantidade = int(
                    quantidade
                )
            except:
                return jsonify({
                    'error': 'Quantidade de salários inválida'
                }), 400

            if quantidade <= 0:
                return jsonify({
                    'error': 'Quantidade de salários deve ser maior que zero'
                }), 400

            if (
                valor_salario is None
                or valor_salario <= 0
            ):
                if (
                    exito_existente
                    and exito_existente[2] is not None
                ):
                    valor_salario = exito_existente[2]

                elif (
                    tipo_honorario == 'SALARIOS'
                    and valor_honorario
                    and valor_honorario > 0
                ):
                    valor_salario = valor_honorario

            if (
                valor_salario is None
                or valor_salario <= 0
            ):
                return jsonify({
                    'error': 'Valor do salário é obrigatório'
                }), 400

            valor_exito = quantidade

            valor_total_exito = (
                quantidade
                * valor_salario
            )

            valor_causa = None

        else:
            if (
                valor_exito is None
                or valor_exito <= 0
            ):
                return jsonify({
                    'error': 'Percentual do êxito é obrigatório'
                }), 400

            if valor_exito > 100:
                return jsonify({
                    'error': 'Percentual do êxito não pode ser maior que 100'
                }), 400

            if (
                valor_causa is None
                or valor_causa <= 0
            ):
                if (
                    exito_existente
                    and exito_existente[3] is not None
                ):
                    valor_causa = exito_existente[3]

            if (
                valor_causa is None
                or valor_causa <= 0
            ):
                valor_causa = converter_decimal(
                    45000
                )

            valor_total_exito = (
                valor_exito
                / 100
            ) * valor_causa

            quantidade = None
            valor_salario = None

        if (
            not distribuicao
            and exito_existente
        ):
            distribuicao = (
                exito_existente[5]
                or ''
            )

        if distribuicao not in [
            'AVISTA',
            'PARCELADO',
            'ENTRADA_PARCELAS',
            'RETIDO_FONTE'
        ]:
            return jsonify({
                'error': 'Distribuição do êxito inválida'
            }), 400

        if (
            distribuicao in [
                'PARCELADO',
                'ENTRADA_PARCELAS'
            ]
        ):
            if (
                numero_parcelas is None
                or numero_parcelas == ''
            ):
                if (
                    exito_existente
                    and exito_existente[7]
                ):
                    numero_parcelas = (
                        exito_existente[7]
                    )

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

        else:
            numero_parcelas = None

        if (
            distribuicao ==
            'ENTRADA_PARCELAS'
        ):
            if (
                valor_entrada is None
                or valor_entrada <= 0
            ):
                if (
                    exito_existente
                    and exito_existente[6]
                ):
                    valor_entrada = (
                        exito_existente[6]
                    )

            if (
                valor_entrada is None
                or valor_entrada <= 0
            ):
                return jsonify({
                    'error': 'Valor da entrada é obrigatório'
                }), 400

            if (
                valor_entrada >=
                valor_total_exito
            ):
                return jsonify({
                    'error': 'Valor da entrada deve ser menor que o valor total'
                }), 400

        else:
            valor_entrada = None

        if (
            distribuicao !=
            'RETIDO_FONTE'
        ):
            if (
                not dia_vencimento
                and exito_existente
            ):
                dia_vencimento = (
                    exito_existente[8]
                )

            if (
                not mes_inicio
                and exito_existente
            ):
                mes_inicio = (
                    exito_existente[9]
                )

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

        else:
            dia_vencimento = None
            mes_inicio = None

        cur.execute("""
            UPDATE PAGAMENTOS
            SET
                TIPO_EXITO = ?,
                VALOR_EXITO = ?
            WHERE ID_PAGAMENTOS = ?
        """, (
            tipo_exito,
            valor_exito,
            id_pagamento
        ))

        if exito_existente:
            id_pagamento_exito = (
                exito_existente[0]
            )

            cur.execute("""
                UPDATE PAGAMENTO_EXITO
                SET
                    TIPO_PAGAMENTO = ?,
                    VALOR_SALARIO = ?,
                    VALOR_CAUSA = ?,
                    QUANTIDADE = ?,
                    DISTRIBUICAO = ?,
                    VALOR_ENTRADA = ?,
                    NUM_PARCELAS = ?,
                    DIA_VENCIMENTO = ?,
                    MES_INICIO = ?
                WHERE ID_PAGAMENTO_EXITO = ?
            """, (
                tipo_exito,
                valor_salario,
                valor_causa,
                quantidade,
                distribuicao,
                valor_entrada,
                numero_parcelas,
                dia_vencimento,
                mes_inicio,
                id_pagamento_exito
            ))

        else:
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
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                RETURNING ID_PAGAMENTO_EXITO
            """, (
                id_pagamento,
                tipo_exito,
                valor_salario,
                valor_causa,
                quantidade,
                distribuicao,
                valor_entrada,
                numero_parcelas,
                dia_vencimento,
                mes_inicio
            ))

            id_pagamento_exito = (
                cur.fetchone()[0]
            )

        cur.execute("""
            DELETE FROM PARCELAS_EXITO
            WHERE ID_PAGAMENTO_EXITO = ?
        """, (
            id_pagamento_exito,
        ))

        data_inicio = (
            pagamento[5]
            or datetime.date.today()
        )

        if isinstance(
            data_inicio,
            datetime.datetime
        ):
            data_inicio = (
                data_inicio.date()
            )

        if (
            distribuicao ==
            'RETIDO_FONTE'
        ):
            cur.execute("""
                INSERT INTO PARCELAS_EXITO (
                    ID_PAGAMENTO_EXITO,
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
                id_pagamento_exito,
                1,
                valor_total_exito,
                data_inicio,
                datetime.date.today(),
                valor_total_exito,
                'PAGA'
            ))

        else:
            ano_inicio = (
                data_inicio.year
            )

            if (
                mes_inicio <
                data_inicio.month
            ):
                ano_inicio += 1

            if (
                distribuicao ==
                'AVISTA'
            ):
                vencimento = (
                    criar_data_vencimento(
                        ano_inicio,
                        mes_inicio,
                        dia_vencimento
                    )
                )

                cur.execute("""
                    INSERT INTO PARCELAS_EXITO (
                        ID_PAGAMENTO_EXITO,
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
                    id_pagamento_exito,
                    1,
                    valor_total_exito,
                    vencimento,
                    None,
                    None,
                    'PENDENTE'
                ))

            elif (
                distribuicao ==
                'PARCELADO'
            ):
                valores = dividir_valor(
                    valor_total_exito,
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

                    vencimento = (
                        criar_data_vencimento(
                            ano,
                            mes,
                            dia_vencimento
                        )
                    )

                    cur.execute("""
                        INSERT INTO PARCELAS_EXITO (
                            ID_PAGAMENTO_EXITO,
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
                        id_pagamento_exito,
                        indice + 1,
                        valores[indice],
                        vencimento,
                        None,
                        None,
                        'PENDENTE'
                    ))

            elif (
                distribuicao ==
                'ENTRADA_PARCELAS'
            ):
                cur.execute("""
                    INSERT INTO PARCELAS_EXITO (
                        ID_PAGAMENTO_EXITO,
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
                    id_pagamento_exito,
                    0,
                    valor_entrada,
                    data_inicio,
                    None,
                    None,
                    'PENDENTE'
                ))

                restante = (
                    valor_total_exito
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

                    vencimento = (
                        criar_data_vencimento(
                            ano,
                            mes,
                            dia_vencimento
                        )
                    )

                    cur.execute("""
                        INSERT INTO PARCELAS_EXITO (
                            ID_PAGAMENTO_EXITO,
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
                        id_pagamento_exito,
                        indice + 1,
                        valores[indice],
                        vencimento,
                        None,
                        None,
                        'PENDENTE'
                    ))

        if id_atualizacao:
            cur.execute("""
                SELECT
                    ID_ATUALIZACOES
                FROM ATUALIZACOES
                WHERE ID_ATUALIZACOES = ?
                  AND ID_PROCESSOS = ?
            """, (
                id_atualizacao,
                id_processo
            ))

            if not cur.fetchone():
                con.rollback()

                return jsonify({
                    'error': 'Atualização não encontrada'
                }), 404

            cur.execute("""
                UPDATE ATUALIZACOES
                SET
                    TITULO = ?,
                    DESCRICAO = ?,
                    PROCESSO_CONCLUIDO = 1
                WHERE ID_ATUALIZACOES = ?
                  AND ID_PROCESSOS = ?
            """, (
                titulo,
                descricao
                    if descricao
                    else None,
                id_atualizacao,
                id_processo
            ))

        else:
            cur.execute("""
                INSERT INTO ATUALIZACOES (
                    ID_PROCESSOS,
                    TITULO,
                    DESCRICAO,
                    PROCESSO_CONCLUIDO
                )
                VALUES (
                    ?, ?, ?, ?
                )
            """, (
                id_processo,
                titulo,
                descricao
                    if descricao
                    else None,
                1
            ))

        cur.execute("""
            UPDATE PROCESSOS
            SET STATUS = 'concluido'
            WHERE ID_PROCESSOS = ?
              AND ID_USUARIOS_ADVOGADO = ?
        """, (
            id_processo,
            id_advogado
        ))

        con.commit()

        return jsonify({
            'mensagem': 'Processo concluído com sucesso',
            'id_pagamento_exito': id_pagamento_exito
        }), 200

    except Exception as e:
        con.rollback()

        print(
            'Erro ao concluir processo:',
            e
        )

        import traceback
        traceback.print_exc()

        return jsonify({
            'error': str(e)
        }), 500

    finally:
        cur.close()
        con.close()