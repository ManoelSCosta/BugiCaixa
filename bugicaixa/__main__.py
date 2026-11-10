"""Ponto de entrada.

    python3 -m bugicaixa                      abre a tela no navegador
    python3 -m bugicaixa <ferramenta> ...     usa uma ferramenta pela linha de comando
    python3 -m bugicaixa --criar-atalho       cria atalho no menu de aplicativos (Linux)
"""

import argparse
import json
import os
import sys
import urllib.request
import webbrowser

from . import ID_APP, NOME_APP, VERSAO, ferramentas, servidor

PORTA_PADRAO = 8765


def _ja_rodando(porta):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % porta, timeout=1) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == ID_APP
    except Exception:
        return False


def _criar_atalho():
    if not sys.platform.startswith("linux"):
        print("Atalho automático só no Linux. No Windows, crie um atalho para iniciar.bat.")
        return 1
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pasta = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"),
                         "applications")
    os.makedirs(pasta, exist_ok=True)
    destino = os.path.join(pasta, ID_APP + ".desktop")
    with open(destino, "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nType=Application\nName=%s\n"
                "Comment=Caixa de bugigangas: ferramentas locais de apoio (análise de logs e outras)\n"
                "Exec=%s -m bugicaixa\nPath=%s\nIcon=%s\n"
                "Terminal=false\nCategories=Development;Utility;\n"
                % (NOME_APP, sys.executable or "python3", raiz,
                   os.path.join(servidor.PASTA_WEB, "icone.svg")))
    print("Atalho criado: %s" % destino)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and ferramentas.obter(argv[0]) is not None:
        ferramenta = ferramentas.obter(argv[0])
        if not hasattr(ferramenta, "cli"):
            print("A ferramenta %s só funciona pela tela." % argv[0], file=sys.stderr)
            return 1
        return ferramenta.cli(argv[1:])

    p = argparse.ArgumentParser(
        prog="bugicaixa", description="%s %s" % (NOME_APP, VERSAO),
        epilog="Ferramentas pela linha de comando: " + ", ".join(ferramentas.todas()))
    p.add_argument("--porta", type=int, default=PORTA_PADRAO)
    p.add_argument("--sem-navegador", action="store_true", help="não abrir o navegador automaticamente")
    p.add_argument("--criar-atalho", action="store_true", help="criar atalho no menu de aplicativos (Linux)")
    args = p.parse_args(argv)

    if args.criar_atalho:
        return _criar_atalho()

    if _ja_rodando(args.porta):
        url = "http://127.0.0.1:%d/" % args.porta
        print("%s já está aberta em %s" % (NOME_APP, url))
        if not args.sem_navegador:
            webbrowser.open(url)
        return 0

    srv = servidor.criar(args.porta)
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("%s %s rodando em %s" % (NOME_APP, VERSAO, url))
    print("Para encerrar: botão Encerrar na tela, ou Ctrl+C aqui.")
    if not args.sem_navegador:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        srv.estado.limpar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
