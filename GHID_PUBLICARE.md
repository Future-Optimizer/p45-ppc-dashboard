# Ghid: publicarea dashboard-ului PPC

## Ce e deja pregătit

- **`public/index.html`** — versiunea publică a dashboard-ului (identică cu `ppc-dashboard-live.html`), fără cod sensibil.
- **`.gitignore`** — exclude `config/` (credențiale Google Ads), `*.yaml`, `*.csv`, `*.xlsx` din orice repo public.
- **`scripts/publish.ps1`** — script care: actualizează datele din Google Ads, copiază fișierele în `public/`, face commit + push pe GitHub.

**Important:** `config/google-ads.yaml` (cheile API) NU se publică niciodată. `.gitignore` are deja regula asta.

## Pas 1 — Curăță folderul `.git` (o singură dată)

În folderul proiectului există un `.git` stricat dintr-o încercare anterioară. Șterge-l manual din File Explorer:

1. Deschide folderul `Paralela 45` în File Explorer.
2. Activează "Show hidden items" (View → arată elementele ascunse).
3. Șterge folderul `.git` (dacă există).

## Pas 2 — Inițializează git și creează repo pe GitHub

Deschide PowerShell în folderul proiectului și rulează:

```powershell
cd "C:\Users\Workbox\Documents\Claude\Projects\Paralela 45"
git init
git add .gitignore scripts public README_PPC_DASHBOARD.md
git commit -m "Initial commit - dashboard public"
```

Apoi pe [github.com](https://github.com):

1. Creează un cont (dacă nu ai deja).
2. "New repository" → numește-l ex. `ppc-dashboard` → **Public** sau **Private** (Pages funcționează gratuit doar pe repo public, sau pe Private cu GitHub Pro).
3. Copiază comenzile afișate de GitHub pentru "push an existing repository":

```powershell
git remote add origin https://github.com/<user-ul-tau>/ppc-dashboard.git
git branch -M main
git push -u origin main
```

(La primul push, GitHub îți va cere autentificare — urmează instrucțiunile lor din browser.)

## Pas 3 — Activează GitHub Pages

1. În repo, pe GitHub: **Settings → Pages**.
2. La "Source", alege branch-ul `main` și folderul `/public`.
3. Salvează. În 1-2 minute, dashboard-ul e live la:

```
https://<user-ul-tau>.github.io/ppc-dashboard/
```

Acest link poate fi trimis oricui — nu necesită autentificare.

## Pas 4 — Actualizări automate

De fiecare dată când vrei date proaspete, rulează:

```powershell
.\scripts\publish.ps1
```

Acest script reîmprospătează datele din Google Ads și le publică automat (commit + push). Link-ul public se actualizează în 1-2 minute.

### Automatizare completă (zilnic, fără să rulezi tu nimic)

Folosește **Windows Task Scheduler**:

1. Deschide "Task Scheduler" → "Create Basic Task".
2. Nume: "Publicare dashboard PPC".
3. Trigger: zilnic, la ora dorită (ex. 08:00).
4. Action: "Start a program" →
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -File "C:\Users\Workbox\Documents\Claude\Projects\Paralela 45\scripts\publish.ps1"`
5. Salvează.

De atunci, dashboard-ul public se va actualiza automat în fiecare zi, fără intervenție.

## Notă de securitate

- Linkul public (`index.html` + `ppc-data.js`) conține doar cifre agregate (spend, ROAS, conversii) — nicio cheie API, niciun cont, nicio credențială.
- Dacă vrei să restricționezi accesul mai târziu (ex. doar cu parolă), poți folosi un serviciu ca Netlify cu "Password Protection" în loc de GitHub Pages — dar necesită un cont Netlify suplimentar.
