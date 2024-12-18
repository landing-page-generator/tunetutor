import os
import random
import requests
import time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pathlib import Path
from suno_api import generate_tunes, get_audio_information
from langchain_openai import ChatOpenAI
from yt_dlp import YoutubeDL
from openai import OpenAI

load_dotenv()

app = FastAPI()

llm = ChatOpenAI(model="gpt-4o")

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


def generate_lyrics(query: str, version: int):
    prompt = Path(f"prompts/lyrics-{version}.txt").read_text()
    prompt += "\n\n" + query
    response = llm.invoke(prompt).content
    return response


def generate_style(query: str, version: int):
    prompt = Path(f"prompts/style-{version}.txt").read_text()
    if version == 2:
        return prompt  # fixed, no AI
    prompt += "\n\n" + query
    response = llm.invoke(prompt).content
    return response


def generate_brainwash(query: str, version: int):
    version = int(version)
    lyrics = generate_lyrics(query, version)
    style = generate_style(query, version)
    print(f"Lyrics:\n\n{lyrics}")
    print(f"Style:\n\n{style}")
    audios = generate_tunes(lyrics, style, query)
    print(f"AUDIOS:\n\n{audios}")
    return lyrics, style, audios


@app.get("/")
async def index_form():
    html_content = open("index.html").read()
    return HTMLResponse(content=html_content, status_code=200)


@app.post("/form-results")
async def index_form_results(request: Request):
    form_data = await request.form()
    query = form_data.get("query")
    version = form_data.get("version")
    lyrics, style, audios = generate_brainwash(query, version)
    html = "<h1>Music Generation Results:</h1>"
    html += "<ol>"
    for audio in audios:
        audio_url = audio["url"]
        suno_id = audio["id"]
        html += f"<li>Listen: <audio src='{audio_url}' style='vertical-align: middle;' controls></audio><br>Watch: <a href='/api/video?suno_id={suno_id}' target='_blank'>API</a><br>Suno ID: {suno_id}<br>"
    html += f"<h1>Lyrics:</h1><pre>{lyrics}</pre>"
    html += f"<h1>Style:</h1><pre>{style}</pre>"
    html += f"<h1>User Query:</h1><pre>{query}</pre>"
    html += "<br><br><a href='/'>← Go Back</a>"
    return HTMLResponse(content=html, status_code=200)


@app.post("/api/generate", response_class=JSONResponse)
async def generate_music_api(request: Request, input: dict):
    query = input.get("query")
    version = input.get("version")
    lyrics, style, audios = generate_brainwash(query, version)
    return JSONResponse(
        content={
            "lyrics": lyrics,
            "style": style,
            "urls": [audio["url"] for audio in audios],
            "ids": [audio["id"] for audio in audios],
        }
    )


def get_audio_url(suno_id: str) -> str:
    for _ in range(60):
        data = get_audio_information(suno_id)
        if data[0]["status"] in ["streaming", "complete"]:
            print(f"{data[0]['id']} ==> {data[0]['audio_url']}")
            return data[0]["audio_url"]
        # sleep 5s
        time.sleep(5)
    return None


def subtitle_audio(audio_file_path):
    client = OpenAI()
    with open(audio_file_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="srt",
            # timestamp_granularities=["word"],  # Timestamp granularities are only supported with response_format=verbose_json'
        )
        print(transcription)
        return transcription


def get_audio_duration(audio_file_path: str) -> float:
    duration_command = f'ffmpeg -i "{audio_file_path}" 2>&1 | grep "Duration"'
    duration_output = os.popen(duration_command).read()
    if duration_output:
        time_str = duration_output.split("Duration: ")[1].split(",")[0]
        h, m, s = time_str.split(":")
        return float(h) * 3600 + float(m) * 60 + float(s)
    return 0


def repeat_subtitles(subtitles: str, audio_duration: float, times: int) -> str:
    repeated_subtitles = ""
    for i in range(times):
        # For each line in subtitles, shift timestamps by i * audio_duration
        shifted = ""
        for line in subtitles.split("\n"):
            if " --> " in line:  # This is a timestamp line
                start, end = line.split(" --> ")

                # Convert timestamp to seconds, add offset, convert back
                def timestamp_to_seconds(ts):
                    h, m, s = ts.split(":")
                    s, ms = s.split(",")
                    return float(h) * 3600 + float(m) * 60 + float(s) + float(ms) / 1000

                def seconds_to_timestamp(secs):
                    h = int(secs // 3600)
                    m = int((secs % 3600) // 60)
                    s = secs % 60
                    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

                start_sec = timestamp_to_seconds(start) + (i * audio_duration)
                end_sec = timestamp_to_seconds(end) + (i * audio_duration)

                line = f"{seconds_to_timestamp(start_sec)} --> {seconds_to_timestamp(end_sec)}"
            shifted += line + "\n"
        repeated_subtitles += shifted
    return repeated_subtitles


@app.get("/api/video")
async def videofy(request: Request, suno_id: str, youtube_id: str = None):
    print(suno_id, youtube_id)
    os.makedirs("static/suno", exist_ok=True)
    os.makedirs("static/youtube", exist_ok=True)
    os.makedirs("static/output", exist_ok=True)
    os.makedirs("static/output-hardsub", exist_ok=True)
    os.makedirs("static/subtitles", exist_ok=True)

    audio_filename = f"static/suno/suno-{suno_id}.mp3"
    if not os.path.exists(audio_filename):
        audio_url = get_audio_url(suno_id)
        response = requests.get(audio_url)
        if response.status_code == 200:
            with open(audio_filename, "wb") as file:
                file.write(response.content)

    subtitle_filename = f"static/subtitles/suno-{suno_id}-10x.srt"
    if not os.path.exists(subtitle_filename):
        with open(subtitle_filename, "w") as file:
            subtitles = subtitle_audio(audio_filename)
            audio_duration = get_audio_duration(audio_filename)
            print(f"Audio duration: {audio_duration} seconds")
            repeated_subtitles = repeat_subtitles(subtitles, audio_duration, 50)
            file.write(repeated_subtitles)
    has_subtitles = (
        os.path.exists(subtitle_filename) and os.path.getsize(subtitle_filename) > 0
    )

    if not youtube_id:
        youtube_ids = open("youtube_ids.txt").read().strip().splitlines()
        youtube_id = random.choice(youtube_ids)
    video_filename = f"static/youtube/youtube-{youtube_id}.mp4"
    if not os.path.exists(video_filename):
        ydl_opts = {
            "format": "bestvideo[ext=mp4]",
            "outtmpl": video_filename,
        }
        cookiefile_ro = (
            "/etc/secrets/youtube_cookies.txt"  # Render secret file, read-only
        )
        if os.path.exists(cookiefile_ro):
            cookiefile_rw = "youtube_cookies.txt"
            with open(cookiefile_ro, "r") as src, open(cookiefile_rw, "w") as dst:
                dst.write(src.read())
            ydl_opts["cookiefile"] = cookiefile_rw

        with YoutubeDL(ydl_opts) as ydl:
            urls = f"https://www.youtube.com/watch?v={youtube_id}"
            ydl.download(urls)

    download_filename = f"tutu-{suno_id}-{youtube_id}.mp4"
    output_filename = f"static/output/{download_filename}"
    merge_command = f'ffmpeg -y -i "{video_filename}" -stream_loop -1 -i "{audio_filename}" -map 0:v -map 1:a -c:v copy -shortest {output_filename}'
    print(merge_command)
    os.system(merge_command)
    output_filename_hardsub = f"static/output-hardsub/{download_filename}"

    # ffmpeg -y -i "static/output/tutu-71a77644-0028-450a-b32d-452c1d07bb9e-E1CgDCh5KC0.mp4" -vf "subtitles=static/subtitles/suno-71a77644-0028-450a-b32d-452c1d07bb9e.srt:force_style='Fontsize=24,PrimaryColour=&H0000ff&,OutlineColour=&H80000000'" static/output2/tutu-71a77644-0028-450a-b32d-452c1d07bb9e-E1CgDCh5KC0.mp4
    if has_subtitles:
        # TODO: combine it with merge command maybe
        # see https://superuser.com/a/869473 & https://stackoverflow.com/a/25880038 :
        # -vf "subtitles=subs.srt:force_style='Fontsize=24,PrimaryColour=&H0000ff&,OutlineColour=&H80000000'"
        subtitle_command = f"""ffmpeg -y -i "{output_filename}" -vf "subtitles={subtitle_filename}:force_style='Fontsize=24,OutlineColour=&H80000000,BorderStyle=3,Outline=1,Shadow=0,MarginV=20'" {output_filename_hardsub}"""
        print(subtitle_command)
        os.system(subtitle_command)

    result_filename = output_filename_hardsub if has_subtitles else output_filename

    hostname = request.headers.get("host", "localhost:8000")
    scheme = request.headers.get("x-forwarded-proto", "http")
    return JSONResponse(content={"url": f"{scheme}://{hostname}/{result_filename}"})


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
