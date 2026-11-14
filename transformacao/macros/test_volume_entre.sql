{#
  Teste de volume: a contagem de linhas do modelo deve ficar entre minimo e maximo.
  Pega carga parcial, arquivo truncado e duplicacao em massa. Falha devolvendo a contagem.
#}
{% test volume_entre(model, minimo, maximo) %}

select linhas
from (
    select count(*) as linhas
    from {{ model }}
) contagem
where linhas < {{ minimo }}
   or linhas > {{ maximo }}

{% endtest %}
