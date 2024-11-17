# REPO MOVED TO [https://github.com/sundaiclub/tunetutor](https://github.com/sundaiclub/tunetutor).

GOTO https://github.com/sundaiclub/tunetutor

# Tune Tutor

Generate educational jungles using Suno.

Hacked on [Sundai](https://sundai.club), Nov 3, 2024.

# Installation

```bash
virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

# Running 

## Locally

```bash
python main.py
```

To expose your localhost to the world:

```
npm install -g localtunnel
lt --port 8000
```

Then open the webpage and enter the password. The password is your machine IP4 or IP6 address.

## On Render
```bash
uvicorn main:app --host 0.0.0.0 --port 80 --workers 4
```

## Docker
```bash
docker build -t vyahhi/sundai-tutu .
docker image ls
docker push vyahhi/sundai-tutu
```
