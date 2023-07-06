# YouMood project

## Requirements
- [Google API key](https://console.developers.google.com)
- Linux + Docker Compose
- PostgreSQL 12 + existing empty database

## How to run
1. Fetch token and save token using your Google API key
```shell
sudo bash -c "GOOGLE_API_KEY=<YOUR_GOOGLE_API_KEY> docker compose run --rm -it backend python3 fetch_gapi_token.py"
```
You will see code and have to input it on https://www.google.com/device.
Now your token is saved in docker volume `pytube_cache`.

2. Run docker containers
```shell
sudo bash -c "GOOGLE_API_KEY=<YOUR_GOOGLE_API_KEY> DSN=postgresql://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:<DB_PORT>/<DB_NAME> PORT=<HTTP_PORT> docker compose run frontend"
```
For example:
```shell
sudo bash -c "GOOGLE_API_KEY=ABCDEFGHijklmnop-OPQRST1234567890UWVXYZ DSN=postgresql://john:hcwr3EFDho97DSw4ty@127.0.0.1:5432/youmood PORT=80 docker compose run frontend"
```
