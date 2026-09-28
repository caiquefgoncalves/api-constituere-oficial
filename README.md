# API Constituére

API em Python para apoiar a gestão de escritórios de advocacia. O serviço reúne operações de usuários, escritórios, clientes, processos, pagamentos e agendamentos, com persistência em Firebird e comunicação em tempo real via Socket.IO.

## Funcionalidades

- Cadastro, autenticação, perfil e recuperação de senha de usuários.
- Gestão de escritórios e vínculo de advogados, incluindo cargos e status.
- Cadastro e consulta de clientes.
- Registro e acompanhamento de processos, atualizações, parcelas e rendimentos.
- Criação, consulta, edição, confirmação, recusa e cancelamento de agendamentos.
- Notificações e envio de e-mails relacionados a contas e agendamentos.
- Consulta auxiliar de dados da OAB e do CNSA por automação com Selenium.
- Disponibilização de arquivos enviados em `/uploads/<caminho>`.

## Tecnologias

- Python e Flask para a API HTTP.
- Flask-CORS para acesso a partir das origens de frontend configuradas.
- Flask-SocketIO para conexões em tempo real e salas por usuário.
- Firebird, acessado pela biblioteca `fdb`.
- PyJWT e Flask-Bcrypt para recursos de autenticação e senhas.
- Selenium para automações de consulta externa.

## Organização do projeto

| Arquivo | Responsabilidade |
| --- | --- |
| `main.py` | Cria a aplicação Flask, configura CORS, Socket.IO, uploads e importa as rotas. |
| `usuario.py` | Rotas de usuários, escritórios, advogados, clientes e notificações. |
| `processos.py` | Rotas de processos, atualizações, pagamentos e rendimentos. |
| `agendamentos.py` | Rotas e regras de negócio de agendamentos. |
| `funcao.py` | Validações, tokens, conversões e funções auxiliares, incluindo e-mails. |
| `permissoes.py` | Verificações de acesso a escritórios. |
| `db.py` | Abre conexões com o Firebird. |
| `config.py` | Configurações da aplicação e da conexão com o banco. |
| `consulta_oab.py`, `consulta_cnsa.py` | Consultas automatizadas a serviços externos. |
| `uploads/` | Arquivos enviados pela aplicação. |

## Requisitos

- Python compatível com as dependências listadas em `requirements.txt`.
- Uma instância Firebird acessível e um banco com o esquema esperado pela aplicação.
- Para as consultas Selenium, navegador e WebDriver compatíveis com a configuração local.

O arquivo `BANCO_CONSTITUERE.FDB` presente neste repositório é um banco local. Em outros ambientes, configure a conexão para apontar ao banco apropriado antes de iniciar o serviço.

## Instalação e execução

No Windows, a partir da pasta do projeto:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

O servidor de desenvolvimento inicia na porta `5000`, ouvindo em todas as interfaces. A aplicação também imprime no terminal as rotas HTTP registradas. Para uso local, acesse a API em `http://localhost:5000`.

Antes de executar em outro ambiente, ajuste em `config.py` os parâmetros `DB_HOST`, `DB_NAME`, `DB_USER` e `DB_PASSWORD` para o Firebird correspondente. As origens permitidas para CORS estão definidas em `main.py` (`ALLOWED_ORIGINS`) e devem incluir o endereço do frontend utilizado.

## Rotas

As rotas são registradas diretamente nos módulos e não há prefixo global de API. Alguns exemplos:

| Método | Caminho | Finalidade |
| --- | --- | --- |
| `POST` | `/login` | Autentica um usuário. |
| `POST` | `/criar_usuarios` | Cria um usuário. |
| `GET` | `/meus_dados` | Consulta os dados do usuário autenticado. |
| `GET` | `/clientes` | Lista clientes. |
| `POST` | `/cadastrar_processo` | Cadastra um processo. |
| `GET` | `/processos` | Lista processos. |
| `GET` | `/pagamentos` | Lista pagamentos. |
| `POST` | `/agendamentos` | Cria um agendamento. |
| `GET` | `/agendamentos` | Lista agendamentos. |

As rotas protegidas esperam as credenciais/tokens definidos pela implementação. Consulte os decoradores e validações nos módulos correspondentes para os parâmetros e formatos JSON de cada operação.

## Socket.IO

Além de HTTP, o servidor aceita conexões Socket.IO. Um cliente pode emitir `entrar_usuario` com `{ "id_usuario": 123 }` para entrar na sala `usuario_123`, ou `sair_usuario` com o mesmo formato para sair. Eventos de conexão e desconexão são registrados pelo servidor.

## Observações de configuração

`main.py` inicia com `debug=True`, apropriado para desenvolvimento. Revise as configurações de execução, credenciais e chave secreta antes de disponibilizar a aplicação em um ambiente compartilhado ou de produção. Não versione credenciais reais.
