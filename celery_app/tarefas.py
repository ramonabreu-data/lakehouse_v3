"""Atualizacao automatica do painel — app Celery (worker + beat).

Todo dia as `HORA_ATUALIZACAO` (07:00 por padrao), no fuso **America/Fortaleza**,
a tarefa `painel.atualizar` refaz o caminho inteiro do dado:

1. **Dataset**  — manda o Dremio reler os metadados do parquet da zona de
   entrada, para enxergar um arquivo novo publicado no MinIO.
2. **DataFrame + analise** — reexecuta o notebook de refinamento no Spark, que
   regrava `refinamento.semarh_painel`, `..._fases` e os dois resumos. E o mesmo
   notebook que uma pessoa roda no JupyterLab: nao ha logica duplicada aqui.
3. **Dashboard** — grava o carimbo da atualizacao num arquivo compartilhado com
   o Streamlit. O painel usa esse carimbo como chave de cache, entao o dado novo
   aparece na proxima interacao, sem esperar o TTL de 5 min vencer.

Rodar a mao (util para testar sem esperar o beat):

    docker compose exec celery-worker celery -A celery_app.tarefas call painel.atualizar
    docker compose logs -f celery-worker
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger

log = get_task_logger(__name__)

# Fuso unico de toda a stack: horario do agendamento, carimbo da atualizacao e
# o que o painel exibe. Fortaleza (UTC-3, sem horario de verao).
FUSO = ZoneInfo(os.getenv("TZ", "America/Fortaleza"))
BROKER = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
# Horario da carga diaria, "HH:MM" no fuso acima.
HORA_ATUALIZACAO = os.getenv("HORA_ATUALIZACAO", "07:00")
_hora, _minuto = (int(p) for p in HORA_ATUALIZACAO.split(":"))

DIR_NOTEBOOKS = Path(os.getenv("DIR_NOTEBOOKS", "/workspace/notebooks"))
NOTEBOOK = os.getenv("NOTEBOOK_REFINAMENTO", "semarh_painel/refinamento_selo_ambiental.ipynb")
ARQUIVO_ESTADO = Path(os.getenv("ARQUIVO_ESTADO", "/estado/atualizacao.json"))
VARS_ENV = Path(os.getenv("VARS_ENV", "/opt/painel/vars.env"))
# Fonte bruta no Dremio (o parquet da zona de entrada, promovido como dataset).
FONTE_BRUTA = os.getenv(
    "FONTE_BRUTA_DREMIO",
    'minio.entrada."sermarh_painel"."selo_ambiental_2026.parquet"',
)
TABELA_CONFERE = os.getenv("TABELA_CONFERE", "nessie.refinamento.semarh_painel_fases")

app = Celery("painel", broker=BROKER, backend=BROKER)
app.conf.update(
    timezone=str(FUSO),
    enable_utc=False,
    task_track_started=True,
    # O refinamento leva ~1 min; o teto generoso cobre um Dremio frio.
    task_time_limit=25 * 60,
    task_soft_time_limit=20 * 60,
    # Cada execucao sobe um driver Spark. Reciclar o processo devolve a memoria
    # em vez de acumular ao longo do dia.
    worker_max_tasks_per_child=4,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "atualizar-painel": {
            "task": "painel.atualizar",
            # Uma carga por dia, no horario comercial de abertura. O crontab do
            # Celery usa o `timezone` acima — nao o UTC do container.
            "schedule": crontab(hour=_hora, minute=_minuto),
        }
    },
)


def _conexao_dremio():
    """Conexao Arrow Flight com a conta de servico do painel (vars.env)."""
    from dotenv import load_dotenv
    from dremio_simple_query.connect import DremioConnection, get_token

    if VARS_ENV.exists():
        load_dotenv(VARS_ENV)
    endpoint = os.getenv("DREMIO_ENDPOINT", "dremio:9047")
    token = get_token(
        uri=f"http://{endpoint}/apiv2/login",
        payload={
            "userName": os.getenv("DREMIO_USERNAME"),
            "password": os.getenv("DREMIO_PASSWORD"),
        },
    )
    return DremioConnection(token, f"grpc://{os.getenv('DREMIO_FLIGHT_ENDPOINT', 'dremio:32010')}")


def _gravar_estado(dados: dict) -> None:
    """Escreve o carimbo de forma atomica (o painel le esse arquivo a todo run)."""
    ARQUIVO_ESTADO.parent.mkdir(parents=True, exist_ok=True)
    temporario = ARQUIVO_ESTADO.with_suffix(".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2))
    temporario.replace(ARQUIVO_ESTADO)


def _ler_estado() -> dict:
    try:
        return json.loads(ARQUIVO_ESTADO.read_text())
    except Exception:
        return {}


@app.task(name="painel.atualizar", bind=True)
def atualizar(self, forcar: bool = False) -> dict:
    """Refaz dataset -> tabelas refinadas -> carimbo para o dashboard.

    Publica o progresso em `update_state` para a barra do botao "Atualizar
    agora" do painel acompanhar. O trecho longo (o notebook no Spark) nao tem
    como reportar de dentro, entao a barra avanca pelo tempo decorrido usando a
    duracao da ULTIMA execucao como estimativa — quanto mais roda, melhor a
    estimativa fica.
    """
    inicio = time.monotonic()
    agora = datetime.now(FUSO)
    etapas: dict[str, str] = {}

    def progresso(percentual: int, etapa: str) -> None:
        self.update_state(state="PROGRESS", meta={"percentual": percentual, "etapa": etapa})

    progresso(5, "Preparando a atualização")

    # 1. dataset: o Dremio so enxerga um parquet novo depois do refresh.
    try:
        _conexao_dremio().toPandas(f"ALTER TABLE {FONTE_BRUTA} REFRESH METADATA FORCE UPDATE")
        etapas["dremio_refresh"] = "ok"
    except Exception as erro:  # nao aborta: o refinamento le do MinIO, nao do Dremio
        etapas["dremio_refresh"] = f"falhou: {erro}"[:300]
        log.warning("refresh de metadados falhou (segue mesmo assim): %s", erro)
    progresso(20, "Lendo o dataset da zona de entrada")

    # 2. dataframe + analise: o MESMO notebook que roda no JupyterLab.
    estimativa = float(_ler_estado().get("duracao_s") or 90)
    with tempfile.TemporaryDirectory() as tmp:
        processo = subprocess.Popen(
            ["jupyter", "nbconvert", "--to", "notebook", "--execute",
             "--ExecutePreprocessor.timeout=900",
             "--output", str(Path(tmp) / "execucao.ipynb"), NOTEBOOK],
            cwd=DIR_NOTEBOOKS, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        while processo.poll() is None:
            fracao = min((time.monotonic() - inicio) / max(estimativa, 1), 1.0)
            progresso(20 + int(70 * fracao), "Refinando os dados no Spark")
            time.sleep(2)
        saida, erro_saida = processo.communicate()
        processo.stdout_texto, processo.stderr_texto = saida, erro_saida
    if processo.returncode != 0:
        # As validacoes do notebook viram assert: se o dado chegou inconsistente,
        # a tarefa falha e as tabelas antigas continuam no ar (nada e publicado
        # pela metade). O erro fica no log e no carimbo.
        cauda = (processo.stderr_texto or processo.stdout_texto or "")[-1500:]
        etapas["refinamento"] = "falhou"
        _gravar_estado({**_ler_estado(),
                        "ultima_falha_em": datetime.now(FUSO).isoformat(timespec="seconds"),
                        "erro": cauda, "etapas": etapas})
        raise RuntimeError(f"notebook de refinamento falhou:\n{cauda}")
    etapas["refinamento"] = "ok"

    # 3. confere e carimba — o carimbo e a chave de cache do dashboard.
    progresso(92, "Conferindo as tabelas publicadas")
    linhas = None
    try:
        linhas = int(_conexao_dremio().toPandas(f"SELECT COUNT(*) AS n FROM {TABELA_CONFERE}")["n"][0])
        etapas["conferencia"] = "ok"
    except Exception as erro:
        etapas["conferencia"] = f"falhou: {erro}"[:300]

    # Carimbo com a hora do FIM: e o que o painel mostra como "atualizado em".
    estado = {
        "atualizado_em": datetime.now(FUSO).isoformat(timespec="seconds"),
        "iniciado_em": agora.isoformat(timespec="seconds"),
        "duracao_s": round(time.monotonic() - inicio, 1),
        "linhas": linhas,
        "origem": "manual" if forcar else "automática",
        "hora_agendada": HORA_ATUALIZACAO,
        "fuso": str(FUSO),
        "etapas": etapas,
        "tarefa": self.request.id,
    }
    progresso(100, "Concluído")
    _gravar_estado(estado)
    log.info("painel atualizado: %s", estado)
    return estado
