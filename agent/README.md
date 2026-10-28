# Modulul D: Agentul

- `orchestrator.py`: bucla: extrage → (planificator decide → registry.apeleaza) × N → decide_verdict.
- `planner.py`: „creierul”. Două variante cu aceeași interfață: **scriptat** (fără LLM, plasă de siguranță)
  și **LLM** (tool calling, varianta agentică pentru juriu).
- `actiuni.py`: tools care produc ceva pentru oameni: `cere_date_client`, `escaladeaza`.
- `prompts/system_prompt.md`: instrucțiunile agentului.

**Regula de aur:** LLM-ul nu scrie verdictul. Îl calculează `engine/verdict.py`.



