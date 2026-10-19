# Instruções para Agentes de IA

Você está trabalhando no repositório UnB-QueimadaFlora (Foco no Incêndio DF), da disciplina Sistemas de Bancos de Dados 2 (FCTE / UnB, 2026.2).

## 1. Diretriz de escrita e comunicação (Obrigatório)

Antes de produzir qualquer texto, documentação ou resposta, leia e siga estritamente a skill [`.agents/skills/humanizer/SKILL.md`](.agents/skills/humanizer/SKILL.md).

- O público é composto exclusivamente por programadores. Seja direto, técnico e preciso.
- Elimine adjetivos vazios (como robusto, crucial, vital, inovador).
- Não repita informações. Em vez de reescrever dados já documentados, apenas aponte o link para o arquivo correspondente quando indispensável.
- Proibido o uso de travessoes (em dashes) e double hyphens. Use ponto, virgula, dois-pontos ou parenteses.
- Sem preâmbulos, conclusões de resumo ou frases de chatbot.

## 2. Onde ler o contexto técnico

Consulte sempre:

- [`docs/entrega/01/README.md`](docs/entrega/01/README.md): documento consolidado da Entrega 1 (pergunta de gestão, modelo espacial, histórico e reprodução).
- [`docs/adr/01-adotar-postgresql-com-postgis-camada-gold.md`](docs/adr/01-adotar-postgresql-com-postgis-camada-gold.md): decisão de arquitetura da camada Gold.
- [`docs/glossario.md`](docs/glossario.md): glossário técnico.

## 3. Regras inegociáveis de código e modelagem

1. PostgreSQL com PostGIS.
2. Colunas de geometria sempre com SRID 31983, índice GiST e validação `ST_IsValid` (ver `docs/entrega/01/README.md#4-esquema-espacial-e-relacional-postgis`).
3. Focos imutáveis, com satélite, flag do satélite de referência e carimbos separados de `data_hora_evento` e `data_hora_ingestao`.
4. Escopo E1: apenas focos do INPE, UCs, APPs e imóveis/reserva do CAR-DF. Flora e vazão estão fora da E1. Hidrografia é opcional.