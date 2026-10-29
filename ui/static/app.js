/* Green Proof: aleg dosarul -> 1. Fișiere -> 2. Raport -> 3. Decizie.
   Pagina afișează ce întoarce serverul (ui/server.py, ui/raport.py) și trimite deciziile; verdictul, raportul,
   dovezile și validarea deciziei vin din API. Pe ecran stă doar pasul curent, restul e la un clic. */
"use strict";

// ------------------------------------------------------------------ texte de afișare
const STATUS = { in_asteptare: "În așteptare", aprobat: "Aprobat", respins: "Respins", interventie: "Intervenție umană" };
const FILTRE = [
  ["toate", "Toate"], ["in_asteptare", "În așteptare"], ["aprobat", "Aprobate"],
  ["respins", "Respinse"], ["interventie", "Intervenție umană"],
];
const GOL_FILTRU = {
  toate: "Niciun dosar", in_asteptare: "Niciun dosar în așteptare", aprobat: "Niciun dosar aprobat",
  respins: "Niciun dosar respins", interventie: "Niciun dosar la intervenție umană",
};
const BUTON = { aprobat: "Aprobă", respins: "Respinge", interventie: "Intervenție umană" };
const RECOMANDARE = {
  aprobat: "Aprobare", aprobat_conditionat: "Aprobare condiționată", respins: "Respingere", interventie: "Intervenție umană",
};
const DUPA_DECIZIE = { aprobat: "Dosar aprobat", respins: "Dosar respins", interventie: "Dosar trimis la intervenție umană" };
const CLASA_REZULTAT = { OK: "pos", NU: "neg", SEMNAL: "warn", NEEVALUABIL: "neutru", OK_CONDITIONAT: "warn" };
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
  echipament_combustibil_fosil: "Echipament pe combustibil fosil", vehicule: "Vehicule",
};
const UNITATE = {
  suma_eur: "EUR", ped_kwh_m2: "kWh/m²/an", energie_finala_kwh_m2: "kWh/m²/an", suprafata_m2: "m²",
  capacitate_mw: "MW", productie_anuala_mwh: "MWh/an", consum_inainte_mwh: "MWh/an", consum_dupa_mwh: "MWh/an",
};

// ------------------------------------------------------------------ stare
const S = {
  dosare: [], filtru: null, selectat: null, detalii: {},
  rezultate: {},          // rezultatul agentului (cu dovezile pe documente), generat în această sesiune
  rapoarte: {},           // raportul structurat (ui/raport.py)
  pas: {}, maxPas: {},    // pasul curent și cel mai departe pas deschis, pe dosar
  deschise: new Set(),    // secțiuni și rânduri desfășurate
  viz: null,              // fișierul previzualizat în panou
  alegere: {}, comentariu: {}, confirmare: null, mesaj: {}, lucreaza: false,
  ultimaCheie: "",        // dosar+pas randat ultima dată, ca tranziția să ruleze doar la schimbare
  raportNou: null,        // raportul tocmai generat: secțiunile apar în ordine
};
const $ = (sel) => document.querySelector(sel);
const app = () => $("#app");

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
  // listele (chiriași, vehicule, afirmații): câte un element pe rând
  if (Array.isArray(v)) {
    return `<ul class="lista-valori">${v.map((x) => {
      if (x && typeof x === "object" && "nume" in x) {
        const parti = [x.caen ? `CAEN ${x.caen}` : null, typeof x.m2 === "number" ? `${nrRo(x.m2)} m²` : null].filter(Boolean);
        return `<li>${esc(x.nume)}${parti.length ? ` <span class="muted">(${parti.join(", ")})</span>` : ""}</li>`;
      }
      return `<li>${x && typeof x === "object" ? perechi(x) : esc(x)}</li>`;
    }).join("")}</ul>`;
  }
  if (typeof v === "object") return perechi(v);
  return esc(v);
}
// un obiect fără nume (ex. un vehicul) se citește ca „cheie: valoare · …”, nu ca JSON lipit
const perechi = (o) => Object.entries(o).filter(([, x]) => x !== null && x !== undefined && x !== "")
  .map(([k, x]) => `<span class="muted">${esc(k.replace(/_/g, " "))}:</span> ${esc(typeof x === "number" ? nrRo(x, Number.isInteger(x) ? 0 : 1)
    : typeof x === "object" ? JSON.stringify(x) : x)}`).join(" · ");
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
  const inainte = Object.fromEntries(FILTRE.map(([f]) => [f, numar(f)]));
  try {
    S.dosare = await api("/api/dosare");
  } catch (e) {
    $("#nav").innerHTML = `<p class="eroare">Serverul nu răspunde. <button class="link" data-act="reincarca">Reîncearcă</button></p>`;
    return;
  }
  randeazaNav();
  randeazaLista();
  // numerele care s-au schimbat după o decizie se evidențiază scurt
  if (S.dosare.length) {
    for (const [f] of FILTRE) {
      if (inainte[f] !== undefined && inainte[f] !== numar(f) && S.dosare.length) {
        const el = document.querySelector(`[data-filtru="${f}"] .nr`);
        if (el) { el.classList.add("schimbat"); setTimeout(() => el.classList.remove("schimbat"), 1200); }
      }
    }
  }
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
  const intra = app().dataset.stare === "start";
  S.filtru = f;
  const telefon = window.matchMedia("(max-width: 860px)").matches;
  app().dataset.stare = S.selectat && !telefon ? "dosar" : "lista";
  randeazaNav();
  randeazaLista();
  if (intra) {
    const el = $("#lista-interior");
    el.classList.remove("intra");
    void el.offsetWidth;
    el.classList.add("intra");
  }
  randeazaPanou();
}

async function selecteaza(id) {
  S.selectat = id;
  S.viz = null;
  S.confirmare = null;
  S.mesaj[id] = null;
  S.pas[id] = S.pas[id] || 1;
  S.maxPas[id] = S.maxPas[id] || 1;
  app().dataset.stare = "dosar";
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
  $(".zona").scrollTop = 0;
}

async function genereazaRaport(id) {
  S.lucreaza = true;
  S.mesaj[id] = null;
  randeazaPanou();
  try {
    S.rezultate[id] = await api(`${caleDosar(id)}/evaluare`, { method: "POST" });
    S.rapoarte[id] = await api(`${caleDosar(id)}/raport`);
    S.maxPas[id] = Math.max(S.maxPas[id] || 1, 2);
    S.pas[id] = 2;
    S.raportNou = id;
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
  let reusit = false;
  try {
    await api(`${caleDosar(id)}/decizie`, {
      method: "POST",
      body: JSON.stringify({ decizie, comentariu: (S.comentariu[id] || "").trim(), confirmat }),
    });
    S.confirmare = null;
    S.alegere[id] = null;
    S.comentariu[id] = "";
    reusit = true;
  } catch (e) {
    if (e.status === 409 && e.detaliu && e.detaliu.necesita_confirmare) {
      S.confirmare = {
        id, decizie, recomandare: e.detaliu.recomandare_agent,
        eticheta: e.detaliu.recomandare_eticheta, motive: e.detaliu.motive || [],
      };
    } else {
      S.mesaj[id] = { tip: "eroare", text: e.message };
    }
  }
  S.lucreaza = false;
  await Promise.all([incarcaLista(), incarcaDetalii(id)]);
  if (reusit) arataToast(DUPA_DECIZIE[decizie], id);
}

let cronometruToast = null;
function arataToast(text, id) {
  const t = $("#toast");
  t.innerHTML = `<span>${esc(text)}</span>${id ? `<button type="button" data-act="anuleaza" data-id="${esc(id)}">Anulează</button>` : ""}`;
  t.hidden = false;
  clearTimeout(cronometruToast);
  cronometruToast = setTimeout(() => { t.hidden = true; }, 6000);
}

async function anuleazaDecizia(id) {
  $("#toast").hidden = true;
  try {
    await api(`${caleDosar(id)}/decizie`, { method: "DELETE" });
  } catch (e) {
    arataToast(`Anularea nu a reușit: ${e.message}`);
    return;
  }
  await Promise.all([incarcaLista(), incarcaDetalii(id)]);
  arataToast("Decizie anulată");
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
  try { await api("/api/decizii", { method: "DELETE" }); } catch (e) { arataToast(`Resetarea nu a reușit: ${e.message}`); return; }
  S.mesaj = {};
  S.confirmare = null;
  await incarcaLista();
  if (S.selectat) await incarcaDetalii(S.selectat);
}

function comutaConcentrare(activ) {
  app().dataset.concentrare = String(activ);
  const b = $("[data-act='concentrare']");
  if (b) {
    b.textContent = activ ? "⤡" : "⤢";
    b.setAttribute("aria-label", activ ? "Ieși din modul concentrare" : "Mod concentrare");
    b.title = activ ? "Ieși din modul concentrare (Esc)" : "Mod concentrare";
  }
}

// ------------------------------------------------------------------ randare: filtre și listă
const numar = (f) => (f === "toate" ? S.dosare.length : S.dosare.filter((d) => d.status === f).length);

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
  $("#nav").innerHTML = FILTRE.map(([f, et]) =>
    `<button class="filtru" type="button" data-filtru="${f}" aria-current="${S.filtru === f}" title="${et}">
      <span class="punct ${f}"></span><span class="et">${et}</span><span class="nr">${numar(f)}</span></button>`,
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
  }).join("") : `<p class="gol-lista">${GOL_FILTRU[S.filtru]}</p>`;
}

// ------------------------------------------------------------------ randare: panoul dosarului
function randeazaPanou() {
  const el = $("#panou");
  const id = S.selectat;
  const cap = `<div class="panou-cap"><span class="eticheta-col">Dosar</span>${id ? `<button class="icon-btn concentrare" type="button"
    data-act="concentrare" aria-label="Mod concentrare" title="Mod concentrare">⤢</button>` : ""}</div>`;
  if (!id) {
    el.innerHTML = `${cap}<p class="gol">${S.filtru ? "Alege un dosar din listă" : "Alege un filtru din stânga"}</p>`;
    return;
  }
  const d = S.detalii[id];
  if (!d) return;
  if (d.eroare) {
    el.innerHTML = `${cap}<p class="gol">Dosarul nu a putut fi încărcat. <button class="link" data-act="reincarca-dosar">Reîncearcă</button></p>`;
    return;
  }
  const { nume, sufix } = numeAfisat(S.dosare.find((x) => x.id === id) || { id, proiect: d.proiect });
  const pas = S.pas[id] || 1;
  const max = S.maxPas[id] || 1;
  const pasi = [[1, "Fișiere"], [2, "Raport"], [3, "Decizie"]].map(([n, et]) =>
    `<button class="pas-btn ${n < pas ? "gata" : ""}" type="button" data-pas="${n}" ${n > max ? "disabled" : ""}
      ${n === pas ? 'aria-current="step"' : ""}><span class="cerc">${n < pas ? "✓" : n}</span><span class="txt">${et}</span></button>`,
  ).join("");

  let corp;
  if (S.viz) corp = randeazaVizualizare();
  else if (pas === 1) corp = pasFisiere(id, d);
  else if (pas === 2) corp = pasRaport(id);
  else corp = pasDecizie(id, d);

  // tranziția rulează doar când se schimbă dosarul sau pasul, nu la fiecare desfășurare
  const cheie = `${id}|${pas}|${S.viz ? "viz" : ""}`;
  const anim = cheie !== S.ultimaCheie;
  S.ultimaCheie = cheie;

  el.innerHTML = `${cap}
    <div class="continut ${anim ? "apare" : ""}">
      <button class="btn inapoi" type="button" data-act="inapoi">← Dosare</button>
      <header class="antet">
        <h2>${esc(nume)}${sufix ? `<span class="muted">${esc(sufix)}</span>` : ""}</h2>
        <span class="status"><span class="punct ${d.status}"></span>${STATUS[d.status]}</span>
      </header>
      <nav class="pasi-nav" aria-label="Pași" style="--progres:${(pas - 1) / 2}"><span class="pista"></span><span class="umplere"></span>${pasi}</nav>
      ${corp}
    </div>`;
  comutaConcentrare(app().dataset.concentrare === "true");

  const zona = el.querySelector("textarea");
  if (zona) zona.value = S.comentariu[id] || "";
  if (S.raportNou === id && pas === 2) S.raportNou = null;
}

function pasFisiere(id, d) {
  const ordonate = [...d.documente].sort((a, b) => (a.provenienta === "client" ? 0 : 1) - (b.provenienta === "client" ? 0 : 1));
  const fisiere = ordonate.map((doc) => `<li><button class="fisier" type="button" data-url="${esc(doc.url)}" data-fisier="${esc(doc.fisier)}">
      <span class="nume-f">${esc(doc.fisier)}</span><span class="tip">${esc(tipScurt(doc))}</span></button></li>`).join("");
  const cheie = `lipsa:${id}`;
  const deschis = S.deschise.has(cheie);
  const n = d.documente_lipsa.length;
  const lipsa = n ? `
    <button class="cap" type="button" data-comuta="${cheie}" aria-expanded="${deschis}">
      <span class="sageata">▶</span><span class="muted">${n} ${n === 1 ? "document lipsă" : "documente lipsă"}</span></button>
    ${deschis ? `<ul class="lipsa-lista">${d.documente_lipsa.map((x) => `<li><span class="mono">${esc(x.id)}</span><span>${esc(x.nume)}</span></li>`).join("")}</ul>` : ""}` : "";
  const eroare = S.mesaj[id] && S.mesaj[id].tip === "eroare" ? `<p class="eroare" role="alert">${esc(S.mesaj[id].text)}</p>` : "";
  const buton = S.lucreaza
    ? `<button class="btn primary" type="button" disabled><span class="rotita" aria-hidden="true"></span>Se analizează…</button>`
    : `<button class="btn primary" type="button" data-act="genereaza">Generează raportul</button>`;
  return `<ul class="randuri">${fisiere || `<li class="muted">Niciun fișier.</li>`}</ul>${lipsa}
    <div class="actiuni-pas">${buton}</div>${S.lucreaza ? `<div class="progres" role="progressbar" aria-label="Agentul analizează dosarul"></div>` : ""}${eroare}`;
}

function sectiune(cheie, titlu, numarEl, continut) {
  const deschis = S.deschise.has(cheie);
  return `<section class="sectiune">
    <button class="cap" type="button" data-comuta="${cheie}" aria-expanded="${deschis}">
      <span class="sageata">▶</span>${titlu}<span class="nr num">${numarEl}</span></button>
    ${deschis ? `<div class="corp">${continut()}</div>` : ""}</section>`;
}

// închis: un rând cu „…”; deschis: textul complet pe mai multe rânduri
function randPliabil(cheie, id, scurt, dreapta, continut) {
  const deschis = S.deschise.has(cheie);
  return `<div class="rand">
    <button class="rand-cap" type="button" data-comuta="${cheie}" aria-expanded="${deschis}">
      <span class="sageata">▶</span><span class="id">${id}</span><span class="scurt">${scurt}</span><span class="dreapta">${dreapta}</span></button>
    ${deschis ? `<div class="rand-corp">${continut()}</div>` : ""}</div>`;
}

const legaturaSursa = (c) => c.url
  ? `<button class="link" type="button" data-url="${esc(c.url)}" data-fisier="${esc(c.fisier)}" data-pagina="${c.pagina ?? ""}">${esc(c.fisier)}${c.pagina ? `, p. ${c.pagina}` : ""}</button>`
  : esc(c.sursa || "");

function elementRaport(id, sectiuneCheie, x, k) {
  const rez = S.rezultate[id];
  if (x.tip === "regula") {
    const vazute = new Set();
    const surse = ((rez && rez.dovezi[x.id]) || []).filter((c) => c.url && !vazute.has(`${c.fisier}#${c.pagina}`) && vazute.add(`${c.fisier}#${c.pagina}`));
    const eticheta = sectiuneCheie === "de_verificat" ? `<span class="rezultat ${CLASA_REZULTAT[x.rezultat] || "neutru"}">${esc(x.eticheta_rezultat)}</span>` : "";
    return randPliabil(`r:${id}:${sectiuneCheie}:${x.id}`, esc(x.id), `${esc(x.nume)} <span class="muted">· ${esc(x.dovada)}</span>`,
      `${eticheta}<span class="pag">${esc(x.pagina)}</span>`,
      () => `<p>${esc(x.dovada)}</p>
        <p class="muted">${esc(x.nume)} · <span class="rezultat ${CLASA_REZULTAT[x.rezultat] || "neutru"}">${esc(x.eticheta_rezultat)}</span> · Framework: ${esc(x.pagina)}</p>
        ${surse.length ? `<p class="muted">Documente: ${surse.map(legaturaSursa).join(" · ")}</p>` : ""}`);
  }
  if (x.tip === "document") {
    return randPliabil(`r:${id}:doc:${x.id}`, esc(x.id), esc(x.nume), `<span class="pag">${esc(x.actiune)}</span>`,
      () => `<p>${esc(x.nume)}</p><p class="muted">${x.obligatoriu ? "Obligatoriu" : "Recomandat"} · Acțiune: ${esc(x.actiune)}</p>`);
  }
  return randPliabil(`r:${id}:act:${k}`, "", esc(x.text), "", () => `<p>${esc(x.text)}</p>`);
}

// eticheta din dreapta rândului: statusul pasului sau, la evaluări, rezultatele regulilor
function etichetaPas(st) {
  if (st.reguli && st.reguli.length) {
    if (st.reguli.length === 1) return `<span class="rezultat ${CLASA_REZULTAT[st.reguli[0].rezultat] || "neutru"}">${esc(st.reguli[0].id)} ${esc(st.reguli[0].eticheta)}</span>`;
    const pe = {};
    for (const x of st.reguli) (pe[x.rezultat] = pe[x.rezultat] || []).push(x);
    return Object.entries(pe).map(([rz, xs]) => `<span class="rezultat ${CLASA_REZULTAT[rz] || "neutru"}">${xs.length} ${esc(xs[0].eticheta)}</span>`).join("");
  }
  if (st.cheie === "efectuat") return "";
  const icon = st.cheie === "eroare" ? `<span class="icon-eroare" aria-hidden="true">!</span>` : "";
  return `<span class="rezultat ${st.clasa}">${icon}${esc(st.eticheta)}</span>`;
}

function pasRaport(id) {
  const r = S.rezultate[id];
  const raport = S.rapoarte[id];
  if (!r || !raport) return `<p class="muted">Raportul nu a fost generat.</p>`;
  const v = r.verdict;
  const d = S.detalii[id];
  const nou = S.raportNou === id;
  let i = 0;
  const bloc = (continut) => `<div class="bloc ${nou ? "intra" : ""}" style="--i:${i++}">${continut}</div>`;

  const rec = raport.recomandare;
  const eticheta = rec ? `<span class="rec-pastila rec-${esc(rec.cheie)}"><span class="rec-marcaj" aria-hidden="true"></span>${esc(rec.eticheta)}</span>` : "";
  const parti = [bloc(`<h3 class="titlu-bloc">Concluzie ${eticheta}</h3>
    <div class="concluzie">${raport.concluzie.map((p) => `<p>${esc(p)}</p>`).join("")}</div>
    ${r.din_salvare ? `<p class="salvat">Rezultat salvat la ${dataRo(r.salvat_la)}</p>` : ""}`)];

  for (const s of raport.sectiuni) {
    const total = s.grupuri.reduce((n, g) => n + g.elemente.length, 0);
    const grupuri = s.grupuri.map((g) => `<p class="grup">${esc(g.titlu)}</p>
      <div class="elemente">${g.elemente.map((x, k) => elementRaport(id, s.cheie, x, `${g.cheie}${k}`)).join("")}</div>`).join("");
    parti.push(bloc(`<h3 class="titlu-bloc"><span class="semn ${s.cheie}" aria-hidden="true">${esc(s.semn)}</span>${esc(s.titlu)}<span class="nr num">${total}</span></h3>${grupuri}`));
  }

  const imp = raport.impact;
  if (imp) {
    const metoda = [imp.formula ? "formula RBI" : "", imp.sursa].filter(Boolean).join(", ");
    const cheieCalcul = `calcul:${id}`;
    const calcul = imp.pasi.length ? `<div class="elemente">${randPliabil(cheieCalcul, "", "Calculul pas cu pas", "",
      () => `${imp.formula ? `<p class="mono">${esc(imp.formula)}</p>` : ""}${imp.pasi.map((p) => `<p class="muted mono">${esc(p)}</p>`).join("")}`)}</div>` : "";
    parti.push(bloc(`<h3 class="titlu-bloc">Impact</h3>
      <div class="impact"><span class="valoare">${nrRo(imp.tco2_an, 1)}<small>tCO₂/an</small></span>
        ${imp.mwh_an !== null && imp.mwh_an !== undefined ? `<span class="valoare">${nrRo(imp.mwh_an, 1)}<small>MWh/an</small></span>` : ""}</div>
      ${metoda ? `<p class="metoda">${esc(metoda)}</p>` : ""}
      ${imp.proxy ? `<p class="proxy">Valori de referință aproximative (proxy)</p>` : ""}${calcul}`));
  }
  if (raport.referinte.length) {
    parti.push(bloc(`<h3 class="titlu-bloc">Referințe Framework</h3><ul class="referinte">${raport.referinte.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`));
  }

  const date = () => `<dl class="date">${d.campuri.map((c) =>
    `<dt>${esc(numeCamp(c.camp))}</dt><dd>${valoareCamp(c.camp, c.valoare)}</dd><dd class="sursa">${c.valoare === null || c.valoare === undefined ? "" : legaturaSursa(c)}</dd>`,
  ).join("")}</dl>`;
  // starea fiecărui pas vine calculată de server din câmpurile structurate (ui/pasi.py), nu din textul rezumatului
  const pasiAgent = () => v.trace.map((p, i) => {
    const st = (r.pasi || [])[i];
    const actiune = p.actiune ? (UNEALTA[p.actiune] || p.actiune.replace(/_/g, " ")) : "Concluzie";
    return randPliabil(`pas:${id}:${p.pas}`, p.pas, esc(actiune), st ? etichetaPas(st) : "", () => {
      const argumente = Object.entries(p.argumente || {}).map(([k, x]) => `${k}: ${typeof x === "object" ? JSON.stringify(x) : x}`).join(" · ");
      const reguli = st && st.reguli && st.reguli.length
        ? `<p>${st.reguli.map((x) => `<span class="mono">${esc(x.id)}</span> <span class="rezultat ${CLASA_REZULTAT[x.rezultat] || "neutru"}">${esc(x.eticheta)}</span>`).join(" · ")}</p>` : "";
      const sursa = st && st.sursa ? `<p class="muted">Valoarea din dosar: ${valoareCamp(st.sursa.camp, st.sursa.valoare)} · ${legaturaSursa(st.sursa)}</p>` : "";
      const detaliu = st && st.detaliu ? `<p class="muted">${esc(st.detaliu)}</p>` : "";
      return `<p>${esc(p.motiv || "")}</p>${argumente ? `<p class="muted mono">${esc(argumente)}</p>` : ""}${reguli}${sursa}${detaliu}`;
    });
  }).join("");

  return `<div class="raport">${parti.join("")}</div>
    <div class="sectiuni">
      ${sectiune(`sec:${id}:date`, "Date extrase", d.campuri.length, date)}
      ${sectiune(`sec:${id}:pasi`, "Pașii agentului", v.trace.length, pasiAgent)}
    </div>
    <div class="actiuni-pas">
      <button class="btn primary" type="button" data-act="la-decizie">Ia decizia</button>
      <a class="btn" href="${caleDosar(id)}/raport.html" target="_blank" rel="noopener">Descarcă raportul</a>
    </div>`;
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
    // la confirmare se văd motivele nerezolvate (mai ales când analistul aprobă fără recomandarea „Aprobare”)
    const motiveConfirmare = confirm && S.confirmare.motive && S.confirmare.motive.length
      ? `<ul class="motive">${S.confirmare.motive.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : "";
    const avertizare = confirm
      ? `<div class="avertizare" role="alert"><p>Agentul recomandă ${esc(S.confirmare.eticheta || RECOMANDARE[S.confirmare.recomandare] || "altceva")}.
          Decizia ta va fi marcată ca diferită${motiveConfirmare ? ". Rămân nerezolvate:" : "."}</p>${motiveConfirmare}</div>` : "";
    formular = `<div class="formular">${comentariu}${avertizare}
      <button class="btn primary trimite" type="button" data-act="trimite" ${S.lucreaza ? "disabled" : ""}>${confirm ? `Confirmă: ${BUTON[alegere]}` : "Trimite"}</button></div>`;
  }
  const mesaj = S.mesaj[id] ? `<p class="eroare" role="alert">${esc(S.mesaj[id].text)}</p>` : "";
  const x = d.decizie;
  const decizia = x ? `<p class="decizia-ta">Decizia ta: <b>${STATUS[x.decizie]}</b> · ${dataRo(x.data)}${x.difera_de_agent ? " · diferă de agent" : ""}
      ${x.comentariu ? `<br>„${esc(x.comentariu)}”` : ""}</p>` : "";
  return `${blocRecomandare(r && r.recomandare_detalii)}
    <div class="butoane">${butoane}</div>${formular}${mesaj}${decizia}`;
}

// Recomandarea agentului, doar din verdict (ui/raport.py): eticheta, subtitlul și „De ce?” cu 1-3 motive
function blocRecomandare(rec) {
  if (!rec) return `<p class="recomandat">Agentul recomandă: <b>—</b></p>`;
  const rest = rec.toate_motivele.length - rec.motive.length;
  return `<section class="rec rec-${esc(rec.cheie)}" aria-label="Recomandarea agentului">
    <p class="rec-cap"><span class="rec-marcaj" aria-hidden="true"></span><span class="rec-eticheta">${esc(rec.eticheta)}</span>
      <span class="rec-sub">${esc(rec.subtitlu)}</span></p>
    ${rec.inconsistenta ? `<p class="avertizare" role="alert">${esc(rec.inconsistenta)}.</p>` : ""}
    <p class="de-ce">De ce?</p>
    <ul class="motive">${rec.motive.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>
    ${rest > 0 ? `<p class="muted">Încă ${rest} în raport, la „De verificat”.</p>` : ""}
  </section>`;
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
    (m, sir, douaPuncte, nr, cuvant) => {
      if (sir) return douaPuncte ? `<span class="k">${sir}</span>${douaPuncte}` : `<span class="s">${sir}</span>`;
      return `<span class="n">${nr || cuvant}</span>`;
    },
  );
}

// ------------------------------------------------------------------ evenimente
document.addEventListener("click", (ev) => {
  const t = ev.target;
  if (!t.closest(".meniu")) $("#meniu").hidden = true;
  const anuleaza = t.closest("[data-act='anuleaza']");
  if (anuleaza) { anuleazaDecizia(anuleaza.dataset.id); return; }
  const f = t.closest("[data-filtru]");
  if (f) { alegeFiltru(f.dataset.filtru); return; }
  const dosar = t.closest("[data-dosar]");
  if (dosar) { selecteaza(dosar.dataset.dosar); return; }
  const id = S.selectat;
  const sursa = t.closest("[data-url]");
  if (sursa) {
    S.viz = { url: sursa.dataset.url, fisier: sursa.dataset.fisier, pagina: sursa.dataset.pagina || null };
    randeazaPanou();
    $(".zona").scrollTop = 0;
    return;
  }
  const comuta = t.closest("[data-comuta]");
  if (comuta) {
    const k = comuta.dataset.comuta;
    if (S.deschise.has(k)) S.deschise.delete(k); else S.deschise.add(k);
    randeazaPanou();
    const inapoi = document.querySelector(`[data-comuta="${CSS.escape(k)}"]`);
    if (inapoi) inapoi.focus({ preventScroll: true });
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
    case "concentrare": comutaConcentrare(app().dataset.concentrare !== "true"); break;
    case "inapoi": app().dataset.stare = "lista"; break;
    case "reincarca": incarcaLista(); break;
    case "reincarca-dosar": incarcaDetalii(id); break;
  }
});

document.addEventListener("input", (ev) => {
  if (ev.target.id === "comentariu" && S.selectat) S.comentariu[S.selectat] = ev.target.value;
});

document.addEventListener("keydown", (ev) => {
  if (document.querySelector("dialog[open]")) return;
  if (ev.key === "Escape") {
    if (!$("#meniu").hidden) { $("#meniu").hidden = true; return; }
    if (S.viz) { S.viz = null; randeazaPanou(); return; }
    if (app().dataset.concentrare === "true") { comutaConcentrare(false); return; }
    return;
  }
  // ↑/↓ prin dosare (Enter deschide dosarul care are focusul), cât timp nu se scrie într-un câmp
  if ((ev.key === "ArrowDown" || ev.key === "ArrowUp") && !ev.target.closest("textarea, input")) {
    const randuri = [...document.querySelectorAll("#lista .dosar")];
    if (!randuri.length || app().dataset.stare === "start" || app().dataset.concentrare === "true") return;
    ev.preventDefault();
    const curent = randuri.indexOf(document.activeElement);
    const pornire = curent >= 0 ? curent : randuri.findIndex((r) => r.getAttribute("aria-selected") === "true");
    const urmator = pornire < 0 ? 0 : Math.min(randuri.length - 1, Math.max(0, pornire + (ev.key === "ArrowDown" ? 1 : -1)));
    randuri[urmator].focus();
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
