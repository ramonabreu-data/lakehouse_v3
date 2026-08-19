# Imagem da API de dados refinados.
#
# Deliberadamente NAO reusa ${PROJETO}/spark-lakehouse:1.0 (a do painel e do
# Spark): aquela passa de 17 GB por causa de torch/tensorflow. A API so precisa
# falar Arrow Flight e servir JSON — sobe em segundos e cabe em ~400 MB.
#
# Construir:  docker compose build api
# Testar:     docker build -f docker/api/Dockerfile --target dev -t plataforma/api:test api
#             docker run --rm plataforma/api:test
#
# Dois estagios com a mesma base: `dev` acrescenta o pytest e roda a suite;
# `producao` fica so com o runtime. O estagio de teste nunca vai para producao.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /servico

COPY requirements.txt /servico/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app /servico/app


# --- estagio de teste ------------------------------------------------------
FROM base AS dev

COPY requirements-dev.txt /servico/requirements-dev.txt
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY pytest.ini /servico/pytest.ini
COPY tests /servico/tests
CMD ["pytest"]


# --- estagio de producao ---------------------------------------------------
FROM base AS producao

# Usuario sem privilegio: a API e o unico servico desta stack exposto a
# aplicacoes de terceiros, entao nao roda como root.
RUN useradd --system --create-home --uid 10001 api
USER api

EXPOSE 8000

# --factory: a aplicacao e montada por criar_app(), que le o ambiente na subida.
# 2 workers dao folga para uma consulta lenta ao Dremio nao travar as demais;
# cada consulta ja roda no threadpool do FastAPI (as rotas sao sincronas).
CMD ["uvicorn", "app.principal:criar_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-server-header"]
