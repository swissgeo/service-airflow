FROM apache/airflow:3.4.0rc2-python3.14

COPY --chown=airflow:0 src/webserver_config.py /opt/airflow/webserver_config.py
COPY --chown=airflow:0 src/k8s_auth_manager.py /opt/airflow/custom/k8s_auth_manager.py

# Put /opt/airflow/custom on sys.path through a .pth file instead of PYTHONPATH,
# which the Helm chart overrides
RUN python -c "import sysconfig; print(sysconfig.get_path('purelib'))" \
    | xargs -I{} sh -c 'echo /opt/airflow/custom > {}/airflow-custom.pth'

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
