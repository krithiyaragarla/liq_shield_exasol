.PHONY: data test api ui load excel
data:   ; python scripts/generate_data.py
test:   ; python -m pytest -q
api:    ; uvicorn app.api:app --port 8000
ui:     ; streamlit run app/dashboard.py
load:   ; python scripts/load_exasol.py
excel:  ; python scripts/build_excel.py
