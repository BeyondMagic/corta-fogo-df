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

O comando inicia o PostgreSQL 16 com PostGIS na porta 5434, aplica as migrações do Flyway e executa os contêineres de carga dos dados de satélite e das camadas territoriais.

Para parar os contêineres e remover os volumes de dados:

```bash
docker compose down -v
```

Para conferir o total de registros carregados e ver detalhes de validação, consulte o [guia de reprodução na Entrega 1](docs/entrega/01/README.md#10-como-reproduzir-a-carga).

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
