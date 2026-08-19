"""Motores — como se consulta cada tecnologia.

Um pacote por fonte de dados. O registro abaixo e o unico lugar que precisa
saber que um motor existe:

1. crie `app/motores/<nome>/` seguindo o contrato de `base.py`;
2. acrescente o modulo em MODULOS;
3. aponte a `Fonte` do conjunto para o novo nome, no catalogo.

Nenhuma rota, nenhum servico e nenhuma validacao mudam por causa disso.
"""

from __future__ import annotations

from app.configuracao import Configuracao
from app.motores import dremio
from app.motores.base import Motor
from app.nucleo import CatalogoInvalido, Fonte

__all__ = ["MODULOS", "Motor", "NOMES", "conferir_fonte", "construir"]

# Acrescente aqui o modulo de cada fonte nova.
MODULOS = (dremio,)

REGISTRO = {modulo.NOME: modulo for modulo in MODULOS}
NOMES = frozenset(REGISTRO)


def conferir_fonte(fonte: Fonte) -> None:
    """Chamado na conferencia do catalogo, no import.

    Cada motor valida o proprio formato de endereco: o Dremio exige caminho no
    space `refinamento`, um motor HTTP exigiria URL, e assim por diante.
    """
    modulo = REGISTRO.get(fonte.motor)
    if modulo is None:
        raise CatalogoInvalido(
            f"motor `{fonte.motor}` nao registrado; conhecidos: {', '.join(sorted(NOMES))}."
        )
    modulo.conferir_fonte(fonte)


def construir(config: Configuracao) -> dict[str, Motor]:
    """Instancia todos os motores registrados. Roda uma vez, na subida."""
    return {nome: modulo.construir(config) for nome, modulo in REGISTRO.items()}
