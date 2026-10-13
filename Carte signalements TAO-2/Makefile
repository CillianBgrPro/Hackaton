# Projet TAO sécurité : cartes, analyses et maquettes
#   make              -> tout construire (carte des signalements, carte des Safe Places, analyses)
#   make signalements -> carte des signalements et exports SIG
#   make safe-places  -> carte des Safe Places potentielles (télécharge ~250 Mo la première fois)
#   make analyses     -> questionnaire, plan du pilote, Trajet Sécurité
#   make serve        -> sert dist/ sur http://localhost:8000

PYTHON ?= python3
VENV   := .venv
PY     := $(VENV)/bin/python
DEPS   := $(VENV)/.installed
XLSX   ?= data/signalements.xlsx

.PHONY: all signalements fetch refresh basemap data html artifact survey safe-places analyses serve clean

all: signalements safe-places analyses

$(DEPS): requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt
	touch $(DEPS)

fetch: $(DEPS)
	$(PY) src/fetch_sources.py

refresh: $(DEPS)  ## retélécharge toutes les sources (nouveau GTFS, mise à jour IGN et OpenStreetMap)
	$(PY) src/fetch_sources.py --force
	$(PY) -m src.safe_places.fetch_osm --force

basemap: fetch
	$(PY) src/build_basemap.py

data: basemap
	$(PY) src/process_signalements.py "$(XLSX)"

html signalements: data
	$(PY) src/assemble.py

artifact: data
	$(PY) src/assemble.py --fragment

survey: $(DEPS)
	$(PY) -m src.analyses.survey

safe-places: data survey
	$(PY) -m src.safe_places.fetch_osm
	$(PY) -m src.safe_places.build_candidates
	$(PY) src/assemble.py --web src/safe_places/web --data build/safe_places.json --out dist/safe-places/carte-safe-places-tao.html --fragment build/safe-places-artifact.html

analyses: data survey
	$(PY) -m src.analyses.pilot
	$(PY) -m src.analyses.trajet_securite

serve:
	cd dist && $(PYTHON) -m http.server 8000

clean:
	rm -rf build dist
