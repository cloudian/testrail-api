#!/usr/bin/env python3
import configparser
import api

# Configuration
conf = configparser.ConfigParser()
with open("config", "r") as f:
    conf.read_file(f)

URL = conf.get("testrail", "base_url")
project_id = conf.get("testrail", "project_id")
client = api.Client(URL, project_id=project_id, user=conf.get("testrail", "user"), password=conf.get("testrail", "password"))

all_suites = client.get_suites()

print(all_suites)
