# -*- coding: utf-8 -*-
import hashlib
import re

import demjson
import scrapy
import time
from scrapy import Selector

from weixin.db.LogDao import LogDao
from weixin.db.WxSourceDao import WxSourceDao
from weixin.util import NetworkUtil
from weixin.util import TimerUtil

isEnd = False


class WXDetailSpider(scrapy.Spider):
    name = 'wx_detail'
    download_delay = 20  # 基础间隔 0.5*download_delay --- 1.5*download_delays之间的随机数
    handle_httpstatus_list = [301, 302, 204, 206, 403, 404, 500]  # 可以处理重定向及其他错误码导致的 页面无法获取解析的问题

    def __init__(self, name=None, **kwargs):
        super(WXDetailSpider, self).__init__(name=None, **kwargs)
        self.count = 0
        self.wxSourceDao = WxSourceDao()
        self.request_stop = False
        self.request_stop_time = 0
        self.logDao = LogDao('wx_list_detail')

    def start_requests(self):
        # unKnow = ["didalive", "HIS_Technology", "CINNO_CreateMore", "ad_helper", "zhongduchongdu"]; 是搜索不到的
        # TODO..加上while可能有问题，有些可能抓不到
        while True:
            # 检测网络
            if not NetworkUtil.checkNetWork():
                # 20s检测一次
                TimerUtil.sleep(20)
                self.logDao.warn(u'检测网络不可行')
                continue

            # 检测服务器
            if not NetworkUtil.checkService():
                # 20s检测一次
                TimerUtil.sleep(20)
                self.logDao.warn(u'检测服务器不可行')
                continue

            if self.request_stop:
                # 拨号生效时间不定，所以需要间隔一段时间再重试
                timeSpace = time.time() - self.request_stop_time
                if timeSpace / 60 <= 2:
                    # 当时间间隔小于 2分钟 就不请求
                    continue
                    pass
                else:
                    self.request_stop = False

            # 进行爬虫
            # TODO..清除cookie
            # 获取源  可用有值
            sources = self.wxSourceDao.queryWxUrl(isRandom=True)

            for source in sources:
                if self.request_stop:
                    self.logDao.warn(u'出现被绊或者出现网络异常，退出循环')
                    # 当网络出现被绊的情况，就需要停止所有的请求等待IP更换
                    break
                (wx_name, wx_account, wx_url, wx_avatar, update_status, is_enable, update_time) = source
                # 进行页面访问
                newUrl = wx_url
                self.logDao.warn(u'进行抓取:' + newUrl)
                # TODO..no more duplicates will be shown (see DUPEFILTER_DEBUG to show all duplicates)
                yield scrapy.Request(url=newUrl,
                                     meta={'request_type': 'wx_page_list', 'url': newUrl,
                                           'wx_account': wx_account, 'source': source},
                                     callback=self.parseArticleList, dont_filter=True)
                # 跑空线程2秒
                TimerUtil.sleep(2)

            if sources:
                self.logDao.info(u'请求了一轮了，但是可能还有没有请求完成')

            if self.request_stop:
                # 则需要发起通知 进行重新拨号
                # 但是并不知道什么时候网络重新拨号成功呢
                # 记录当前时间
                # 充值updating的状态为updateFail
                self.wxSourceDao.resetUpdating()
                self.logDao.warn(u'更改更新中状态为updateFail,防止下次取不到')
                self.logDao.warn(u'发送重新拨号信号，请等待2分钟会尝试重新抓取')
                self.request_stop_time = time.time()
                pass
            else:
                # 正常抓好之后，当前跑空线程40分钟，不影响一些还没请求完成的request
                if sources:
                    TimerUtil.sleep(40 * 60)
                    pass

    def parseArticleList(self, response):
        source = response.meta['source']
        wx_account = response.meta['wx_account']
        url = response.meta['url']
        body = response.body

        self.logDao.info(u'开始解析列表:' + wx_account)
        if "您的访问列表过于频繁" in body or response.status == 302:
            self.request_stop = True
            # 更新状态为更新失败
            self.logDao.warn(u'您的访问列表过于频繁')
        else:
            # 进行解析
            selector = Selector(text=body)
            articleJS = selector.xpath('//script/text()').extract()
            for js in articleJS:
                if 'var msgList = ' in js:
                    p8 = re.compile('var\s*msgList\s*=.*;')
                    matchList = p8.findall(js)
                    for match in matchList:
                        match = match.lstrip('var msgList = ').rstrip(';')
                        # 格式化
                        articles = demjson.decode(match) or {}
                        articles = articles['list'] or []
                        self.logDao.info(u'匹配到文章列表' + wx_account)
                        for article in articles:
                            app_msg_ext_info = article['app_msg_ext_info'] or {}
                            detailUrl = app_msg_ext_info['content_url'] or ''
                            title = app_msg_ext_info['digest'] or ''
                            detailUrl = "http://mp.weixin.qq.com" + detailUrl
                            detailUrl = detailUrl.replace("amp;", "")
                            self.logDao.info(u'抓取' + wx_account + ':' + title + ':' + detailUrl)
                            yield scrapy.Request(url=detailUrl,
                                                 meta={'request_type': 'wx_detail', 'wx_account': wx_account,
                                                       "source": source, "title": title,
                                                       "detailUrl": detailUrl},
                                                 callback=self.parseArticle)
                            break
                        break

    def parseArticle(self, response):
        wx_account = response.meta['wx_account']
        source = response.meta['source']
        title = response.meta['title']
        detailUrl = response.meta['detailUrl']
        body = response.body

        self.logDao.info(u'开始解析文章' + wx_account + ':' + title + ':' + detailUrl)
        self.logDao.info(u'开始解析文章：' + detailUrl)
        if "您的访问文章过于频繁" in body or response.status == 302:
            self.request_stop = True
            # 更新状态为更新失败
            self.logDao.warn(u'您的访问文章过于频繁')
        else:
            # 进行解析
            selector = Selector(text=response.body)
            post_date = selector.xpath('//*[@id="post-date"]/text()').extract_first()
            post_user = selector.xpath('//*[@id="post-user"]/text()').extract_first()
            content = selector.xpath('//*[@id="js_content"]')
            page = selector.xpath('//*[@id="img-content"]')

            self.logDao.info(wx_account + u'得到文章：' + title + ":" + post_date + ':' + post_user)
            self.logDao.info(u'得到文章：' + detailUrl)
            m2 = hashlib.md5()
            m2.update(title.encode('utf8'))
            title_hash = m2.hexdigest()
            self.saveFile(title_hash, page.extract_first())
            # TODO...差数据库

    def saveFile(self, title, content):
        filename = 'html/%s.html' % title
        with open(filename, 'wb') as f:
            f.write(content.encode("utf8"))
        self.log('Saved file %s' % filename)