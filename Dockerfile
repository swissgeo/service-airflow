FROM apache/airflow:3.2.2

COPY --chown=airflow:0 webserver_config.py /opt/airflow/webserver_config.py
