#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import json
import datetime
import sys
import logging
import asyncio
from concurrent import futures
from cachetools import cached, TTLCache, cachedmethod
from aliyunsdkcore.client import AcsClient
from aliyunsdkrds.request.v20140815.DescribeDBInstancesRequest import DescribeDBInstancesRequest
from aliyunsdkrds.request.v20140815.DescribeDBInstancePerformanceRequest import DescribeDBInstancePerformanceRequest
from aliyunsdkrds.request.v20140815.DescribeResourceUsageRequest import DescribeResourceUsageRequest
from prometheus_client.core import Summary, GaugeMetricFamily




# 这里的api_request是用来记录阿里云API调用的延迟
api_request_summry = Summary(
    'aliyun_api_request_latency_seconds',
    'CloudMonitor request latency',
    ['api']
)
api_request_failed_summry = Summary(
    'aliyun_api_failed_request_latency_seconds',
    'CloudMonitor failed request latency',
    ['api']
)


class CollectorConfig(object):
    def __init__(self, file_opts, command_args, page_size=20, rate_limit=10, ):
        self.command_args = command_args
        self.rate_limit = rate_limit
        self.page_size = page_size
        self.server = file_opts['server']
        self.credential = file_opts['credential']
        self.performance_list = file_opts['performance_list']
        if (
                (self.credential['access_key_id'] is None)
                or
                (self.credential['access_key_secret'] is None)
                or
                (self.credential['region_id'] is None)
        ):
            raise Exception('Credential in config file not fully configured!')


class AliyunRDSCollector(object):
    def __init__(self, config):
        self.credential = config.credential
        self.rate_limit = config.rate_limit
        self.page_size = config.page_size
        self.client = AcsClient(
            ak=self.credential['access_key_id'],
            secret=self.credential['access_key_secret'],
            region_id=self.credential['region_id'],
        )
        self.config = config

    @cached(cache=TTLCache(maxsize=4096, ttl=300))
    def query_rds_instance_list(self):
    # query_rds_instance_list用于请求RDS数据库实例和返回数据库实例状态列表
        page_num = 1
        request = DescribeDBInstancesRequest()
        request.set_PageSize(self.page_size)
        request.set_accept_format('json')
        rds_instance_list = []
        now = datetime.datetime.now().timestamp()
        while True:
            try:
                request.set_PageNumber(page_num)
                response = json.loads(self.client.do_action_with_exception(request).decode('utf-8'))
                api_request_summry.labels(api='DescribeDBInstancesRequest').observe(
                    amount=(datetime.datetime.now().timestamp() - now)
                )
            except Exception as e:
                logging.error('Error request Aliyun api', exc_info=e)
                api_request_failed_summry.labels(api='DescribeDBInstancesRequest').observe(
                    amount=(datetime.datetime.now().timestamp() - now)
                )
                return []
            if response['PageRecordCount'] == 0:
                break
            DBInstance_list = response['Items']['DBInstance']
            rds_instance_list.extend(DBInstance_list)
            page_num += 1
        logging.debug("size of rds_instance_list = {}".format(sys.getsizeof(rds_instance_list)))
        return rds_instance_list

    @cached(cache=TTLCache(maxsize=4096, ttl=20))
    def query_rds_performance_data_list(self):
    # 调用阿里云API请求RDS实例的性能数据
        now = datetime.datetime.now()
        rds_performance_data_list = list(self.aliyun_client_do_action_response_list())
        logging.debug("rds_performance_data_list used time = {}".format(datetime.datetime.now() - now))
        logging.debug("size of rds_performance_data_list = {}".format(sys.getsizeof(rds_performance_data_list)))
        return rds_performance_data_list

    def query_rds_performance_data_job_list_generator(self):
        rds_instance_list = self.query_rds_instance_list()
        now = datetime.datetime.utcnow()
        starttime = (now - datetime.timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%MZ')
        endtime = now.strftime('%Y-%m-%dT%H:%MZ')
        performance_lists = self.config.performance_list
        request_task_list = []
        for i in range(len(rds_instance_list)):
            DBInstanceId = rds_instance_list[i]['DBInstanceId']
            Engine = rds_instance_list[i]['Engine']
            rds_performance_list = performance_lists[Engine]            
            for j in range(len(rds_performance_list)):
                request = DescribeDBInstancePerformanceRequest()
                performance_key = rds_performance_list[j]
                request.set_DBInstanceId(DBInstanceId)
                request.set_accept_format('json')
                request.set_StartTime(starttime)
                request.set_EndTime(endtime)
                request.set_Key(performance_key)
                request_task_list.append(request)
        return request_task_list

    def aliyun_client_do_action(self, request):
        now = datetime.datetime.now().timestamp()
        try:
            response = self.client.do_action_with_exception(request)
            api_request_summry.labels(api='DescribeDBInstancePerformanceRequest').observe(
                amount=(datetime.datetime.now().timestamp() - now)
            )
            return response
        except Exception as e:
            logging.error('Error request Aliyun api', exc_info=e)
            api_request_failed_summry.labels(api='DescribeDBInstancePerformanceRequest').observe(
                amount=(datetime.datetime.now().timestamp() - now.timestamp())
            )
            return []

    def aliyun_client_do_action_response_list(self):
    # 通过线程池并行调用阿里云API
        request_list = self.query_rds_performance_data_job_list_generator()
        with futures.ThreadPoolExecutor(50) as executor:
            response = executor.map(self.aliyun_client_do_action, request_list)
        return response

    @cached(cache=TTLCache(maxsize=1024, ttl=60))
    def query_rds_resource_usage_list(self):
        rds_instance_list = self.query_rds_instance_list()
        request = DescribeResourceUsageRequest()
        rds_resource_usage_dict = {}
        for i in range(len(rds_instance_list)):
            DBInstanceId = rds_instance_list[i]['DBInstanceId']
            request.set_DBInstanceId(DBInstanceId=DBInstanceId)
            response = json.loads(self.client.do_action_with_exception(request).decode('utf-8'))
            rds_resource_usage_dict[DBInstanceId] = response
        return rds_resource_usage_dict

    def generate_rds_performance_metrics(self):
        now = datetime.datetime.now()
        rds_performance_data_list = self.query_rds_performance_data_list()
        logging.debug("rds_performance_data_list used time = {}".format(datetime.datetime.now() - now))
        for i in range(len(rds_performance_data_list)):
            rds_performance_data = json.loads(rds_performance_data_list[i].decode("utf-8"))
            DBInstanceId = rds_performance_data["DBInstanceId"]
            PerformanceKey = rds_performance_data['PerformanceKeys']['PerformanceKey']
            if len(PerformanceKey) == 0:
                continue
            PerformanceKey = PerformanceKey[0]
            Key = PerformanceKey["Key"]
            Unit = PerformanceKey["Unit"]
            Value = PerformanceKey["Values"]["PerformanceValue"][0]["Value"].split("&")
            ValueFormat = PerformanceKey["ValueFormat"].split("&")
            for k, v in zip(ValueFormat, Value):
                name = "{}_{}_{}".format("aliyun_rds_performance", Key, k).replace('-', '_')
                gauge = GaugeMetricFamily(
                    name=name,
                    documentation='',
                    labels=["instanceId", "Unit",]
                )
                gauge.add_metric(
                    labels=[DBInstanceId, Unit],
                    value=v,
                )
                yield gauge

    def generate_rds_status_metrics(self):
        rds_instance_list = self.query_rds_instance_list()
        for i in range(len(rds_instance_list)):
            rds_status = rds_instance_list[i]
            rds_status_keys = [
                "CreateTime",
                "DBInstanceDescription",
                "DBInstanceId",
                "DBInstanceStatus",
                "DBInstanceType",
                "Engine",
                "EngineVersion",
                "ExpireTime",
                "LockMode",
                "PayType",
                "RegionId",
            ]
            # if rds_status["DBInstanceStatus"] != "Running":
            #     continue
            gauge = GaugeMetricFamily(
                name="aliyun_rds_status",
                documentation='',
                labels=rds_status_keys,
            )
            gauge.add_metric(
                [
                    rds_status["CreateTime"],
                    rds_status["DBInstanceDescription"],
                    rds_status["DBInstanceId"],
                    rds_status["DBInstanceStatus"],
                    rds_status["DBInstanceType"],
                    rds_status["Engine"],
                    rds_status["EngineVersion"],
                    rds_status["ExpireTime"],
                    rds_status["LockMode"],
                    rds_status["PayType"],
                    rds_status["RegionId"],
                ],
                value=1
            )
            yield gauge

    def generator_rds_resource_usage_metrics(self):
        rds_instance_list = self.query_rds_instance_list()
        rds_resource_usage_dict = self.query_rds_resource_usage_list()
        for i in range(len(rds_instance_list)):
            DBInstanceId = rds_instance_list[i]['DBInstanceId']
            rds_resource_usage = rds_resource_usage_dict[DBInstanceId]
            Engine = rds_resource_usage['Engine']
            for k, v in rds_resource_usage.items():
                if k == 'Engine' or k == 'RequestId' or k == 'DBInstanceId':
                    continue
                name = "aliyun_rds_resource_usage_{}".format(k)
                gauge = GaugeMetricFamily(
                    name=name,
                    documentation='',
                    labels=["instanceId", "Engine"]
                )
                gauge.add_metric(
                    [DBInstanceId, Engine],
                    value=v,
                )
                yield gauge

    def collect(self):
        yield from self.generate_rds_performance_metrics()
        yield from self.generator_rds_resource_usage_metrics()
        yield from self.generate_rds_status_metrics()
