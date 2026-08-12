# Notebooks-modelo

Modelos prontos para conectar fontes externas, tratar os dados e entregá-los ao Streamlit.

JupyterLab: <http://localhost:8889> (sem token). Esta pasta aparece lá como `notebooks/`.

## Ordem de execução

```
    origem externa                 tratamento                    consumo
  ┌────────────────┐          ┌────────────────┐          ┌────────────────┐
  │ 01 PostgreSQL  │          │                │          │                │
  │ 02 MySQL       │ ──────►  │ 10_tratamento  │ ──────►  │  20_publicar   │
  │ 03 CSV         │          │                │          │   → Streamlit  │
  │ 04 JSON        │          │                │          │                │
  └────────────────┘          └────────────────┘          └────────────────┘
       coleta            limpeza → refinamento              Arrow Flight
```

| Notebook | O que faz |
|---|---|
| `00_ambiente.ipynb` | Confere se MinIO, Nessie e Dremio respondem. **Rode primeiro.** |
| `01_origem_postgres.ipynb` | Lê tabela de um PostgreSQL externo via JDBC → `coleta` |
| `02_origem_mysql.ipynb` | Idem para MySQL/MariaDB |
| `03_origem_csv.ipynb` | Lê CSV da zona de entrada → `coleta` |
| `04_origem_json.ipynb` | Lê JSON (inclusive aninhado) da zona de entrada → `coleta` |
| `10_tratamento.ipynb` | `coleta` → `limpeza` → `refinamento` |
| `20_publicar.ipynb` | Confere a ponte Dremio → Arrow Flight → Streamlit |
| `lakehouse.py` | Módulo comum: sessão Spark, leitura, escrita, perfil |

## As três camadas

| Camada | Pergunta que responde | O que entra |
|---|---|---|
| `coleta` | *o que a origem mandou?* | dado como veio, sem tratamento |
| `limpeza` | *o dado está correto?* | tipos, nulos, duplicatas, validação |
| `refinamento` | *está pronto para uso?* | joins, agregações, regras de negócio |

O Streamlit lê **só do refinamento**. Separar as camadas permite corrigir uma regra de negócio sem
reprocessar a ingestão, e auditar em que ponto um número mudou.

A camada vira namespace no Nessie e prefixo dentro do armazém — `coleta.clientes` fica fisicamente
em `s3a://armazem/coleta/clientes_<uuid>/`.

## O módulo `lakehouse.py`

Evita repetir 25 linhas de configuração do Spark em cada notebook. Lê tudo do ambiente, então
nenhuma senha da stack precisa aparecer em código.

```python
from lakehouse import sessao, ler_jdbc, ler_arquivo, gravar, perfil, listar

spark = sessao("meu-notebook")

df = ler_jdbc(spark, tipo="postgres", host="10.0.0.5", banco="vendas",
              tabela="public.pedidos", usuario="app", senha="...")
df = ler_arquivo(spark, "vendas.csv")          # da zona de entrada
df = ler_arquivo(spark, "dados.json", zona="historico")

perfil(df)                                      # linhas, tipos, nulos, distintos
gravar(df, "coleta.pedidos")                    # tabela Iceberg no catálogo
gravar(df, "refinamento.vendas", particao="ano_mes")
listar(spark)                                   # o que já existe no catálogo
```

## Regras que evitam retrabalho

**Uma sessão Spark por kernel.** `sessao()` reaproveita a existente. Para mudar a lista de pacotes,
reinicie o kernel — pacotes só são resolvidos na criação da sessão.

**A primeira execução baixa os JARs** do Maven Central: 1 a 3 minutos, e exige internet. Depois
ficam em cache no `~/.ivy2` do container.

**Não mexa nas versões fixadas** em `lakehouse.py` sem ler o comentário ao lado. Iceberg 1.10+ grava
no formato v3, que o Dremio 26 não lê com segurança; extensões Nessie 0.107+ exigem Java 17, e esta
imagem do Spark tem Java 11.

**Agregue no notebook, não no dashboard.** O Streamlit deve receber poucas linhas prontas. Assim a
tela responde rápido e a regra fica versionada no lakehouse.

**Não deixe senha de origem no notebook** se ele for versionado. Use variável de ambiente:
`senha = os.environ["SENHA_ORIGEM"]`.

## Colocar arquivos na zona de entrada

Console do MinIO em <http://localhost:9001> → bucket da zona de entrada. Ou deixe em
`seed/minio-data/` antes do primeiro boot da stack.

## Fontes além destas

A leitura por JDBC serve para qualquer banco cujo driver você adicione:

```python
spark = sessao("oracle", pacotes_extra=["com.oracle.database.jdbc:ojdbc11:23.5.0.24.07"])
```

O Dremio, por sua vez, conecta direto em 24 tipos de fonte (Oracle, SQL Server, DB2, Snowflake,
Elasticsearch, entre outras) sem passar pelo Spark — útil quando você só quer consultar, não
materializar. Nesse caso a fonte é criada na UI do Dremio e o Streamlit já a enxerga.
