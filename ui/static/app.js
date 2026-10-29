/* Green Proof: pagina afișează ce întoarce serverul (ui/server.py) și trimite deciziile.
   Nicio regulă de eligibilitate aici: verdictul, recomandarea, dovezile și validarea deciziei vin din API. */
"use strict";

// ------------------------------------------------------------------ texte de afișare
const STATUS = { in_asteptare: "În așteptare", aprobat: "Aprobat", respins: "Respins", interventie: "Intervenție umană" };
const BUTON = { aprobat: "Aprobă", respins: "Respinge", interventie: "Intervenție umană" };
const RECOMANDARE = { aprobat: "Aprobare", respins: "Respingere", interventie: "Intervenție umană" };
const RECOMANDARE_SCURT = { aprobat: "aprobă", respins: "respinge", interventie: "intervenție" };
const VERDICT = {
  ELIGIBIL: "Eligibil",
  ELIGIBIL_CU_MONITORIZARE: "Eligibil, cu monitorizare",
  NEELIGIBIL: "Neeligibil",
  EXCEPTIE_ESCALADARE_COMITET: "Excepție: escaladare la comitet",
};
const REZULTAT_REGULA = {
  OK: ["Îndeplinită", "pos"], NU: ["Neîndeplinită", "neg"], SEMNAL: ["Semnal", "warn"],
  NEEVALUABIL: ["Neevaluabilă", ""], OK_CONDITIONAT: ["Condiționat", "pos"],
};
const CATEGORIE = {
  green_buildings: "Clădiri verzi", renewable_energy: "Energie regenerabilă", energy_efficiency: "Eficiență energetică",
  clean_transportation: "Transport curat", pollution_prevention: "Prevenirea poluării", circular_economy: "Economie circulară",
};
const TIP_DOCUMENT = {
  cerere_finantare: "Cerere de finanțare", certificat_energetic: "Certificat energetic",
  certificat_sustenabilitate: "Certificat de sustenabilitate", contract_inchiriere: "Contract de închiriere",
  contract_ppa_verde: "Contract PPA verde", declaratie_mediu_produs: "Declarație de mediu (EPD)",
  analiza_ciclu_viata: "Analiză ciclu de viață (LCA)", nota_tehnica: "Notă tehnică",
  raport_etanseitate: "Raport de etanșeitate", raport_taxonomie_ue: "Raport taxonomie UE", raspuns_anaf: "Răspuns ANAF",
};
const CAMP = {
  cui: "CUI", tara: "Țara", aprobat_proces_standard: "Aprobat prin procesul standard", data_aprobare: "Data aprobării",
  data_marcare_verde: "Data marcării ca verde", suma_eur: "Suma creditului", cota_banca: "Cota băncii",
  descriere_proiect: "Proiect", afirmatii_client: "Afirmațiile clientului", certificare_sistem: "Sistem de certificare",
  certificare_nivel: "Nivelul certificării", certificare_stadiu: "Stadiul certificării",
  nr_certificat_declarat: "Nr. certificat declarat", epc_clasa: "Clasa energetică (EPC)", ped_kwh_m2: "Energie primară",
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
const FILTRE = [
  ["toate", "Toate dosarele"], ["in_asteptare", "În așteptare"], ["interventie", "Intervenție umană"],
  ["aprobat", "Aprobate"], ["respins", "Respinse"],
];

// ------------------------------------------------------------------ stare
const S = {
  stare: null, dosare: [], filtru: "toate", selectat: null, detalii: {}, rezultate: {},
  deschise: new Set(), tab: {}, comentariu: {}, confirmare: null, mesaj: {}, lucreaza: false,
};
const $ = (sel) => document.querySelector(sel);

// ------------------------------------------------------------------ formatare
const nrRo = (v, zecimale = 0) =>
  new Intl.NumberFormat("ro-RO", { minimumFractionDigits: zecimale, maximumFractionDigits: zecimale }).format(v);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const liniuta = '<span class="muted">—</span>';
function dataRo(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return esc(iso);
  return d.toLocaleString("ro-RO", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function oraRo(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" });
}
function valoareCamp(camp, v) {
  if (v === null || v === undefined || v === "") return liniuta;
  if (camp === "cota_banca" && typeof v === "number") return `${nrRo(v * 100, 1)}%`;
  if (typeof v === "boolean") return v ? "Da" : "Nu";
  if (typeof v === "number") {
    const u = UNITATE[camp];
    return `<span class="num">${nrRo(v, Number.isInteger(v) ? 0 : 1)}</span>${u ? ` <span class="muted">${u}</span>` : ""}`;
  }
  if (Array.isArray(v)) {
    if (camp === "chiriasi") return `${v.length} ${v.length === 1 ? "chiriaș" : "chiriași"} <span class="muted">(tabelul de mai jos)</span>`;
    return v.map((x) => esc(typeof x === "object" ? JSON.stringify(x) : x)).join("<br>");
  }
  if (typeof v === "object") return esc(JSON.stringify(v));
  return esc(v);
}
const numeCamp = (c) => CAMP[c] || c.replace(/_/g, " ");
const numeTip = (t) => (t ? TIP_DOCUMENT[t] || t.replace(/_/g, " ") : "");
function numeRegistru(fisier) {
  const f = fisier.toLowerCase();
  if (f.includes("breeam")) return "Răspunsul registrului BREEAM";
  if (f.includes("anaf")) return "Răspunsul ANAF";
  return "Răspuns de la o sursă externă";
}
const pill = (cheie) => `<span class="pill ${cheie}">${STATUS[cheie] || esc(cheie)}</span>`;

// ------------------------------------------------------------------ API
async function api(cale, optiuni = {}) {
  const r = await fetch(cale, { headers: { "Content-Type": "application/json" }, ...optiuni });
  let date = null;
  try { date = await r.json(); } catch { /* răspuns fără corp JSON */ }
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

// ------------------------------------------------------------------ încărcare
async function incarcaStare() {
  try {
    S.stare = await api("/api/stare");
  } catch { S.stare = null; }
  randeazaModuri();
}

async function incarcaLista() {
  try {
    S.dosare = await api("/api/dosare");
  } catch (e) {
    $("#lista").innerHTML = `<div class="empty">Nu am putut încărca dosarele (${esc(e.message)}). <button class="link" data-act="reincarca">Reîncearcă</button></div>`;
    $("#rezumat").textContent = "Serverul nu răspunde.";
    return;
  }
  randeazaLista();
}

async function incarcaDetalii(id) {
  try {
    S.detalii[id] = await api(caleDosar(id));
  } catch (e) {
    S.detalii[id] = { eroare: e.message };
  }
  randeazaDetaliu();
}

async function selecteaza(id, { push = true } = {}) {
  S.selectat = id;
  S.confirmare = null;
  S.mesaj[id] = null;
  $("#work").dataset.vedere = "detaliu";
  if (push && location.hash !== `#${id}`) history.replaceState(null, "", `#${encodeURIComponent(id)}`);
  randeazaLista();
  if (!S.detalii[id] || S.detalii[id].eroare) {
    $("#detaliu").innerHTML = `<div class="empty">Se încarcă dosarul…</div>`;
    await incarcaDetalii(id);
  } else {
    randeazaDetaliu();
  }
}

// ------------------------------------------------------------------ acțiuni
async function deschideSolutia(id) {
  S.lucreaza = true;
  S.mesaj[id] = null;
  randeazaDetaliu();
  try {
    const rezultat = await api(`${caleDosar(id)}/evaluare`, { method: "POST" });
    S.rezultate[id] = rezultat;
    S.deschise.add(id);
    S.tab[id] = "reguli";
  } catch (e) {
    S.mesaj[id] = { tip: "eroare", text: e.message };
  }
  S.lucreaza = false;
  await Promise.all([incarcaLista(), incarcaDetalii(id)]);
}

async function decide(id, decizie, confirmat = false) {
  const comentariu = (S.comentariu[id] || "").trim();
  S.lucreaza = true;
  S.mesaj[id] = null;
  randeazaDetaliu();
  try {
    await api(`${caleDosar(id)}/decizie`, { method: "POST", body: JSON.stringify({ decizie, comentariu, confirmat }) });
    S.confirmare = null;
    S.comentariu[id] = "";
    S.mesaj[id] = { tip: "ok", text: `Decizia „${STATUS[decizie]}” a fost înregistrată.` };
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
  const dialog = $("#confirm-reset");
  const nr = S.dosare.filter((d) => d.status !== "in_asteptare").length;
  $("#reset-text").textContent = nr
    ? `Se șterg deciziile pentru ${nr} ${nr === 1 ? "dosar" : "dosare"}. Rezultatele agentului rămân salvate.`
    : "Nu există decizii înregistrate. Rezultatele agentului rămân salvate.";
  dialog.showModal();
  const raspuns = await new Promise((rezolva) => {
    dialog.onclick = (ev) => {
      const b = ev.target.closest("[data-raspuns]");
      if (b) { dialog.close(); rezolva(b.dataset.raspuns); }
    };
    dialog.oncancel = () => rezolva("nu");
  });
  if (raspuns !== "da") return;
  try {
    await api("/api/decizii", { method: "DELETE" });
  } catch (e) {
    alert(`Resetarea nu a reușit: ${e.message}`);
  }
  S.mesaj = {};
  S.confirmare = null;
  await incarcaLista();
  if (S.selectat) await incarcaDetalii(S.selectat);
}

function previzualizeaza(url, fisier, pagina) {
  const dialog = $("#preview");
  const corp = $("#preview-body");
  const tinta = pagina ? `${url}#page=${pagina}` : url;
  $("#preview-titlu").textContent = fisier;
  $("#preview-meta").textContent = pagina ? `Pagina ${pagina}` : (fisier.toLowerCase().endsWith(".json") ? "JSON" : "PDF");
  $("#preview-tab").href = tinta;
  if (fisier.toLowerCase().endsWith(".json")) {
    corp.innerHTML = `<pre>Se încarcă…</pre>`;
    fetch(url)
      .then((r) => { if (!r.ok) throw new Error(`Eroare ${r.status}`); return r.json(); })
      .then((date) => { corp.innerHTML = `<pre>${coloreazaJson(JSON.stringify(date, null, 2))}</pre>`; })
      .catch((e) => { corp.innerHTML = `<pre>Fișierul nu a putut fi citit (${esc(e.message)}).</pre>`; });
  } else {
    corp.innerHTML = `<iframe title="${esc(fisier)}" src="${esc(tinta)}"></iframe>`;
  }
  if (!dialog.open) dialog.showModal();
}

function coloreazaJson(text) {
  return esc(text).replace(
    /(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\b|\b(true|false|null)\b/g,
    (m, sir, douaPuncte, numar, cuvant) => {
      if (sir) return douaPuncte ? `<span class="k">${sir}</span>${douaPuncte}` : `<span class="s">${sir}</span>`;
      if (numar) return `<span class="n">${numar}</span>`;
      return `<span class="n">${cuvant}</span>`;
    },
  );
}

// ------------------------------------------------------------------ randare: bara laterală și listă
function randeazaModuri() {
  const s = S.stare;
  if (!s) { $("#moduri").innerHTML = ""; return; }
  const alocare = s.data_alocare ? new Date(s.data_alocare) : null;
  if (alocare && !Number.isNaN(alocare.getTime())) {
    $("#scope").textContent = `Alocare la ${alocare.toLocaleDateString("ro-RO", { day: "numeric", month: "long", year: "numeric" })}`;
  }
  const rand = (et, v) => `<dt>${et}</dt><dd>${v}</dd>`;
  $("#moduri").innerHTML =
    rand("Extracție", s.mod_extractie === "real" ? "din PDF-uri" : "date de test") +
    rand("Surse externe", s.mod_tools === "online" ? "online" : "offline") +
    rand("Agent", s.mod_agent === "llm" ? "LLM" : "plan fix");
}

function randeazaNav() {
  const numar = (f) => (f === "toate" ? S.dosare.length : S.dosare.filter((d) => d.status === f).length);
  $("#nav").innerHTML = FILTRE.map(([f, eticheta]) => {
    // numărul apare doar pe cozile care cer o acțiune
    const arata = f === "in_asteptare" || f === "interventie";
    return `<button class="nav-item" type="button" data-filtru="${f}" aria-current="${S.filtru === f}">
      <span class="dot ${f}"></span>${eticheta}${arata ? `<span class="count">${numar(f)}</span>` : ""}</button>`;
  }).join("");
}

function randeazaLista() {
  randeazaNav();
  const asteapta = S.dosare.filter((d) => d.status === "in_asteptare").length;
  const interventii = S.dosare.filter((d) => d.status === "interventie").length;
  const parti = [`${asteapta} ${asteapta === 1 ? "dosar așteaptă" : "dosare așteaptă"} decizia ta`];
  if (interventii) parti.push(`${interventii} ${interventii === 1 ? "cere" : "cer"} intervenție umană`);
  parti.push("agentul recomandă, analistul decide");
  $("#rezumat").textContent = parti.join(" · ");

  const vizibile = S.dosare.filter((d) => S.filtru === "toate" || d.status === S.filtru);
  $("#lista-titlu").textContent = FILTRE.find(([f]) => f === S.filtru)[1];
  $("#lista-total").textContent = `${vizibile.length} din ${S.dosare.length}`;
  if (!vizibile.length) {
    $("#lista").innerHTML = `<div class="empty">Niciun dosar în această listă.</div>`;
    return;
  }
  $("#lista").innerHTML = vizibile.map((d) => {
    const suma = typeof d.suma_eur === "number" ? `${nrRo(d.suma_eur)} EUR` : "sumă negăsită";
    const rec = d.recomandare ? `Agent: <b>${RECOMANDARE_SCURT[d.recomandare]}</b>` : "Agent: —";
    return `<button class="dosar-row" type="button" role="option" data-dosar="${esc(d.id)}" aria-selected="${S.selectat === d.id}">
      <span class="row-line"><span class="row-name">${esc(d.proiect || d.id)}</span>${pill(d.status)}</span>
      <span class="row-line"><span class="row-meta"><span class="num">${suma}</span> · <span class="mono">${esc(d.id)}</span></span><span class="row-rec">${rec}</span></span>
    </button>`;
  }).join("");
}

// ------------------------------------------------------------------ randare: detaliul dosarului
function butonSursa(c) {
  return `<button class="sursa" type="button" data-url="${esc(c.url)}" data-fisier="${esc(c.fisier)}" data-pagina="${c.pagina ?? ""}"
    title="${esc(c.citat ? `„${c.citat}”` : c.sursa)}"><svg aria-hidden="true"><use href="#doc"/></svg>
    <span class="f">${esc(c.fisier)}</span>${c.pagina ? `<span class="p">p. ${c.pagina}</span>` : ""}</button>`;
}

function randeazaDetaliu() {
  const id = S.selectat;
  const el = $("#detaliu");
  if (!id) { el.innerHTML = `<div class="empty">Alege un dosar din listă.</div>`; return; }
  const d = S.detalii[id];
  if (!d) return;
  if (d.eroare) {
    el.innerHTML = `<div class="empty">Dosarul nu a putut fi încărcat (${esc(d.eroare)}). <button class="link" data-act="reincarca-dosar">Reîncearcă</button></div>`;
    return;
  }
  const deschis = S.deschise.has(id);
  // în sesiune, soluția deschisă e cea întoarsă de agent; altfel doar data ultimului rezultat salvat
  const rezultat = deschis ? (S.rezultate[id] || d.rezultat) : null;
  const tab = S.tab[id] || (deschis ? "reguli" : "documente");
  const campuri = Object.fromEntries(d.campuri.map((c) => [c.camp, c]));
  const suma = campuri.suma_eur && campuri.suma_eur.valoare;
  const cota = campuri.cota_banca && campuri.cota_banca.valoare;
  const lipsaObligatorii = d.documente_lipsa.filter((x) => x.obligatoriu).length;
  const documenteClient = d.documente.filter((x) => x.provenienta === "client").length;
  const subtitlu = [CATEGORIE[d.categorie] || d.categorie, campuri.adresa_cladire && campuri.adresa_cladire.valoare].filter(Boolean);

  el.innerHTML = `
    <button class="btn inapoi" type="button" data-act="inapoi">Înapoi la dosare</button>
    <header class="obiect">
      <div>
        <p class="id mono">${esc(id)}</p>
        <h2>${esc(d.proiect || id)}</h2>
        <p class="sub">${subtitlu.map(esc).join(" · ") || "—"}</p>
      </div>
      ${pill(d.status)}
    </header>

    <div class="kpis">
      <div class="kpi"><p class="kpi-label">Suma creditului</p>
        <p class="kpi-value bani">${typeof suma === "number" ? `${nrRo(suma)}<small>EUR</small>` : liniuta}</p></div>
      <div class="kpi"><p class="kpi-label">Cota băncii</p>
        <p class="kpi-value">${typeof cota === "number" ? `${nrRo(cota * 100, 1)}<small>%</small>` : liniuta}</p></div>
      <div class="kpi"><p class="kpi-label">Documente primite</p>
        <p class="kpi-value">${documenteClient}<small>${d.documente.length - documenteClient} din registre</small></p></div>
      <div class="kpi"><p class="kpi-label">Obligatorii lipsă</p>
        <p class="kpi-value ${lipsaObligatorii ? "rau" : ""}">${lipsaObligatorii}</p></div>
    </div>

    <section class="solutie" aria-label="Soluția agentului">${randeazaSolutie(id, d, rezultat)}</section>
    <section class="decizie" aria-label="Decizia analistului">${randeazaDecizie(id, d, rezultat, deschis)}</section>

    <nav class="tabs" role="tablist" aria-label="Detaliile dosarului">
      ${[["reguli", "Reguli și dovezi"], ["traseu", "Traseul agentului"],
         ["documente", "Documente", `${d.documente.length} · ${d.documente_lipsa.length} lipsă`],
         ["date", "Date extrase", d.campuri.length]]
        .map(([t, et, meta]) => `<button type="button" role="tab" data-tab="${t}" aria-selected="${tab === t}">${et}${meta !== undefined ? `<span class="meta num">${meta}</span>` : ""}</button>`).join("")}
    </nav>
    <div class="tab-body" role="tabpanel">${randeazaTab(tab, id, d, rezultat)}</div>`;

  const zona = el.querySelector("textarea");
  if (zona) zona.value = S.comentariu[id] || "";
}

function randeazaSolutie(id, d, rezultat) {
  // cu soluția deschisă, erorile apar lângă butoanele de decizie
  const mesaj = !rezultat && S.mesaj[id] && S.mesaj[id].tip === "eroare"
    ? `<p class="eroare" role="alert">${esc(S.mesaj[id].text)}</p>` : "";
  if (!rezultat) {
    const salvat = d.rezultat ? `Ultimul rezultat salvat: ${dataRo(d.rezultat.salvat_la)}.` : "Dosarul nu a fost evaluat încă.";
    return `<div class="deschide">
      <p><strong>Agentul verifică dosarul față de regulile cadrului verde.</strong>${salvat}</p>
      <button class="btn primary" type="button" data-act="deschide" ${S.lucreaza ? "disabled" : ""}>${S.lucreaza ? "Agentul lucrează…" : "Vezi soluția agentului"}</button>
    </div>${mesaj}`;
  }
  const v = rezultat.verdict;
  const salvare = rezultat.din_salvare
    ? `<p class="notice" role="status">Agentul nu a putut rula acum (${esc(rezultat.eroare || "eroare")}). Se arată rezultatul salvat la ${dataRo(rezultat.salvat_la)}.</p>` : "";
  return `<div class="recomandare">
      <span class="bara" aria-hidden="true"></span>
      <div>
        <p class="eticheta">Recomandarea agentului</p>
        <p class="verdict">${RECOMANDARE[rezultat.recomandare] || "—"} <span>· ${VERDICT[v.verdict] || esc(v.verdict)}</span></p>
        ${v.cale_eligibilitate ? `<p class="cale">${esc(v.cale_eligibilitate)}</p>` : ""}
      </div>
      <p class="cand">${rezultat.din_salvare ? "rezultat salvat" : "rulat"} la ${oraRo(rezultat.salvat_la)}<br>
        <button class="link" type="button" data-act="deschide" ${S.lucreaza ? "disabled" : ""}>Rulează din nou</button></p>
    </div>${salvare}${mesaj}`;
}

function randeazaDecizie(id, d, rezultat, deschis) {
  const dezactivat = !deschis || S.lucreaza;
  const butoane = ["aprobat", "respins", "interventie"].map((x) => {
    const recomandat = rezultat && rezultat.recomandare === x;
    return `<button class="btn ${recomandat ? "primary" : ""}" type="button" data-decizie="${x}" ${dezactivat ? "disabled" : ""}>
      ${BUTON[x]}${recomandat ? ' <span class="tag">recomandat</span>' : ""}</button>`;
  }).join("");

  let stare;
  if (!deschis) stare = "Deschide soluția agentului înainte de a decide.";
  else if (S.mesaj[id] && S.mesaj[id].tip === "ok") stare = `<span role="status">${esc(S.mesaj[id].text)}</span>`;
  else stare = "";
  if (d.decizie) {
    const x = d.decizie;
    const comentariu = x.comentariu ? `: „${esc(x.comentariu)}”` : "";
    const diferit = x.difera_de_agent ? ` · diferă de recomandarea agentului (${RECOMANDARE[x.recomandare_agent] || "—"})` : "";
    stare = `${stare ? `${stare} ` : ""}Decizia curentă: <b>${STATUS[x.decizie]}</b>, ${dataRo(x.data)}${diferit}${comentariu}`;
  }
  const eroareDecizie = S.mesaj[id] && S.mesaj[id].tip === "eroare" && deschis
    ? `<p class="eroare stare" role="alert">${esc(S.mesaj[id].text)}</p>` : `<p class="stare">${stare}</p>`;

  const confirmare = S.confirmare && S.confirmare.id === id
    ? `<div class="confirmare" role="alertdialog" aria-label="Confirmă decizia">
        <p>Agentul recomandă ${RECOMANDARE[S.confirmare.recomandare] || "altceva"}. Înregistrezi „${STATUS[S.confirmare.decizie]}”?
          <span class="muted">Decizia se salvează marcată ca diferită de recomandare.</span></p>
        <span class="butoane"><button class="btn" type="button" data-act="renunta">Renunță</button>
          <button class="btn ink" type="button" data-act="confirma">Confirmă decizia</button></span>
      </div>` : "";

  return `<label for="comentariu">Comentariu <span>obligatoriu pentru Respinge și Intervenție umană</span></label>
    <textarea id="comentariu" rows="2" ${dezactivat ? "disabled" : ""} placeholder="Motivul deciziei"></textarea>
    <div class="butoane">${butoane}</div>
    ${confirmare}${eroareDecizie}`;
}

function randeazaTab(tab, id, d, rezultat) {
  const asteaptaSolutia = `<div class="empty">Apare după ce deschizi soluția agentului.</div>`;
  if (tab === "reguli") return rezultat ? tabReguli(rezultat) : asteaptaSolutia;
  if (tab === "traseu") return rezultat ? tabTraseu(rezultat) : asteaptaSolutia;
  if (tab === "documente") return tabDocumente(d);
  return tabDate(d);
}

function tabReguli(r) {
  const v = r.verdict;
  const randuri = v.reguli.map((regula) => {
    const [eticheta, clasa] = REZULTAT_REGULA[regula.rezultat] || [regula.rezultat, ""];
    // aceeași pagină o singură dată, chiar dacă susține mai multe câmpuri
    const vazute = new Set();
    const surse = (r.dovezi[regula.regula_id] || []).filter((c) => c.url && !vazute.has(`${c.fisier}#${c.pagina}`) && vazute.add(`${c.fisier}#${c.pagina}`));
    return `<tr>
      <td><span class="mono">${esc(regula.regula_id)}</span><span class="sub">${esc((r.nume_reguli || {})[regula.regula_id] || "")}</span></td>
      <td><span class="pill ${clasa}">${eticheta}</span></td>
      <td>${esc(regula.dovada)}${surse.length ? `<span class="surse">${surse.map(butonSursa).join("")}</span>` : ""}</td>
      <td class="n">${esc(regula.sursa_framework)}</td>
    </tr>`;
  }).join("");
  const actiuni = v.actiuni.length
    ? `<h3>Ce urmează</h3><ul class="actiuni">${v.actiuni.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : "";
  const det = v.impact_detalii || {};
  const impact = typeof v.impact_tco2_an === "number"
    ? `<h3>Impact estimat</h3><div class="impact">
        <div><p class="valoare">${nrRo(v.impact_tco2_an, 1)}<small>tCO₂/an evitate</small></p>
          <p class="meta">${esc(det.sursa || "")}</p></div>
        <div>${det.formula ? `<p class="formula">${esc(det.formula)}</p>` : ""}
          <ol>${(det.pasi || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ol>
          ${det.atentie ? `<p class="notice">${esc(det.atentie)}</p>` : ""}</div>
      </div>` : "";
  return `<table class="reguli">
      <thead><tr><th>Regula</th><th>Rezultat</th><th>Dovada și documentul din care vine</th><th class="n">Cadrul verde</th></tr></thead>
      <tbody>${randuri || `<tr><td colspan="4"><div class="empty">Agentul nu a evaluat nicio regulă.</div></td></tr>`}</tbody>
    </table>${actiuni}${impact}`;
}

function tabTraseu(r) {
  const pasi = r.verdict.trace.map((p) => {
    const rez = p.rezultat;
    let stare = "";
    if (rez && typeof rez === "object") {
      stare = rez.eroare ? `<span class="rez nu">eroare: ${esc(rez.eroare)}</span>`
        : rez.gasit ? `<span class="rez ok">găsit</span>` : `<span class="rez nu">negăsit</span>`;
    } else if (p.tip === "final") {
      stare = `<span class="rez">final</span>`;
    }
    const argumente = Object.entries(p.argumente || {}).map(([k, x]) => `${k}=${typeof x === "object" ? JSON.stringify(x) : x}`).join("  ");
    return `<li class="pas">
      <span class="nr">${p.pas}</span>
      <div>${p.actiune ? `<span class="unealta">${esc(p.actiune)}</span>` : "<strong>Concluzie</strong>"}
        ${argumente ? `<p class="arg">${esc(argumente)}</p>` : ""}
        <p class="motiv">${esc(p.motiv || "")}</p></div>
      ${stare}
    </li>`;
  }).join("");
  return `<h3>${r.verdict.trace.length} pași, în ordinea în care agentul i-a făcut</h3><ol class="pasi">${pasi}</ol>`;
}

function tabDocumente(d) {
  // întâi documentele clientului, apoi răspunsurile registrelor
  const ordonate = [...d.documente].sort((a, b) => (a.provenienta === "client" ? 0 : 1) - (b.provenienta === "client" ? 0 : 1));
  const randuri = ordonate.map((doc) => `<tr class="clic" data-url="${esc(doc.url)}" data-fisier="${esc(doc.fisier)}" tabindex="0">
      <td>${esc(doc.fisier)}<span class="sub">${doc.provenienta === "client" ? (numeTip(doc.tip_detectat) || "neclasificat") : numeRegistru(doc.fisier)}${doc.nume_contrazice_continut ? " · numele fișierului nu se potrivește cu conținutul" : ""}</span></td>
      <td>${doc.provenienta === "client" ? "Client" : "Registru"}</td>
      <td class="n">${typeof doc.incredere === "number" ? `${nrRo(doc.incredere * 100)}%` : liniuta}</td>
      <td>${doc.cerinte.length ? `<span class="mono">${doc.cerinte.map(esc).join(", ")}</span>` : liniuta}</td>
      <td class="n"><span class="link">Previzualizează</span></td>
    </tr>`).join("");
  const lipsa = d.documente_lipsa.length
    ? `<h3><span class="alerta">${d.documente_lipsa.length} ${d.documente_lipsa.length === 1 ? "document lipsește" : "documente lipsesc"}</span> din dosar</h3>
       <ul class="lipsa">${d.documente_lipsa.map((x) => `<li><span class="mono">${esc(x.id)}</span><span>${esc(x.nume)}</span>${x.obligatoriu ? `<span class="pill">obligatoriu</span>` : ""}</li>`).join("")}</ul>`
    : `<h3>Documente lipsă</h3><div class="empty">Dosarul are toate documentele cerute.</div>`;
  const recomandate = d.documente_recomandate_lipsa.length
    ? `<h3>Recomandate, dar lipsă</h3><ul class="lipsa">${d.documente_recomandate_lipsa.map((x) => `<li><span class="mono">${esc(x.id || "")}</span><span>${esc(x.nume || x)}</span></li>`).join("")}</ul>` : "";
  return `<table class="documente">
      <thead><tr><th>Fișier</th><th>Proveniență</th><th class="n">Încredere</th><th>Cerințe</th><th class="n"></th></tr></thead>
      <tbody>${randuri || `<tr><td colspan="5"><div class="empty">Niciun document în dosar.</div></td></tr>`}</tbody>
    </table>${lipsa}${recomandate}`;
}

function tabDate(d) {
  const rand = (c) => {
    const incredere = typeof c.incredere === "number" && c.valoare !== null
      ? `<span class="incredere ${c.incredere < 0.7 ? "slab" : ""}">încredere ${nrRo(c.incredere * 100)}%${c.citat_verificat === false ? " · citat neverificat" : ""}</span>` : "";
    return `<div class="kv-row"><dt>${esc(numeCamp(c.camp))}</dt><dd>${valoareCamp(c.camp, c.valoare)}${incredere}</dd>
      <dd>${c.url ? butonSursa(c) : ""}</dd></div>`;
  };
  const gasite = d.campuri.filter((c) => c.valoare !== null && c.valoare !== undefined);
  const negasite = d.campuri_lipsa;
  const chiriasi = d.chiriasi.length
    ? `<h3>Chiriași</h3><table><thead><tr><th>Chiriaș</th><th>CAEN</th><th class="n">Suprafață</th></tr></thead><tbody>
        ${d.chiriasi.map((c) => `<tr><td>${esc(c.nume)}</td><td>${c.caen ? `<span class="mono">${esc(c.caen)}</span>` : liniuta}</td>
          <td class="n">${typeof c.m2 === "number" ? `${nrRo(c.m2)} <span class="muted">m²</span>` : liniuta}</td></tr>`).join("")}
       </tbody></table>` : "";
  const afirmatii = d.afirmatii_client.length
    ? `<h3>Ce afirmă clientul</h3><ul class="actiuni">${d.afirmatii_client.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : "";
  const lipsa = negasite.length
    ? `<h3>Negăsite în documente</h3><ul class="lipsa">${negasite.map((c) => `<li><span class="mono">${esc((c.pentru || []).join(", "))}</span>
        <span>${esc(numeCamp(c.camp))} <span class="muted">· se aștepta în ${esc((c.documente_asteptate || []).join(", ") || "—")}</span></span>
        ${c.obligatoriu ? `<span class="pill">obligatoriu</span>` : ""}</li>`).join("")}</ul>` : "";
  return `<dl class="kv">${gasite.map(rand).join("") || `<div class="empty">Nu s-a extras niciun câmp.</div>`}</dl>${lipsa}${chiriasi}${afirmatii}`;
}

// ------------------------------------------------------------------ evenimente
document.addEventListener("click", (ev) => {
  const t = ev.target;
  const filtru = t.closest("[data-filtru]");
  if (filtru) {
    S.filtru = filtru.dataset.filtru;
    randeazaLista();
    $("#sidebar").classList.remove("open");
    $("#work").dataset.vedere = "lista";
    return;
  }
  const rand = t.closest("[data-dosar]");
  if (rand) { selecteaza(rand.dataset.dosar); return; }
  const sursa = t.closest("[data-url]");
  if (sursa) { previzualizeaza(sursa.dataset.url, sursa.dataset.fisier, sursa.dataset.pagina); return; }
  const tab = t.closest("[data-tab]");
  if (tab) { S.tab[S.selectat] = tab.dataset.tab; randeazaDetaliu(); return; }
  const decizie = t.closest("[data-decizie]");
  if (decizie) { decide(S.selectat, decizie.dataset.decizie); return; }
  const act = t.closest("[data-act]");
  if (!act) return;
  const id = S.selectat;
  switch (act.dataset.act) {
    case "deschide": deschideSolutia(id); break;
    case "confirma": if (S.confirmare) decide(S.confirmare.id, S.confirmare.decizie, true); break;
    case "renunta": S.confirmare = null; randeazaDetaliu(); break;
    case "inapoi": $("#work").dataset.vedere = "lista"; window.scrollTo(0, 0); break;
    case "reincarca": incarcaLista(); break;
    case "reincarca-dosar": incarcaDetalii(id); break;
  }
});

document.addEventListener("input", (ev) => {
  if (ev.target.id === "comentariu" && S.selectat) S.comentariu[S.selectat] = ev.target.value;
});

document.addEventListener("keydown", (ev) => {
  const rand = ev.target.closest && ev.target.closest("tr[data-url]");
  if (rand && (ev.key === "Enter" || ev.key === " ")) {
    ev.preventDefault();
    previzualizeaza(rand.dataset.url, rand.dataset.fisier, null);
  }
});

$("#reset").addEventListener("click", reseteaza);
$("#preview-inchide").addEventListener("click", () => $("#preview").close());
$("#preview").addEventListener("close", () => { $("#preview-body").innerHTML = ""; });
$(".menu-toggle").addEventListener("click", () => $("#sidebar").classList.add("open"));
$(".menu-close").addEventListener("click", () => $("#sidebar").classList.remove("open"));

// ------------------------------------------------------------------ pornire
(async function porneste() {
  await Promise.all([incarcaStare(), incarcaLista()]);
  const dinAdresa = decodeURIComponent(location.hash.slice(1));
  const primul = S.dosare.find((d) => d.id === dinAdresa) || S.dosare.find((d) => d.status === "in_asteptare") || S.dosare[0];
  if (primul) {
    await selecteaza(primul.id, { push: false });
    // pe telefon pagina începe cu lista
    if (!dinAdresa) $("#work").dataset.vedere = "lista";
  }
})();
