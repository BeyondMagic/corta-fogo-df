---
icon: material/shield-key-outline
---

# :material-shield-key-outline: ETL reverso e controle de acesso

A fila de vistoria calculada no analítico volta ao PostgreSQL operacional, e cada papel que toca nela só tem o privilégio de que precisa. O DDL está na migração [`V10`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/migrations/V10__fila_operacional_e_acesso_minimo.sql).

## ETL reverso

| Item | Definição |
| :--- | :--- |
| Origem | `gold.painel_imoveis_prioritarios` (dbt-duckdb): um imóvel reincidente por linha, na ordem do IPV |
| Destino | `operacional.fila_vistoria` (PostgreSQL), uma linha por imóvel, com `status_vistoria` e `observacao` |
| Quem consome | Quem vistoria (IBRAM, CBMDF): lê a fila e registra o andamento de cada imóvel |
| Quem empurra | Dagster: o asset `operacional/fila_vistoria` roda no `job_transformacao`, logo depois do `dbt build` (todo dia às 03:00) |
| Execução avulsa | `docker compose --profile transformacao run --rm etl_reverso` |

O destino não puxa: o ETL empurra, por *upsert* em uma transação, com o papel `etl_reverso`:

- **Idempotente:** rodar duas vezes deixa a tabela igual (a segunda carga insere 0 linhas).
- **Preserva o que a vistoria escreveu:** `status_vistoria` e `observacao` não entram no `UPDATE` do ETL, então uma nova carga nunca os sobrescreve.
- **Imóvel que sai da fila:** fica com `na_fila = FALSE`, sem apagar a linha, para manter o histórico de vistoria. Volta para a fila se reaparecer.
- **Fila vazia:** o ETL recusa publicar, para não marcar todos os imóveis como fora da fila.
- **Destino fora do ar:** a transação não grava nada pela metade e o Dagster repete o passo (`RetryPolicy`, até 3 reexecuções com recuo exponencial). Não há fila de mensagens: se o PostgreSQL ficar indisponível além disso, a execução falha e a carga seguinte recupera o estado.

A tabela não tem chave estrangeira para `imovel_car`: `load_camadas.py` recarrega o cadastro com `TRUNCATE ... CASCADE`, que apagaria a fila e o histórico de vistoria junto.

## Controle de acesso (privilégio mínimo)

Três papéis sem login. Quem se conecta, ou faz `SET ROLE`, só herda o que o papel permite.

| Papel | Pode | Não pode | Recorte |
| :--- | :--- | :--- | :--- |
| `etl_reverso` | Inserir a fila e atualizar as métricas, `na_fila` e `carga_em` | Alterar `status_vistoria`, `observacao`; tocar em outras tabelas | Coluna |
| `fiscal_vistoria` | Ler a fila ativa e alterar `status_vistoria` e `observacao` | Ver imóvel com cadastro não ativo; alterar métricas; apagar; ler `public.imovel_car` | **Linha** (RLS: `na_fila AND cadastro_ativo`) e coluna |
| `analista_leitura` | Ler `cod_imovel`, `situacao`, `condicao`, `area_ha` e `data_download` de `imovel_car` | Ler a geometria `geom`; `SELECT *`; entrar no schema `operacional` | **Coluna** |

O recorte de coluna em `analista_leitura` tem motivo de LGPD: `cod_imovel` e geometria identificam o imóvel e, por consulta ao portal público do SICAR, o titular. Quem só analisa atributos não precisa do perímetro.

## Demonstração

```bash
docker compose up -d
docker compose --profile transformacao run --rm dbt build
docker compose --profile transformacao --profile demonstracao run --rm demo_acesso
```

O script [`demo_acesso_minimo.py`](https://github.com/BeyondMagic/corta-fogo-df/blob/main/scripts/testes/demo_acesso_minimo.py) exerce cada papel com `SET ROLE` no banco real e reprova (exit 1) se alguma verificação falhar. Resultado da última execução (24/11/2026):

| Verificação | Resultado |
| :--- | :--- |
| ETL reverso | 1.593 imóveis na fila, igual à Gold; segunda carga insere 0 |
| `fiscal_vistoria` | Vê 1.413 de 1.593 (só cadastros ativos); altera `status_vistoria`; negado em `indice_prioridade`, `DELETE` e `public.imovel_car` |
| Nova carga do ETL | `status_vistoria` e `observacao` do fiscal preservados |
| `analista_leitura` | Lê `cod_imovel`, `situacao` e `area_ha`; negado em `geom`, `SELECT *` e schema `operacional` |
| Saída da fila | 5 imóveis marcados `na_fila = FALSE`, linhas mantidas; todos voltam na carga seguinte |

## Limites

- Os papéis não têm login nem senha: o acesso real a produção exigiria criar usuários membros de cada papel e segredos fora do repositório.
- A RLS filtra por situação cadastral, não por Região Administrativa ou por equipe de vistoria.
- O acesso ao warehouse DuckDB (arquivo local) não tem controle por papel: o privilégio mínimo vale para o PostgreSQL operacional.
