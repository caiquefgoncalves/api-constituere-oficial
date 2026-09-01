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
            return jsonify({
                'error': 'Tipo do honorário de êxito é obrigatório'
            }), 400

        tipo_exito = tipo_exito.upper()

        if tipo_exito not in [
            'PERCENTUAL',
            'SALARIOS_BENEFICIO'
        ]:
            return jsonify({
                'error': 'Tipo do honorário de êxito inválido'
            }), 400

        if (
            valor_exito is None
            or valor_exito <= 0
        ):
            return jsonify({
                'error': 'Valor do êxito é obrigatório'
            }), 400

        if (
            tipo_exito == 'PERCENTUAL'
            and valor_exito > 100
        ):
            return jsonify({
                'error': 'Percentual de êxito não pode ser maior que 100'
            }), 400

    else:
        tipo_exito = None
        valor_exito = None

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
            SELECT DISTINCT
                cliente.ID_USUARIOS

            FROM USUARIOS cliente

            INNER JOIN ADVOGADO_ESCRITORIO ae_responsavel
                ON ae_responsavel.ID_USUARIOS =
                   cliente.ID_USUARIO_RESPONSAVEL

            INNER JOIN ADVOGADO_ESCRITORIO ae_logado
                ON ae_logado.ID_ESCRITORIOS =
                   ae_responsavel.ID_ESCRITORIOS

            WHERE cliente.ID_USUARIOS = ?
              AND cliente.TIPO IN (2, 3)
              AND cliente.ATIVO = 1
              AND ae_logado.ID_USUARIOS = ?
        """, (
            id_cliente,
            id_advogado
        ))

        cliente = cur.fetchone()

        if not cliente:
            return jsonify({
                'error': 'Cliente não encontrado ou não pertence aos seus escritórios'
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

        con.commit()

        return jsonify({
            'mensagem': 'Processo cadastrado com sucesso',
            'id_processo': id_processo,
            'id_pagamento': id_pagamento,
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

                # Ainda não existe STATUS
                # na estrutura de PROCESSOS
                # que você me passou.
                'status': 'em_andamento',

                # Também não existe DESCRICAO
                # na tabela PROCESSOS atual.
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