# Advisor: consultor de setups

Herramienta **independiente del bot** (`src/astra`). No opera, no usa credenciales: solo lee datos públicos.

- **Crypto:** Binance (con fallback a OKX)
- **Acciones:** Yahoo Finance
- **Noticias:** Google News RSS

## Uso desde Claude Code

```
/setup-trader SOL      # evalúa un activo
/setup-trader          # escanea la watchlist y trae los mejores setups
```

El skill está en [`.claude/skills/setup-trader/SKILL.md`](../.claude/skills/setup-trader/SKILL.md). Ahí están las reglas: SL estructural, TP1 en el primer obstáculo, R/R ponderado >= 1:2 y pivote a 2 alternativas.

## Uso directo

```bash
.venv/bin/python advisor/advisor.py analyze NVDA --save
.venv/bin/python advisor/advisor.py scan --top 5 --all
.venv/bin/python advisor/advisor.py rr --side long --entry 100 --sl 95 --tp1 110 --tp2 120 --atr 4
```

- `watchlist.json`: el universo que se escanea. Editalo libremente; `names` mejora la búsqueda de noticias.
- `account.json`: capital actual, objetivo, apalancamiento máximo y riesgo por trade. Se crea copiando `account.example.json` y está excluido de git. **Actualizá `current_capital` a medida que opères.** Los comandos `size` y `plan` lo usan.
- `journal.csv`: registro de setups. Completá `outcome`, `exit_price` y `closed_at` a mano para medir el sistema. Está excluido de git.
- `snapshots/`: JSON guardados con `--save`. También excluido de git.

**R/R ponderado** = 50% del R/R a TP1 + 50% del R/R a TP2 (se ajusta con `--split`).
