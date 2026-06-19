# Setup de Google (una sola vez, lo hace el dueno del repo)

Esto se hace **una sola vez en tu vida**, no por cada Raspberry Pi. Despues de
esto, cualquier persona solo inicia sesion con su cuenta de Google desde la app
y no toca nada de Google.

El resultado es un **Client ID** y un **Client Secret** que guardas en un archivo
`.env` (no se versiona). El instalador te los pide y crea el `.env` solo. Son los
mismos para todas las Pi.

> Nota tecnica importante: el permiso de YouTube es un "scope restringido". Para
> uso entre pocas personas conocidas (no publico masivo) **no requiere** la
> verificacion formal de Google ni la evaluacion de seguridad CASA. Lo unico que
> veran los usuarios es una pantalla de "Google no ha verificado esta app" que se
> acepta con un clic. Fuentes oficiales confirmadas: ver el final de este archivo.

---

## Paso 1: Proyecto en Google Cloud

1. Entra a https://console.cloud.google.com
2. Crea un proyecto (o usa uno existente). Cualquiera sirve.

## Paso 2: Habilitar la API

1. Ve a "APIs y servicios" > "Biblioteca".
2. Busca **YouTube Data API v3** y haz clic en **Habilitar**.

## Paso 3: Pantalla de consentimiento OAuth (Google Auth Platform)

> Google renovo esta seccion (ahora se llama "Google Auth Platform"). El
> asistente inicial es corto: solo pide nombre de la app, correos y el tipo de
> audiencia. Los permisos (scopes) y la publicacion se configuran DESPUES, en
> secciones aparte del menu de la izquierda. Por eso ya no aparecen dentro del
> asistente.

### 3a. Crear la app (asistente inicial)

1. Ve a "APIs y servicios" > "Pantalla de consentimiento de OAuth".
2. Tipo de usuario / Audiencia: **External (Externo)**.
3. Llena lo basico:
   - Nombre de la app (lo que veran los usuarios al iniciar sesion, ej. "Transmisiones Mevel").
   - Correo de asistencia al usuario (lo ve el usuario) y correo de contacto del
     desarrollador (lo usa Google para avisarte). Pueden ser el mismo correo.
4. Acepta las politicas y termina el asistente.

### 3b. Agregar el permiso (scope), en "Acceso a los datos"

1. En el menu de la izquierda, entra a **"Acceso a los datos"** (Data Access).
2. Clic en **"Agregar o quitar permisos"**.
3. Busca `youtube`; si no aparece en la lista, pega la URL en el cuadro de
   "agregar permiso manualmente":
   `https://www.googleapis.com/auth/youtube`
4. Guarda.

> Nota: aunque no lo agregues aqui, la app igual puede pedir el permiso al
> iniciar sesion. Pero agregarlo es lo correcto.

### 3c. Publicar la app (CRITICO), en "Publico"

1. En el menu de la izquierda, entra a **"Publico"** (Audience).
2. Veras **"Estado de publicacion: Testing"** y un boton **"Publicar app"**.
3. Clic en ese boton para pasarla a **"En produccion" (In production)**.

> Si la dejas en "Testing", los tokens caducan **cada 7 dias** y habria que
> volver a vincular cada semana. En "Produccion" eso no pasa.

## Paso 4: Crear el cliente OAuth (tipo dispositivo)

1. Ve a "APIs y servicios" > "Credenciales".
2. "Crear credenciales" > "ID de cliente de OAuth".
3. Tipo de aplicacion: **"TV and Limited Input devices"** (TV y dispositivos de
   entrada limitada). Este tipo es el que habilita el Device Flow (codigo + QR).
4. Dale un nombre y crea. Google te mostrara un **Client ID** y un **Client Secret**.

## Paso 5: Guardar las credenciales (NO van en el repo)

Las credenciales **no se versionan**: viven en un archivo `.env` local que esta
en `.gitignore`. No necesitas editar `config.py`.

En cada Pi, al correr `./install.sh`, el instalador te pide los dos valores y crea
el `.env` automaticamente:

```
YT_CLIENT_ID: 1234567890-xxxxxxxx.apps.googleusercontent.com
YT_CLIENT_SECRET: GOCSPX-xxxxxxxxxxxxxxxx
```

Si prefieres crearlo a mano, copia `.env.example` a `.env` y pon ahi esas dos
lineas. **Guarda el Client ID y el Client Secret en un lugar seguro** (un gestor
de contrasenas), porque los necesitaras al instalar en cada Pi.

Por que no se suben al repo: aunque para clientes de dispositivo Google no trata
el secret como confidencial, exponerlo en un repo publico permitiria que alguien
abuse de tu app bajo tu nombre, y los escaneres de Google podrian invalidarlo
automaticamente. Por eso se mantiene fuera del codigo. Los tokens de cada cuenta
(`.youtube_tokens.json`) tampoco se versionan.

---

## Lo que vera el usuario final (la persona con su cuenta)

1. Abre el panel, clic en "Vincular con YouTube".
2. La app muestra un codigo y un enlace/QR.
3. Inicia sesion con su cuenta de Google.
4. Vera una vez la pantalla **"Google no ha verificado esta app"**.
   Debe hacer clic en **"Avanzado"** y luego **"Ir a (nombre de la app)"**.
   Esto es normal y esperado; aceptarlo una vez es suficiente.
5. Escribe el codigo, aprueba, y queda vinculado. El video saldra en **su** canal.

## Requisitos de la cuenta de YouTube de esa persona

Para poder transmitir por encoder/RTMP, su canal necesita:
- Tener **live streaming habilitado** (la primera vez, YouTube puede tardar hasta
  24 horas en activarlo).
- La cuenta **verificada por telefono**.
- Sin restricciones de transmision en los ultimos 90 dias.
- **No hay requisito de numero de suscriptores** para transmitir por encoder/RTMP
  (ese requisito solo aplica a transmitir desde el celular).

## Limites (que conviene conocer)

- Tope de **100 usuarios nuevos** en toda la vida del proyecto sin verificar.
  Para uso entre pocas personas conocidas estas lejisimos de eso.
- Si algun dia quisieras abrir esto al **publico masivo** (desconocidos), ahi si
  Google exige verificacion formal + evaluacion de seguridad CASA anual.

---

## Fuentes oficiales (verificadas)

- Device Flow para YouTube y scope permitido:
  https://developers.google.com/youtube/v3/guides/auth/devices
  https://developers.google.com/identity/protocols/oauth2/limited-input-device
- Caducidad de 7 dias en modo Testing:
  https://developers.google.com/identity/protocols/oauth2
- App sin verificar y tope de 100 usuarios:
  https://support.google.com/cloud/answer/7454865
- client_secret no confidencial en apps instaladas/dispositivo:
  https://developers.google.com/identity/protocols/oauth2 (seccion Installed applications)
