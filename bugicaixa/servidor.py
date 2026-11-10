"""Servidor HTTP local que entrega a tela e executa as ferramentas.

Escuta apenas em 127.0.0.1. Os arquivos escolhidos na tela sao copiados para
uma pasta temporaria, processados e apagados; nada sai da maquina.
"""

import json
import os
import shutil
import tempfile
import threading
import traceback
import uuid
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import ID_APP, NOME_APP, VERSAO, ferramentas
from .base import Arquivo, ErroFerramenta

PASTA_WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
TIPOS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}
MAX_RELATORIOS = 10


class Estado:
    def __init__(self):
        self.pasta_tmp = tempfile.mkdtemp(prefix=ID_APP + "-")
        self.envios = {}                 # id -> Arquivo
        self.relatorios = OrderedDict()  # id -> {"html", "nome_arquivo"}
        self.trava = threading.Lock()

    def limpar(self):
        shutil.rmtree(self.pasta_tmp, ignore_errors=True)


class Manipulador(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "BugiCaixa/" + VERSAO

    def log_message(self, *args):
        pass

    # ---- respostas -------------------------------------------------------

    def _enviar(self, status, corpo, tipo, extras=None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extras or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, dados, status=200):
        self._enviar(status, json.dumps(dados, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8")

    def _erro(self, status, mensagem):
        self._json({"erro": mensagem}, status)

    def _origem_ok(self):
        """So aceita chamadas feitas pela propria tela (bloqueia outros sites
        abertos no navegador tentando falar com este servidor)."""
        porta = self.server.server_address[1]
        validos = {"127.0.0.1:%d" % porta, "localhost:%d" % porta}
        if self.headers.get("Host") not in validos:
            return False
        origem = self.headers.get("Origin")
        return origem is None or origem in {"http://" + v for v in validos}

    def _recusar(self):
        self.close_connection = True
        self._erro(403, "Origem não permitida.")

    # ---- GET -------------------------------------------------------------

    def do_GET(self):
        if not self._origem_ok():
            return self._recusar()
        url = urlsplit(self.path)
        rota = url.path
        est = self.server.estado
        if rota == "/":
            return self._estatico("index.html")
        if rota.startswith("/web/"):
            return self._estatico(rota[5:])
        if rota == "/api/ping":
            return self._json({"app": ID_APP, "versao": VERSAO})
        if rota == "/api/ferramentas":
            return self._json({"app": NOME_APP, "versao": VERSAO, "ferramentas": [
                {"id": f.ID, "nome": f.NOME, "descricao": getattr(f, "DESCRICAO", ""),
                 "campos": f.campos()} for f in ferramentas.todas().values()]})
        if rota.startswith("/api/relatorio/"):
            rel = est.relatorios.get(rota.rsplit("/", 1)[-1])
            if rel is None:
                return self._enviar(404, "Relatório não está mais disponível. Gere novamente."
                                    .encode("utf-8"), "text/plain; charset=utf-8")
            extras = {}
            if "baixar" in parse_qs(url.query):
                extras["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(rel["nome_arquivo"])
            return self._enviar(200, rel["html"].encode("utf-8"), TIPOS[".html"], extras)
        self._erro(404, "Não encontrado.")

    def _estatico(self, nome):
        caminho = os.path.join(PASTA_WEB, os.path.basename(nome))
        tipo = TIPOS.get(os.path.splitext(caminho)[1])
        if tipo is None or not os.path.isfile(caminho):
            return self._erro(404, "Não encontrado.")
        with open(caminho, "rb") as f:
            self._enviar(200, f.read(), tipo)

    # ---- POST ------------------------------------------------------------

    def do_POST(self):
        if not self._origem_ok():
            return self._recusar()
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            tamanho = -1
        if tamanho < 0:
            self.close_connection = True
            return self._erro(400, "Requisição inválida.")
        rota = urlsplit(self.path).path
        if rota == "/api/envio":
            return self._receber_arquivo(tamanho)
        corpo = self.rfile.read(tamanho) if tamanho else b""
        if rota.startswith("/api/executar/"):
            return self._executar(rota.rsplit("/", 1)[-1], corpo)
        if rota == "/api/encerrar":
            self._json({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._erro(404, "Não encontrado.")

    def _receber_arquivo(self, tamanho):
        est = self.server.estado
        nome = os.path.basename(unquote(self.headers.get("X-Nome-Arquivo") or "arquivo")) or "arquivo"
        id_envio = uuid.uuid4().hex
        caminho = os.path.join(est.pasta_tmp, id_envio)
        falta = tamanho
        with open(caminho, "wb") as f:
            while falta > 0:
                bloco = self.rfile.read(min(falta, 1 << 20))
                if not bloco:
                    break
                f.write(bloco)
                falta -= len(bloco)
        if falta:
            os.remove(caminho)
            self.close_connection = True
            return self._erro(400, "Envio interrompido.")
        est.envios[id_envio] = Arquivo(nome, caminho, tamanho)
        self._json({"id": id_envio})

    def _executar(self, id_ferramenta, corpo):
        est = self.server.estado
        ferramenta = ferramentas.obter(id_ferramenta)
        if ferramenta is None:
            return self._erro(404, "Ferramenta desconhecida.")
        try:
            pedido = json.loads(corpo.decode("utf-8") or "{}")
        except ValueError:
            return self._erro(400, "Requisição inválida.")
        valores, usados = {}, []
        for campo in ferramenta.campos():
            bruto = pedido.get(campo["id"])
            if campo["tipo"] == "arquivos":
                ids = [i for i in (bruto or []) if i in est.envios]
                usados += ids
                valores[campo["id"]] = [est.envios[i] for i in ids]
            elif campo["tipo"] == "opcao":
                valores[campo["id"]] = bool(bruto) if bruto is not None else bool(campo.get("padrao"))
            else:
                valores[campo["id"]] = str(bruto) if bruto is not None else campo.get("padrao", "")
        try:
            resultado = ferramenta.executar(valores)
        except ErroFerramenta as ex:
            return self._erro(400, str(ex))
        except Exception as ex:  # falha inesperada: mostra na tela e no terminal
            traceback.print_exc()
            return self._erro(500, "Erro inesperado na ferramenta: %s: %s" % (type(ex).__name__, ex))
        finally:
            for i in usados:
                arq = est.envios.pop(i, None)
                if arq:
                    try:
                        os.remove(arq.caminho)
                    except OSError:
                        pass
        id_rel = uuid.uuid4().hex
        with est.trava:
            est.relatorios[id_rel] = {"html": resultado["html"],
                                      "nome_arquivo": resultado.get("nome_arquivo") or "relatorio.html"}
            while len(est.relatorios) > MAX_RELATORIOS:
                est.relatorios.popitem(last=False)
        self._json({"relatorio": id_rel, "resumo": resultado.get("resumo", ""),
                    "nome_arquivo": est.relatorios[id_rel]["nome_arquivo"]})


def criar(porta):
    """Sobe o servidor na porta pedida; se estiver ocupada, usa uma livre."""
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)
    except OSError:
        srv = ThreadingHTTPServer(("127.0.0.1", 0), Manipulador)
    srv.daemon_threads = True
    srv.estado = Estado()
    return srv
