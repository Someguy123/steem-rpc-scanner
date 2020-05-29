FROM python:3.8
VOLUME /app
WORKDIR /app

RUN pip3 install -U pipenv wheel pip && \
    curl -fsS https://cdn.privex.io/github/shell-core/install.sh | bash >/dev/null

COPY Pipfile Pipfile.lock /app/

RUN pipenv install --ignore-pipfile

COPY . /app

ENTRYPOINT [ "/app/run.sh" ]
