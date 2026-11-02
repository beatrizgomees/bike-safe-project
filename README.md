# Bike Safe — Backend

Backend do Bike Safe: coleta dados abertos do Recife (acidentes, estações Bike PE, ciclovias e ciclofaixas), cruza tudo, grava no PostgreSQL e expõe uma API para o app/dashboard. A comunicação entre os módulos passa por um broker MQTT (Mosquitto).

```
Sensor Virtual ──MQTT──▶ Broker (Mosquitto) ──▶ Módulo de Processamento ──▶ PostgreSQL ──▶ API ──▶ App / Dashboard
   (SV)                    1883 / 9001                (MP)                                  :8000        ▲
                                                        └──── publica acidentes processados ───MQTT/WS──┘
```

| Módulo | Pasta | O que faz |
|---|---|---|
| Sensor Virtual (SV) | `src/sensor/` | Lê as bases abertas, filtra acidentes com ciclista e publica no broker |
| Broker | `compose.yaml` (Mosquitto) | Middleware de mensagens. Porta 1883 (MQTT) e 9001 (WebSocket) |
| Módulo de Processamento (MP) | `src/processing/` | Geocodifica, cruza com ciclovias/estações, grava no banco e publica para o app |
| Banco | `sql/schema.sql` | PostgreSQL com as tabelas e views |
| API | `src/api/api.py` | API HTTP (porta 8000) lida pelo app |
| Orquestrador | `main.py` | Sobe a infra, o MP e a API e dispara o SV |

---

## 1. Pré-requisitos

| Ferramenta | Versão | Para quê | Como conferir |
|---|---|---|---|
| Python | 3.11 ou superior | Rodar os módulos | `py --version` (Windows) / `python3 --version` |
| Docker Desktop | recente, com Compose v2 | PostgreSQL e Mosquitto | `docker --version` e `docker compose version` |
| Git | qualquer | Clonar o projeto (opcional) | `git --version` |
| Internet | — | Baixar as bases abertas, geocodificar endereços e baixar imagens Docker | — |

Observações:

- **O Docker Desktop precisa estar aberto** (ícone da baleia sem aviso de "starting") antes de rodar o projeto. No Windows ele usa o WSL 2; se o Docker pedir, ative-o.
- **Portas livres no seu PC:** `5432` (PostgreSQL), `1883` e `9001` (Mosquitto) e `8000` (API). Se alguma estiver ocupada, veja a seção de problemas.
- Não é preciso instalar PostgreSQL nem Mosquitto no Windows: ambos rodam em contêiner.

---

## 2. Configuração (uma vez só)

### 2.1 Ambiente virtual e dependências

No PowerShell, dentro da pasta do projeto:

```powershell
cd C:\Users\biahd\Documents\bike-safe-project

py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Se o PowerShell bloquear o script de ativação:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dependências instaladas (`requirements.txt`): `requests`, `python-dotenv`, `psycopg[binary]` (PostgreSQL) e `paho-mqtt` (MQTT).

### 2.2 Arquivo `.env`

Copie o modelo e preencha:

```powershell
copy .env.example .env
```

O que precisa ser definido:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `POSTGRES_PASSWORD` | **sim** | Senha do banco. O Compose se recusa a subir sem ela |
| `POSTGRES_USER` | não | Usuário do banco (padrão `admin`) |
| `POSTGRES_PUBLISH_PORT` | não | Porta do banco no seu PC (padrão `5432`) |
| `MQTT_PUBLISH_PORT` | não | Porta MQTT no seu PC (padrão `1883`) |
| demais (URL base e ids dos recursos de dados abertos, contato do geocodificador) | conforme o `.env.example` | Origem das bases de dados |

> O `.env` contém senha: **não** o envie ao Git (confira se ele está no `.gitignore`).

---

## 3. Como rodar

### Opção A — um comando só (recomendada)

Com o Docker aberto e o ambiente virtual ativado:

```powershell
py main.py
```

O `main.py` faz, em ordem:

1. Verifica o Docker e sobe o **PostgreSQL** e o **Mosquitto** (`docker compose up -d --wait`).
2. Aplica o `sql/schema.sql` no banco.
3. Inicia o **Módulo de Processamento** e a **API** (processos separados).
4. O **Sensor Virtual** publica as bases e transmite os acidentes pelo broker.
5. O MP processa, grava no banco e publica para o app.
6. Imprime o endereço da API/dashboard e fica aguardando. Para encerrar, aperte `Enter` ou `Ctrl+C`.

Na primeira execução o Docker baixa as imagens (alguns minutos) e a geocodificação de endereços é a etapa mais demorada.

### Opção B — cada módulo em um terminal

Útil para depurar. Suba só a infraestrutura:

```powershell
docker compose up -d --wait postgres mosquitto
```

Depois, **cada comando em um terminal próprio**, com o ambiente virtual ativado e na raiz do projeto, nesta ordem:

```powershell
# terminal 1 — API (porta 8000)
py -m src.api.api

# terminal 2 — Módulo de Processamento
py -m src.processing.modulo_processamento

# terminal 3 — Sensor Virtual (publica as bases e os acidentes)
py -m src.sensor.sensor_virtual
```

O MP precisa estar rodando **antes** do SV, porque o broker não guarda as mensagens das bases para quem entrar depois.

Se rodar fora do `main.py`, o schema precisa ter sido aplicado uma vez:

```powershell
docker compose exec -T postgres psql -U admin -d bikesafe < sql/schema.sql
```

(No PowerShell, use `Get-Content sql/schema.sql | docker compose exec -T postgres psql -U admin -d bikesafe`.)

---

## 4. Conferindo se está funcionando

| O quê | Como |
|---|---|
| Contêineres de pé | `docker compose ps` → `postgres` e `mosquitto` como *healthy/running* |
| API respondendo | Abrir <http://localhost:8000/api/resumo> — deve retornar JSON com os totais |
| Acidentes no banco | <http://localhost:8000/api/acidentes?limite=5> |
| Ciclovias / estações | <http://localhost:8000/api/ciclovias> e <http://localhost:8000/api/estacoes> |
| Banco direto | DBeaver/pgAdmin em `localhost:5432`, banco `bikesafe`, usuário e senha do `.env` |
| Mensagens MQTT | MQTT Explorer em `localhost:1883` (assine `bikesafe/#`) |
| WebSocket do broker | porta `9001` (usada pelo app/dashboard no navegador) |

### Rotas da API

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/resumo` | Totais: acidentes com bike, localizados, em ciclovia, perto de estação |
| GET | `/api/acidentes[?limite=N]` | Acidentes processados |
| GET | `/api/acidentes/<protocolo>` | Detalhe de um acidente |
| GET | `/api/ciclovias[?rede=...]` | Trechos de ciclovias e ciclofaixas (geometria) |
| GET | `/api/estacoes` | Estações Bike PE |
| GET | `/api/reportes?dispositivo=<id>` | Reportes feitos por um aparelho |
| POST | `/api/reportes` | Cria um reporte (JSON: `dispositivo`, `tipo`, `lat`, `lon`, `descricao?`, `endereco?`) |

A tabela `reportes` é criada automaticamente quando a API sobe.

### Tópicos MQTT

| Tópico | Quem publica | Conteúdo |
|---|---|---|
| `bikesafe/bases/*` e `bases/fim` | SV | Bases abertas (acidentes, ciclovias, estações) |
| `bikesafe/eventos/acidente` | SV | Um acidente por mensagem |
| `bikesafe/mp/concluido` | MP | Aviso de que as bases foram processadas |
| `bikesafe/app/acidente` | MP | Acidente já processado (para o app/dashboard) |
| `bikesafe/app/ultimos` | MP | Últimos 20 acidentes (retida) |
| `bikesafe/status/<nome>` | cada módulo | Online/offline (Last Will) |

---

## 5. Conectando o app Flutter

O app consulta a API (HTTP) e escuta o broker (WebSocket). O endereço do servidor depende de onde o app roda:

| App rodando em | Endereço do servidor |
|---|---|
| Chrome (web) | `localhost` |
| Emulador Android | `10.0.2.2` (é o seu PC visto de dentro do emulador) |
| Celular de verdade | IP do PC na rede (`ipconfig`), com o PC e o celular na mesma rede e o Firewall liberando 8000 e 9001 |

No Android é preciso `android:usesCleartextTraffic="true"` e a permissão `INTERNET` no `AndroidManifest.xml`, já que a API usa HTTP. O endereço pode ser alterado no app em *Configurações → Avançado → Conexão com o servidor*.

Sem o broker, o app continua funcionando: ele consulta a API/banco a cada 15 s e volta ao tempo real quando o broker retorna.

---

## 6. Parando e limpando

```powershell
# encerra o main.py: Enter ou Ctrl+C no terminal

docker compose stop            # para os contêineres, mantém os dados
docker compose down            # remove os contêineres, mantém os dados (volume pgdata)
docker compose down -v         # remove também o banco — apaga TODOS os dados
```

---

## 7. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `error during connect` / `docker info` falha | Docker Desktop fechado | Abra o Docker Desktop e espere iniciar |
| `defina POSTGRES_PASSWORD no .env` | `.env` ausente ou sem a senha | Crie o `.env` (seção 2.2) |
| `port is already allocated` / porta em uso | 5432, 1883, 9001 ou 8000 ocupadas | Feche o programa que usa a porta, ou mude `POSTGRES_PUBLISH_PORT` / `MQTT_PUBLISH_PORT` no `.env` |
| `ModuleNotFoundError: No module named 'src...'` | Comando rodado fora da raiz, ou arquivo ausente | Rode da raiz do projeto, use `py -m src...` e confira se a pasta tem todos os arquivos do módulo |
| `ModuleNotFoundError: psycopg` / `paho` | Ambiente virtual não ativado | `.\.venv\Scripts\Activate.ps1` e `pip install -r requirements.txt` |
| `password authentication failed` | Senha do `.env` mudou depois de criar o volume | `docker compose down -v` e suba de novo (apaga o banco) |
| `/api/resumo` retorna zeros | Banco ainda vazio: MP não processou | Veja o terminal do MP; rode o SV depois que o MP estiver ativo |
| `/api/ciclovias` dá 404 | `api.py` antigo | Use o `src/api/api.py` mais recente e reinicie a API |
| App não conecta ao broker | Porta 9001 sem WebSocket | O Mosquitto precisa ter `listener 9001` + `protocol websockets` e a porta publicada (`docker compose ps` deve mostrar `0.0.0.0:9001->9001`) |
| Geocodificação lenta ou com falhas | Limite de requisições do serviço de geocodificação | Aguarde; o resultado fica em cache e as próximas execuções são mais rápidas |

---

## 8. Estrutura de pastas

```
bike-safe-project/
├── main.py                  # orquestrador
├── compose.yaml             # PostgreSQL + Mosquitto (+ app opcional)
├── Dockerfile
├── requirements.txt
├── .env / .env.example
├── mosquitto/mosquitto.conf
├── sql/schema.sql           # tabelas e views
├── dashboard/index.html     # dashboard web simples (Leaflet + MQTT)
└── src/
    ├── collector/           # coleta das bases abertas
    ├── sensor/              # Sensor Virtual e filtros
    ├── mqtt/                # config, tópicos e cliente MQTT
    ├── processing/          # Módulo de Processamento e cruzamentos
    ├── database/banco.py    # acesso ao PostgreSQL
    ├── infra/docker_db.py   # sobe Docker, banco e broker
    ├── api/api.py           # API HTTP
    └── utils/               # geo e geocodificador
```
