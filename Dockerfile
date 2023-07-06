FROM ubuntu:22.04 AS base

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV SHELL="/bin/bash"

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

ENV PIP_NO_CACHE_DIR 1
ENV PIP_RETRIES 10

ENV REQUESTS_CA_BUNDLE /etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE /etc/ssl/certs/ca-certificates.crt

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update && \
    apt-get install -y --no-install-recommends libc++-dev g++ python3 python3-dev python3-pip python3-opencv && \
    rm -rf /var/lib/apt/lists/*


FROM base AS backend
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install -r /tmp/requirements.txt
COPY src /opt/app/
COPY migrations /opt/app/migrations/
WORKDIR /opt/app
CMD ["python3", "main.py"]
