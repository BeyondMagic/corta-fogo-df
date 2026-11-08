#!/usr/bin/env python3
"""
Backfill por particao mensal executado de verdade, sem duplicidade e de forma seletiva.

Roda dentro do contêiner do Dagster, contra a tabela Delta real de focos:
  1. Reexecuta 3 particoes (2024-08 a 2024-10) pelo Dagster: nada novo entra.
  2. Remove a particao 2024-09 do Delta (simula perda) e faz backfill so dela.
  3. Confirma que a tabela voltou ao estado original e que as demais particoes nao foram tocadas.

Uso: docker compose --profile orquestracao exec dagster_webserver python /opt/dagster/app/demo_backfill.py
Sai com codigo 1 se alguma verificacao falhar.
"""

import json
import re
import subprocess
import sys
import time
import urllib.request

from deltalake import DeltaTable

DELTA = "/app/data/delta/foco_calor"
WORKSPACE = "/opt/dagster/home/workspace.yaml"
ALVO = ["2024-08", "2024-09", "2024-10"]
PERDIDA = "2024-09"
falhas = []


def checar(ok, descricao):
    print(f"  [{'OK' if ok else 'FALHA'}] {descricao}")
    if not ok:
        falhas.append(descricao)


def contagens():
    df = DeltaTable(DELTA).to_pandas()[["ano", "mes", "id_foco"]]
    por = df.groupby(["ano", "mes"]).size()
    return {f"{a}-{m}": int(n) for (a, m), n in por.items()}, len(df), df["id_foco"].nunique()


def graphql(consulta):
    req = urllib.request.Request(
        "http://localhost:3000/graphql", json.dumps({"query": consulta}).encode(), {"content-type": "application/json"}
    )
    return json.load(urllib.request.urlopen(req))["data"]


def backfill(particoes):
    saida = subprocess.run(
        ["dagster", "job", "backfill", "-j", "job_lote_mensal", "-w", WORKSPACE,
         "--partitions", ",".join(f"{p}-01" for p in particoes), "--noprompt"],
        capture_output=True, text=True,
    )
    achado = re.search(r"backfill job `(\w+)`", saida.stdout + saida.stderr)
    if not achado:
        raise SystemExit(f"Nao foi possivel lancar o backfill:\n{saida.stdout}\n{saida.stderr}")
    backfill_id = achado.group(1)
    consulta = (
        '{ runsOrError(filter:{tags:[{key:"dagster/backfill", value:"%s"}]}, limit: 50)'
        "{ ... on Runs { results { status } } } }" % backfill_id
    )
    fim = time.time() + 300
    while time.time() < fim:
        status = [r["status"] for r in graphql(consulta)["runsOrError"]["results"]]
        if len(status) == len(particoes) and all(s in ("SUCCESS", "FAILURE", "CANCELED") for s in status):
            return backfill_id, status
        time.sleep(4)
    raise SystemExit("Tempo esgotado esperando o backfill.")


def main():
    antes, total, distintos = contagens()
    print(f"Estado inicial: {total} linhas em {len(antes)} particoes; alvo do backfill: {ALVO}")

    print("1. Backfill de 3 particoes sem perda de dados")
    bid, status = backfill(ALVO)
    apos, total1, distintos1 = contagens()
    print(f"   backfill {bid}: {status}")
    checar(all(s == "SUCCESS" for s in status), "as 3 execucoes terminaram com sucesso")
    checar(total1 == total, f"total inalterado: {total1} linhas (nenhuma duplicata inserida)")
    checar(apos == antes, "contagem de todas as particoes inalterada")

    print(f"2. Perda simulada da particao {PERDIDA} e backfill so dela")
    ano, mes = PERDIDA.split("-")
    removidas = DeltaTable(DELTA).delete(f"ano = '{ano}' AND mes = '{mes}'")["num_deleted_rows"]
    perdido, total2, _ = contagens()
    print(f"   {removidas} linhas removidas; tabela com {total2} linhas")
    checar(PERDIDA not in perdido and total2 == total - removidas, "particao removida do Delta")
    bid, status = backfill([PERDIDA])
    final, total3, distintos3 = contagens()
    print(f"   backfill {bid}: {status}")

    print("3. Efeito nos dados")
    checar(status == ["SUCCESS"], "backfill da particao terminou com sucesso")
    checar(total3 == total and distintos3 == total, f"tabela restaurada: {total3} linhas, todas com id_foco unico")
    checar(final[PERDIDA] == antes[PERDIDA], f"particao {PERDIDA} restaurada ({final[PERDIDA]} linhas)")
    checar(final == antes, "as outras 131 particoes ficaram identicas as do inicio (reprocessamento seletivo)")

    print("Backfill demonstrado sem falhas." if not falhas else f"{len(falhas)} verificacao(oes) falharam.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
