FROM apache/airflow:3.4.0rc2-python3.14

COPY --chown=airflow:0 src/webserver_config.py /opt/airflow/webserver_config.py

ARG VERSION=unknown
ARG GIT_HASH=unknown
ARG GIT_BRANCH=unknown
ARG GIT_DIRTY=""
ARG AUTHOR=unknown
LABEL git.hash=$GIT_HASH
LABEL git.branch=$GIT_BRANCH
LABEL git.dirty=$GIT_DIRTY
LABEL author=$AUTHOR
LABEL version=$VERSION
