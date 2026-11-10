import os
import tempfile
import unittest

from bugicaixa.base import Arquivo, ErroFerramenta
from bugicaixa.ferramentas import analisador_logs
from bugicaixa.ferramentas.analisador_logs.analise import Analise, assinatura, interpretar_linha

LOG = """\
banner sem data
2026-09-14 15:06:38,923 INFO  com.acme.App - Iniciando
2026-09-14 15:07:00,000 ERROR com.acme.PagamentoService - Falha ao pagar pedido 123
java.lang.IllegalStateException: saldo insuficiente
\tat org.springframework.web.Foo.bar(Foo.java:10)
\tat com.acme.PagamentoService.pagar(PagamentoService.java:42)
2026-09-14 15:08:00,000 ERROR com.acme.PagamentoService - Falha ao pagar pedido 987
java.lang.IllegalStateException: saldo insuficiente
\tat com.acme.PagamentoService.pagar(PagamentoService.java:42)
2026-09-14 15:09:00,000 WARN  com.acme.Fila - Fila lenta: 35 mensagens
2026-09-14 15:10:00,000 INFO  com.acme.Fila - Consumidor caiu: java.net.ConnectException: Connection refused
"""


def _analisar(texto):
    with tempfile.TemporaryDirectory() as pasta:
        caminho = os.path.join(pasta, "app.log")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(texto)
        a = Analise()
        a.adicionar_arquivo(caminho, "app.log", len(texto))
        return a


class TestInterpretarLinha(unittest.TestCase):
    def campos(self, linha):
        ev = interpretar_linha(linha)
        return (ev.nivel, ev.logger, ev.msg)

    def test_formatos(self):
        casos = {
            "2026-09-11 10:23:45.123  ERROR 8412 --- [exec-3] c.e.app.Svc : falhou": ("ERROR", "c.e.app.Svc", "falhou"),
            "2026-09-11T10:23:45.123Z  INFO 1 --- [app] [main] o.s.b.Svc   : Started": ("INFO", "o.s.b.Svc", "Started"),
            "2026-09-14 15:06:38,923 [main] WARN  o.a.Foo - cuidado": ("WARN", "o.a.Foo", "cuidado"),
            "2026/09/14 15:06:38 [error] 123#0: connect() failed": ("ERROR", "", "123#0: connect() failed"),
            "14/09/2026 15:06:38 ERROR algo quebrou": ("ERROR", "", "algo quebrou"),
            "Sep 14 15:06:38 host app[1]: CRITICAL boom": ("FATAL", "", "boom"),
            "2026-09-14 15:06:38,923 - meuapp - WARNING - atenção": ("WARN", "", "atenção"),
        }
        for linha, esperado in casos.items():
            with self.subTest(linha=linha):
                self.assertEqual(self.campos(linha), esperado)

    def test_json_por_linha(self):
        ev = interpretar_linha('{"@timestamp":"2026-09-14T15:06:38.1Z","level":"error","message":"x",'
                               '"logger_name":"a.B","stack_trace":"java.lang.X: y\\n\\tat com.x.Y.z(Y.java:1)"}')
        self.assertEqual((ev.nivel, ev.logger, ev.msg, len(ev.trace)), ("ERROR", "a.B", "x", 2))
        self.assertEqual(ev.ts.hour, 15)

    def test_continuacao_nao_e_evento(self):
        for linha in ("\tat com.x.Y.z(Y.java:1)", "Caused by: java.lang.X: y", "texto solto", '{"a": 1}'):
            self.assertIsNone(interpretar_linha(linha))

    def test_traceback_python(self):
        ev = interpretar_linha("2026-09-14 15:06:38,923 - app - ERROR - deu ruim")
        ev.trace = ["Traceback (most recent call last):",
                    '  File "/app/svc.py", line 10, in run', "    x()",
                    '  File "/usr/lib/python3/site-packages/r.py", line 3, in get', "    raise",
                    "requests.exceptions.ConnectionError: falhou"]
        self.assertEqual(assinatura(ev), "ConnectionError @ run (svc.py:10)")


class TestAnalise(unittest.TestCase):
    def test_agrupamento(self):
        a = _analisar(LOG)
        self.assertEqual(a.eventos, 5)
        self.assertEqual(a.linhas_soltas, 1)
        erros = a.do_nivel("ERROR")
        self.assertEqual(len(erros), 2)
        principal = erros[0][1]
        self.assertEqual(principal.assinatura,
                         "IllegalStateException @ com.acme.PagamentoService.pagar(PagamentoService.java:42)")
        self.assertEqual(principal.ocorrencias, 2)
        self.assertEqual(principal.reclassificados, 0)

    def test_info_com_excecao_vira_erro(self):
        reclass = _analisar(LOG).do_nivel("ERROR")[1][1]
        self.assertEqual((reclass.ocorrencias, reclass.reclassificados), (1, 1))

    def test_warn_permanece_warn(self):
        avisos = _analisar(LOG).do_nivel("WARN")
        self.assertEqual([g.assinatura for _, g in avisos], ["Fila :: Fila lenta: <N> mensagens"])


class TestFerramenta(unittest.TestCase):
    def _executar(self, texto, **extras):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = os.path.join(pasta, "app.log")
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(texto)
            valores = {"arquivos": [Arquivo("app.log", caminho, len(texto))], "comparar": False}
            valores.update(extras)
            return analisador_logs.executar(valores)

    def test_gera_relatorio(self):
        res = self._executar(LOG, sistema="Minha API")
        self.assertIn("Relatório de logs — Minha API", res["html"])
        self.assertIn("PagamentoService.pagar", res["html"])
        self.assertTrue(res["nome_arquivo"].startswith("relatorio-logs-minha-api-"))

    def test_conteudo_do_log_e_escapado(self):
        res = self._executar("2026-01-01 10:00:00 ERROR a.B - <script>alert(1)</script>\n")
        self.assertNotIn("<script>alert(1)</script>", res["html"])

    def test_arquivo_sem_registros(self):
        with self.assertRaises(ErroFerramenta):
            self._executar("nada reconhecível aqui\n")


if __name__ == "__main__":
    unittest.main()
