"""Relatorio HTML autocontido (abre offline, imprime bem em PDF)."""

import html
from collections import Counter
from datetime import datetime

CSS = """
:root{--fg:#1c1c1e;--bg:#fff;--suave:#6b6b70;--linha:#e3e3e6;--painel:#f7f7f8;
 --erro:#b3261e;--aviso:#8a6100;--novo:#7b1fa2;--reclass:#00695c;--link:#1a56c4;
 --t-novo:#f3e5f5;--t-piorou:#fdecea;--t-melhorou:#e6f4ea;--ok:#1e6b34;--t-igual:#eceef0;--t-reclass:#e0f2f1}
@media screen and (prefers-color-scheme:dark){:root{--fg:#e8e8ea;--bg:#17181a;--suave:#a0a0a8;
 --linha:#34363a;--painel:#202225;--erro:#ff8a80;--aviso:#f2c14e;--novo:#d9a3ee;--reclass:#6fd6c6;
 --link:#8ab4f8;--t-novo:#3b2542;--t-piorou:#4a2320;--t-melhorou:#1d3a26;--ok:#8fd6a3;
 --t-igual:#2c2e32;--t-reclass:#17393a}}
*{box-sizing:border-box}
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0 auto;
 padding:32px;max-width:1200px;color:var(--fg);background:var(--bg);line-height:1.5;font-size:14px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:32px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--linha)}
.sub{color:var(--suave);font-size:13px;margin-bottom:24px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.card{flex:1 1 130px;border:1px solid var(--linha);border-radius:8px;padding:12px 14px}
.card .v{font-size:24px;font-weight:600;line-height:1.1}
.card .l{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--suave);margin-top:2px}
.err .v{color:var(--erro)}.warn .v{color:var(--aviso)}.novo .v{color:var(--novo)}.reclass .v{color:var(--reclass)}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--linha);vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--suave);font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.quando{white-space:nowrap;font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:10px;font-weight:600;padding:1px 6px;border-radius:4px;
 letter-spacing:.4px;vertical-align:middle;white-space:nowrap}
.t-novo{background:var(--t-novo);color:var(--novo)}
.t-piorou{background:var(--t-piorou);color:var(--erro)}
.t-melhorou{background:var(--t-melhorou);color:var(--ok)}
.t-igual{background:var(--t-igual);color:var(--suave)}
.t-reclass{background:var(--t-reclass);color:var(--reclass)}
.fp{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;word-break:break-word}
details{margin-top:6px}
summary{cursor:pointer;font-size:12px;color:var(--link)}
pre{background:var(--painel);border:1px solid var(--linha);border-radius:6px;padding:10px;
 overflow-x:auto;font-size:11px;line-height:1.45;white-space:pre-wrap;word-break:break-word;margin:6px 0 0}
.bar{display:flex;align-items:center;gap:8px;margin:2px 0;font-size:11px}
.bar .lb{width:90px;color:var(--suave);white-space:nowrap;font-variant-numeric:tabular-nums}
.bar .trilho{flex:1;max-width:560px}
.bar .fill{display:block;height:12px;background:var(--erro);border-radius:2px;min-width:2px}
.bar .n{color:var(--suave);font-variant-numeric:tabular-nums}
.vazio,.nota{color:var(--suave);font-size:13px}
.vazio{font-style:italic;padding:8px 0}
footer{margin-top:40px;padding-top:12px;border-top:1px solid var(--linha);color:var(--suave);font-size:11px}
@media print{body{padding:0;font-size:11px;max-width:none}details{display:none}
 h2{page-break-after:avoid}tr{page-break-inside:avoid}}
"""


def e(x):
    return html.escape(str(x), quote=True)


def fmt_ts(d):
    return d.strftime("%d/%m/%Y %H:%M:%S") if d else "–"


def fmt_ts_curto(d):
    return d.strftime("%d/%m %H:%M:%S") if d else "–"


def fmt_num(n):
    return "{:,}".format(n).replace(",", ".")


def fmt_tamanho(b):
    if b >= 1048576:
        return ("%.1f MB" % (b / 1048576.0)).replace(".", ",")
    if b >= 1024:
        return "%d KB" % round(b / 1024.0)
    return "%d B" % b


def plural(n, um, varios):
    return "%s %s" % (fmt_num(n), um if n == 1 else varios)


def tag_variacao(atual, anterior):
    if anterior is None:
        return '<span class="tag t-novo">NOVO</span>'
    if atual > anterior * 1.2 and atual - anterior >= 2:
        return '<span class="tag t-piorou">+%s</span>' % fmt_num(atual - anterior)
    if atual < anterior * 0.8:
        return '<span class="tag t-melhorou">−%s</span>' % fmt_num(anterior - atual)
    return '<span class="tag t-igual">=</span>'


def _tabela(grupos_ord, base, varios_arquivos):
    if not grupos_ord:
        return '<p class="vazio">Nenhuma ocorrência no período.</p>'
    out = ["<table><thead><tr><th class='num'>#</th><th>Assinatura</th><th class='num'>Qtd</th>"]
    if base is not None:
        out.append("<th>Situação</th>")
    out.append("<th>Primeira</th><th>Última</th>")
    if varios_arquivos:
        out.append("<th>Arquivo</th>")
    out.append("</tr></thead><tbody>")
    for i, (chave, g) in enumerate(grupos_ord, 1):
        det = ""
        if g.exemplo is not None:
            corpo = g.exemplo.msg[:3000]
            if g.exemplo.trace:
                corpo += "\n" + g.exemplo.trace_txt
            det = ("<details><summary>ver exemplo (%s, linha %d)</summary><pre>%s</pre></details>"
                   % (e(g.exemplo.arquivo), g.exemplo.linha, e(corpo[:6000])))
        reclass = ""
        if g.reclassificados:
            parcial = "" if g.reclassificados == g.ocorrencias else \
                " (%d/%d)" % (g.reclassificados, g.ocorrencias)
            reclass = ' <span class="tag t-reclass">INFO→ERRO%s</span>' % parcial
        out.append("<tr><td class='num'>%d</td><td><span class='fp'>%s</span>%s%s</td>"
                   "<td class='num'>%s</td>" % (i, e(g.assinatura), reclass, det, fmt_num(g.ocorrencias)))
        if base is not None:
            out.append("<td>%s</td>" % tag_variacao(g.ocorrencias, base.get("%s|%s" % chave)))
        out.append("<td class='quando'>%s</td><td class='quando'>%s</td>"
                   % (fmt_ts_curto(g.primeira), fmt_ts_curto(g.ultima)))
        if varios_arquivos:
            out.append("<td>%s</td>" % e(", ".join(
                "%s (%d)" % (a, n) for a, n in g.arquivos.most_common(3))))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _serie_temporal(por_hora, limite=48):
    """[(rotulo, valor)], por hora; por dia quando o periodo passa de 3 dias."""
    if not por_hora:
        return [], ""
    if len({k[:10] for k in por_hora}) > 3:
        por_dia = Counter()
        for k, v in por_hora.items():
            por_dia[k[:10]] += v
        itens = sorted(por_dia.items())[-limite:]
        return [("%s/%s" % (k[8:10], k[5:7]), v) for k, v in itens], "por dia"
    itens = sorted(por_hora.items())[-limite:]
    return [("%s/%s %sh" % (k[8:10], k[5:7], k[11:13]), v) for k, v in itens], "por hora"


def _barras(itens):
    topo = max(v for _, v in itens) or 1
    out = []
    for rotulo, v in itens:
        out.append('<div class="bar"><span class="lb">%s</span><span class="trilho">'
                   '<span class="fill" style="width:%.1f%%"></span></span><span class="n">%s</span></div>'
                   % (e(rotulo), 100.0 * v / topo, fmt_num(v)))
    return "".join(out)


def gerar_html(titulo, analise, base=None, limite_avisos=30):
    """base: {"gerado_em", "grupos"} da analise anterior, ou None se nao ha comparacao."""
    erros = analise.do_nivel("ERROR")
    avisos = analise.do_nivel("WARN")
    total_err = sum(g.ocorrencias for _, g in erros)
    total_warn = sum(g.ocorrencias for _, g in avisos)
    total_reclass = sum(g.reclassificados for _, g in erros)
    grupos_base = base.get("grupos", {}) if base else None
    novos = [k for k, _ in erros if "%s|%s" % k not in grupos_base] if base else []
    varios = len(analise.arquivos) > 1

    periodo = "%s a %s" % (fmt_ts(analise.inicio), fmt_ts(analise.fim)) \
        if analise.inicio else "indeterminado"

    resumo = []
    if total_err == 0:
        resumo.append("Nenhum erro registrado no período analisado.")
    else:
        resumo.append("%s de erro, em %s."
                      % (plural(total_err, "ocorrência", "ocorrências").capitalize(),
                         plural(len(erros), "causa distinta", "causas distintas")))
        topo = erros[0][1]
        resumo.append("A causa mais frequente foi <span class='fp'>%s</span>, com %s (%d%% do total)."
                      % (e(topo.assinatura), plural(topo.ocorrencias, "ocorrência", "ocorrências"),
                         round(100.0 * topo.ocorrencias / total_err)))
    if total_reclass:
        resumo.append("%s como INFO (ou sem nível) pela aplicação e foram contadas como erro "
                      "por trazerem exceção/stack trace ou resposta HTTP 5xx."
                      % plural(total_reclass, "ocorrência estava registrada",
                               "ocorrências estavam registradas").capitalize())
    if base:
        quando = base.get("gerado_em", "")
        try:
            quando = datetime.fromisoformat(quando).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
        if novos:
            resumo.append("%s na análise anterior (%s)."
                          % (plural(len(novos), "causa de erro não aparecia",
                                    "causas de erro não apareciam").capitalize(), e(quando)))
        else:
            resumo.append("Nenhuma causa de erro nova em relação à análise anterior (%s)." % e(quando))

    p = [
        "<!DOCTYPE html><html lang='pt-br'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>%s</title><style>%s</style></head><body>" % (e(titulo), CSS),
        "<h1>%s</h1>" % e(titulo),
        "<div class='sub'>Gerado em %s · %s · período: %s</div>"
        % (datetime.now().strftime("%d/%m/%Y %H:%M"),
           plural(len(analise.arquivos), "arquivo", "arquivos"), e(periodo)),
        "<div class='cards'>",
        "<div class='card err'><div class='v'>%s</div><div class='l'>Erros</div></div>" % fmt_num(total_err),
        "<div class='card err'><div class='v'>%s</div><div class='l'>Causas distintas</div></div>" % fmt_num(len(erros)),
        "<div class='card warn'><div class='v'>%s</div><div class='l'>Avisos</div></div>" % fmt_num(total_warn),
        "<div class='card reclass'><div class='v'>%s</div><div class='l'>Reclassificados de INFO</div></div>" % fmt_num(total_reclass),
    ]
    if base:
        p.append("<div class='card novo'><div class='v'>%s</div><div class='l'>Causas novas</div></div>"
                 % fmt_num(len(novos)))
    p.append("<div class='card'><div class='v'>%s</div><div class='l'>Registros lidos</div></div></div>"
             % fmt_num(analise.eventos))
    p.append("<h2>Resumo</h2><p>%s</p>" % " ".join(resumo))

    hora_err = Counter()
    for _, g in erros:
        hora_err.update(g.por_hora)
    itens, unidade = _serie_temporal(hora_err)
    if itens:
        p.append("<h2>Erros %s</h2>%s" % (unidade, _barras(itens)))

    p.append("<h2>Erros por causa</h2>")
    p.append(_tabela(erros, grupos_base, varios))

    p.append("<h2>Avisos por causa</h2>")
    p.append(_tabela(avisos[:limite_avisos], grupos_base, varios))
    if len(avisos) > limite_avisos:
        resto = avisos[limite_avisos:]
        p.append("<p class='nota'>Exibidas as %d causas de aviso mais frequentes; outras %d "
                 "(%s) foram omitidas.</p>"
                 % (limite_avisos, len(resto),
                    plural(sum(g.ocorrencias for _, g in resto), "ocorrência", "ocorrências")))

    p.append("<h2>Arquivos analisados</h2><table><thead><tr><th>Arquivo</th>"
             "<th class='num'>Tamanho</th><th class='num'>Registros</th></tr></thead><tbody>")
    for nome, tamanho, eventos in analise.arquivos:
        p.append("<tr><td>%s</td><td class='num'>%s</td><td class='num'>%s</td></tr>"
                 % (e(nome), fmt_tamanho(tamanho), fmt_num(eventos)))
    p.append("</tbody></table>")
    niveis = " · ".join("%s: %s" % (e(n), fmt_num(q)) for n, q in analise.niveis.most_common())
    p.append("<p class='nota'>Registros por nível — %s.</p>" % niveis)

    p.append("<footer>Relatório gerado localmente. Nenhum dado foi transmitido para "
             "serviços externos.</footer></body></html>")
    return "".join(p)
