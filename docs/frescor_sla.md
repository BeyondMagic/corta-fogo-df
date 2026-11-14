---
icon: material/timer-sand
---

# :material-timer-sand: Frescor e SLA da tabela de consumo

**Tabela de consumo:** `gold.painel_imoveis_prioritarios`, a fila de vistoria que responde à pergunta de gestão. É a tabela que o dashboard lê, pelo export `gold.json`.

## O que o SLA promete

| Verificação | Métrica | SLA | Onde é medida |
| :--- | :--- | :--- | :--- |
| **Processamento** | Idade da tabela: `agora - max(gerado_em)`. `gerado_em` é o instante da execução do dbt que gerou a tabela | Até **30 horas** | Warehouse DuckDB |
| **Fonte** | Há quanto tempo existe no lago Delta (`foco_calor` e `imovel_car`) uma linha gravada depois de `gerado_em`, ou seja, um dado que a tabela ainda não processou | Até **30 horas** | Warehouse e lago Delta |

**Por que 30 horas:** o `job_transformacao` do Dagster roda todo dia às 03:00 (America/Sao_Paulo), então a tabela tem no máximo 24 horas quando tudo funciona. As 6 horas a mais são a margem para corrigir uma execução que falhou antes de sair do SLA. O limite é a variável `SLA_FRESCOR_HORAS` do Compose.

**O que fica de fora:** o atraso do próprio INPE e do SICAR. O INPE publica os arquivos anuais com defasagem, e o recorte do SICAR é estático no repositório. Isso não depende do pipeline.

## Como é verificado

`src/pipeline/frescor.py` mede as duas verificações e sai com código 1 se alguma passar do SLA.

```bash
docker compose --profile transformacao run --rm frescor
```

Saída na carga de 14/11/2026:

```text
OK   processamento (gold.painel_imoveis_prioritarios): 0.9 de 30 horas (gerada em 14/11/2026 18:45 UTC)
OK   fonte (delta foco_calor): 0.0 de 30 horas (tudo o que esta no lago ja foi processado)
OK   fonte (delta imovel_car): 0.0 de 30 horas (tudo o que esta no lago ja foi processado)
SLA de frescor cumprido (3 verificacao(oes)).
```

A mesma tabela com o limite reduzido para 0,5 hora (`SLA_FRESCOR_HORAS=0.5`) viola o SLA e o comando sai com código 1:

```text
FORA processamento (gold.painel_imoveis_prioritarios): 1.0 de 0.5 horas (gerada em 14/11/2026 18:45 UTC)
OK   fonte (delta foco_calor): 0.0 de 0.5 horas (tudo o que esta no lago ja foi processado)
OK   fonte (delta imovel_car): 0.0 de 0.5 horas (tudo o que esta no lago ja foi processado)
SLA de frescor VIOLADO (1 de 3 verificacao(oes)).
```

No Dagster, a verificação é o *asset check* `frescor_sla` sobre `painel_imoveis_prioritarios`:

| Onde | Quando |
| :--- | :--- |
| `job_frescor` | De hora em hora (`agenda_frescor`). Acusa o atraso assim que a tabela passa de 30 horas. |
| `job_transformacao` | Depois de cada `dbt build` diário. |

## O que acontece quando o SLA é violado

1. **O check falha no Dagster** e aparece em vermelho no grafo de ativos, na tabela `painel_imoveis_prioritarios`.
2. **O dashboard mostra a data dos dados.** O bloco de resposta exibe quando a Gold foi gerada. Se o retrato exportado tiver mais de 30 horas, o texto diz que é o último retrato, com a idade.
3. **Correção:** ver no Dagster por que o `job_transformacao` falhou, corrigir e rodá-lo manualmente. Depois, regerar o `gold.json` (`docker compose --profile transformacao run --rm exportar_painel`).

## Testes

`scripts/testes/test_frescor.py`: limite exato do SLA (30 horas passa, 30 horas e 1 minuto viola), tabela ausente, dado pendente no lago dentro e fora do prazo, e a medição sobre um DuckDB temporário.
