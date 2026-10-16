-- =====================================================================
-- bike-safe-project: cruzamento acidentes com bicicleta x ciclovias x estações
-- PostgreSQL 12+
--
-- Como aplicar (cria o banco se não existir e depois as tabelas):
--     psql -U postgres -f sql/schema.sql
--
-- Pode ser executado várias vezes (IF NOT EXISTS / OR REPLACE).
-- É o mesmo schema que a classe Banco (src/database/banco.py) cria sozinha.
--
-- ATENÇÃO: os comandos \gexec e \connect abaixo são do psql. No pgAdmin
-- (Query Tool) eles não funcionam: crie o banco "bikesafe" pela interface,
-- conecte nele e execute só a parte a partir de "TABELAS".
-- =====================================================================

-- PostgreSQL não tem "CREATE DATABASE IF NOT EXISTS": o SELECT gera o
-- comando só se o banco ainda não existe, e \gexec executa o resultado.
SELECT 'CREATE DATABASE bikesafe'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'bikesafe')\gexec

\connect bikesafe

-- ======================= TABELAS =====================================

-- ======================= DADOS COMPLETOS (bases do portal) ===========
-- Cópia integral das bases coletadas. As tabelas do cruzamento (mais abaixo)
-- guardam só o que foi derivado delas.

-- ---------------------------------------------------------------------
-- acidentes: TODOS os acidentes da base (com e sem bicicleta)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acidentes (
    protocolo                  TEXT PRIMARY KEY,
    data                       TEXT,
    hora                       TEXT,
    natureza                   TEXT,
    situacao                   TEXT,
    bairro                     TEXT,
    endereco                   TEXT,
    numero                     TEXT,
    detalhe_endereco_acidente  TEXT,
    complemento                TEXT,
    bairro_cruzamento          TEXT,
    num_semaforo               TEXT,
    sentido_via                TEXT,
    tipo                       TEXT,
    auto                       DOUBLE PRECISION,
    moto                       DOUBLE PRECISION,
    ciclom                     DOUBLE PRECISION,
    ciclista                   DOUBLE PRECISION,
    pedestre                   DOUBLE PRECISION,
    onibus                     DOUBLE PRECISION,
    caminhao                   DOUBLE PRECISION,
    viatura                    DOUBLE PRECISION,
    outros                     DOUBLE PRECISION,
    vitimas                    DOUBLE PRECISION,
    vitimas_fatais             DOUBLE PRECISION,
    acidente_verificado        TEXT,
    tempo_clima                TEXT,
    situacao_semaforo          TEXT,
    sinalizacao                TEXT,
    condicao_via               TEXT,
    conservacao_via            TEXT,
    ponto_controle             TEXT,
    situacao_placa             TEXT,
    velocidade_max_via         TEXT,
    mao_direcao                TEXT,
    divisao_via1               TEXT,
    divisao_via2               TEXT
);

COMMENT ON TABLE  acidentes IS 'Acidentes de trânsito (dados abertos do Recife), base completa. Sem coordenadas.';
COMMENT ON COLUMN acidentes.ciclista IS 'Ciclistas envolvidos (a base traz "1,0"; convertido para número).';

CREATE INDEX IF NOT EXISTS ix_acidentes_bairro   ON acidentes (bairro);
CREATE INDEX IF NOT EXISTS ix_acidentes_ciclista ON acidentes (ciclista) WHERE ciclista > 0;

-- ---------------------------------------------------------------------
-- malha_cicloviaria: "Detalhes da implantação" (CSV). Recarregada por inteiro.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS malha_cicloviaria (
    id          BIGSERIAL PRIMARY KEY,
    rota        TEXT,
    tipologia   TEXT,
    sentido     TEXT,
    percurso    TEXT,
    bairros     TEXT,
    extensao    DOUBLE PRECISION,
    inauguracao TEXT
);

COMMENT ON TABLE malha_cicloviaria IS 'Malha cicloviária do Recife, detalhes da implantação (um registro por rota).';

-- ---------------------------------------------------------------------
-- ciclovia_trechos: linhas dos GeoJSON (uma linha por trecho), por rede
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ciclovia_trechos (
    id            BIGSERIAL PRIMARY KEY,
    rede          TEXT NOT NULL,
    rota          TEXT,
    bairro        TEXT,
    sentido       TEXT,
    tipo          TEXT,
    extensao_m    DOUBLE PRECISION CHECK (extensao_m >= 0),
    n_pontos      INTEGER,
    geometria     JSONB NOT NULL,
    propriedades  JSONB
);

COMMENT ON TABLE  ciclovia_trechos IS 'Trechos de ciclovia/ciclofaixa dos arquivos GeoJSON do portal.';
COMMENT ON COLUMN ciclovia_trechos.geometria    IS 'GeoJSON LineString: coordinates = [[lon, lat], ...].';
COMMENT ON COLUMN ciclovia_trechos.propriedades IS 'Todas as propriedades originais do arquivo (nomes variam entre as redes).';

CREATE INDEX IF NOT EXISTS ix_trechos_rede ON ciclovia_trechos (rede);

-- ======================= CRUZAMENTO ==================================

-- ---------------------------------------------------------------------
-- acidentes_bike: 1 linha por acidente com ciclista (chave = protocolo)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acidentes_bike (
    protocolo       TEXT PRIMARY KEY,
    data            TEXT,
    hora            TEXT,
    bairro          TEXT,
    endereco        TEXT,
    numero          TEXT,
    natureza        TEXT,
    vitimas         DOUBLE PRECISION CHECK (vitimas >= 0),
    vitimas_fatais  DOUBLE PRECISION CHECK (vitimas_fatais >= 0),
    lat             DOUBLE PRECISION CHECK (lat BETWEEN -90 AND 90),
    lon             DOUBLE PRECISION CHECK (lon BETWEEN -180 AND 180),
    geo_precisao    TEXT NOT NULL
                    CHECK (geo_precisao IN ('endereco', 'rua', 'nao_encontrado')),
    -- lat e lon andam juntos: ou os dois existem, ou nenhum
    CONSTRAINT ck_lat_lon_juntos CHECK ((lat IS NULL) = (lon IS NULL))
);

COMMENT ON TABLE  acidentes_bike IS 'Acidentes de trânsito com ciclista, geocodificados (fonte: dados abertos do Recife).';
COMMENT ON COLUMN acidentes_bike.protocolo    IS 'Protocolo do acidente na base original.';
COMMENT ON COLUMN acidentes_bike.data         IS 'Data como veio na base (texto).';
COMMENT ON COLUMN acidentes_bike.vitimas      IS 'Número de vítimas (a base traz "1,0"; convertido para número).';
COMMENT ON COLUMN acidentes_bike.geo_precisao IS 'endereco = rua+número encontrados; rua = só a rua (posição aproximada); nao_encontrado = sem coordenadas.';

CREATE INDEX IF NOT EXISTS ix_acid_bairro ON acidentes_bike (bairro);
CREATE INDEX IF NOT EXISTS ix_acid_precisao ON acidentes_bike (geo_precisao);

-- ---------------------------------------------------------------------
-- acidente_ciclovia: 1 linha por acidente x rede de ciclovias
-- (rede = 'permanente', 'operacional', ...; novas redes não mudam o schema)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acidente_ciclovia (
    protocolo    TEXT NOT NULL
                 REFERENCES acidentes_bike (protocolo) ON DELETE CASCADE,
    rede         TEXT NOT NULL,
    rota         TEXT,
    tipo         TEXT,
    dist_m       DOUBLE PRECISION CHECK (dist_m >= 0),
    na_ciclovia  BOOLEAN,
    PRIMARY KEY (protocolo, rede)
);

COMMENT ON TABLE  acidente_ciclovia IS 'Ciclovia mais próxima de cada acidente, por rede.';
COMMENT ON COLUMN acidente_ciclovia.rede        IS 'Rede de ciclovias: permanente, operacional, ...';
COMMENT ON COLUMN acidente_ciclovia.dist_m      IS 'Distância em metros até o trecho mais próximo da rede.';
COMMENT ON COLUMN acidente_ciclovia.na_ciclovia IS 'true se dist_m <= raio do cruzamento (padrão 30 m); NULL se o acidente não foi geocodificado.';

CREATE INDEX IF NOT EXISTS ix_acid_ciclo_rede
    ON acidente_ciclovia (rede, na_ciclovia);

-- ---------------------------------------------------------------------
-- vw_acidentes_ciclovias: junção pronta para consulta
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_acidentes_ciclovias AS
SELECT a.*, c.rede, c.rota, c.tipo, c.dist_m, c.na_ciclovia
FROM acidentes_bike a
LEFT JOIN acidente_ciclovia c USING (protocolo);

-- ---------------------------------------------------------------------
-- estacoes_bike: estações de bike compartilhada (Bike PE), com coordenadas
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS estacoes_bike (
    codigo       TEXT PRIMARY KEY,
    nome         TEXT,
    localizacao  TEXT,
    bairro       TEXT,
    capacidade   DOUBLE PRECISION CHECK (capacidade >= 0),
    lat          DOUBLE PRECISION CHECK (lat BETWEEN -90 AND 90),
    lon          DOUBLE PRECISION CHECK (lon BETWEEN -180 AND 180),
    coord_valida BOOLEAN NOT NULL DEFAULT TRUE
);

-- bancos criados com a versão anterior (lat/lon obrigatórios): ajusta sem perder dados
ALTER TABLE estacoes_bike ALTER COLUMN lat DROP NOT NULL;
ALTER TABLE estacoes_bike ALTER COLUMN lon DROP NOT NULL;
ALTER TABLE estacoes_bike ADD COLUMN IF NOT EXISTS coord_valida BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON TABLE  estacoes_bike IS 'Estações de Bikes - Bike PE (fonte: dados abertos do Recife), base completa.';
COMMENT ON COLUMN estacoes_bike.coord_valida IS 'false se lat/lon estão vazios, zerados ou fora do Recife (não entram no cruzamento).';

-- ---------------------------------------------------------------------
-- acidente_estacao: estação de bike mais próxima de cada acidente
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acidente_estacao (
    protocolo         TEXT PRIMARY KEY
                      REFERENCES acidentes_bike (protocolo) ON DELETE CASCADE,
    estacao_codigo    TEXT REFERENCES estacoes_bike (codigo) ON DELETE SET NULL,
    dist_m            DOUBLE PRECISION CHECK (dist_m >= 0),
    no_raio           BOOLEAN,
    estacoes_no_raio  INTEGER CHECK (estacoes_no_raio >= 0)
);

COMMENT ON TABLE  acidente_estacao IS 'Estação mais próxima de cada acidente e quantas existem no raio.';
COMMENT ON COLUMN acidente_estacao.dist_m           IS 'Distância em metros até a estação mais próxima (linha reta).';
COMMENT ON COLUMN acidente_estacao.no_raio          IS 'true se dist_m <= raio de estação do cruzamento (padrão 300 m).';
COMMENT ON COLUMN acidente_estacao.estacoes_no_raio IS 'Quantas estações existem dentro desse raio.';

-- ---------------------------------------------------------------------
-- vw_acidentes_estacoes: acidente + estação mais próxima
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_acidentes_estacoes AS
SELECT a.protocolo, a.data, a.bairro, a.endereco, a.numero, a.lat, a.lon,
       a.geo_precisao,
       e.codigo AS estacao_codigo, e.nome AS estacao_nome,
       e.bairro AS estacao_bairro,
       x.dist_m, x.no_raio, x.estacoes_no_raio
FROM acidentes_bike a
LEFT JOIN acidente_estacao x USING (protocolo)
LEFT JOIN estacoes_bike e ON e.codigo = x.estacao_codigo;

-- ---------------------------------------------------------------------
-- vw_acidentes_bike_completo: todos os campos do acidente + posição geocodificada
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_acidentes_bike_completo AS
SELECT a.*, b.lat, b.lon, b.geo_precisao
FROM acidentes a
JOIN acidentes_bike b USING (protocolo);

-- ---------------------------------------------------------------------
-- Consultas úteis (exemplos)
-- ---------------------------------------------------------------------
-- Quantos acidentes ocorreram em ciclovia, por rede:
--   SELECT rede,
--          COUNT(*) FILTER (WHERE na_ciclovia) AS em_ciclovia,
--          COUNT(*) AS total
--   FROM acidente_ciclovia GROUP BY rede;
--
-- Só posições confiáveis (rua + número), mais próximos primeiro:
--   SELECT protocolo, endereco, rede, rota, dist_m, na_ciclovia
--   FROM vw_acidentes_ciclovias
--   WHERE geo_precisao = 'endereco'
--   ORDER BY dist_m;
--
-- Acidentes a mais de 300 m de qualquer estação (sem apoio de bike por perto):
--   SELECT protocolo, endereco, bairro, estacao_nome, dist_m
--   FROM vw_acidentes_estacoes
--   WHERE no_raio = false
--   ORDER BY dist_m DESC;
--
-- Estações com mais acidentes por perto:
--   SELECT estacao_codigo, estacao_nome, COUNT(*) AS acidentes
--   FROM vw_acidentes_estacoes WHERE no_raio
--   GROUP BY 1, 2 ORDER BY acidentes DESC;