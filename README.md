# BugiCaixa

Uma caixa de bugigangas: ferramentas de apoio que rodam no seu computador, com
tela no navegador. Precisa apenas de **Python 3.8+** — sem dependências, e
nenhum arquivo sai da máquina.

Ferramentas disponíveis:

- **BugiLog** (analisador de logs) — agrupa erros e avisos equivalentes de arquivos de
  log e monta um relatório com as causas mais frequentes.

## Abrir

| Sistema | Como |
|---|---|
| Linux / macOS | `./iniciar.sh` |
| Windows | duplo clique em `iniciar.bat` |
| Qualquer um | `python3 -m bugicaixa` (dentro desta pasta) |

A tela abre no navegador em `http://127.0.0.1:8765`. Para fechar, use o botão
**Encerrar** (ou Ctrl+C no terminal). Abrir de novo com o programa já rodando
só reabre a tela.

Opcional:

- `python3 -m bugicaixa --criar-atalho` — ícone no menu de aplicativos (Linux).
- `pipx install .` (ou `pip install .`) — instala o comando `bugicaixa`.

## BugiLog — analisador de logs

1. Clique na caixa **Arquivos de log** (ou arraste os arquivos para ela).
2. Opcional: informe o **Sistema**. Usando sempre o mesmo nome, o relatório
   compara com a análise anterior (causa `NOVO`, `+N`, `−N`, `=`).
3. **Gerar relatório**. O resultado aparece embaixo; dá para salvar o HTML,
   imprimir em PDF ou abrir em outra aba.

O que ele faz:

- Agrupa erros e avisos por *assinatura* (exceção + ponto do código, ignorando
  IDs, datas, números e outros valores variáveis).
- Conta como erro os registros INFO que trazem exceção/stack trace ou resposta
  HTTP 5xx (marcados `INFO→ERRO`). Registros WARN ficam como a aplicação decidiu.
- Mostra um exemplo real de cada causa, com arquivo e linha.

Formatos reconhecidos sem configuração — basta a linha começar com data e hora:
Spring Boot / Logback / Log4j, Python `logging`, .NET, nginx (error), syslog e
JSON por linha (Logstash/ECS). Arquivos `.gz` são lidos direto.

Pela linha de comando (aceita pastas):

```bash
python3 -m bugicaixa bugilog ./logs -o relatorio.html --sistema "Minha API"
```

O BugiLog também existe como projeto próprio, que roda inteiro no navegador e
é distribuído como contêiner: <https://github.com/ManoelSCosta/BugiLog>.

O histórico de comparação fica em `~/.local/share/bugicaixa`
(Windows: `%APPDATA%\bugicaixa`; macOS: `~/Library/Application Support/bugicaixa`).

## Desenvolvimento

```
bugicaixa/
  __main__.py        entrada: tela, linha de comando, atalho
  servidor.py        servidor HTTP local (só 127.0.0.1)
  base.py            peças compartilhadas (Arquivo, ErroFerramenta, pasta de dados)
  web/               tela (HTML/CSS/JS puros)
  ferramentas/       uma pasta ou módulo por ferramenta
tests/
```

Testes: `python3 -m unittest`

### Criar outra ferramenta

Cada módulo em `bugicaixa/ferramentas/` que definir `ID`, `NOME`, `DESCRICAO`,
`campos()` e `executar(valores)` aparece sozinho no menu — a tela monta o
formulário a partir de `campos()`. O contrato está em
`bugicaixa/ferramentas/__init__.py`; use `analisador_logs` como modelo.

Não versione logs reais nem relatórios gerados a partir deles (o `.gitignore`
já barra `*.log`, `*.gz` e `relatorio-*.html`).

## Licença

[MIT](LICENSE)
