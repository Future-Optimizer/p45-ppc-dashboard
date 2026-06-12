#!/usr/bin/env python3
"""
generate_refresh_token.py

Genereaza un OAuth2 refresh_token pentru Google Ads API, folosind
client_id / client_secret dintr-un OAuth Client de tip "Desktop app"
(console.cloud.google.com -> APIs & Services -> Credentials).

Ruleaza o singura data, local (deschide un browser pentru autorizare):

    pip install -r requirements.txt
    python generate_refresh_token.py --client_id XXX --client_secret YYY

La final afiseaza refresh_token-ul -> copiaza-l in config/google-ads.yaml
la campul "refresh_token".

Scope folosit: https://www.googleapis.com/auth/adwords
"""

import argparse
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main(client_id: str, client_secret: str) -> None:
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
    )

    # Va deschide un browser local; autentifica-te cu contul Google care
    # are acces la conturile Google Ads dorite.
    flow.run_local_server(
        host="localhost",
        port=0,
        authorization_prompt_message="Deschide acest link in browser pentru autorizare: ",
        success_message="Autorizare completa. Te poti inchide aceasta fereastra.",
        open_browser=True,
    )

    print("\nRefresh token:\n")
    print(flow.credentials.refresh_token)
    print("\nCopiaza valoarea de mai sus in config/google-ads.yaml -> refresh_token\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client_id", required=True, help="OAuth2 client ID (Desktop app)")
    parser.add_argument("--client_secret", required=True, help="OAuth2 client secret")
    args = parser.parse_args()
    main(args.client_id, args.client_secret)
