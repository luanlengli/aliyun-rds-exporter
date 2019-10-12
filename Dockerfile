FROM python:3.7-alpine
WORKDIR /opt/aliyun-rds-exporter
ADD . /opt/aliyun-rds-exporter
RUN \
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install -r requirements.txt && \
    chmod a+rx main.py
EXPOSE 5234

CMD ["python", "main.py"]