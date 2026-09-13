from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

from .models import Filial, Imposto, TipoFilial
from .logger import log


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.upper().strip()
    prefixes = [
        "MULTICOM ATACADO E VAREJO S/A -",
        "MULTICOM ATACADO E VAREJO -",
        "MULTICOM ATACADO E VAREJO SA -",
        "MULTICOM -",
        "MULTICOM",
    ]
    for p in prefixes:
        if text.startswith(p):
            text = text[len(p):].strip()
    return " ".join(text.split())


class MappingRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._filiais: list[Filial] = []
        self._impostos: dict[str, Imposto] = {}
        self._alias_index: dict[str, Filial] = {}
        self.load()

    def load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._filiais.clear()
        self._alias_index.clear()

        for grupo in data.get("empresas", {}).values():
            for item in grupo.get("filiais", []):
                filial = Filial(
                    codigo=int(item["codigo"]),
                    nome=item["nome"],
                    tipo=TipoFilial(item.get("tipo", "LOJA")),
                    aliases=list(item.get("aliases", [])),
                )
                self._filiais.append(filial)
                self._alias_index[_normalize(filial.nome)] = filial
                for alias in filial.aliases:
                    self._alias_index[_normalize(alias)] = filial

        self._impostos = {}
        for chave, cfg in data.get("impostos", {}).items():
            self._impostos[chave] = Imposto(
                chave=chave,
                descricao=cfg["descricao"],
                especie_totvs=cfg["especie_totvs"],
                especie_descricao=cfg["especie_descricao"],
                pessoa_codigo=int(cfg["pessoa_codigo"]),
                pessoa_nome=cfg["pessoa_nome"],
                observacao_template=cfg["observacao_template"],
                colunas_tipo_folha=list(cfg.get("colunas_tipo_folha", [])),
            )

        log.info("Mapeamento carregado: %d filiais, %d impostos",
                 len(self._filiais), len(self._impostos))

    def reload(self) -> None:
        self.load()

    @property
    def filiais(self) -> list[Filial]:
        return list(self._filiais)

    def filial_por_codigo(self, codigo: int) -> Filial | None:
        """Lookup direto por código. Devolve None se não cadastrada.
        Usado pelo menu contextual da tabela (editar filial de um
        lançamento — build-79)."""
        for f in self._filiais:
            if f.codigo == codigo:
                return f
        return None

    def imposto(self, chave: str) -> Imposto:
        try:
            return self._impostos[chave]
        except KeyError as exc:
            raise KeyError(f"Imposto '{chave}' não configurado em mapeamento.json") from exc

    def resolve_filial(
        self,
        nome_documento: str,
        limiar: int = 80,
    ) -> Optional[Filial]:
        """
        Resolve o nome bruto de uma filial (como veio no relatório) para o
        cadastro TOTVS. Estratégia: exato normalizado → fuzzy match.
        """
        chave = _normalize(nome_documento)
        if not chave:
            return None

        if chave in self._alias_index:
            return self._alias_index[chave]

        candidatos = list(self._alias_index.keys())
        match = process.extractOne(chave, candidatos, scorer=fuzz.WRatio)
        if match and match[1] >= limiar:
            resolvido = self._alias_index[match[0]]
            log.info(
                "Fuzzy match: '%s' → '%s' (código %d, score %.1f)",
                nome_documento, resolvido.nome, resolvido.codigo, match[1],
            )
            return resolvido

        log.warning("Filial não resolvida: '%s' (melhor score: %s)",
                    nome_documento, match[1] if match else "n/a")
        return None
