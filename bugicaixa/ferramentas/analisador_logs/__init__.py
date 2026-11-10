"""Ferramenta: Analisador de Logs."""

import argparse
import glob
import os
import sys
from datetime import datetime

from ...base import Arquivo, ErroFerramenta, slug
from . import historico
from .analise import Analise
from .relatorio import fmt_num, gerar_html

ID = "analisador-logs"
NOME = "Analisador de Logs"
DESCRICAO = ("Lê arquivos de log, agrupa erros e avisos equivalentes e monta um "
             "relatório com as causas mais frequentes.")
ORDEM = 10


def campos():
    return [
        {"id": "arquivos", "tipo": "arquivos", "rotulo": "Arquivos de log", "obrigatorio": True,
         "aceita": ".log,.txt,.out,.json,.gz,text/plain",
         "ajuda": "Um ou mais arquivos (.log, .txt, .gz). Vários arquivos viram um único relatório."},
        {"id": "sistema", "tipo": "texto", "rotulo": "Sistema (opcional)",
         "sugestoes": historico.sistemas_conhecidos(),
         "ajuda": "Nome da aplicação. Informe sempre o mesmo nome para comparar com a análise anterior."},
        {"id": "titulo", "tipo": "texto", "rotulo": "Título do relatório (opcional)"},
        {"id": "comparar", "tipo": "opcao", "padrao": True,
         "rotulo": "Comparar com a análise anterior deste sistema"},
    ]


def executar(valores):
    arquivos = valores.get("arquivos") or []
    if not arquivos:
        raise ErroFerramenta("Selecione pelo menos um arquivo de log.")
    sistema = (valores.get("sistema") or "").strip()
    titulo = (valores.get("titulo") or "").strip()

    analise = Analise()
    for arq in arquivos:
        try:
            analise.adicionar_arquivo(arq.caminho, arq.nome, arq.tamanho)
        except (OSError, EOFError) as ex:
            raise ErroFerramenta("Não foi possível ler %s: %s" % (arq.nome, ex))
    if not analise.eventos:
        raise ErroFerramenta(
            "Nenhum registro de log reconhecido. O analisador espera linhas que comecem "
            "com data e hora (ex.: 2026-01-31 10:15:00 ERROR ...) ou um JSON por linha.")

    base = None
    if sistema and valores.get("comparar", True):
        base = historico.comparar_e_gravar(sistema, analise)

    if not titulo:
        titulo = "Relatório de logs — %s" % (sistema or os.path.splitext(arquivos[0].nome)[0])
    erros = analise.do_nivel("ERROR")
    resumo = "%s registros lidos · %s erros em %s causas · %s avisos" % (
        fmt_num(analise.eventos), fmt_num(sum(g.ocorrencias for _, g in erros)),
        fmt_num(len(erros)), fmt_num(sum(g.ocorrencias for _, g in analise.do_nivel("WARN"))))
    nome_arquivo = "relatorio-logs-%s-%s.html" % (
        slug(sistema or os.path.splitext(arquivos[0].nome)[0]) or "logs",
        datetime.now().strftime("%Y%m%d-%H%M"))
    return {"html": gerar_html(titulo, analise, base), "nome_arquivo": nome_arquivo, "resumo": resumo}


def _expandir(entradas):
    caminhos = []
    for ent in entradas:
        if os.path.isdir(ent):
            for ext in ("*.log", "*.txt", "*.gz"):
                caminhos += sorted(glob.glob(os.path.join(ent, "**", ext), recursive=True))
        else:
            caminhos += sorted(glob.glob(ent)) or [ent]
    vistos, saida = set(), []
    for c in caminhos:
        ap = os.path.abspath(c)
        if ap not in vistos and os.path.isfile(ap):
            vistos.add(ap)
            saida.append(ap)
    return saida


def cli(argv):
    p = argparse.ArgumentParser(prog="bugicaixa %s" % ID, description=DESCRICAO)
    p.add_argument("entradas", nargs="+", help="arquivo(s) ou pasta(s) de log")
    p.add_argument("-o", "--saida", help="arquivo HTML de saída (padrão: nome automático)")
    p.add_argument("--sistema", default="", help="nome do sistema, usado para comparar com a análise anterior")
    p.add_argument("--titulo", default="")
    p.add_argument("--sem-comparacao", action="store_true", help="não ler nem gravar histórico")
    args = p.parse_args(argv)

    caminhos = _expandir(args.entradas)
    if not caminhos:
        print("Nenhum arquivo de log encontrado.", file=sys.stderr)
        return 1
    try:
        res = executar({
            "arquivos": [Arquivo(os.path.basename(c), c, os.path.getsize(c)) for c in caminhos],
            "sistema": args.sistema, "titulo": args.titulo, "comparar": not args.sem_comparacao,
        })
    except ErroFerramenta as ex:
        print(str(ex), file=sys.stderr)
        return 1
    saida = args.saida or res["nome_arquivo"]
    with open(saida, "w", encoding="utf-8") as f:
        f.write(res["html"])
    print("%s -> %s" % (res["resumo"], saida))
    return 0
