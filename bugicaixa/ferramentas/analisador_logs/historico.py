"""Guarda o resultado da analise anterior de cada sistema, para comparacao.

Um JSON por sistema na pasta de dados do usuario. Reanalisar exatamente os
mesmos arquivos nao "gasta" a comparacao: a base continua sendo a analise
anterior a eles.
"""

import hashlib
import json
import os
from datetime import datetime

from ...base import pasta_dados, slug


def _pasta():
    caminho = os.path.join(pasta_dados(), "analisador-logs")
    os.makedirs(caminho, exist_ok=True)
    return caminho


def _caminho(sistema):
    return os.path.join(_pasta(), slug(sistema) + ".json")


def sistemas_conhecidos():
    nomes = []
    for arq in sorted(os.listdir(_pasta())):
        if arq.endswith(".json"):
            try:
                with open(os.path.join(_pasta(), arq), "r", encoding="utf-8") as f:
                    nomes.append(json.load(f).get("sistema") or arq[:-5])
            except (OSError, ValueError):
                continue
    return nomes


def identidade_da_entrada(analise):
    h = hashlib.sha1()
    for nome, tamanho, eventos in sorted(analise.arquivos):
        h.update(("%s|%d|%d;" % (nome, tamanho, eventos)).encode("utf-8"))
    h.update(("%s|%s" % (analise.inicio, analise.fim)).encode("utf-8"))
    return h.hexdigest()


def comparar_e_gravar(sistema, analise):
    """Retorna a base de comparacao ({"gerado_em", "grupos"}) ou None, e grava
    a analise atual como base da proxima."""
    caminho = _caminho(sistema)
    estado = {}
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                estado = json.load(f)
        except (OSError, ValueError):
            estado = {}
    atual = {
        "identidade": identidade_da_entrada(analise),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "arquivos": [a[0] for a in analise.arquivos],
        "grupos": analise.contagens(),
    }
    ultimo = estado.get("atual")
    if ultimo and ultimo.get("identidade") == atual["identidade"]:
        base = estado.get("anterior")
        atual["gerado_em"] = ultimo.get("gerado_em", atual["gerado_em"])
    else:
        base = ultimo
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump({"sistema": sistema, "atual": atual, "anterior": base},
                  f, ensure_ascii=False, indent=1)
    return base
