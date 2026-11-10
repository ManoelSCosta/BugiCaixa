"""Pecas compartilhadas entre o servidor e as ferramentas."""

import os
import re
import sys
import unicodedata
from collections import namedtuple

from . import ID_APP

# Arquivo recebido pela tela (ou pela linha de comando) e entregue a ferramenta.
Arquivo = namedtuple("Arquivo", "nome caminho tamanho")


class ErroFerramenta(Exception):
    """Erro com mensagem pronta para ser mostrada ao usuario."""


def pasta_dados():
    """Pasta do usuario onde as ferramentas guardam historico/configuracao."""
    if sys.platform.startswith("win"):
        raiz = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        raiz = os.path.expanduser("~/Library/Application Support")
    else:
        raiz = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    caminho = os.path.join(raiz, ID_APP)
    os.makedirs(caminho, exist_ok=True)
    return caminho


def slug(texto):
    """'Fila de E-mail API' -> 'fila-de-e-mail-api' (seguro para nome de arquivo)."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:60]
