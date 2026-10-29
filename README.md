# Canal de YouTube en piloto automático (100 % gratis)

Cada día, GitHub ejecuta el proyecto: Gemini escribe el guion → edge-tts pone la voz → Pexels da los clips →
FFmpeg monta el Short con subtítulos → se sube a tu canal.

Solo tienes que hacer esta configuración una vez (~45 min).

## Paso 1. Subir el proyecto a GitHub
1. Crea cuenta en https://github.com y un repositorio **público** nuevo (público = minutos de Actions ilimitados).
2. Sube todos los archivos de esta carpeta. Si la carpeta oculta `.github` no se sube al arrastrar,
   usa **Add file → Create new file**, escribe el nombre `.github/workflows/daily.yml` y pega su contenido.

## Paso 2. Claves gratuitas
- **Gemini**: https://aistudio.google.com/apikey → *Create API key*.
- **Pexels**: https://www.pexels.com/api/ → pide la clave (es inmediata).

## Paso 3. Permiso para YouTube
1. https://console.cloud.google.com → crea un proyecto.
2. *APIs y servicios → Biblioteca* → busca **YouTube Data API v3** → *Habilitar*.
3. *Pantalla de consentimiento OAuth* → tipo **Externo** → rellena nombre y tu email.
   Añade tu email en *Usuarios de prueba*.
4. **Importante:** pulsa **Publicar aplicación** (pasar a "En producción"). Si la dejas en "Pruebas", el permiso caduca a los 7 días y el canal dejará de subir.
5. *Credenciales → Crear credenciales → ID de cliente de OAuth → Aplicación de escritorio*.
   Descarga el JSON y renómbralo `client_secret.json` (en la carpeta del proyecto, en tu PC).
6. En tu PC (necesitas Python): `pip install google-auth-oauthlib` y luego `python get_refresh_token.py`.
   Se abre el navegador, eliges tu canal y aceptas (verás un aviso de "app no verificada": *Avanzado → Continuar*).
   Te imprime 3 valores. No subas `client_secret.json` a GitHub.

## Paso 4. Guardar los secretos en GitHub
Repositorio → *Settings → Secrets and variables → Actions → New repository secret*. Crea estos 5:
`GEMINI_API_KEY`, `PEXELS_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`.

## Paso 5. Probar
*Actions → Short diario → Run workflow* con **dry_run marcado**. Al terminar, descarga el vídeo desde *Artifacts*
y míralo. Si te gusta, ejecútalo otra vez sin dry_run y se subirá. Desde ahí corre solo cada día.

## Ajustes (config.json)
Nicho, idioma, voz (`es-MX-JorgeNeural`, `es-ES-ElviraNeural`, etc.), visibilidad y nº de escenas.
La hora se cambia en el `cron` de `daily.yml`.

## Avisos importantes
- **Subidas privadas forzadas:** los proyectos de API nuevos y sin auditar suben los vídeos como *privados* hasta que Google los
  audite (formulario: "YouTube API Services – Audit and Quota Extension Form"). Hasta entonces puedes hacerlos públicos a mano
  desde YouTube Studio, o solicitar la auditoría.
- **Monetización:** YouTube no paga canales con contenido masivo y repetitivo sin valor añadido. Revisa de vez en cuando
  los guiones y ajusta el nicho en `config.json` para mantener calidad.
- Si Gemini cambia el nombre del modelo, edita `modelo_gemini` en `config.json`.
