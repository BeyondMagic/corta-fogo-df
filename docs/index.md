# Corta-Fogo DF

Plataforma de engenharia de dados para cruzamento espacial e temporal de focos de calor, áreas públicas protegidas e imóveis rurais no Distrito Federal.

> Projeto desenvolvido para a disciplina [Sistemas de Bancos de Dados 2 (FCTE / UnB, Turma 03, Semestre 2026.2)](https://unb-bd2.github.io/PlanoEnsino/projeto/).

## Equipe

> Grupo 5

A equipe é formada por sete integrantes, cada um responsável por uma frente de trabalho das entregas distribuídas ao longo do semestre.

| Integrante | [Entrega 1](./entrega/01/README.md) | [Entrega 2](./entrega/02/README.md) | Entrega 3 | Entrega 4 |
| :-------------------------------------------------------------------------------------------- | :------------------------------- | :---------------------------------- | :-------: | :-------: |
| [Cláudio Henrique](https://github.com/BeyondMagic/corta-fogo-df/commits?author=claudiohsc)    | Infraestrutura                   | Infraestrutura e Lakehouse          |     -     |     -     |
| [Elias F.](https://github.com/BeyondMagic/corta-fogo-df/commits?author=EliasOliver21)         | Caracterização e Métricas        | Semântica de Entrega e Benchmarks   |     -     |     -     |
| [Gabriel Fernando](https://github.com/BeyondMagic/corta-fogo-df/commits?author=MMcLovin)      | Ingestão de camadas territoriais | Consumidor CDC e Replicação         |     -     |     -     |
| [Gabriel Souza](https://github.com/BeyondMagic/corta-fogo-df/commits?author=GabrielMS00)      | Coordenação e Pergunta de Gestão | Coordenação e Arquitetura           |     -     |     -     |
| [João V. Farias](https://github.com/BeyondMagic/corta-fogo-df/commits?author=beyondmagic)     | ADR e ingestão de dados de focos | ADR e Ingestão em Lote              |     -     |     -     |
| [Manoel Felipe](https://github.com/BeyondMagic/corta-fogo-df/commits?author=Manoel835)       | Modelagem de Dados               | Modelagem de Tabela Aberta          |     -     |     -     |
| [Samuel Ribeiro](https://github.com/BeyondMagic/corta-fogo-df/commits?author=SamuelRicosta) | Migrações                        | Mutações OLTP e Artefatos           |     -     |     -     |

<!-- AI: vamos fazer uma tabela com o nome completo e matrícula dentro de um snippet (que abre quando aperta) -->

<details>
  <summary>Detalhes da Equipe</summary>
  <div class="content">
    <table>
      <thead>
        <tr>
          <th>Integrante</th>
          <th>Matrícula</th>
          <th>GitHub</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Cláudio Henrique dos Santos Carvalho</td>
          <td>221007958</td>
          <td><a href="https://github.com/claudiohsc">GitHub</a></td>
        </tr>
        <tr>
          <td>Elias Faria de Oliveira</td>
          <td>221007706</td>
          <td><a href="https://github.com/EliasOliver21">GitHub</a></td>
        </tr>
        <tr>
          <td>Gabriel Fernando de Jesus Silva</td>
          <td>222022162</td>
          <td><a href="https://github.com/MMcLovin">GitHub</a></td>
        </tr>
        <tr>
          <td>Gabriel Marques de Souza</td>
          <td>202016266</td>
          <td><a href="https://github.com/GabrielMS00">GitHub</a></td>
        </tr>
        <tr>
          <td>João Victor da Silva Batista de Farias</td>
          <td>221022604</td>
          <td><a href="https://github.com/beyondmagic">GitHub</a></td>
        </tr>
        <tr>
          <td>Manoel Felipe Teixeira Neto</td>
          <td>211041240</td>
          <td><a href="https://github.com/Manoel835">GitHub</a></td>
        </tr>
        <tr>
          <td>Samuel Ribeiro da Costa</td>
          <td>211031486</td>
          <td><a href="https://github.com/SamuelRicosta">GitHub</a></td>
        </tr>
      </tbody>
    </table>
  </div>
</details>

<!--
## Processo

- [Entrega 1](https://unb-bd2.github.io/PlanoEnsino/projeto/e1/);
•⁠ ⁠Samuel Ribeiro da Costa

  </div>

</details>

<!--
## Processo

- [Entrega 1](https://unb-bd2.github.io/PlanoEnsino/projeto/e1/);
- [Entrega 2](https://unb-bd2.github.io/PlanoEnsino/projeto/e2/);
- [Entrega 3](https://unb-bd2.github.io/PlanoEnsino/projeto/e3/);
- [Entrega 4](https://unb-bd2.github.io/PlanoEnsino/projeto/e4/).
-->

### Política de Inteligência Artificial

A equipe utilizou assistentes de IA para auxiliar na escrita de código, e revisão de documentação. A responsibilidade é da equipe por cada frente de trabalho de toda entrega, e a equipe se compromete a seguir as seguintes diretrizes:

- os [Registros de Decisões de Arquitetura](adr/README.md) servem como guia para assistentes de IA, que devem seguir as decisões de arquitetura e os padrões de modelagem do projeto;
- para reduzir baboseiras, informações repetidas, irrelevantes ou incorretas, foi feito um [guia com instruções](https://github.com/BeyondMagic/corta-fogo-df/blob/main/AGENT.md) para assistentes e agentes, que devem ser seguidas rigorosamente para todo prompt;
- o que foi enviado ao repositório, independente de ter sido criado por um humano ou por um assistente de IA, é de responsabilidade do integrante que enviou as alterações.

<!--

## Estrutura

- SGBD principal: PostgreSQL 16 com extensão PostGIS 3.4.
- Projeção padronizada: SIRGAS 2000 / UTM zone 23S (EPSG:31983) em todas as tabelas.
- Total de focos de calor no DF (2015 a 2025): 38.945 registros de 20 satélites distintos.
- Imóveis rurais do CAR-DF: 21.047 feições com 13.499 polígonos de reserva legal.
- Unidades de Conservação e APPs: 84 UCs e 2.234 polígonos de preservação permanente do IBRAM. -->

<!--

## Seções

- **[Entrega 1: Fonte Transacional e Sistema de Origem](entrega/01/README.md):** escopo, pergunta de gestão, modelagem espacial e declaração de histórico.
- **[Decisões de Arquitetura (ADR)](adr/README.md):** registro formal das escolhas de banco, formatos e camadas.
- **[Diretrizes Técnicas](ai/CONTEXT.md):** contexto consolidado e regras para desenvolvedores e assistentes de IA. -->
