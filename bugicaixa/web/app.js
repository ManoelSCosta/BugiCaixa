"use strict";
// Tela generica: monta o formulario de cada ferramenta a partir da descricao
// dos campos que o servidor devolve em /api/ferramentas.

const $ = (id) => document.getElementById(id);
const estado = { ferramentas: [], atual: null, arquivos: {}, ocupado: false };

function el(tag, attrs, ...filhos) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos) if (f != null) n.append(f);
  return n;
}

function tamanho(b) {
  if (b >= 1048576) return (b / 1048576).toFixed(1).replace(".", ",") + " MB";
  if (b >= 1024) return Math.round(b / 1024) + " KB";
  return b + " B";
}

function situacao(texto, tipo) {
  const s = $("situacao");
  s.textContent = texto || "";
  s.className = tipo || "";
}

async function api(caminho, opcoes) {
  let resp;
  try {
    resp = await fetch(caminho, opcoes);
  } catch (e) {
    throw new Error("Sem resposta do programa. Ele foi encerrado? Abra-o novamente.");
  }
  const dados = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(dados.erro || "Falha (" + resp.status + ").");
  return dados;
}

// ---- formulario -----------------------------------------------------------

function campoArquivos(campo) {
  estado.arquivos[campo.id] = [];
  const entrada = el("input", { type: "file", multiple: true, hidden: true, accept: campo.aceita });
  const lista = el("ul", { class: "lista-arquivos" });

  const redesenhar = () => {
    lista.replaceChildren(...estado.arquivos[campo.id].map((arq, i) =>
      el("li", null,
        el("span", { class: "nome", title: arq.name }, arq.name),
        el("span", { class: "tam" }, tamanho(arq.size)),
        el("button", { type: "button", title: "Remover", "aria-label": "Remover " + arq.name,
          onclick: () => { estado.arquivos[campo.id].splice(i, 1); redesenhar(); } }, "×"))));
  };
  const adicionar = (novos) => {
    const atuais = estado.arquivos[campo.id];
    for (const a of novos) {
      if (!atuais.some((x) => x.name === a.name && x.size === a.size && x.lastModified === a.lastModified)) {
        atuais.push(a);
      }
    }
    redesenhar();
    situacao("");
  };

  entrada.addEventListener("change", () => { adicionar(entrada.files); entrada.value = ""; });
  const zona = el("button", { type: "button", class: "soltar", onclick: () => entrada.click() },
    el("strong", null, "Clique para selecionar"), " ou arraste os arquivos para cá");
  zona.addEventListener("dragover", (e) => { e.preventDefault(); zona.classList.add("sobre"); });
  zona.addEventListener("dragleave", () => zona.classList.remove("sobre"));
  zona.addEventListener("drop", (e) => {
    e.preventDefault();
    zona.classList.remove("sobre");
    adicionar([...e.dataTransfer.files].filter((f) => f.size > 0 || f.type));
  });

  return el("div", { class: "campo largo" },
    el("span", { class: "rotulo" }, campo.rotulo), zona, entrada, lista,
    campo.ajuda ? el("div", { class: "ajuda" }, campo.ajuda) : null);
}

function campoTexto(campo) {
  const id = "campo-" + campo.id;
  const entrada = el("input", { type: "text", id, name: campo.id, value: campo.padrao || "", autocomplete: "off" });
  let sugestoes = null;
  if (campo.sugestoes && campo.sugestoes.length) {
    sugestoes = el("datalist", { id: id + "-lista" }, ...campo.sugestoes.map((s) => el("option", { value: s })));
    entrada.setAttribute("list", id + "-lista");
  }
  return el("div", { class: "campo" }, el("label", { for: id }, campo.rotulo), entrada, sugestoes,
    campo.ajuda ? el("div", { class: "ajuda" }, campo.ajuda) : null);
}

function campoOpcao(campo) {
  return el("div", { class: "campo largo" },
    el("label", { class: "opcao" },
      el("input", { type: "checkbox", name: campo.id, checked: !!campo.padrao }), campo.rotulo),
    campo.ajuda ? el("div", { class: "ajuda" }, campo.ajuda) : null);
}

function mostrarFerramenta(f) {
  estado.atual = f;
  estado.arquivos = {};
  $("nome-ferramenta").textContent = f.nome;
  $("descricao-ferramenta").textContent = f.descricao;
  const construtores = { arquivos: campoArquivos, opcao: campoOpcao, texto: campoTexto };
  $("formulario").replaceChildren(...f.campos.map((c) => (construtores[c.tipo] || campoTexto)(c)));
  for (const b of $("menu").children) b.setAttribute("aria-current", b.dataset.id === f.id);
  situacao("");
}

// ---- execucao -------------------------------------------------------------

async function executar() {
  if (estado.ocupado) return;
  const f = estado.atual;
  const form = $("formulario");
  for (const c of f.campos) {
    if (c.tipo === "arquivos" && c.obrigatorio && !estado.arquivos[c.id].length) {
      situacao("Selecione pelo menos um arquivo.", "erro");
      return;
    }
  }
  estado.ocupado = true;
  $("executar").disabled = true;
  try {
    const pedido = {};
    for (const c of f.campos) {
      if (c.tipo === "arquivos") {
        pedido[c.id] = [];
        const arqs = estado.arquivos[c.id];
        for (let i = 0; i < arqs.length; i++) {
          situacao("Lendo " + arqs[i].name + " (" + (i + 1) + " de " + arqs.length + ")…");
          const r = await api("/api/envio", {
            method: "POST", body: arqs[i],
            headers: { "X-Nome-Arquivo": encodeURIComponent(arqs[i].name), "Content-Type": "application/octet-stream" },
          });
          pedido[c.id].push(r.id);
        }
      } else if (c.tipo === "opcao") {
        pedido[c.id] = form.elements[c.id].checked;
      } else {
        pedido[c.id] = form.elements[c.id].value;
      }
    }
    situacao("Analisando…");
    const r = await api("/api/executar/" + f.id, {
      method: "POST", body: JSON.stringify(pedido), headers: { "Content-Type": "application/json" },
    });
    const url = "/api/relatorio/" + r.relatorio;
    $("quadro").src = url;
    $("quadro").hidden = false;
    $("vazio").hidden = true;
    $("resumo").textContent = r.resumo;
    $("salvar").href = url + "?baixar=1";
    $("salvar").setAttribute("download", r.nome_arquivo);
    $("nova-aba").href = url;
    $("botoes-relatorio").hidden = false;
    situacao("Relatório pronto.", "ok");
    $("saida").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    situacao(e.message, "erro");
  } finally {
    estado.ocupado = false;
    $("executar").disabled = false;
  }
}

async function encerrar() {
  if (!confirm("Encerrar o programa? Relatórios não salvos serão perdidos.")) return;
  try { await fetch("/api/encerrar", { method: "POST" }); } catch (e) { /* ja encerrou */ }
  document.body.replaceChildren(el("div", { class: "encerrado" },
    el("h1", null, "Programa encerrado"), el("p", { class: "suave" }, "Você já pode fechar esta aba.")));
}

async function iniciar() {
  $("executar").addEventListener("click", executar);
  $("formulario").addEventListener("submit", (e) => { e.preventDefault(); executar(); });
  $("encerrar").addEventListener("click", encerrar);
  $("imprimir").addEventListener("click", () => $("quadro").contentWindow.print());
  // Impede o navegador de abrir o arquivo se ele for solto fora da area certa.
  for (const ev of ["dragover", "drop"]) window.addEventListener(ev, (e) => e.preventDefault());
  try {
    const dados = await api("/api/ferramentas");
    estado.ferramentas = dados.ferramentas;
    $("versao").textContent = "v" + dados.versao;
    $("menu").replaceChildren(...dados.ferramentas.map((f) =>
      el("button", { type: "button", "data-id": f.id, onclick: () => mostrarFerramenta(f) }, f.nome)));
    if (dados.ferramentas.length) mostrarFerramenta(dados.ferramentas[0]);
  } catch (e) {
    situacao(e.message, "erro");
  }
}

iniciar();
