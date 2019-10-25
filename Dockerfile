FROM python:3-alpine


RUN apk update && apk upgrade && pip install -U pip

COPY . /app
WORKDIR /app
RUN pip --no-cache-dir install -r requirements.txt 

RUN crontab /app/crontab.txt
RUN touch /var/log/cron.log

RUN ln -snf /usr/share/zoneinfo/Asia/Jakarta /etc/localtime && echo "Asia/Jakarta" > /etc/timezone

CMD crond && tail -f /var/log/cron.log