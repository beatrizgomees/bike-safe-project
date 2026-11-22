# Bike Safe

Sistema distribuído que transforma os **dados abertos de acidentes de trânsito do Recife** em informação útil para o ciclista. Cada acidente com bicicleta é localizado no mapa e cruzado com a **malha cicloviária** (ciclovias e ciclofaixas) e com as **estações de bicicleta compartilhada**. O resultado chega a um **aplicativo web**, que roda no navegador, em tempo real.

## Sobre o projeto

**Problema.** A Prefeitura do Recife publica os acidentes de trânsito, a malha cicloviária e as estações de bicicleta em bases separadas. Nenhuma delas responde perguntas simples para quem pedala: onde os acidentes com ciclistas acontecem? Ocorrem dentro ou fora da ciclovia? Há algum perto de mim?

**Objetivo.** Juntar essas bases, enriquecer cada acidente com a sua relação com a infraestrutura cicloviária e apresentar isso ao ciclista, como parte de uma estratégia de conscientização para apoiar a escolha de rotas.

**O que o sistema faz:**

- Seleciona, nas bases abertas, os acidentes que envolvem ciclistas.
- Localiza cada acidente (pela coordenada da base ou pelo endereço) e mede a distância até a ciclovia ou ciclofaixa mais próxima (**"na ciclovia" = até 30 m**) e até a estação de bicicleta mais próxima (**entorno de 300 m**).
- Grava os resultados em um banco de dados e os entrega ao app em tempo real.
- No app, o usuário vê:
  - um resumo com os totais e a proporção de acidentes em ciclovia;
  - um mapa com os acidentes agrupados, as ciclovias, as ciclofaixas e as estações, com filtros por camada;
  - o detalhe de cada acidente;
  - a estação mais próxima de onde ele está e os acidentes ao redor dela.
- O usuário também **reporta ocorrências** (colisão, queda, buraco, alagamento e outras), com a localização e o endereço preenchidos automaticamente.
- Se o canal de tempo real cair, o app **continua funcionando**: passa a consultar a API periodicamente e volta ao tempo real quando a conexão retorna.

### Arquitetura

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
                 bases abertas do Recife
                          │
                          ▼
┌────────────────┐  MQTT  ┌──────────────┐  MQTT  ┌──────────────────────────┐
│ Sensor Virtual │ ─────▶ │  Middleware  │ ─────▶ │ Módulo de Processamento  │
│      (SV)      │        │ (Mosquitto)  │ ◀───── │          (MP)            │
└────────────────┘        └──────┬───────┘        └────────────┬─────────────┘
                                 │ tempo real                  │ grava
                                 ▼                             ▼
                        ┌─────────────────┐   HTTP   ┌───────────┐   SQL   ┌────────────┐
                        │  Aplicação web  │ ◀──────▶ │    API    │ ◀─────▶ │ PostgreSQL │
                        │ (Flutter, Chrome)│ consulta │           │         │            │
                        └─────────────────┘ e reporte└───────────┘         └────────────┘
```

- **Sensor Virtual:** é um sensor de software. Consulta as bases abertas da cidade e publica as bases de referência e os acidentes, um a um, no middleware.
- **Middleware (broker MQTT):** faz a comunicação por publicação e assinatura. Nenhum componente conhece o endereço do outro.
- **Módulo de Processamento:** assina os acidentes, enriquece cada um, grava no banco e publica o resultado para o app.
- **API:** é a única porta de leitura do banco. Atende às consultas do app e recebe os reportes dos usuários.
- **Aplicação web:** recebe os acidentes em tempo real (MQTT sobre WebSocket) e consulta o histórico pela API (HTTP).

## Tecnologias

### Backend

| Tecnologia | Papel no projeto |
|---|---|
| **Python 3.11+** | Linguagem do Sensor Virtual, do Módulo de Processamento e da API, com orientação a objetos |
| **MQTT 3.1.1** | Protocolo de mensagens por publicação e assinatura, com QoS 1 (entrega pelo menos uma vez) |
| **Eclipse Mosquitto** | Broker MQTT (middleware), em contêiner: porta 1883 (TCP, módulos Python) e 9001 (WebSocket, app no navegador) |
| **paho-mqtt** | Cliente MQTT dos módulos em Python |
| **PostgreSQL** | Banco de dados relacional, em contêiner |
| **psycopg** (`psycopg[binary]`) | Acesso ao PostgreSQL a partir do Python |
| **http.server** (biblioteca padrão) | Servidor da API HTTP, com respostas em JSON |
| **Nominatim (OpenStreetMap)** | Conversão de endereço em coordenada (geocodificação), com cache em disco |
| **requests**, **python-dotenv** | Download das bases abertas e leitura do `.env` |
| **Docker / Docker Compose** | Sobem o PostgreSQL e o Mosquitto |

### Aplicação web

| Tecnologia | Papel no projeto |
|---|---|
| **Flutter / Dart** | Aplicação executada no navegador |
| **flutter_map** + **latlong2** | Mapa (tiles do OpenStreetMap), camadas e cálculo de distâncias |
| **mqtt_client** | Recebe os acidentes em tempo real pelo broker, por WebSocket |
| **http** | Consultas e envio de reportes para a API |
| **geolocator** | Localização do usuário (estação mais próxima e local do reporte) |
| **shared_preferences** | Guarda sessão, servidor, tema e preferências no navegador |
| **Nominatim (geocodificação reversa)** | Converte a localização do reporte em rua, bairro e CEP |

### Paradigma de comunicação

O sistema é **híbrido**:
- **Publicação e assinatura (MQTT)** para os eventos, que formam um fluxo contínuo e chegam a vários receptores.
- **Requisição e resposta (HTTP/REST)** para as consultas e os reportes, que são operações pontuais e precisam de resposta imediata.

## Estrutura de pastas

```
bike-safe-project/
├── main.py                    # orquestrador: sobe a infra, o MP e a API e dispara o SV
├── compose.yaml               # PostgreSQL + Mosquitto
├── dockerfile
├── requirements.txt           # dependências Python
├── .env.example               # modelo das variáveis de ambiente (copiar para .env)
├── .gitignore / .dockerignore
├── src/
│   ├── collector/             # coleta das bases abertas
│   │   ├── base_collector.py
│   │   ├── acidentes_collector.py
│   │   ├── ciclovias_collector.py
│   │   ├── estacoes_collector.py
│   │   ├── geojson_collector.py
│   │   └── rotas_collector.py
│   ├── sensor/                # Sensor Virtual
│   │   ├── sensor_virtual.py
│   │   └── filtros.py         # seleção dos acidentes com ciclista
│   ├── mqtt/                  # cliente MQTT, configuração e tópicos
│   │   ├── cliente.py
│   │   ├── config.py
│   │   └── topicos.py
│   ├── processing/            # Módulo de Processamento
│   │   ├── modulo_processamento.py
│   │   ├── acidentes_ciclovias.py   # cruzamento com ciclovias e estações
│   │   └── fontes_memoria.py        # bases de referência em memória
│   ├── database/
│   │   └── banco.py           # acesso ao PostgreSQL
│   ├── api/
│   │   ├── api.py             # API HTTP
│   │   └── auth.py            # cadastro e login
│   ├── infra/
│   │   └── docker_db.py       # sobe o Docker, aplica o schema e espera o broker
│   └── utils/
│       └── init.sql           # schema do banco (tabelas e views)
└── app/                       # aplicação web (Flutter)
    ├── pubspec.yaml
    ├── web/
    └── lib/
        ├── main.dart                  # entrada: login ou app
        ├── config.dart                # servidor, sessão e preferências
        ├── api_service.dart           # chamadas à API
        ├── reportes_api.dart          # listar e enviar reportes
        ├── mqtt_service.dart          # tempo real e modo offline
        ├── mqtt_factory*.dart         # cliente MQTT por WebSocket no navegador
        ├── dashboard_controller.dart  # estado do app (histórico + tempo real)
        ├── models/                    # acidente, estação, resumo, reporte
        ├── location/                  # localização do usuário e endereço
        ├── view_controllers/          # lógica das telas de login e reporte
        ├── components/                # partes reutilizáveis (lista, detalhe etc.)
        └── telas/                     # home, mapa, reportados, reportar, ajustes, login
```

## Como rodar

### Pré-requisitos

| Ferramenta | Para quê | Como conferir |
|---|---|---|
| Git | Clonar o projeto | `git --version` |
| Python 3.11 ou superior | Backend | `py --version` (Windows) ou `python3 --version` |
| Docker Desktop (com Compose v2) | PostgreSQL e Mosquitto | `docker --version` e `docker compose version` |
| Flutter 3.22 ou superior | Aplicação web | `flutter --version` |
| Google Chrome | Executar o app | `flutter devices` deve listar **Chrome** |
| Internet | Baixar as bases, geocodificar e baixar os tiles do mapa | — |

O **Docker Desktop precisa estar aberto** antes de rodar o backend. As portas **5432** (PostgreSQL), **1883** (MQTT), **9001** (MQTT sobre WebSocket) e **8000** (API) precisam estar livres.

O app depende do backend (até o login passa pela API), então a ordem é: **clonar → preparar o backend → subir o backend → rodar o app**.

### 0. Clonar o projeto

```powershell
git clone <url-do-repositorio>
cd bike-safe-project
```

### 1. Backend

**Configuração (uma vez só)**, no PowerShell, na raiz do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

copy .env.example .env
```

Abra o `.env` e defina pelo menos a senha do banco, sem espaços e sem aspas:

```
POSTGRES_PASSWORD=uma_senha_qualquer
```

Se o PowerShell bloquear a ativação do ambiente virtual, rode `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**Execução.** Com o Docker aberto e o ambiente virtual ativado:

```powershell
python main.py
```

**Deixe esse terminal aberto** enquanto usa o app.

O `main.py` faz, em ordem:
1. Sobe o PostgreSQL e o Mosquitto.
2. Aplica o schema.
3. Inicia o Módulo de Processamento e a API, cada um em seu processo.
4. Dispara o Sensor Virtual, que publica as bases e transmite os acidentes.

Na primeira vez, o Docker baixa as imagens e a geocodificação dos endereços demora mais.

Para rodar cada componente separado, útil para depurar, use um terminal para cada um, na raiz do projeto:

```powershell
python -m src.api.api
python -m src.processing.modulo_processamento
python -m src.sensor.sensor_virtual   # por último: o MP precisa estar rodando antes
```

**Conferindo:**

| O quê | Como |
|---|---|
| Contêineres | `docker compose ps`: `postgres` e `mosquitto` como *healthy* |
| API | <http://localhost:8000/api/resumo> deve devolver um JSON com os totais |
| Acidentes | <http://localhost:8000/api/acidentes?limite=5> |
| Mensagens MQTT | MQTT Explorer em `localhost:1883`, assinando `bikesafe/#` |

**Parando:** `Enter` ou `Ctrl+C` no terminal do `main.py`, depois `docker compose stop`. O comando `docker compose down -v` também apaga o banco.

### 2. Aplicação web (front)

O navegador não permite conexão TCP direta, só HTTP e WebSocket. Por isso, o app fala com o broker por **MQTT sobre WebSocket, na porta 9001**, e com a API por HTTP, na porta 8000. O Mosquitto já precisa estar com os dois ouvintes, o que o `compose.yaml` do projeto configura:

```
listener 1883
listener 9001
protocol websockets
```

**Passo 1. Abrir outro terminal** (o do backend continua rodando) e entrar na pasta do app:

```powershell
cd bike-safe-project\app
```

**Passo 2. Instalar as dependências** (só na primeira vez, ou quando o `pubspec.yaml` mudar):

```powershell
flutter pub get
```

**Passo 3. Executar no Chrome:**

```powershell
flutter run -d chrome
```

O Chrome abre com o app.

**Passo 4. Configurar o servidor e entrar.** Na tela de login, toque em **Servidor** e preencha:

| Campo | Valor |
|---|---|
| Endereço | `localhost` |
| Porta da API | `8000` |

Depois, toque em **Criar conta** no primeiro acesso, ou em **Entrar** se já tiver conta.

**Conferindo:**

| O quê | Como deve estar |
|---|---|
| Home | Mostra os totais e os últimos acidentes |
| Etiqueta no topo | **"Ao vivo"**: o tempo real pelo WebSocket está funcionando |
| Mapa | Acidentes, ciclovias e ciclofaixas aparecem, com filtros por camada |
| Localização | O Chrome pede permissão ao usar "Usar minha localização" ou ao reportar |

**Encerrando:** aperte `q` no terminal do `flutter run`. Da próxima vez, basta subir o backend (`python main.py`) e rodar `flutter run -d chrome` na pasta `app/`.

Para gerar uma versão para publicar, rode `flutter build web`. Os arquivos saem em `app/build/web/`. Fora do `localhost`, o site precisa de `https` (para a localização) e o broker de WebSocket seguro (`wss`).

## API

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/resumo` | Totais: acidentes com bicicleta, localizados, em ciclovia e com estação no entorno |
| GET | `/api/acidentes?limite=N` | Acidentes processados |
| GET | `/api/acidentes/<protocolo>` | Detalhe de um acidente |
| GET | `/api/ciclovias` | Trechos de ciclovias e ciclofaixas (geometria) |
| GET | `/api/estacoes` | Estações de bicicleta |
| GET | `/api/reportes?dispositivo=<id>` | Reportes feitos por um aparelho |
| POST | `/api/reportes` | Novo reporte: `dispositivo`, `tipo` (um ou mais, separados por vírgula), `lat`, `lon`, `descricao?`, `endereco?` |
| POST | `/api/auth/registro` | Cria uma conta |
| POST | `/api/auth/login` | Entra e devolve um token |
| GET | `/api/auth/eu` | Confere o token |

Tipos de reporte aceitos: `colisao`, `queda`, `atropelamento`, `quase_acidente`, `buraco`, `alagamento`, `obstrucao`, `iluminacao`, `sinalizacao`, `outro`.

## Tópicos MQTT

Todos os tópicos ficam sob o prefixo `bikesafe/`.

| Tópico | Publica | Assina | Conteúdo |
|---|---|---|---|
| `bases/*` e `bases/fim` | Sensor Virtual | Processamento | Bases de referência e aviso de fim da carga |
| `eventos/acidente` | Sensor Virtual | Processamento | Um acidente por mensagem |
| `mp/concluido` | Processamento | Sensor Virtual | Aviso de que as bases foram processadas |
| `app/acidente` | Processamento | App | Acidente já enriquecido |
| `app/ultimos` | Processamento | App | Os 20 acidentes mais recentes (mensagem retida) |
| `status/<nome>` | Cada módulo | — | `online` ou `offline` (Last Will) |

## Problemas comuns

| Sintoma | Solução |
|---|---|
| `POSTGRES_PASSWORD ... missing a value` | Crie o `.env` na raiz, com `POSTGRES_PASSWORD=...` |
| `port is already allocated` | Feche o que usa a porta, ou mude `POSTGRES_PUBLISH_PORT` ou `MQTT_PUBLISH_PORT` no `.env` |
| `error during connect` | Abra o Docker Desktop e espere iniciar |
| `No module named 'paho'` ou `'psycopg'` | Ative o ambiente virtual e rode `python -m pip install -r requirements.txt` |
| `No module named src....` | Rode os comandos a partir da raiz do projeto, com `python -m src....` |
| App mostra "API indisponível" | Confira se o backend está rodando e se o servidor no app é `localhost`, porta `8000`. Teste <http://localhost:8000/api/resumo> |
| Etiqueta sempre "Offline" | A porta 9001 não está com WebSocket. Confira o `listener 9001` / `protocol websockets` do Mosquitto e se `docker compose ps` mostra `0.0.0.0:9001->9001`. Mesmo assim o app funciona, buscando na API a cada 15 s |
| Erro de CORS no console do navegador (F12) | Use o `src/api/api.py` mais recente e reinicie a API |
| Localização não funciona | Libere a localização no cadeado da barra de endereço do Chrome |
| Mudança no código do app não aparece | Aperte `R` (maiúsculo) no terminal do `flutter run` |
| `MissingPluginException` | Pare o app, rode `flutter clean` e `flutter pub get`, e execute de novo |
