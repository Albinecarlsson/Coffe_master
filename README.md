# Coffe_master
modding of a isomac milano

# Espresso Mod (Pi) - Dev-first scaffold

This repo supports developing an espresso machine mod **without hardware** using a simulator.

## Quickstart
```bash
python -m venv .venv
source .venv/scripts/activate
pip install -U pip
pip install -e ".[dev]"
cp .env.example .env
uvicorn espresso_mod.main:app --reload
```


# How to test like hardware exists
```bash
uvicorn espresso_mod.main:app --reload

curl -X POST http://127.0.0.1:8000/control/setpoint -H "Content-Type: application/json" -d '{"setpoint_c":93}'
curl -X POST http://127.0.0.1:8000/control/enable -H "Content-Type: application/json" -d '{"enabled":true}'
curl http://127.0.0.1:8000/state

curl -X POST http://127.0.0.1:8000/shot/run/classic_espresso
```
