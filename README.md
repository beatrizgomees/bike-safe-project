# Middleware Virtual — Sistema Distribuído (Recife)

Middleware virtual que lê e processa 3 bases de dados
abertos da Prefeitura do Recife a partir de arquivos JSON locais (sem
banco de dados, sem servidor, sem chamadas de rede).

## Bases de dados

Os arquivos em `data/` seguem o mesmo formato bruto devolvido pela API do
[Portal de Dados Abertos do Recife](https://dados.recife.pe.gov.br) (CKAN):

### Saída de exemplo

```
--- CONSOLIDADO DASHBOARD ---
Cidade:              RECIFE
Malha cicloviária:   3 rotas (11.6 km)
Estações Bike PE:    3 (53 vagas)
Acidentes:           4 (3 com vítima, 1 fatais)
  com bicicleta:     2
-----------------------------
```


- Cruzar acidentes/ciclovias por bairro (`bairro`/`bairros`).
- Persistir o dashboard processado em um arquivo de saída (JSON/CSV).
- Buscar os dados diretamente da API do portal (versão com `requests`).
