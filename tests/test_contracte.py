"""Teste de contract și integrare pentru sistemul de orchestrare și evaluare."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agent.orchestrator import _decide_verdict, _executa_bucla, proceseaza_dosar
from agent.planner import Decizie
from contracts import Camp, DosarExtras, RezultatRegula, StareDosar, ToolResult, Verdict
from engine.verdict import decide_verdict
from eval.run_eval import compara_verdict_cu_asteptat
from registry import apeleaza, schema_pentru_llm, tool


def _creeaza_stare_test(dosar_id: str = "test_dosar") -> StareDosar:
    extras = DosarExtras(
        dosar_id=dosar_id,
        cui=Camp(valoare="12345678", sursa="test"),
        suma_eur=Camp(valoare=1000000, sursa="test"),
        cota_banca=Camp(valoare=0.5, sursa="test"),
        data_aprobare=Camp(valoare="2026-01-01", sursa="test"),
        tara=Camp(valoare="Romania", sursa="test"),
        adresa_cladire=Camp(valoare="Strada Test nr 1", sursa="test"),
        suprafata_m2=Camp(valoare=5000, sursa="test"),
        stadiu_cladire=Camp(valoare="Finalizata", sursa="test"),
        nr_certificat_declarat=Camp(valoare="CERT-123", sursa="test"),
    )
    return StareDosar(
        dosar_folder="dosare/dosar_01_complet_eligibil",
        extras=extras,
    )


# ---------------------------------------------------------------------------
# Teste de contract comune
# ---------------------------------------------------------------------------

def test_extrage_mock_pe_toate_dosarele():
    """Verifică că extras_mock.json din toate dosarele se încarcă ca DosarExtras."""
    cale_dosare = Path("dosare")
    foldere = [f for f in cale_dosare.iterdir() if f.is_dir() and (f / "extras_mock.json").exists()]

    assert len(foldere) >= 4

    for folder in foldere:
        with open(folder / "extras_mock.json", "r", encoding="utf-8") as f:
            date = json.load(f)
        extras = DosarExtras(**date)
        assert extras.dosar_id == folder.name
        assert isinstance(extras.cui, Camp)


def test_schema_pentru_llm_format():
    """Verifică că schema_pentru_llm() produce formatul valid pentru unelte LLM."""
    scheme = schema_pentru_llm()
    assert isinstance(scheme, list)
    assert len(scheme) > 0

    for s in scheme:
        assert s.get("type") == "function"
        assert "function" in s
        assert "name" in s["function"]
        assert "parameters" in s["function"]


# ---------------------------------------------------------------------------
# 1. Successful orchestration
# ---------------------------------------------------------------------------

def test_successful_orchestration():
    dosar_path = "dosare/dosar_01_complet_eligibil"
    verdict = proceseaza_dosar(dosar_path)

    assert isinstance(verdict, Verdict)
    assert verdict.verdict == "ELIGIBIL"
    assert verdict.cale_eligibilitate is not None
    assert "GB-01" in verdict.cale_eligibilitate
    assert verdict.impact_tco2_an == 606.0
    assert len(verdict.trace) > 0

    for intrare in verdict.trace:
        assert "pas" in intrare
        assert "tip" in intrare
        assert "timestamp" in intrare


# ---------------------------------------------------------------------------
# 2. Missing extras_mock.json
# ---------------------------------------------------------------------------

def test_missing_extras_mock():
    with pytest.raises(FileNotFoundError) as exc_info:
        proceseaza_dosar("dosare/dosar_complet_inexistent_999")

    assert "extras_mock.json nu există" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. Unknown tool
# ---------------------------------------------------------------------------

def test_unknown_tool():
    stare = _creeaza_stare_test()
    rezultat = apeleaza("tool_complet_necunoscut_xyz", {}, stare)

    assert isinstance(rezultat, ToolResult)
    assert rezultat.tool == "tool_complet_necunoscut_xyz"
    assert rezultat.gasit is False
    assert rezultat.eroare is not None
    assert "Tool necunoscut" in rezultat.eroare


# ---------------------------------------------------------------------------
# 4. Tool failure
# ---------------------------------------------------------------------------

def test_tool_failure():
    stare = _creeaza_stare_test()

    @tool("tool_test_care_esueaza")
    def tool_defect(stare: StareDosar) -> ToolResult:
        raise RuntimeError("Defecțiune forțată pentru test")

    rezultat = apeleaza("tool_test_care_esueaza", {}, stare)

    assert isinstance(rezultat, ToolResult)
    assert rezultat.gasit is False
    assert rezultat.eroare is not None
    assert "Defecțiune forțată" in rezultat.eroare


# ---------------------------------------------------------------------------
# 5. Final planner decision
# ---------------------------------------------------------------------------

def test_final_planner_decision():
    stare = _creeaza_stare_test()

    class MockPlanificatorFinal:
        def pas_urmator(self, st, ultim_rez):
            return Decizie(tip="final", motiv="Oprire imediată solicitată")

    with patch("agent.orchestrator._obtine_planificator", return_value=MockPlanificatorFinal()):
        _executa_bucla(stare)

    assert len(stare.trace) == 1
    assert stare.trace[0]["tip"] == "final"
    assert stare.trace[0]["rezultat"] == "final"
    assert stare.escaladat is False


# ---------------------------------------------------------------------------
# 6. Automatic step-limit escalation
# ---------------------------------------------------------------------------

def test_automatic_step_limit_escalation():
    stare = _creeaza_stare_test()

    @tool("tool_inutil_loop")
    def tool_inutil(stare: StareDosar) -> ToolResult:
        return ToolResult(tool="tool_inutil_loop", gasit=True)

    class MockPlanificatorInfinit:
        def pas_urmator(self, st, ultim_rez):
            return Decizie(tip="tool", nume="tool_inutil_loop", motiv="Bucla infinita")

    with patch("agent.orchestrator._obtine_planificator", return_value=MockPlanificatorInfinit()):
        with patch("agent.orchestrator._get_max_pasi", return_value=3):
            _executa_bucla(stare)

    assert stare.escaladat is True
    assert len(stare.trace) == 4
    assert stare.trace[-1]["tip"] == "escaladare_automata"
    assert any("Escaladare automată" in actiune for actiune in stare.actiuni)

    verdict = _decide_verdict(stare)
    assert verdict.verdict == "EXCEPTIE_ESCALADARE_COMITET"


# ---------------------------------------------------------------------------
# 7. Invalid planner decision
# ---------------------------------------------------------------------------

def test_invalid_planner_decision():
    stare = _creeaza_stare_test()

    class MockPlanificatorInvalidTip:
        def pas_urmator(self, st, ultim_rez):
            class ObiectDubios:
                tip = "necunoscut"
            return ObiectDubios()

    with patch("agent.orchestrator._obtine_planificator", return_value=MockPlanificatorInvalidTip()):
        with pytest.raises(ValueError) as exc:
            _executa_bucla(stare)
        assert "Decizie invalidă de la planificator" in str(exc.value)

    class MockPlanificatorFaraNume:
        def pas_urmator(self, st, ultim_rez):
            return Decizie(tip="tool", nume="", motiv="fara nume")

    with patch("agent.orchestrator._obtine_planificator", return_value=MockPlanificatorFaraNume()):
        with pytest.raises(ValueError) as exc:
            _executa_bucla(stare)
        assert "nu are specificat un nume valid de tool" in str(exc.value)


# ---------------------------------------------------------------------------
# 8. Verdict precedence
# ---------------------------------------------------------------------------

def test_verdict_precedence():
    # Precedență 1: regulă obligatorie cu NU => NEELIGIBIL
    stare_nu = _creeaza_stare_test()
    stare_nu.reguli["G-01"] = RezultatRegula(
        regula_id="G-01", rezultat="NU", dovada="Tara interzisa", sursa_framework="Anexa B"
    )
    stare_nu.reguli["GB-01"] = RezultatRegula(
        regula_id="GB-01", rezultat="OK", dovada="BREEAM Excellent", sursa_framework="Framework"
    )
    v_nu = decide_verdict(stare_nu)
    assert v_nu.verdict == "NEELIGIBIL"

    # Precedență 2: SEMNAL sau escaladare => EXCEPTIE_ESCALADARE_COMITET
    stare_semnal = _creeaza_stare_test()
    stare_semnal.reguli["G-01"] = RezultatRegula(regula_id="G-01", rezultat="OK", dovada="", sursa_framework="")
    stare_semnal.reguli["GB-01"] = RezultatRegula(regula_id="GB-01", rezultat="OK", dovada="", sursa_framework="")
    stare_semnal.reguli["GB-X1"] = RezultatRegula(regula_id="GB-X1", rezultat="SEMNAL", dovada="", sursa_framework="")
    v_semnal = decide_verdict(stare_semnal)
    assert v_semnal.verdict == "EXCEPTIE_ESCALADARE_COMITET"

    stare_escaladat = _creeaza_stare_test()
    stare_escaladat.reguli["G-01"] = RezultatRegula(regula_id="G-01", rezultat="OK", dovada="", sursa_framework="")
    stare_escaladat.reguli["GB-01"] = RezultatRegula(regula_id="GB-01", rezultat="OK", dovada="", sursa_framework="")
    stare_escaladat.escaladat = True
    v_escaladat = decide_verdict(stare_escaladat)
    assert v_escaladat.verdict == "EXCEPTIE_ESCALADARE_COMITET"

    # Precedență 3: Cale OK => ELIGIBIL
    stare_ok = _creeaza_stare_test()
    stare_ok.reguli["G-01"] = RezultatRegula(regula_id="G-01", rezultat="OK", dovada="", sursa_framework="")
    stare_ok.reguli["GB-01"] = RezultatRegula(regula_id="GB-01", rezultat="OK", dovada="BREEAM", sursa_framework="")
    v_ok = decide_verdict(stare_ok)
    assert v_ok.verdict == "ELIGIBIL"

    # Precedență 4: Cale OK_CONDITIONAT => ELIGIBIL_CU_MONITORIZARE
    stare_cond = _creeaza_stare_test()
    stare_cond.reguli["G-01"] = RezultatRegula(regula_id="G-01", rezultat="OK", dovada="", sursa_framework="")
    stare_cond.reguli["GB-01"] = RezultatRegula(regula_id="GB-01", rezultat="OK_CONDITIONAT", dovada="Interim", sursa_framework="")
    v_cond = decide_verdict(stare_cond)
    assert v_cond.verdict == "ELIGIBIL_CU_MONITORIZARE"

    # Precedență 5: Fără cale eligibilă => NEELIGIBIL
    stare_fara_cale = _creeaza_stare_test()
    stare_fara_cale.reguli["G-01"] = RezultatRegula(regula_id="G-01", rezultat="OK", dovada="", sursa_framework="")
    stare_fara_cale.reguli["GB-01"] = RezultatRegula(regula_id="GB-01", rezultat="NU", dovada="", sursa_framework="")
    stare_fara_cale.reguli["GB-02"] = RezultatRegula(regula_id="GB-02", rezultat="NEEVALUABIL", dovada="", sursa_framework="")
    stare_fara_cale.reguli["GB-03"] = RezultatRegula(regula_id="GB-03", rezultat="NU", dovada="", sursa_framework="")
    v_fara = decide_verdict(stare_fara_cale)
    assert v_fara.verdict == "NEELIGIBIL"


# ---------------------------------------------------------------------------
# 9. Evaluation mismatch
# ---------------------------------------------------------------------------

def test_evaluation_mismatch():
    verdict = Verdict(
        dosar_id="test_dosar",
        verdict="NEELIGIBIL",
        cale_eligibilitate="GB-01",
        reguli=[RezultatRegula(regula_id="GB-01", rezultat="NU", dovada="", sursa_framework="")],
        impact_tco2_an=100.0,
    )

    asteptat = {
        "verdict": "ELIGIBIL",
        "cale_eligibilitate": "GB-03 (EPC)",
        "reguli": [{"id": "GB-01", "rezultat": "OK"}],
        "impact": {"rezultat_tco2_an": 250.0},
    }

    erori = compara_verdict_cu_asteptat(verdict, asteptat)
    assert len(erori) >= 3
    assert any("Verdict diferit" in e for e in erori)
    assert any("Cale eligibilitate nepotrivită" in e for e in erori)
    assert any("Regula 'GB-01'" in e for e in erori)
    assert any("Impact CO2 diferit" in e for e in erori)
