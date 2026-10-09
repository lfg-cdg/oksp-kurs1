#!/usr/bin/env bash
# Запуск/остановка сервиса для замеров: один синхронный рабочий процесс.
# ./bench/server.sh start | stop
cd "$(dirname "$0")/.."
PID=bench/results/server.pid
case "$1" in
  start)
    set -a; [ -f .env ] && . ./.env; set +a
    gunicorn -w 1 -b 127.0.0.1:${APP_PORT:-8080} --pid "$PID" --daemon \
      --access-logfile bench/results/access.log "app:create_app()"
    sleep 2; echo "сервис запущен, pid $(cat $PID)";;
  stop)
    [ -f "$PID" ] && kill "$(cat $PID)" && sleep 1 && echo "сервис остановлен";;
esac
