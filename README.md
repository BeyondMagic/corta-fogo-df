# Corta-Fogo DF

Plataforma de engenharia de dados para cruzamento espacial e temporal de focos de calor, áreas públicas protegidas e imóveis rurais no Distrito Federal.

Projeto desenvolvido para a disciplina Sistemas de Bancos de Dados 2 (FCTE / UnB, 2026.2, Turma 03, Grupo 5).

## Pergunta de gestão

> Quais imóveis rurais do Distrito Federal tiveram focos de calor reincidentes em áreas de reserva legal, de preservação permanente ou a até 1 km de unidades de conservação entre 2015 e 2025?

A pergunta orienta o recorte geográfico no Distrito Federal, a série histórica de 11 anos de focos de calor de satélite e os cruzamentos de sobreposição e proximidade entre a malha fundiária rural e as áreas protegidas.

## Documentação

A documentação detalhada do projeto está disponível na pasta `docs/` e publicada no site:

- [Site da documentação](https://beyondmagic.github.io/corta-fogo-df/)
- [Entrega 1: Fonte Transacional e Sistema de Origem](docs/entrega/01/README.md): escopo da primeira etapa, modelo relacional e espacial, histórico e procedimentos de carga.
- [Esquema da tabela aberta (E2)](docs/modelagem/esquema_tabela_aberta.md): contrato Delta Lake, partição temporal e evolução de esquema.
- [Registros de Decisões de Arquitetura (ADRs)](docs/adr/README.md): justificativas técnicas para escolhas de banco de dados, extensões espaciais e projeção cartográfica.
- [Glossário Técnico](docs/glossario.md): conceitos espaciais, cadastrais e referências bibliográficas.

## Execução local

O ambiente utiliza Docker e Docker Compose.

### Pré-requisitos

- Docker e Docker Compose v2 (comando `docker compose`)
- Conexão de rede ativa para download de camadas públicas do SISDIA/IBRAM

### Como subir os serviços

```bash
docker compose up
```

O comando inicia o PostgreSQL 16 com PostGIS na porta 5434 (com `wal_level=logical`), aplica as migrações do Flyway e executa os serviços abaixo:

| Serviço | O que faz |
| :--- | :--- |
| `load`, `load_camadas` | Carga no PostgreSQL dos focos de calor e das camadas territoriais (UC, APP, imóveis do CAR, reserva legal). |
| `refresh_gold` | Atualiza a camada Gold materializada, depois das duas cargas. |
| `batch_ingest` | Ingestão em lote idempotente dos focos de calor na tabela Delta `foco_calor`, particionada por `ano/mes`. |
| `cdc_consumer` | Depois do `load_camadas`: cria o slot `cdc_imovel`, faz o snapshot de `imovel_car` na tabela Delta e passa a consumir as mudanças do PostgreSQL. |

As tabelas Delta ficam no volume nomeado `lakehouse`. O volume é removido junto com o banco pelo `down -v`, para o Delta nunca sobreviver a um banco recriado (o `MERGE` do `cdc_consumer` ignora eventos com LSN menor que o já gravado).

Para parar os contêineres e remover os volumes de dados:

```bash
docker compose down -v
```

### Verificar o ciclo CDC e a camada analítica

Com o ambiente no ar, o script de mutações executa um INSERT e um DELETE em `foco_calor` e um UPDATE em `imovel_car`, cada um em transação própria (precisa de `pip install psycopg2-binary` no host):

```bash
python scripts/cdc/gerar_mutacoes_oltp.py
```

Em seguida, o serviço `verificar_lakehouse` lê as tabelas Delta direto com DuckDB e compara com o PostgreSQL:

```bash
docker compose run --rm verificar_lakehouse
```

A verificação reprova (exit 1) se houver `id_foco` repetido em `foco_calor` ou se os `cod_imovel` vivos do Delta divergirem dos de `imovel_car` no PostgreSQL. Como o CDC é assíncrono, a comparação é repetida por até 90 segundos antes de reprovar. A saída também informa, sem reprovar, a diferença de contagem de `foco_calor` entre Delta e PostgreSQL, as linhas por partição e os arquivos Parquet físicos.

A tabela `imovel_car` do Delta preserva exclusões como `operacao_cdc='D'` em vez de apagar a linha. As mutações de `foco_calor` não passam pelo CDC: a tabela é insert-only no PostgreSQL e o Delta de `foco_calor` vem do lote.

Para conferir o total de registros carregados no PostgreSQL e ver detalhes de validação, consulte o [guia de reprodução na Entrega 1](docs/entrega/01/README.md#10-como-reproduzir-a-carga).

## Equipe

Grupo 5:

| Integrante | GitHub |
| :--- | :--- |
| Cláudio Henrique | [@claudiohsc](https://github.com/claudiohsc) |
| Elias F. | [@EliasOliver21](https://github.com/EliasOliver21) |
| Gabriel Fernando | [@MMcLovin](https://github.com/MMcLovin) |
| Gabriel Souza | [@GabrielMS00](https://github.com/GabrielMS00) |
| João V. Farias | [@beyondmagic](https://github.com/beyondmagic) |
| Manoel Felipe | [@Manoel835](https://github.com/Manoel835) |
| Samuel Ribeiro | [@SamuelRicosta](https://github.com/SamuelRicosta) |

Matrículas e o histórico de cada membro ao longo das entregas estão na [página da equipe na documentação](docs/index.md).
