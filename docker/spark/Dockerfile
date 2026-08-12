# Imagem do Spark/Jupyter da stack, com as bibliotecas de ciencia de dados e ML
# ja instaladas. Sem isto, o `pip install` teria de rodar no entrypoint: atrasa
# todo boot e se perde quando o container e recriado.
#
# Construir:  docker compose build spark
# Reconstruir do zero: docker compose build --no-cache spark
#
# A base ja e grande (~17 GB, torch e tensorflow com CUDA). Esta camada adiciona
# alguns GB. Se espaco for problema, corte o que nao usar do requirements.txt.

FROM alexmerced/spark35nb:latest

# Dependencias de sistema que alguns pacotes pedem para compilar/rodar.
# libgomp1 -> lightgbm e catboost;  libgeos/libproj -> geopandas e folium.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgeos-dev \
        libproj-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Modelo de portugues do spacy. Descomente se for fazer NLP em pt-BR (+ ~20 MB).
# RUN python -m spacy download pt_core_news_sm

# Corpora basicos do NLTK. Descomente se precisar (+ ~30 MB).
# RUN python -m nltk.downloader -d /usr/share/nltk_data stopwords punkt

# Verificacao em tempo de build: se a instalacao quebrou o tensorflow, o torch ou
# o pyspark, a construcao falha aqui em vez de o problema aparecer so no notebook.
RUN python3 -c "\
import numpy, pandas, sklearn, matplotlib, pyspark; \
import tensorflow as tf, torch; \
import shap, optuna, mlflow, catboost, prophet, geopandas; \
assert numpy.__version__.startswith('1.'), f'numpy 2.x quebra TF/torch: {numpy.__version__}'; \
print('OK', 'numpy', numpy.__version__, '| tf', tf.__version__, '| torch', torch.__version__)"

WORKDIR /workspace
