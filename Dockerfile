FROM python:3.7
WORKDIR /opt/aliyun-rds-exporter
ADD . /opt/aliyun-rds-exporter
RUN \
    pip install -r requirements.txt && \
    chmod a+rx main.py
EXPOSE 5234

CMD ["python", "main.py"]