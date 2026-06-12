# PPC Command Center — date live

Acest folder conține:

- `paralela45-ppc-dashboard.html` — varianta originală, cu date mock fixe (rămâne neschimbată, ca referință de design).
- `ppc-dashboard-live.html` — dashboard-ul **live**, care citește datele din `ppc-data.js` și se actualizează automat când acel fișier e regenerat.
- `ppc-data.js` — fișierul de date (generat de scripturi). Conține `window.PPC_DATA = {...}`.
- `config/` — credențiale și configurare conturi.
- `scripts/` — scripturile Python care extrag date din API-uri și regenerează `ppc-data.js`.

## 1. Setup Google Ads (singura platformă conectată acum)

### 1.1 Instalează dependențele

```bash
cd scripts
pip install -r requirements.txt
```

### 1.2 Completează `config/google-ads.yaml`

1. Copiază `config/google-ads.yaml.template` → `config/google-ads.yaml`.
2. Completează:
   - `developer_token` — din Google Ads → Tools & Settings → API Center.
   - `client_id` / `client_secret` — din console.cloud.google.com → APIs & Services → Credentials (OAuth Client tip **Desktop app**).
   - `refresh_token` — generează-l o singură dată cu:
     ```bash
     python scripts/generate_refresh_token.py --client_id XXX --client_secret YYY
     ```
     Se deschide un browser, te autentifici cu contul Google care are acces la conturile Ads, și scriptul îți afișează refresh token-ul. Copiază-l în `google-ads.yaml`.
   - `login_customer_id` — completează **doar** dacă accesezi conturile printr-un cont manager (MCC). Lasă comentat altfel.

⚠️ `config/google-ads.yaml` conține credențiale — nu îl trimite/partaja, nu îl pune pe Git/Drive public.

### 1.3 Completează `config/accounts.json`

- `google_ads.customer_ids` — ID-urile conturilor Google Ads (10 cifre, fără liniuțe), ex: `"1234567890"`.
- `destination_mapping.rules` — opțional, leagă cuvinte din numele campaniilor de destinații turistice (pentru cardul "Top Destinații"). Exemplele incluse (Creta, Antalya, Corfu, etc.) pot fi adaptate/extinse după convenția ta de denumire a campaniilor.
- `alert_thresholds` — praguri ROAS pentru alertele automate (critic / warning).

### 1.4 Rulează scriptul

```bash
python scripts/fetch_google_ads_data.py            # ultimele 30 de zile
python scripts/fetch_google_ads_data.py --period 7d
python scripts/fetch_google_ads_data.py --period 90d
python scripts/fetch_google_ads_data.py --period today
```

Scriptul rescrie `ppc-data.js` cu:
- KPI-uri (spend, revenue, ROAS global, conversii, CPA) + variație vs perioada anterioară
- cardul Google Ads (spend, ROAS, conversii, CPA)
- top campanii Google Ads sortate după ROAS
- breakdown destinații (dacă ai completat `destination_mapping`)
- alerte automate pe baza pragurilor ROAS
- grafice spend/ROAS zilnice (ultimele 14 zile)
- spend de azi (sidebar)

### 1.5 Vizualizează

Deschide `ppc-dashboard-live.html` direct în browser (dublu-click sau drag în Chrome). Butonul **↻ Refresh date** reîncarcă pagina — rulează din nou scriptul înainte, ca să vezi date proaspete.

## 2. Meta, Bing, TikTok — încă neconectate

Cardurile lor apar estompate, cu status „⚠ Neconectat”, și KPI-urile globale includ momentan doar Google Ads.

Pentru a le conecta:

1. Obține credențialele API necesare (vezi notițele din `config/accounts.json`):
   - **Meta Ads**: access token + ad account ID (Meta Marketing API / Business Manager).
   - **Bing Ads**: developer token + OAuth client/secret + refresh token (Microsoft Advertising API — flux similar Google Ads).
   - **TikTok Ads**: access token + advertiser ID (TikTok Marketing API).
2. Completează secțiunea corespunzătoare în `config/accounts.json`.
3. Scrie un script `fetch_<platforma>_ads_data.py` care urmează același șablon ca `fetch_google_ads_data.py`:
   - calculează totaluri (cost, conversii, valoare conversii) pentru perioada cerută,
   - actualizează `platforms.<platforma>` în `ppc-data.js` (status `connected`, `spend_display`, `roas`, `conversions`, `cpa_display`, `share_pct`),
   - opțional adaugă campanii în `campaigns`, zile în `daily`, alerte în `alerts`.
4. Recalculează `share_pct` pentru toate platformele conectate astfel încât să reflecte ponderea reală din spend total, și KPI-urile globale (`kpis`) ca sumă peste toate platformele conectate (nu doar Google).

## 3. Reîmprospătare automată (opțional)

Poți programa rularea scriptului (de exemplu zilnic dimineața) folosind skill-ul **schedule** din Cowork, sau Task Scheduler din Windows, ca să ai `ppc-data.js` mereu proaspăt fără să rulezi manual comanda.

## 4. Schema `ppc-data.js`

```jsonc
{
  "meta": { "generated_at": "...", "period_label": "...", "period_key": "30d", "source": "live|mock" },
  "kpis": {
    "spend_total": { "display": "654", "unit": "K RON", "delta_display": "↑ 18%", "delta_dir": "up|down" },
    "revenue": { ... }, "roas_global": { ... }, "conversions": { ... }, "cpa_avg": { ... }
  },
  "platforms": {
    "google": { "name": "Google Ads", "status": "connected|not_connected", "status_label": "...",
                 "status_class": "ok|warn|crit|off", "spend_display": "328K", "roas": 7.2,
                 "roas_class": "good|warn|bad|off", "conversions": 712, "cpa_display": "461 RON",
                 "share_pct": 50 },
    "meta": { ... }, "bing": { ... }, "tiktok": { ... }
  },
  "campaigns": [ { "platform": "google", "name": "...", "spend_display": "98.4K", "conversions": 234, "roas": 9.1, "roas_class": "good" } ],
  "destinations": [ { "name": "🇬🇷 Creta", "revenue": 684000, "revenue_display": "684K", "roas": 8.2 } ],
  "alerts": [ { "severity": "crit|warn|info", "icon": "🔴", "title": "...", "desc": "...", "time": "azi" } ],
  "daily": { "days": ["16","17",...], "spend": [18400,...], "roas": [5.2,...] },
  "sidebar_spend_today": { "google": "11.240 RON", "meta": "— RON", "bing": "— RON", "tiktok": "— RON" }
}
```

Orice script de fetch (pentru orice platformă) trebuie doar să producă/actualizeze acest fișier — `ppc-dashboard-live.html` nu necesită modificări.
