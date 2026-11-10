"""Registro de ferramentas.

Cada subpacote/modulo desta pasta que definir ID, NOME, DESCRICAO, campos() e
executar(valores) aparece automaticamente na tela. Veja analisador_logs como
exemplo.

Contrato:
    ID         identificador curto, usado na URL e na linha de comando
    NOME       nome exibido no menu
    DESCRICAO  uma frase sobre o que a ferramenta faz
    campos()   lista de dicts descrevendo o formulario:
                 {"id", "tipo": "arquivos" | "texto" | "opcao", "rotulo",
                  "ajuda", "padrao", "sugestoes", "aceita", "obrigatorio"}
    executar(valores) -> {"html": str, "nome_arquivo": str, "resumo": str}
               valores[id] e uma lista de base.Arquivo (tipo "arquivos"),
               str (tipo "texto") ou bool (tipo "opcao").
               Levante base.ErroFerramenta para erros que o usuario deve ler.
    cli(argv)  opcional: uso pela linha de comando; retorna o codigo de saida.
"""

import importlib
import pkgutil

_cache = None


def todas():
    global _cache
    if _cache is None:
        achadas = {}
        for info in pkgutil.iter_modules(__path__):
            mod = importlib.import_module("%s.%s" % (__name__, info.name))
            if all(hasattr(mod, a) for a in ("ID", "NOME", "campos", "executar")):
                achadas[mod.ID] = mod
        _cache = dict(sorted(achadas.items(), key=lambda kv: getattr(kv[1], "ORDEM", 100)))
    return _cache


def obter(id_ferramenta):
    return todas().get(id_ferramenta)
