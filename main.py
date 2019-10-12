#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import logging
from prometheus_client.core import REGISTRY
from prometheus_client import make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from wsgiref.simple_server import make_server
from module.collector import CollectorConfig, AliyunRDSCollector
from tools import get_args, get_file_opts


def main():
    # 获取命令行参数
    command_args = get_args()
    # 设置logging日志级别
    if command_args['debug'] == True:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)
    # 获取配置文件参数
    file_opts = get_file_opts(command_args)
    # 实例化配置
    collector_opts = CollectorConfig(file_opts=file_opts, command_args=command_args)
    # 实例化AliyunRDSCollector
    aliyun_rds_collector = AliyunRDSCollector(config=collector_opts)
    # 注册到Prometheus的registry里面
    REGISTRY.register(aliyun_rds_collector)
    app = make_wsgi_app()
    httpd = make_server(
        host=str(collector_opts.server['host']),
        port=int(collector_opts.server['port']),
        app=app,
    )
    logging.info("Start exporter, listen on {}:{}".format(str(collector_opts.server['host']), int(collector_opts.server['port'])))
    httpd.serve_forever()


if __name__ == '__main__':
    main()