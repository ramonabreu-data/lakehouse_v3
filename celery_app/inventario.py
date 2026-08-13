"""Varredura do ambiente — o que existe hoje no Dremio e no MinIO.

A carga diária publica tabelas, mas o ambiente muda por fora também: alguém cria
uma fonte no Dremio, sobe um arquivo num bucket, uma tabela nova aparece no
banco de origem. O inventário tira uma foto de tudo isso a cada execução; a
tarefa compara com a foto anterior e avisa o que entrou ou saiu.

Cobre, numa varredura só:

* **Dremio** — sources, spaces, pastas e todos os datasets (`INFORMATION_SCHEMA`).
  Como PostgreSQL, MongoDB, MinIO e Nessie estão lá como fontes, uma tabela nova
  no banco ou um parquet promovido aparecem aqui sem consulta extra.
* **MinIO** — todos os buckets, com contagem e tamanho. Nos buckets pequenos
  (até `DETALHE_MAX_OBJETOS`) guarda também a lista de arquivos, para dizer *qual*
  arquivo entrou. O `armazem` tem milhares de arquivos internos do Iceberg — ali
  só o total interessa, senão cada commit viraria centenas de "novidades".
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

# Acima disso, guarda so o agregado do bucket (armazem tem milhares de arquivos
# de metadados Iceberg; listar tudo geraria ruido, nao informacao).
DETALHE_MAX_OBJETOS = int(os.getenv("INVENTARIO_DETALHE_MAX", "500"))
# O armazem guarda os arquivos internos do Iceberg (nomes com uuid): listar
# arquivo a arquivo nao diz nada e ainda inunda a mensagem a cada commit. Ali so
# o agregado — "cresceu N arquivos" — tem significado.
BUCKETS_SEM_DETALHE = {os.getenv("ZONA_ARMAZEM", "armazem")}
# Quantos itens citar por categoria na mensagem antes de resumir com "+N".
MAX_CITADOS = 8


def dremio(conexao) -> dict:
    """Esquemas (fontes, spaces, pastas) e datasets visíveis no Dremio."""
    esquemas = conexao.toPandas("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA")
    datasets = conexao.toPandas(
        'SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA."TABLES"'
    )
    return {
        "esquemas": sorted(esquemas["SCHEMA_NAME"].astype(str)),
        "datasets": {
            f"{linha.TABLE_SCHEMA}.{linha.TABLE_NAME}": linha.TABLE_TYPE
            for linha in datasets.itertuples()
        },
    }


def _cliente_s3():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )


def minio() -> dict:
    """Buckets do object store: contagem, bytes e (nos pequenos) os arquivos."""
    s3 = _cliente_s3()
    saida: dict[str, dict] = {}
    for bucket in s3.list_buckets().get("Buckets", []):
        nome = bucket["Name"]
        detalhar = nome not in BUCKETS_SEM_DETALHE
        objetos, bytes_totais, chaves = 0, 0, []
        for pagina in s3.get_paginator("list_objects_v2").paginate(Bucket=nome):
            for item in pagina.get("Contents", []):
                objetos += 1
                bytes_totais += item["Size"]
                if detalhar and objetos <= DETALHE_MAX_OBJETOS:
                    chaves.append(item["Key"])
        saida[nome] = {"objetos": objetos, "bytes": bytes_totais}
        if detalhar and objetos <= DETALHE_MAX_OBJETOS:
            saida[nome]["arquivos"] = sorted(chaves)
    return saida


def bancos() -> dict:
    """Tabelas do PostgreSQL da stack, lidas **direto do banco**.

    Não passa pelo Dremio de propósito: o Dremio guarda o catálogo das fontes em
    cache e só o revalida no ciclo de metadados dele (1h por padrão), então uma
    tabela criada agora demoraria a aparecer. Lendo do `information_schema` do
    próprio Postgres, a varredura enxerga na hora.
    """
    import psycopg2

    conexao = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", ""),
        user=os.getenv("POSTGRES_USER", ""),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        connect_timeout=10,
    )
    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT table_schema, table_name, table_type
                  FROM information_schema.tables
                 WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            """)
            tabelas = {f"{esquema}.{nome}": tipo for esquema, nome, tipo in cursor.fetchall()}
    finally:
        conexao.close()
    return {"postgres": tabelas}


def coletar(conexao) -> dict:
    """Foto completa do ambiente. Falha de uma parte não derruba a outra."""
    foto: dict = {}
    for nome, funcao in (("dremio", lambda: dremio(conexao)),
                         ("minio", minio),
                         ("bancos", bancos)):
        try:
            foto[nome] = funcao()
        except Exception as erro:
            log.warning("varredura de %s falhou: %s", nome, erro)
    return foto


def _lista(itens: list[str]) -> str:
    if len(itens) <= MAX_CITADOS:
        return ", ".join(itens)
    return ", ".join(itens[:MAX_CITADOS]) + f" (+{len(itens) - MAX_CITADOS})"


def diferencas(antes: dict, depois: dict) -> list[str]:
    """O que entrou e o que saiu entre duas fotos, em frases curtas."""
    if not antes or not depois:
        return []
    mudancas: list[str] = []

    # Secao ausente na foto anterior = primeira varredura daquela dimensao.
    # Sem esse cuidado, estrear uma varredura nova anunciaria o ambiente
    # inteiro como "novidade".
    d_antes, d_depois = antes.get("dremio") or {}, depois.get("dremio") or {}
    if not d_antes:
        d_depois = {}
    for rotulo, chave in (("fonte/space", "esquemas"), ("dataset", "datasets")):
        velhos = set(d_antes.get(chave) or [])
        novos = set(d_depois.get(chave) or [])
        if not velhos and not novos:
            continue
        entraram, sairam = sorted(novos - velhos), sorted(velhos - novos)
        if entraram:
            mudancas.append(f"Dremio: +{len(entraram)} {rotulo} — {_lista(entraram)}")
        if sairam:
            mudancas.append(f"Dremio: −{len(sairam)} {rotulo} — {_lista(sairam)}")

    b_antes, b_depois = antes.get("bancos") or {}, depois.get("bancos") or {}
    if not b_antes:
        b_depois = {}
    for banco in sorted(set(b_antes) | set(b_depois)):
        velhas = set(b_antes.get(banco) or {})
        novas = set(b_depois.get(banco) or {})
        entraram, sairam = sorted(novas - velhas), sorted(velhas - novas)
        if entraram:
            mudancas.append(f"{banco}: +{len(entraram)} tabela(s) — {_lista(entraram)}")
        if sairam:
            mudancas.append(f"{banco}: −{len(sairam)} tabela(s) — {_lista(sairam)}")

    m_antes, m_depois = antes.get("minio") or {}, depois.get("minio") or {}
    if not m_antes:
        m_depois = {}
    for bucket in sorted(set(m_antes) | set(m_depois)):
        velho, novo = m_antes.get(bucket), m_depois.get(bucket)
        if velho is None:
            mudancas.append(f"MinIO: bucket novo `{bucket}` ({novo['objetos']} arquivos)")
            continue
        if novo is None:
            mudancas.append(f"MinIO: bucket removido `{bucket}`")
            continue
        arq_velho, arq_novo = set(velho.get("arquivos") or []), set(novo.get("arquivos") or [])
        entraram, sairam = sorted(arq_novo - arq_velho), sorted(arq_velho - arq_novo)
        if entraram:
            mudancas.append(f"MinIO `{bucket}`: +{len(entraram)} arquivo(s) — {_lista(entraram)}")
        if sairam:
            mudancas.append(f"MinIO `{bucket}`: −{len(sairam)} arquivo(s) — {_lista(sairam)}")
        # Buckets grandes (sem lista de arquivos) entram pelo agregado.
        if not entraram and not sairam and velho["objetos"] != novo["objetos"]:
            delta = novo["objetos"] - velho["objetos"]
            mudancas.append(f"MinIO `{bucket}`: {delta:+d} arquivo(s), "
                            f"agora {novo['objetos']} ({novo['bytes'] / 1e6:.1f} MB)")
    return mudancas
