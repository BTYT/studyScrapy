# -*- coding: utf-8 -*-
from scrapy import cmdline

cmdline.execute("scrapy crawl img_crawl  -s HTTPCACHE_ENABLED=0  ".split())