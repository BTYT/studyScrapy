# -*- coding: utf-8 -*-
from scrapy import cmdline

# cmdline.execute("scrapy crawl wx_detail  -s HTTPCACHE_ENABLED=0  ".split())
cmdline.execute("scrapy crawl wx_detail_special  -s HTTPCACHE_ENABLED=0  ".split())
