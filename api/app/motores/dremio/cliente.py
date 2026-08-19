"""Conversa de rede com o Dremio: login e execucao via Arrow Flight.

So o transporte mora aqui. Quem decide O QUE perguntar e `sql.py`; quem amarra
os dois e o motor em `__init__.py`.

O painel usa o `dremio-simple-query`; aqui a conversa e feita direto no pyarrow.
Sao ~40 linhas e evitam arrastar pandas, polars e duckdb para a imagem da API —
que precisa subir rapido e ficar pequena.

Autenticacao: mesma conta de servico do painel, pela rota /apiv2/login. O token
tem validade; guardamos ate perto do vencimento e renovamos sozinhos. Se o
Dremio reiniciar e invalidar o token no meio do caminho, a consulta e refeita
uma vez com token novo em vez de estourar erro para o cliente.
"""

from __future__ import annotations

import logging
import threading
import time

import httpx
import pyarrow as pa
from pyarrow import flight

registrador = logging.getLogger(__name__)

MARGEM_DE_RENOVACAO = 60      # segundos antes do vencimento
VALIDADE_PADRAO = 8 * 3600    # se o Dremio nao informar `expires`


class ErroDremio(RuntimeError):
    """Falha ao falar com o Dremio. Vira HTTP 502."""


class ClienteDremio:
    def __init__(
        self,
        endpoint: str,
        endpoint_flight: str,
        usuario: str,
        senha: str,
        tempo_limite: float = 60.0,
    ) -> None:
        self.endpoint = endpoint
        self.endpoint_flight = endpoint_flight
        self._usuario = usuario
        self._senha = senha
        self.tempo_limite = tempo_limite
        self._token = ""
        self._vence_em = 0.0
        self._trava = threading.Lock()
        self._cliente_flight: flight.FlightClient | None = None

    # -- autenticacao -------------------------------------------------------

    def _renovar(self) -> None:
        try:
            resposta = httpx.post(
                f"http://{self.endpoint}/apiv2/login",
                json={"userName": self._usuario, "password": self._senha},
                timeout=15.0,
            )
            resposta.raise_for_status()
            corpo = resposta.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ErroDremio("Nao foi possivel autenticar no Dremio.") from exc
        token = corpo.get("token")
        if not token:
            raise ErroDremio("O Dremio nao devolveu token de sessao.")
        vencimento = corpo.get("expires")
        # `expires` vem em milissegundos de epoca quando existe.
        self._vence_em = (
            float(vencimento) / 1000.0 if vencimento else time.time() + VALIDADE_PADRAO
        ) - MARGEM_DE_RENOVACAO
        self._token = token

    def _cabecalhos(self, renovar: bool = False) -> list[tuple[bytes, bytes]]:
        with self._trava:
            if renovar or not self._token or time.time() >= self._vence_em:
                self._renovar()
            return [(b"authorization", f"bearer {self._token}".encode())]

    def _flight(self) -> flight.FlightClient:
        if self._cliente_flight is None:
            self._cliente_flight = flight.FlightClient(f"grpc://{self.endpoint_flight}")
        return self._cliente_flight

    # -- consulta -----------------------------------------------------------

    def _executar(self, sql: str, cabecalhos: list[tuple[bytes, bytes]]) -> pa.Table:
        opcoes = flight.FlightCallOptions(headers=cabecalhos, timeout=self.tempo_limite)
        cliente = self._flight()
        informacao = cliente.get_flight_info(flight.FlightDescriptor.for_command(sql), opcoes)
        return cliente.do_get(informacao.endpoints[0].ticket, opcoes).read_all()

    def consultar(self, sql: str) -> pa.Table:
        try:
            return self._executar(sql, self._cabecalhos())
        except (flight.FlightUnauthenticatedError, flight.FlightUnauthorizedError):
            # Token derrubado (reinicio do Dremio, sessao expirada): uma retentativa.
            registrador.info("Token do Dremio recusado; renovando e repetindo a consulta.")
            return self._executar(sql, self._cabecalhos(renovar=True))
