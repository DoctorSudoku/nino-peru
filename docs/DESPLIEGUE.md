# Dónde publicar

## Sin dominio pagado: tres opciones gratis

| Opción | URL que obtienen | Repo privado | Nota |
|---|---|---|---|
| **GitHub Pages** | `https://<usuario>.github.io/nino-peru/` | ❌ requiere plan pago | Cero cuentas nuevas |
| **Cloudflare Pages** | `https://nino-peru.pages.dev` | ✅ sí | CDN con punto de presencia en Lima |
| **Render (Static Site)** | `https://nino-peru.onrender.com` | ✅ sí | Misma plataforma que el observatorio de ManRay |

### Cómo elegir

- **Si el repositorio puede ser público → GitHub Pages.** Es el camino con menos piezas:
  el mismo GitHub que ya corre las actualizaciones sirve el sitio.
- **Si el repositorio debe ser privado → Cloudflare Pages o Render.** Ambos aceptan
  repositorios privados en su plan gratuito.
- **Si ya trabajan con Render → Render Static Site.** Menos plataformas que aprender.

En los tres casos el sitio es público e indexable; lo que cambia es quién puede ver el
código.

> ⚠️ **En Render, elegir "Static Site", nunca "Web Service".** Los servicios web
> gratuitos de Render se duermen a los 15 minutos de inactividad y, mientras duermen,
> responden `Disallow: /` en `/robots.txt`. Un sitio de noticias con eso desaparece de
> Google. Además tardan cerca de un minuto en despertar.

> Cuando compren dominio, no hay que rehacer nada: se apunta el DNS al mismo hosting y
> se cambia una línea en `site.config.json`.

---

## Camino A: GitHub Pages (recomendado si el repo es público)

### 1. Crear el repositorio

```bash
cd nino-peru
git init && git add . && git commit -m "Tablero El Niño: primera versión publicable"
gh repo create nino-peru --public --source=. --push
```

### 2. Configurar la URL real

Editar `site.config.json` y poner el usuario de GitHub:

```json
{ "url": "https://TUUSUARIO.github.io/nino-peru" }
```

De ahí salen `robots.txt` y `sitemap.xml` en cada build.

### 3. Activar Pages

En el repositorio: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

No hay que elegir rama: el workflow sube el artefacto ya construido.

### 4. Publicar

```bash
gh workflow run publicar.yml
```

En un par de minutos el sitio queda en `https://TUUSUARIO.github.io/nino-peru/`.

A partir de ahí corre solo cada 3 horas.

---

## Camino B: Cloudflare Pages (si el repo es privado)

1. **dash.cloudflare.com → Workers & Pages → Create → Pages → Direct Upload.**
   Proyecto: `nino-peru`.
2. **My Profile → API Tokens → Create Token → Custom token**, permiso
   `Account → Cloudflare Pages → Edit`.
3. Guardar los secretos:

```bash
gh secret set CLOUDFLARE_API_TOKEN
gh secret set CLOUDFLARE_ACCOUNT_ID
```

4. Copiar la alternativa ya preparada y desactivar la de GitHub Pages:

```bash
cp deploy/cloudflare/publicar.yml .github/workflows/publicar.yml
cp deploy/cloudflare/_headers public/_headers
```

5. Poner en `site.config.json`: `"url": "https://nino-peru.pages.dev"`.
6. `gh workflow run publicar.yml`.

Cloudflare Pages sí respeta `_headers` (caché y seguridad); GitHub Pages lo ignora.

---

## Camino C: Render (Static Site)

1. **Render Dashboard → New → Blueprint** y conectar el repositorio. El archivo
   [`deploy/render/render.yaml`](../deploy/render/render.yaml) ya trae la configuración:
   comando de build con PyMuPDF y carpeta `public`.
2. Anotar la URL `https://nino-peru.onrender.com` y ponerla en `site.config.json`.
3. Copiar el disparador periódico y definir el secreto:

```bash
cp deploy/render/disparar.yml .github/workflows/render.yml
gh secret set RENDER_DEPLOY_HOOK   # Render → Settings → Deploy Hook
```

A diferencia de los otros dos caminos, aquí **el build corre en Render**, no en GitHub
Actions: el workflow solo llama al *deploy hook* cada 3 horas.

**Límites del plan gratuito**: el ancho de banda y los minutos de build son acotados
por mes; si se agotan sin método de pago, Render suspende el servicio hasta el mes
siguiente. Para un tablero con tráfico moderado sobra, pero conviene vigilarlo.

## Cuando haya dominio propio

1. Comprarlo (`.pe` 40–70 USD/año; `.org` 12–15).
2. **GitHub Pages**: crear `CNAME` en el DNS hacia `TUUSUARIO.github.io` y agregar el
   dominio en Settings → Pages. **Cloudflare**: Custom domains → Add.
3. Cambiar `"url"` en `site.config.json`. Nada más: todas las rutas internas son
   relativas.

---

## Antes de anunciar

- [ ] El sitio carga en `https://` y sin `www` duplicado.
- [ ] `https://…/data/meta.json` responde y trae `errors: []`.
- [ ] Los embebibles cargan en un sitio externo de prueba.
- [ ] Se ve bien en un teléfono de 360 px.
- [ ] `interno/sala-de-redaccion.html` **no** es accesible (no está en `public/`).
- [ ] Hay una persona designada para responder correcciones (`MANTENIMIENTO.md`).

## Métricas

GitHub Pages no trae analítica. La opción sin cookies ni banner: **Cloudflare Web
Analytics** (funciona aunque el sitio esté en GitHub Pages) o **Plausible**/**Umami**.

## Costos

| Concepto | Costo |
|---|---|
| Hosting | 0 |
| Dominio | 0 mientras no compren uno |
| GitHub Actions | 0 (repo público) o incluido en el plan |
| **Total** | **0 USD** |
