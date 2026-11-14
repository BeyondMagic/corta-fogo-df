{#
  Teste de faixa: os valores nao nulos da coluna devem ficar entre minimo e maximo.
#}
{% test entre(model, column_name, minimo, maximo) %}

select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and ({{ column_name }} < {{ minimo }} or {{ column_name }} > {{ maximo }})

{% endtest %}
