# Mutações no OLTP para prova do CDC

`gerar_mutacoes_oltp.py` executa cinco operações reais no PostgreSQL, cada uma em transação própria:

| # | Operação | Tabela | Alvo |
| --- | --- | --- | --- |
| 1 | INSERT | `foco_calor` | N focos fictícios (`--focos`, padrão 2), satélite de referência, ponto aleatório dentro do DF |
| 2 | UPDATE | `imovel_car` | Retificação de `area_ha` (entre -2% e +2%) e `condicao` em imóvel amostrado (ou `--cod-imovel`) |
| 3 | DELETE | `foco_calor` | Último foco inserido na operação 1 |
| 4 | INSERT e UPDATE | `imovel_car` | Imóvel sentinela `DF-0000000-SENTINELA-CDC`, com a geometria do imóvel de mais vértices. O UPDATE muda `situacao` e zera `condicao` |
| 5 | DELETE | `imovel_car` | O imóvel sentinela |

As operações 4 e 5 cobrem o ciclo completo na tabela que o CDC replica. O INSERT e o UPDATE da operação 4 ficam na mesma transação e chegam ao consumidor no mesmo micro-lote, com o `geom` do UPDATE como `unchanged-toast-datum`. Ao final, o sentinela fica no Delta como exclusão lógica (`operacao_cdc='D'`), com `situacao='PE'`, `condicao` nula e a geometria do INSERT. `--sem-sentinela` pula as duas.

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

- Pela [arquitetura da E2](../../arquitetura.md), o consumidor só processa `public.imovel_car`. Os eventos de `foco_calor` aparecem no slot e são descartados.
- No UPDATE de `imovel_car`, o `test_decoding` emitiu `old-key` com `cod_imovel` e `new-tuple` com `cod_imovel` e `geom` como `unchanged-toast-datum`. Nesse caso a chave vem de `old-key`. Se o `new-tuple` trouxer uma chave diferente da do `old-key`, o UPDATE trocou a chave primária: a antiga vira exclusão lógica e a nova entra como linha própria.
