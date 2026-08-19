"""Arrow -> JSON (`motores/arrow.py`). Data, decimal e nulo sao onde isso costuma quebrar no cliente."""

from __future__ import annotations

import datetime as dt
import math

import pyarrow as pa

from app.motores.arrow import tabela_para_registros


def test_tipos_basicos_viram_json_nativo():
    tabela = pa.table({"n": pa.array([1], pa.int32()), "t": ["a"], "b": [True]})
    assert tabela_para_registros(tabela) == [{"n": 1, "t": "a", "b": True}]


def test_data_e_timestamp_saem_em_iso_8601():
    tabela = pa.table(
        {
            "dia": pa.array([dt.date(2025, 3, 1)], pa.date64()),
            "momento": pa.array([dt.datetime(2025, 3, 1, 14, 30)], pa.timestamp("us")),
        }
    )
    registro = tabela_para_registros(tabela)[0]
    assert registro["dia"] == "2025-03-01"
    assert registro["momento"].startswith("2025-03-01T14:30")


def test_nulo_vira_none():
    tabela = pa.table({"x": pa.array([None, 2], pa.int32())})
    assert tabela_para_registros(tabela) == [{"x": None}, {"x": 2}]


def test_nan_e_infinito_viram_none_em_vez_de_json_invalido():
    # JSON nao tem NaN; deixar passar gera corpo que o navegador recusa.
    tabela = pa.table({"x": pa.array([float("nan"), math.inf, 1.5])})
    assert tabela_para_registros(tabela) == [{"x": None}, {"x": None}, {"x": 1.5}]


def test_decimal_vira_float():
    from decimal import Decimal

    tabela = pa.table({"x": pa.array([Decimal("10.25")], pa.decimal128(10, 2))})
    assert tabela_para_registros(tabela) == [{"x": 10.25}]


def test_tabela_vazia_vira_lista_vazia():
    assert tabela_para_registros(pa.table({"x": pa.array([], pa.int32())})) == []
