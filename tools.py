#!/usr/bin/env python3
# -*- coding:utf-8 -*-
import argparse
import yaml
import os


def get_args():
    parser = argparse.ArgumentParser(description="Aliyun RDS Exporter for Prometheus.")
    parser.add_argument(
        '-c',
        '--config',
        default='config/config.yaml',
        help='Path to config file',
    )
    parser.add_argument(
        '-d',
        '--debug',
        action='store_true',
        help='print debug messages'
    )
    return parser.parse_args().__dict__

def get_file_opts(args):
    if (os.path.exists(args['config']) is True) and (os.access(args['config'], os.R_OK) is True):
        with open(file=args['config'], mode='r', encoding='utf-8') as config_file:
            opts = yaml.load(config_file, Loader=yaml.FullLoader)
    else:
        raise Exception('Config file not found or not access!')
    return opts
