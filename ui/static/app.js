/* Green Proof: aleg dosarul -> 1. Fișiere -> 2. Raport -> 3. Decizie.
   Pagina afișează ce întoarce serverul (ui/server.py) și trimite deciziile; verdictul, recomandarea,
   dovezile și validarea deciziei vin din API. Pe ecran stă doar pasul curent, restul e la un clic. */
"use strict";

// ------------------------------------------------------------------ texte de afișare
const STATUS = { in_asteptare: "În așteptare", aprobat: "Aprobat", respins: "Respins", interventie: "Intervenție umană" };
const FILTRE = [
  ["toate", "Toate"], ["in_asteptare", "În așteptare"], ["aprobat", "Aprobate"],
  ["respins", "Respinse"], ["interventie", "Intervenție umană"],
];
const BUTON = { aprobat: "Aprobă", respins: "Respinge", interventie: "Intervenție umană" };
const RECOMANDARE = { aprobat: "Aprobare", respins: "Respingere", interventie: "Intervenție umană" };
const REZULTAT_REGULA = {
  OK: ["Îndeplinită", "pos"], NU: ["Neîndeplinită", "neg"], SEMNAL: ["Semnal", "warn"],
  NEEVALUABIL: ["Neevaluabilă", "neutru"], OK_CONDITIONAT: ["Condiționat", "pos"],
};
const TIP_SCURT = {
  cerere_finantare: "Cerere", certificat_energetic: "Certificat energetic",
  certificat_sustenabilitate: "Certificat sustenabilitate", contract_inchiriere: "Contract închiriere",
  contract_ppa_verde: "Contract PPA", declaratie_mediu_produs: "Declarație de mediu", analiza_ciclu_viata: "Analiză LCA",
  nota_tehnica: "Notă tehnică", raport_etanseitate: "Raport etanșeitate", raport_taxonomie_ue: "Raport taxonomie",
  raspuns_anaf: "Răspuns ANAF",
};
const UNEALTA = {
  verifica_firma: "Verifică firma la ANAF", evalueaza_conditii_generale: "Evaluează condițiile generale",
  cauta_certificat: "Caută certificatul în registru", evalueaza_cale: "Evaluează calea de eligibilitate",
  verifica_chiriasi: "Verifică chiriașii", calculeaza_co2: "Calculează impactul CO₂",
  cere_date_client: "Cere date clientului", escaladeaza: "Escaladează la comitet",
  cauta_emisii_vehicul: "Caută emisiile vehiculului", factor_emisie_tara: "Caută factorul de emisie",
};
const CAMP = {
  cui: "CUI", tara: "Țara", aprobat_proces_standard: "Aprobat prin procesul standard", data_aprobare: "Data aprobării",
  data_marcare_verde: "Data marcării ca verde", suma_eur: "Suma creditului", cota_banca: "Cota băncii",
  descriere_proiect: "Proiect", afirmatii_client: "Afirmațiile clientului", certificare_sistem: "Sistem de certificare",
  certificare_nivel: "Nivelul certificării", certificare_stadiu: "Stadiul certificării",
  nr_certificat_declarat: "Nr. certificat declarat", epc_clasa: "Clasa energetică", ped_kwh_m2: "Energie primară",
  energie_finala_kwh_m2: "Energie finală", suprafata_m2: "Suprafață", adresa_cladire: "Adresa clădirii",
  stadiu_cladire: "Stadiul clădirii", chiriasi: "Chiriași", "chiriasi.caen": "CAEN chiriași", capacitate_mw: "Capacitate",
  productie_anuala_mwh: "Producție anuală", consum_inainte_mwh: "Consum înainte", consum_dupa_mwh: "Consum după",
  tehnologie_bat: "Tehnologie BAT", industrie_beneficiar: "Industria beneficiarului",
  echipament_combustibil_fosil: "Echipament pe combustibil fosil",
};
const UNITATE = {
  suma_eur: "EUR", ped_kwh_m2: "kWh/m²/an", energie_finala_kwh_m2: "kWh/m²/an", suprafata_m2: "m²",
  capacitate_mw: "MW", productie_anuala_mwh: "MWh/an", consum_inainte_mwh: "MWh/an", consum_dupa_mwh: "MWh/an",
};

// ------------------------------------------------------------------ stare
const S = {
  dosare: [], filtru: null, selectat: null, detalii: {},
  rezultate: {},          // raportul generat în această sesiune, pe dosar
  pas: {}, maxPas: {},    // pasul curent și cel mai departe pas deschis, pe dosar
  deschise: new Set(),    // secțiuni și rânduri desfășurate
  viz: null,              // fișierul previzualizat în panou
  alegere: {}, comentariu: {}, confirmare: null, mesaj: {}, lucreaza: false,
};
const $ = (sel) => document.querySelector(sel);

// ------------------------------------------------------------------ formatare
const nrRo = (v, zecimale = 0) =>
  new Intl.NumberFormat("ro-RO", { minimumFractionDigits: zecimale, maximumFractionDigits: zecimale }).format(v);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const liniuta = '<span class="muted">—</span>';
function dataRo(iso) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("ro-RO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
function valoareCamp(camp, v) {
  if (v === null || v === undefined || v === "") return liniuta;
  if (camp === "cota_banca" && typeof v === "number") return `${nrRo(v * 100, 1)}%`;
  if (typeof v === "boolean") return v ? "Da" : "Nu";
  if (typeof v === "number") {
    const u = UNITATE[camp];
    return `<span class="num">${nrRo(v, Number.isInteger(v) ? 0 : 1)}</span>${u ? ` ${u}` : ""}`;
  }
  if (Array.isArray(v)) {
    return v.map((x) => {
      if (x && typeof x === "object" && "nume" in x) {
        const parti = [x.caen ? `CAEN ${x.caen}` : null, typeof x.m2 === "number" ? `${nrRo(x.m2)} m²` : null].filter(Boolean);
        return `${esc(x.nume)}${parti.length ? ` <span class="muted">(${parti.join(", ")})</span>` : ""}`;
      }
      return esc(typeof x === "object" ? JSON.stringify(x) : x);
    }).join("<br>");
  }
  if (typeof v === "object") return esc(JSON.stringify(v));
  return esc(v);
}
const numeCamp = (c) => CAMP[c] || c.replace(/_/g, " ");
function tipScurt(doc) {
  if (doc.provenienta === "client") return TIP_SCURT[doc.tip_detectat] || (doc.tip_detectat || "").replace(/_/g, " ");
  const f = doc.fisier.toLowerCase();
  return f.includes("breeam") ? "Registru BREEAM" : f.includes("anaf") ? "Răspuns ANAF" : "Registru";
}
// Două dosare pot avea același proiect: primesc numărul dosarului ca sufix
function numeAfisat(d) {
  const nume = d.proiect || d.id;
  const dubluri = S.dosare.filter((x) => (x.proiect || x.id) === nume).length > 1;
  const nr = (d.id.match(/\d+/) || [d.id])[0];
  return { nume, sufix: dubluri ? ` · ${nr}` : "" };
}

// ------------------------------------------------------------------ API
async function api(cale, optiuni = {}) {
  const r = await fetch(cale, { headers: { "Content-Type": "application/json" }, ...optiuni });
  let date = null;
  try { date = await r.json(); } catch { /* fără corp JSON */ }
  if (!r.ok) {
    const detaliu = date && date.detail;
    const e = new Error(typeof detaliu === "string" ? detaliu : (detaliu && detaliu.mesaj) || `Eroare ${r.status}`);
    e.status = r.status;
    e.detaliu = detaliu;
    throw e;
  }
  return date;
}
const caleDosar = (id) => `/api/dosare/${encodeURIComponent(id)}`;

async function incarcaLista() {
  try {
    S.dosare = await api("/api/dosare");
  } catch (e) {
    $("#nav").innerHTML = `<p class="eroare">Serverul nu răspunde. <button class="link" data-act="reincarca">Reîncearcă</button></p>`;
    return;
  }
  randeazaNav();
  randeazaLista();
}

async function incarcaDetalii(id) {
  try {
    S.detalii[id] = await api(caleDosar(id));
  } catch (e) {
    S.detalii[id] = { eroare: e.message };
  }
  randeazaPanou();
}

// ------------------------------------------------------------------ acțiuni
function alegeFiltru(f) {
  S.filtru = f;
  const telefon = window.matchMedia("(max-width: 860px)").matches;
  $("#app").dataset.stare = S.selectat && !telefon ? "dosar" : "lista";
  randeazaNav();
  randeazaLista();
  randeazaPanou();
}

async function selecteaza(id) {
  S.selectat = id;
  S.viz = null;
  S.confirmare = null;
  S.mesaj[id] = null;
  S.pas[id] = S.pas[id] || 1;
  S.maxPas[id] = S.maxPas[id] || 1;
  $("#app").dataset.stare = "dosar";
  randeazaLista();
  if (!S.detalii[id] || S.detalii[id].eroare) {
    $("#panou").innerHTML = `<p class="gol">Se încarcă…</p>`;
    await incarcaDetalii(id);
  } else {
    randeazaPanou();
  }
}

function mergiLaPas(id, n) {
  if (n > (S.maxPas[id] || 1)) return;
  S.pas[id] = n;
  S.viz = null;
  randeazaPanou();
  $("#panou").scrollTop = 0;
}

async function genereazaRaport(id) {
  S.lucreaza = true;
  S.mesaj[id] = null;
  randeazaPanou();
  try {
    S.rezultate[id] = await api(`${caleDosar(id)}/evaluare`, { method: "POST" });
    S.maxPas[id] = Math.max(S.maxPas[id] || 1, 2);
    S.pas[id] = 2;
  } catch (e) {
    S.mesaj[id] = { tip: "eroare", text: e.message };
  }
  S.lucreaza = false;
  await Promise.all([incarcaLista(), incarcaDetalii(id)]);
}

async function trimiteDecizia(id) {
  const decizie = S.alegere[id];
  if (!decizie) return;
  // confirmarea se trimite doar după ce serverul a cerut-o și analistul a văzut avertizarea
  const confirmat = !!(S.confirmare && S.confirmare.id === id && S.confirmare.decizie === decizie);
  S.lucreaza = true;
  S.mesaj[id] = null;
  randeazaPanou();
  try {
    await api(`${caleDosar(id)}/decizie`, {
      method: "POST",
      body: JSON.stringify({ decizie, comentariu: (S.comentariu[id] || "").trim(), confirmat }),
    });
    S.confirmare = null;
    S.alegere[id] = null;
    S.comentariu[id] = "";
    S.mesaj[id] = { tip: "ok", text: `Decizie înregistrată: ${STATUS[decizie]}.` };
  } catch (e) {
    if (e.status === 409 && e.detaliu && e.detaliu.necesita_confirmare) {
      S.confirmare = { id, decizie, recomandare: e.detaliu.recomandare_agent };
    } else {
      S.mesaj[id] = { tip: "eroare", text: e.message };
    }
  }
  S.lucreaza = false;
  await Promise.all([incarcaLista(), incarcaDetalii(id)]);
}

async function reseteaza() {
  $("#meniu").hidden = true;
  const dialog = $("#confirm-reset");
  const nr = S.dosare.filter((d) => d.status !== "in_asteptare").length;
  $("#reset-text").textContent = nr
    ? `Se șterg deciziile pentru ${nr} ${nr === 1 ? "dosar" : "dosare"}. Rapoartele agentului rămân.`
    : "Nu există decizii înregistrate.";
  dialog.showModal();
  const raspuns = await new Promise((rezolva) => {
    dialog.onclick = (ev) => {
      const b = ev.target.closest("[data-raspuns]");
      if (b) { dialog.close(); rezolva(b.dataset.raspuns); }
    };
    dialog.oncancel = () => rezolva("nu");
  });
  if (raspuns !== "da") return;
  try { await api("/api/decizii", { method: "DELETE" }); } catch (e) { alert(`Resetarea nu a reușit: ${e.message}`); }
  S.mesaj = {};
  S.confirmare = null;
  await incarcaLista();
  if (S.selectat) await incarcaDetalii(S.selectat);
}

// ------------------------------------------------------------------ randare: filtre și listă
function randeazaModuri(s) {
  if (!s) return;
  const rand = (et, v) => `<dt>${et}</dt><dd>${v}</dd>`;
  $("#moduri").innerHTML =
    rand("Extracție", s.mod_extractie === "real" ? "din PDF-uri" : "date de test") +
    rand("Surse externe", s.mod_tools === "online" ? "online" : "offline") +
    rand("Agent", s.mod_agent === "llm" ? "LLM" : "plan fix") +
    (s.data_alocare ? rand("Alocare", esc(s.data_alocare)) : "");
}

function randeazaNav() {
  const numar = (f) => (f === "toate" ? S.dosare.length : S.dosare.filter((d) => d.status === f).length);
  $("#nav").innerHTML = FILTRE.map(([f, et]) =>
    `<button class="filtru" type="button" data-filtru="${f}" aria-current="${S.filtru === f}">${et}<span class="nr">${numar(f)}</span></button>`,
  ).join("");
}

function randeazaLista() {
  if (!S.filtru) return;
  const vizibile = S.dosare.filter((d) => S.filtru === "toate" || d.status === S.filtru);
  $("#lista-titlu").textContent = FILTRE.find(([f]) => f === S.filtru)[1];
  $("#lista").innerHTML = vizibile.length ? vizibile.map((d) => {
    const { nume, sufix } = numeAfisat(d);
    return `<button class="dosar" type="button" role="option" data-dosar="${esc(d.id)}" aria-selected="${S.selectat === d.id}"
      title="${esc(nume + sufix)} · ${STATUS[d.status]}"><span class="punct ${d.status}"></span>
      <span class="nume">${esc(nume)}</span>${sufix ? `<span class="sufix">${esc(sufix)}</span>` : ""}</button>`;
  }).join("") : `<p class="dosar muted">Niciun dosar.</p>`;
}

// ------------------------------------------------------------------ randare: panoul dosarului
function randeazaPanou() {
  const el = $("#panou");
  const id = S.selectat;
  if (!id) {
    el.innerHTML = `<p class="gol">${S.filtru ? "Alege un dosar din listă" : "Alege un filtru din stânga"}</p>`;
    return;
  }
  const d = S.detalii[id];
  if (!d) return;
  if (d.eroare) {
    el.innerHTML = `<p class="gol">Dosarul nu a putut fi încărcat. <button class="link" data-act="reincarca-dosar">Reîncearcă</button></p>`;
    return;
  }
  const { nume, sufix } = numeAfisat(S.dosare.find((x) => x.id === id) || { id, proiect: d.proiect });
  const pas = S.pas[id] || 1;
  const max = S.maxPas[id] || 1;
  const pasi = [[1, "Fișiere"], [2, "Raport"], [3, "Decizie"]].map(([n, et]) =>
    `<button class="pas-btn ${n < pas ? "gata" : ""}" type="button" data-pas="${n}" ${n > max ? "disabled" : ""}
      ${n === pas ? 'aria-current="step"' : ""}><span class="cerc">${n < pas ? "✓" : n}</span><span class="txt">${et}</span></button>`,
  ).join('<span class="linie" aria-hidden="true"></span>');

  let corp;
  if (S.viz) corp = randeazaVizualizare();
  else if (pas === 1) corp = pasFisiere(id, d);
  else if (pas === 2) corp = pasRaport(id);
  else corp = pasDecizie(id, d);

  el.innerHTML = `
    <button class="btn inapoi" type="button" data-act="inapoi">← Dosare</button>
    <header class="antet">
      <h2>${esc(nume)}${sufix ? `<span class="muted">${esc(sufix)}</span>` : ""}</h2>
      <span class="status"><span class="punct ${d.status}"></span>${STATUS[d.status]}</span>
    </header>
    <nav class="pasi-nav" aria-label="Pași">${pasi}</nav>
    ${corp}`;

  const zona = el.querySelector("textarea");
  if (zona) zona.value = S.comentariu[id] || "";
}

function pasFisiere(id, d) {
  const ordonate = [...d.documente].sort((a, b) => (a.provenienta === "client" ? 0 : 1) - (b.provenienta === "client" ? 0 : 1));
  const fisiere = ordonate.map((doc) => `<li><button class="fisier" type="button" data-url="${esc(doc.url)}" data-fisier="${esc(doc.fisier)}">
      <span class="nume-f">${esc(doc.fisier)}</span><span class="tip">${esc(tipScurt(doc))}</span></button></li>`).join("");
  const cheie = `lipsa:${id}`;
  const deschis = S.deschise.has(cheie);
  const n = d.documente_lipsa.length;
  const lipsa = n ? `
    <button class="cap lipsa-cap" type="button" data-comuta="${cheie}" aria-expanded="${deschis}">
      <span class="sageata">▸</span><span class="muted">${n} ${n === 1 ? "document lipsă" : "documente lipsă"}</span></button>
    ${deschis ? `<ul class="lipsa-lista">${d.documente_lipsa.map((x) => `<li><span class="mono">${esc(x.id)}</span><span>${esc(x.nume)}</span></li>`).join("")}</ul>` : ""}` : "";
  const eroare = S.mesaj[id] && S.mesaj[id].tip === "eroare" ? `<p class="eroare" role="alert">${esc(S.mesaj[id].text)}</p>` : "";
  return `<ul class="randuri">${fisiere || `<li class="muted">Niciun fișier.</li>`}</ul>${lipsa}
    <div class="actiune"><button class="btn primary" type="button" data-act="genereaza" ${S.lucreaza ? "disabled" : ""}>
      ${S.lucreaza ? "Se generează…" : "Generează raportul"}</button>${eroare}</div>`;
}

function sectiune(cheie, titlu, numar, continut) {
  const deschis = S.deschise.has(cheie);
  return `<section class="sectiune">
    <button class="cap" type="button" data-comuta="${cheie}" aria-expanded="${deschis}">
      <span class="sageata">▸</span>${titlu}<span class="nr num">${numar}</span></button>
    ${deschis ? `<div class="corp">${continut()}</div>` : ""}</section>`;
}

// închis: un rând cu „…”; deschis: textul complet pe mai multe rânduri
function randPliabil(cheie, id, scurt, rezultat, continut) {
  const deschis = S.deschise.has(cheie);
  return `<div class="rand">
    <button class="rand-cap" type="button" data-comuta="${cheie}" aria-expanded="${deschis}">
      <span class="sageata">▸</span><span class="id">${id}</span><span class="scurt">${scurt}</span>${rezultat}</button>
    ${deschis ? `<div class="rand-corp">${continut()}</div>` : ""}</div>`;
}

const legaturaSursa = (c) => c.url
  ? `<button class="link" type="button" data-url="${esc(c.url)}" data-fisier="${esc(c.fisier)}" data-pagina="${c.pagina ?? ""}">${esc(c.fisier)}${c.pagina ? `, p. ${c.pagina}` : ""}</button>`
  : esc(c.sursa || "");

function pasRaport(id) {
  const r = S.rezultate[id];
  if (!r) return `<p class="muted">Raportul nu a fost generat.</p>`;
  const v = r.verdict;
  const d = S.detalii[id];
  const cheieInfo = `info:${id}`;
  const urmeaza = v.actiuni.length
    ? `<button class="icon-btn" type="button" data-comuta="${cheieInfo}" aria-expanded="${S.deschise.has(cheieInfo)}" aria-label="Ce urmează" title="Ce urmează">ⓘ</button>` : "";

  const reguli = () => v.reguli.map((g) => {
    const [et, cls] = REZULTAT_REGULA[g.rezultat] || [g.rezultat, "neutru"];
    const vazute = new Set();
    const surse = (r.dovezi[g.regula_id] || []).filter((c) => c.url && !vazute.has(`${c.fisier}#${c.pagina}`) && vazute.add(`${c.fisier}#${c.pagina}`));
    return randPliabil(`regula:${id}:${g.regula_id}`, esc(g.regula_id), esc((r.nume_reguli || {})[g.regula_id] || g.dovada),
      `<span class="rezultat ${cls}">${et}</span>`,
      () => `<p>${esc(g.dovada)}</p><p class="muted">Cadrul verde: ${esc(g.sursa_framework)}</p>
        ${surse.length ? `<p class="muted">Documente: ${surse.map(legaturaSursa).join(" · ")}</p>` : ""}`);
  }).join("");

  const date = () => `<dl class="date">${d.campuri.map((c) =>
    `<dt>${esc(numeCamp(c.camp))}</dt><dd>${valoareCamp(c.camp, c.valoare)}</dd><dd>${c.valoare === null || c.valoare === undefined ? "" : legaturaSursa(c)}</dd>`,
  ).join("")}</dl>`;

  const pasiAgent = () => v.trace.map((p) => {
    const rez = p.rezultat && typeof p.rezultat === "object" ? p.rezultat : null;
    const actiune = p.actiune ? (UNEALTA[p.actiune] || p.actiune.replace(/_/g, " ")) : "Concluzie";
    return randPliabil(`pas:${id}:${p.pas}`, p.pas, esc(actiune), "", () => {
      const argumente = Object.entries(p.argumente || {}).map(([k, x]) => `${k}: ${typeof x === "object" ? JSON.stringify(x) : x}`).join(" · ");
      const stare = rez ? (rez.eroare ? `<span class="rezultat neg">Eroare: ${esc(rez.eroare)}</span>`
        : rez.gasit ? `<span class="rezultat pos">Găsit</span>` : `<span class="rezultat neg">Negăsit</span>`) : "";
      return `<p>${esc(p.motiv || "")}</p>${argumente ? `<p class="muted mono">${esc(argumente)}</p>` : ""}${stare ? `<p>${stare}</p>` : ""}`;
    });
  }).join("");

  return `<div class="recomandare"><span class="eticheta">${RECOMANDARE[r.recomandare] || "—"}</span>${urmeaza}</div>
    ${v.cale_eligibilitate ? `<p class="motiv">${esc(v.cale_eligibilitate)}</p>` : ""}
    ${typeof v.impact_tco2_an === "number" ? `<p class="impact"><b class="num">${nrRo(v.impact_tco2_an, 1)}</b> tCO₂/an evitate</p>` : ""}
    ${r.din_salvare ? `<p class="salvat">Rezultat salvat la ${dataRo(r.salvat_la)}</p>` : ""}
    ${S.deschise.has(cheieInfo) ? `<ul class="info">${v.actiuni.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}
    <div class="sectiuni">
      ${sectiune(`sec:${id}:reguli`, "Reguli verificate", v.reguli.length, reguli)}
      ${sectiune(`sec:${id}:date`, "Date extrase", d.campuri.length, date)}
      ${sectiune(`sec:${id}:pasi`, "Pașii agentului", v.trace.length, pasiAgent)}
    </div>
    <div class="actiune"><button class="btn primary" type="button" data-act="la-decizie">Ia decizia</button></div>`;
}

function pasDecizie(id, d) {
  const r = S.rezultate[id];
  const alegere = S.alegere[id];
  const butoane = ["aprobat", "respins", "interventie"].map((x) =>
    `<button class="btn" type="button" data-alege="${x}" aria-pressed="${alegere === x}" ${S.lucreaza ? "disabled" : ""}>${BUTON[x]}</button>`).join("");
  let formular = "";
  if (alegere) {
    const confirm = S.confirmare && S.confirmare.id === id && S.confirmare.decizie === alegere;
    // comentariul apare doar unde e obligatoriu
    const comentariu = alegere !== "aprobat"
      ? `<label for="comentariu">Comentariu</label><textarea id="comentariu" rows="3"></textarea>` : "";
    const avertizare = confirm
      ? `<p class="avertizare" role="alert">Agentul recomandă ${RECOMANDARE[S.confirmare.recomandare] || "altceva"}. Decizia ta va fi marcată ca diferită.</p>` : "";
    formular = `<div class="formular">${comentariu}${avertizare}
      <button class="btn primary trimite" type="button" data-act="trimite" ${S.lucreaza ? "disabled" : ""}>${confirm ? `Confirmă: ${BUTON[alegere]}` : "Trimite"}</button></div>`;
  }
  const mesaj = S.mesaj[id]
    ? `<p class="${S.mesaj[id].tip === "ok" ? "ok" : "eroare"}" role="${S.mesaj[id].tip === "ok" ? "status" : "alert"}">${esc(S.mesaj[id].text)}</p>` : "";
  const x = d.decizie;
  const decizia = x ? `<p class="decizia-ta">Decizia ta: <b>${STATUS[x.decizie]}</b> · ${dataRo(x.data)}${x.difera_de_agent ? " · diferă de agent" : ""}
      ${x.comentariu ? `<br>„${esc(x.comentariu)}”` : ""}</p>` : "";
  return `<p class="recomandat">Agentul recomandă: <b>${RECOMANDARE[r && r.recomandare] || "—"}</b></p>
    <div class="butoane">${butoane}</div>${formular}${mesaj}${decizia}`;
}

function randeazaVizualizare() {
  const { url, fisier, pagina } = S.viz;
  const tinta = pagina ? `${url}#page=${pagina}` : url;
  const json = fisier.toLowerCase().endsWith(".json");
  if (json) {
    fetch(url)
      .then((r) => { if (!r.ok) throw new Error(`Eroare ${r.status}`); return r.json(); })
      .then((date) => { const pre = $("#viz-json"); if (pre) pre.innerHTML = coloreazaJson(JSON.stringify(date, null, 2)); })
      .catch((e) => { const pre = $("#viz-json"); if (pre) pre.textContent = `Fișierul nu a putut fi citit (${e.message}).`; });
  }
  return `<div class="vizualizare">
    <div class="viz-cap"><span class="nume-f">${esc(fisier)}${pagina ? `<span class="muted"> · p. ${pagina}</span>` : ""}</span>
      <a class="btn" href="${esc(tinta)}" target="_blank" rel="noopener">Deschide în tab nou</a>
      <button class="icon-btn" type="button" data-act="inchide-viz" aria-label="Închide previzualizarea" title="Închide (Esc)">✕</button></div>
    <div class="viz-corp">${json ? `<pre id="viz-json">Se încarcă…</pre>` : `<iframe title="${esc(fisier)}" src="${esc(tinta)}"></iframe>`}</div>
  </div>`;
}

function coloreazaJson(text) {
  return esc(text).replace(
    /(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b|\b(true|false|null)\b/g,
    (m, sir, douaPuncte, numar, cuvant) => {
      if (sir) return douaPuncte ? `<span class="k">${sir}</span>${douaPuncte}` : `<span class="s">${sir}</span>`;
      return `<span class="n">${numar || cuvant}</span>`;
    },
  );
}

// ------------------------------------------------------------------ evenimente
document.addEventListener("click", (ev) => {
  const t = ev.target;
  if (!t.closest(".meniu")) $("#meniu").hidden = true;
  const f = t.closest("[data-filtru]");
  if (f) { alegeFiltru(f.dataset.filtru); return; }
  const dosar = t.closest("[data-dosar]");
  if (dosar) { selecteaza(dosar.dataset.dosar); return; }
  const id = S.selectat;
  const sursa = t.closest("[data-url]");
  if (sursa) {
    S.viz = { url: sursa.dataset.url, fisier: sursa.dataset.fisier, pagina: sursa.dataset.pagina || null };
    randeazaPanou();
    $("#panou").scrollTop = 0;
    return;
  }
  const comuta = t.closest("[data-comuta]");
  if (comuta) {
    const k = comuta.dataset.comuta;
    if (S.deschise.has(k)) S.deschise.delete(k); else S.deschise.add(k);
    randeazaPanou();
    return;
  }
  const pas = t.closest("[data-pas]");
  if (pas) { mergiLaPas(id, Number(pas.dataset.pas)); return; }
  const alege = t.closest("[data-alege]");
  if (alege) {
    S.alegere[id] = alege.dataset.alege;
    S.mesaj[id] = null;
    if (S.confirmare && S.confirmare.decizie !== S.alegere[id]) S.confirmare = null;
    randeazaPanou();
    const zona = $("#comentariu");
    if (zona) zona.focus();
    return;
  }
  const act = t.closest("[data-act]");
  if (!act) return;
  switch (act.dataset.act) {
    case "genereaza": genereazaRaport(id); break;
    case "la-decizie": S.maxPas[id] = 3; mergiLaPas(id, 3); break;
    case "trimite": trimiteDecizia(id); break;
    case "inchide-viz": S.viz = null; randeazaPanou(); break;
    case "inapoi": $("#app").dataset.stare = "lista"; break;
    case "reincarca": incarcaLista(); break;
    case "reincarca-dosar": incarcaDetalii(id); break;
  }
});

document.addEventListener("input", (ev) => {
  if (ev.target.id === "comentariu" && S.selectat) S.comentariu[S.selectat] = ev.target.value;
});

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && S.viz && !document.querySelector("dialog[open]")) {
    S.viz = null;
    randeazaPanou();
  }
});

$("#reset").addEventListener("click", reseteaza);
$("#meniu-btn").addEventListener("click", () => {
  const m = $("#meniu");
  m.hidden = !m.hidden;
  $("#meniu-btn").setAttribute("aria-expanded", String(!m.hidden));
});

// ------------------------------------------------------------------ pornire: doar filtrele; lista apare după alegerea unui filtru
(async function porneste() {
  randeazaPanou();
  const [stare] = await Promise.all([api("/api/stare").catch(() => null), incarcaLista()]);
  randeazaModuri(stare);
})();
