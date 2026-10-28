"""Registru de unelte (tools) pentru agent și module.

Permite înregistrarea tastată a uneltelor cu `@tool`, validarea argumentelor
prin Pydantic, apelul uniform via `apeleaza(nume, argumente, stare)` și
generarea schemelor pentru apeluri LLM (`schema_pentru_llm`).
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Type

from pydantic import BaseModel, ValidationError

from contracts import StareDosar, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class DefinitieTool:
    nume: str
    descriere: str
    model_intrare: Type[BaseModel] | None
    functie: Callable[..., ToolResult]


TOOLS: dict[str, DefinitieTool] = {}


def tool(
    nume: str,
    descriere: str = "",
    model_intrare: Type[BaseModel] | None = None,
) -> Callable[[Callable[..., ToolResult]], Callable[..., ToolResult]]:
    """Decorator pentru înregistrarea unei unelte în registru.

    Poate fi folosit ca:
        @tool("verifica_firma", "Verifica CUI la ANAF", ModelInput)
        def func(intrare: ModelInput, stare: StareDosar) -> ToolResult:
            ...
    sau:
        @tool("verifica_firma")
        def func(intrare: ModelInput, stare: StareDosar) -> ToolResult:
            ...
    """

    def decorator(fn: Callable[..., ToolResult]) -> Callable[..., ToolResult]:
        nonlocal descriere, model_intrare

        if not descriere and fn.__doc__:
            descriere = fn.__doc__.strip()

        # Daca nu este furnizat explicit modelul de intrare, inspectam semnaturile
        if model_intrare is None:
            sig = inspect.signature(fn)
            params = list(sig.parameters.values())
            if params:
                first_param = params[0]
                if (
                    isinstance(first_param.annotation, type)
                    and issubclass(first_param.annotation, BaseModel)
                    and first_param.annotation is not StareDosar
                ):
                    model_intrare = first_param.annotation

        TOOLS[nume] = DefinitieTool(
            nume=nume,
            descriere=descriere or "",
            model_intrare=model_intrare,
            functie=fn,
        )
        return fn

    return decorator


def _asigura_inregistrare_tools() -> None:
    """Importă modulele cunoscute de tools pentru a se asigura înregistrarea lor."""
    module_de_incarcat = [
        "tools.anaf",
        "tools.breeam",
        "engine.reguli",
        "engine.co2",
        "agent.actiuni",
    ]
    for mod in module_de_incarcat:
        try:
            __import__(mod)
        except ImportError as e:
            logger.debug("Modulul %s nu a putut fi importat la inițializare: %s", mod, e)


def apeleaza(
    nume: str,
    argumente: dict[str, Any] | BaseModel | None,
    stare: StareDosar,
) -> ToolResult:
    """Apelează o unealtă după nume, validând argumentele și tratând erorile."""
    _asigura_inregistrare_tools()

    if nume not in TOOLS:
        msg = f"Tool necunoscut: '{nume}'"
        logger.warning(msg)
        return ToolResult(tool=nume, gasit=False, eroare=msg)

    definitie = TOOLS[nume]
    model_cls = definitie.model_intrare

    # 1. Validarea argumentelor
    intrare_validata: Any = argumente
    if model_cls is not None:
        if argumente is None:
            argumente = {}
        if isinstance(argumente, model_cls):
            intrare_validata = argumente
        elif isinstance(argumente, dict):
            try:
                intrare_validata = model_cls.model_validate(argumente)
            except ValidationError as ve:
                err_msg = f"Eroare validare argumente pentru tool '{nume}': {ve}"
                logger.error(err_msg)
                return ToolResult(tool=nume, gasit=False, eroare=err_msg)
        else:
            err_msg = f"Tip de argumente invalid pentru tool '{nume}': {type(argumente).__name__}"
            logger.error(err_msg)
            return ToolResult(tool=nume, gasit=False, eroare=err_msg)
    else:
        if argumente is None:
            intrare_validata = {}

    # 2. Execuția funcției
    try:
        sig = inspect.signature(definitie.functie)
        param_count = len(sig.parameters)

        if param_count == 1:
            rezultat = definitie.functie(stare)
        elif param_count == 2:
            rezultat = definitie.functie(intrare_validata, stare)
        else:
            if isinstance(intrare_validata, BaseModel):
                kwargs = intrare_validata.model_dump()
            elif isinstance(intrare_validata, dict):
                kwargs = intrare_validata
            else:
                kwargs = {}
            rezultat = definitie.functie(stare=stare, **kwargs)

        if not isinstance(rezultat, ToolResult):
            err_msg = f"Tool-ul '{nume}' a întors o valoare invalidă (nu este ToolResult): {type(rezultat)}"
            logger.error(err_msg)
            return ToolResult(tool=nume, gasit=False, eroare=err_msg)

        return rezultat

    except Exception as exc:
        err_msg = f"Eroare la execuția tool-ului '{nume}': {exc}"
        logger.exception(err_msg)
        return ToolResult(tool=nume, gasit=False, eroare=err_msg)


def schema_pentru_llm() -> list[dict[str, Any]]:
    """Generează schema JSON a tuturor tool-urilor înregistrate, pentru LLM."""
    _asigura_inregistrare_tools()

    scheme: list[dict[str, Any]] = []
    for nume, tool_def in TOOLS.items():
        if tool_def.model_intrare is not None:
            parametri = tool_def.model_intrare.model_json_schema()
        else:
            parametri = {"type": "object", "properties": {}}

        scheme.append({
            "type": "function",
            "function": {
                "name": nume,
                "description": tool_def.descriere or "",
                "parameters": parametri,
            },
        })
    return scheme
