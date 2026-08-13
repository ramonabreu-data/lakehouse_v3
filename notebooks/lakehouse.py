"""
Helpers da stack de lakehouse.

Importe nos notebooks:

    from lakehouse import sessao, ler_jdbc, ler_arquivo, gravar, ZONAS

O modulo le tudo do ambiente (definido no docker-compose a partir do .env), entao
nenhum notebook precisa carregar senha em codigo.
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------
# Configuracao vinda do ambiente
# --------------------------------------------------------------------------

ZONA_ENTRADA = os.getenv("ZONA_ENTRADA", "entrada")
ZONA_ARMAZEM = os.getenv("ZONA_ARMAZEM", "armazem")
ZONA_HISTORICO = os.getenv("ZONA_HISTORICO", "historico")
ZONAS = {"entrada": ZONA_ENTRADA, "armazem": ZONA_ARMAZEM, "historico": ZONA_HISTORICO}

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
NESSIE_URI = os.getenv("NESSIE_URI", "http://nessie:19120/api/v2")
MINIO_KEY = os.getenv("AWS_ACCESS_KEY_ID", "")
MINIO_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY", "")

# Camadas logicas. Viram namespace no Nessie e prefixo dentro do armazem.
CAMADAS = ("coleta", "limpeza", "refinamento")

# --------------------------------------------------------------------------
# Versoes fixadas — leia antes de mexer
# --------------------------------------------------------------------------
# iceberg 1.9.2 : 1.10+ traz o formato v3, que o Dremio 26 nao le com seguranca.
# nessie  0.106.0: e a ULTIMA compilada para Java 11, que e o Java desta imagem.
#                  0.107+ quebra com UnsupportedClassVersionError.
# Os drivers JDBC entram todos de uma vez: sao pequenos, ficam em cache no
# ~/.ivy2 e evitam ter de recriar a sessao quando o notebook muda de origem.

PACOTES = [
    "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.9.2",
    "org.projectnessie.nessie-integrations:nessie-spark-extensions-3.5_2.12:0.106.0",
    "org.apache.hadoop:hadoop-aws:3.3.4",
    "software.amazon.awssdk:bundle:2.24.8",
    "software.amazon.awssdk:url-connection-client:2.24.8",
    "org.postgresql:postgresql:42.7.4",
    "com.mysql:mysql-connector-j:9.1.0",
]

DRIVERS = {
    "postgres": ("org.postgresql.Driver", "jdbc:postgresql://{host}:{porta}/{banco}", 5432),
    "mysql": ("com.mysql.cj.jdbc.Driver", "jdbc:mysql://{host}:{porta}/{banco}", 3306),
}


# --------------------------------------------------------------------------
# Sessao Spark
# --------------------------------------------------------------------------

def sessao(nome: str = "notebook", pacotes_extra=(), memoria: str = "1g"):
    """Cria (ou reaproveita) a SparkSession com Iceberg + Nessie + MinIO.

    So existe UMA sessao por kernel. Se voce mudar `pacotes_extra`, reinicie o
    kernel — pacotes sao resolvidos apenas na criacao da sessao.
    """
    from pyspark.sql import SparkSession

    pacotes = ",".join([*PACOTES, *pacotes_extra])
    spark = (
        SparkSession.builder.appName(nome)
        .config("spark.jars.packages", pacotes)
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,"
            "org.projectnessie.spark.extensions.NessieSparkSessionExtensions",
        )
        .config("spark.sql.catalog.nessie", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.nessie.catalog-impl", "org.apache.iceberg.nessie.NessieCatalog")
        .config("spark.sql.catalog.nessie.uri", NESSIE_URI)
        .config("spark.sql.catalog.nessie.ref", "main")
        .config("spark.sql.catalog.nessie.authentication.type", "NONE")
        .config("spark.sql.catalog.nessie.warehouse", f"s3a://{ZONA_ARMAZEM}/")
        .config("spark.sql.catalog.nessie.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.nessie.s3.endpoint", MINIO_ENDPOINT)
        .config("spark.sql.catalog.nessie.s3.path-style-access", "true")
        .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.access.key", MINIO_KEY)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET)
        .config("spark.driver.memory", memoria)
        .config("spark.sql.session.timeZone", "America/Fortaleza")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark


# --------------------------------------------------------------------------
# Leitura de origens
# --------------------------------------------------------------------------

def ler_jdbc(spark, tipo, host, banco, tabela, usuario, senha, porta=None, **opcoes):
    """Le uma tabela (ou subconsulta) de um banco relacional externo.

    `tipo`   : "postgres" ou "mysql"
    `tabela` : nome da tabela, ou uma subconsulta entre parenteses com alias:
               "(SELECT * FROM vendas WHERE ano = 2026) AS v"
    """
    if tipo not in DRIVERS:
        raise ValueError(f"tipo deve ser um de {list(DRIVERS)}, recebi {tipo!r}")
    driver, molde, porta_padrao = DRIVERS[tipo]
    url = molde.format(host=host, porta=porta or porta_padrao, banco=banco)

    leitor = (
        spark.read.format("jdbc")
        .option("url", url)
        .option("dbtable", tabela)
        .option("user", usuario)
        .option("password", senha)
        .option("driver", driver)
    )
    for chave, valor in opcoes.items():
        leitor = leitor.option(chave, valor)
    return leitor.load()


def ler_arquivo(spark, arquivo, formato=None, zona=None, **opcoes):
    """Le um arquivo de uma zona do MinIO.

    `arquivo` : nome ou caminho relativo dentro da zona ("vendas.csv",
                "2026/01/vendas.csv"), ou um s3a:// completo.
    `formato` : csv, json, parquet... Se omitido, deduz pela extensao.
    `zona`    : nome da zona. Padrao: a zona de entrada.
    """
    if arquivo.startswith("s3a://"):
        caminho = arquivo
    else:
        caminho = f"s3a://{zona or ZONA_ENTRADA}/{arquivo.lstrip('/')}"

    if formato is None:
        formato = arquivo.rsplit(".", 1)[-1].lower()
        formato = {"jsonl": "json", "ndjson": "json", "txt": "text"}.get(formato, formato)

    padroes = {"csv": {"header": True, "inferSchema": True}}
    return spark.read.format(formato).options(**{**padroes.get(formato, {}), **opcoes}).load(caminho)


# --------------------------------------------------------------------------
# Escrita no catalogo
# --------------------------------------------------------------------------

def gravar(df, tabela, modo="substituir", particao=None):
    """Grava um DataFrame como tabela Iceberg no catalogo Nessie.

    `tabela`   : "camada.nome" (ex.: "coleta.clientes"). O prefixo "nessie." e
                 adicionado sozinho, e o namespace e criado se faltar.
    `modo`     : "substituir" (recria a tabela) ou "acrescentar" (append).
    `particao` : coluna ou lista de colunas para particionar. Use quando a tabela
                 crescer a ponto de a leitura completa ficar cara.

    O caminho fisico sai como s3a://<armazem>/<camada>/<nome>_<uuid>/.
    Mantemos format-version=2 porque o Dremio 26 nao le o v3 com seguranca.
    """
    if "." not in tabela:
        raise ValueError('use "camada.nome", por exemplo "coleta.clientes"')
    camada = tabela.split(".", 1)[0]
    if camada not in CAMADAS:
        print(f"  aviso: camada {camada!r} fora do padrao {CAMADAS}")

    spark = df.sparkSession
    spark.sql(f"CREATE NAMESPACE IF NOT EXISTS nessie.{camada}")

    destino = f"nessie.{tabela}"
    escritor = df.writeTo(destino).tableProperty("format-version", "2")
    if particao:
        colunas = [particao] if isinstance(particao, str) else list(particao)
        escritor = escritor.partitionedBy(*[df[c] for c in colunas])

    if modo == "substituir":
        escritor.createOrReplace()
    elif modo == "acrescentar":
        escritor.append()
    else:
        raise ValueError('modo deve ser "substituir" ou "acrescentar"')

    total = spark.table(destino).count()
    print(f"  {destino}: {total} linhas  ->  s3a://{ZONA_ARMAZEM}/{camada}/")
    _registrar_publicacao(destino, total)
    return destino


def _registrar_publicacao(tabela: str, linhas: int) -> None:
    """Anota "tabela X ficou com N linhas" no manifesto da execucao.

    Quem liga isso e o servico de atualizacao (Celery), apontando
    MANIFESTO_PUBLICACAO para um arquivo da execucao. E assim que a notificacao
    sabe o que foi publicado sem que ninguem precise listar as tabelas na mao —
    qualquer notebook que use `gravar` entra no aviso automaticamente.

    Fora desse contexto (rodando no JupyterLab), a variavel nao existe e a
    funcao nao faz nada.
    """
    caminho = os.getenv("MANIFESTO_PUBLICACAO")
    if not caminho:
        return
    import json
    from datetime import datetime

    try:
        with open(caminho, "a") as arquivo:
            arquivo.write(json.dumps({
                "tabela": tabela,
                "linhas": linhas,
                "quando": datetime.now().astimezone().isoformat(timespec="seconds"),
            }, ensure_ascii=False) + "\n")
    except Exception as erro:  # nunca derruba a gravacao por causa do log
        print(f"  aviso: nao consegui registrar o manifesto ({erro})")


# --------------------------------------------------------------------------
# Inspecao
# --------------------------------------------------------------------------

def listar(spark, camada=None):
    """Lista as tabelas do catalogo, com contagem de linhas."""
    camadas = [camada] if camada else CAMADAS
    achou = False
    for c in camadas:
        try:
            tabelas = [r.tableName for r in spark.sql(f"SHOW TABLES IN nessie.{c}").collect()]
        except Exception:
            continue
        for t in tabelas:
            achou = True
            n = spark.table(f"nessie.{c}.{t}").count()
            print(f"  nessie.{c}.{t:<32} {n:>8} linhas")
    if not achou:
        print("  (nenhuma tabela ainda)")


def perfil(df, amostra=5):
    """Resumo rapido: shape, tipos, nulos e distintos por coluna."""
    from pyspark.sql import functions as F

    total = df.count()
    print(f"  {total} linhas x {len(df.columns)} colunas\n")
    nulos = df.select([F.count(F.when(F.col(c).isNull(), c)).alias(c) for c in df.columns]).collect()[0]
    distintos = df.agg(*[F.countDistinct(F.col(c)).alias(c) for c in df.columns]).collect()[0]
    print(f"  {'coluna':<24} {'tipo':<12} {'nulos':>8} {'distintos':>10}")
    print(f"  {'-'*24} {'-'*12} {'-'*8} {'-'*10}")
    for nome, tipo in df.dtypes:
        print(f"  {nome:<24} {tipo:<12} {nulos[nome]:>8} {distintos[nome]:>10}")
    if amostra:
        print()
        df.show(amostra, truncate=40)
