# Mutações no OLTP para prova do CDC

`gerar_mutacoes_oltp.py` executa três operações reais no PostgreSQL, cada uma em transação própria:

| # | Operação | Tabela | Alvo |
| --- | --- | --- | --- |
| 1 | INSERT | `foco_calor` | N focos fictícios (`--focos`, padrão 2), satélite de referência, ponto aleatório dentro do DF |
| 2 | UPDATE | `imovel_car` | Retificação de `area_ha` (entre -2% e +2%) e `condicao` em imóvel amostrado (ou `--cod-imovel`) |
| 3 | DELETE | `foco_calor` | Último foco inserido na operação 1 |

O log de cada operação traz os IDs, o carimbo do banco, o `xid` e o LSN após o `COMMIT`. O `xid` é o mesmo das linhas `BEGIN`/`COMMIT` do `test_decoding`.

`foco_calor` é insert-only (`tg_foco_calor_imutavel`, migração `V3`). O DELETE desativa o trigger e o reativa dentro da mesma transação, então nenhuma outra sessão vê a tabela sem ele.

## Uso

Pré-requisito: banco carregado (`docker compose up`) e `wal_level=logical` para existir slot.

```bash
python scripts/cdc/gerar_mutacoes_oltp.py
python scripts/cdc/gerar_mutacoes_oltp.py --focos 3 --seed 42 --slot cdc_imovel
```

`--slot` faz `pg_logical_slot_peek_changes` ao final e imprime os eventos pendentes sem consumi-los. Conexão: `--db-url`/`DATABASE_URL` ou `DB_HOST`, `DB_PORT` (padrão 5434), `DB_NAME`, `DB_USER`, `DB_PASSWORD`.

## Observações para o consumidor

- Pela [arquitetura da E2](../../arquitetura-E2/arquitetura.md), o consumidor só processa `public.imovel_car`. Os eventos de `foco_calor` aparecem no slot e são descartados.
- No UPDATE de `imovel_car`, o `test_decoding` emitiu `old-key` com `cod_imovel` e `new-tuple` com `cod_imovel` e `geom` como `unchanged-toast-datum`. A chave deve vir de `old-key`.
