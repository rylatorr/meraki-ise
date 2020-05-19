FROM python:3-alpine

WORKDIR /app
COPY requirements.txt .
RUN apk update && apk upgrade
RUN apk add gcc\
            musl-dev
RUN pip install -r requirements.txt

COPY . .

CMD ["/app/meraki-ise.py", "-c", "/app/config/config.yaml"]
