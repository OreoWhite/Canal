"""Genera un Short de curiosidades y lo sube a YouTube. Todo con herramientas gratuitas."""
import asyncio, json, os, pathlib, random, subprocess, sys
import requests
import edge_tts

ROOT = pathlib.Path(__file__).parent
WORK = ROOT / "work"
OUT = ROOT / "output"
HISTORY = ROOT / "history.json"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def run(cmd, **kw):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kw)


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


# ---------- 1. Guion con Gemini (gratis) ----------
def generar_guion(previos):
    n = CFG["num_escenas"]
    prompt = f"""Eres guionista de YouTube Shorts virales. Nicho: {CFG['nicho']}.
Idioma: {CFG['idioma']}.
Crea UN Short nuevo. Reglas:
- Gancho potente en la primera frase (máx. 12 palabras).
- Narración de 100 a 120 palabras, tono cercano, datos reales y verificables, sin inventar cifras.
- Termina con una frase que invite a seguir el canal o a comentar.
- Debe ser distinto de estos temas ya publicados: {previos[-60:]}
Devuelve SOLO un JSON con esta forma:
{{"titulo": "máx 70 caracteres, llamativo",
 "descripcion": "2 frases + hashtags",
 "etiquetas": ["8 etiquetas"],
 "narracion": "texto completo que se leerá en voz alta, sin emojis ni acotaciones",
 "escenas": ["{n} búsquedas en INGLÉS de 2-3 palabras para vídeos de stock, en el orden de la narración, visuales y concretas"]}}"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{CFG['modelo_gemini']}:generateContent"
    for intento in range(4):
        try:
            r = requests.post(url, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                              json={"contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}},
                              timeout=120)
            r.raise_for_status()
            data = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            assert data["narracion"] and data["titulo"] and len(data["escenas"]) >= 3
            return data
        except Exception as e:
            print(f"Guion: intento {intento+1} falló: {e}", file=sys.stderr)
    sys.exit("No se pudo generar el guion")


# ---------- 2. Voz con edge-tts (gratis) ----------
async def _tts(texto, ruta):
    try:
        com = edge_tts.Communicate(texto, CFG["voz"], rate=CFG["velocidad_voz"], boundary="WordBoundary")
    except TypeError:
        com = edge_tts.Communicate(texto, CFG["voz"], rate=CFG["velocidad_voz"])
    palabras = []
    with open(ruta, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                ini = ch["offset"] / 1e7
                palabras.append((ch["text"], ini, ini + ch["duration"] / 1e7))
    return palabras


# ---------- 3. Clips de Pexels (gratis) ----------
def bajar_clip(consulta, idx, usados):
    headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
    for q in (consulta, consulta.split()[0], "nature landscape"):
        r = requests.get("https://api.pexels.com/videos/search", headers=headers, timeout=60,
                         params={"query": q, "orientation": "portrait", "size": "medium", "per_page": 15})
        vids = r.json().get("videos", [])
        random.shuffle(vids)
        for v in vids:
            if v["id"] in usados:
                continue
            files = [f for f in v["video_files"] if f.get("file_type") == "video/mp4"
                     and f.get("height", 0) >= f.get("width", 0)]
            if not files:
                continue
            files.sort(key=lambda f: abs(f["height"] - 1280))
            ruta = WORK / f"clip{idx}.mp4"
            with requests.get(files[0]["link"], stream=True, timeout=120) as d:
                d.raise_for_status()
                with open(ruta, "wb") as f:
                    for chunk in d.iter_content(1 << 20):
                        f.write(chunk)
            usados.add(v["id"])
            return ruta
    sys.exit(f"Sin clips para: {consulta}")


# ---------- 4. Subtítulos ASS ----------
def t(s):
    cs = int(round(s * 100))
    return f"{cs//360000}:{(cs//6000)%60:02d}:{(cs//100)%60:02d}.{cs%100:02d}"


def hacer_ass(palabras, ruta):
    cab = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,DejaVu Sans,86,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,2,2,60,60,560,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lineas = []
    for i in range(0, len(palabras), 3):
        g = palabras[i:i + 3]
        fin = g[-1][2] if i + 3 >= len(palabras) else palabras[i + 3][1]
        txt = " ".join(w[0] for w in g).upper().replace("\n", " ")
        lineas.append(f"Dialogue: 0,{t(g[0][1])},{t(fin)},Default,,0,0,0,,{txt}")
    ruta.write_text(cab + "\n".join(lineas) + "\n", encoding="utf-8")


# ---------- 5. Montaje con FFmpeg ----------
def montar(clips, audio, dur, salida):
    por = dur / len(clips)
    segs = []
    for i, c in enumerate(clips):
        seg = WORK / f"seg{i}.mp4"
        run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(c), "-t", f"{por:.3f}", "-an",
             "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", str(seg)])
        segs.append(seg)
    (WORK / "lista.txt").write_text("".join(f"file '{s.name}'\n" for s in segs))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "lista.txt", "-i", audio.name,
         "-vf", "subtitles=subs.ass", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(salida)], cwd=WORK)


# ---------- 6. Subida a YouTube (gratis) ----------
def subir(ruta, g):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    yt = build("youtube", "v3", credentials=creds)
    desc = g["descripcion"].strip() + "\n\n#Shorts"
    body = {"snippet": {"title": g["titulo"][:100], "description": desc, "tags": g["etiquetas"],
                        "categoryId": CFG["categoria_youtube"]},
            "status": {"privacyStatus": CFG["privacidad"], "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(ruta), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    print("Subido: https://youtube.com/shorts/" + resp["id"])


def main():
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    previos = json.loads(HISTORY.read_text(encoding="utf-8"))

    g = generar_guion(previos)
    print("Título:", g["titulo"])

    audio = WORK / "voz.mp3"
    palabras = asyncio.run(_tts(g["narracion"], audio))
    dur = duration(audio)
    if not palabras:  # plan B: reparto uniforme
        ws = g["narracion"].split()
        palabras = [(w, i * dur / len(ws), (i + 1) * dur / len(ws)) for i, w in enumerate(ws)]
    hacer_ass(palabras, WORK / "subs.ass")

    usados = set()
    clips = [bajar_clip(q, i, usados) for i, q in enumerate(g["escenas"])]

    salida = OUT / "short.mp4"
    montar(clips, audio, dur, salida)
    print(f"Vídeo listo ({dur:.0f}s)")

    if os.environ.get("DRY_RUN"):
        print("DRY_RUN activo: no se sube a YouTube.")
    else:
        subir(salida, g)

    previos.append(g["titulo"])
    HISTORY.write_text(json.dumps(previos[-200:], ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
