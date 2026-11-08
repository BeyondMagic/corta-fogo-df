from dagster import Backoff, RetryPolicy

# Falhas transientes (conexao, arquivo em escrita) reexecutam o no com recuo exponencial,
# no maximo 3 reexecucoes. Sem jitter: ha uma unica execucao por vez (max_concurrent_runs: 1),
# entao nao ha concorrencia para desfazer, e o recuo fica previsivel e demonstravel.
POLITICA_RETRY = RetryPolicy(max_retries=3, delay=2, backoff=Backoff.EXPONENTIAL)
