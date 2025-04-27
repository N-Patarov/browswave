import scrapy

class MrBricolageSpider(scrapy.Spider):
    name = 'mr-bricolage'
    allowed_domains = ['mr-bricolage.bg', 'api.mr-bricolage.bg']
    start_urls = ['https://mr-bricolage.bg/instrumenti/elektroprenosimi-instrumenti/vintoverti/c/006003013']

    def parse(self, response):
        product_links = response.xpath("//h2[@class='product__title']/a/@href").getall()
        for link in product_links:
            yield response.follow(link, callback=self.parse_product)

        next_page = response.xpath("//a[@class='pagination_button']/@href").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def parse_product(self, response):
        title = response.xpath("//cx-page-slot[@position='ProductNameSlot']//h1/text()")\
                        .get(default='').strip()

        price_int = response.xpath("//div[contains(@class,'product__price-value')]/text()")\
                            .get(default='').strip()
        price_frac = response.xpath("//sup[contains(@class,'fraction')]/text()")\
                             .get(default='').strip()
        price = f"{price_int}.{price_frac}" if price_int and price_frac else price_int or price_frac

        rating = response.xpath("//span[contains(@class,'rating-count')]/text()")\
                         .get(default='').strip()

        images = response.xpath(
            "//cx-media[contains(@class,'preview-img')]//img/@src"
        ).getall()

        specs = {}
        for row in response.xpath("//table[contains(@class,'product-classification-table')]//tr"):
            key = row.xpath(".//td[1]//text()").get(default='').strip()
            vals = [t.strip() for t in row.xpath(".//td[2]//text()").getall() if t.strip()]
            if key:
                specs[key] = " ".join(vals)

        brand = response.xpath("//table[@class='product-classification-table']//tr[td[1][normalize-space(.)='Марка']]/td[2]/text()")\
                        .get(default='').strip()
        if brand and brand.lower() not in title.lower():
            title = f"{brand} {title}"

        product_code = response.xpath(
            "//span[contains(text(),'Код:')]/text()"
        ).re_first(r"Код:\s*(\d+)")

        item = {
            'title': title,
            'price': price,
            'rating': rating,
            'images': images,
            'specs': specs,
        }

        stock_url = (
            f"https://api.mr-bricolage.bg/occ/v2/bricolage-spa/"
            f"products/{product_code}/stock"
            "?longitude=0&latitude=0"
            "&fields=stores(name,displayName,address(streetname,streetnumber,town),stockInfo(FULL))"
            "&lang=bg&curr=BGN"
        )
        yield scrapy.Request(
            stock_url,
            callback=self.parse_stock,
            cb_kwargs={'item': item},
            dont_filter=True
        )

    def parse_stock(self, response, item):
        if response.status != 200 or not response.text.strip():
            item['availability'] = []
            item['top_store']    = None
            yield item
            return

        xml = scrapy.Selector(text=response.text, type="xml")
        nodes = xml.xpath('//stores/stores')
        if not nodes:
            item['availability'] = []
            item['top_store']    = None
            yield item
            return

        stores = []
        top = {'name': None, 'qty': -1}

        for s in nodes:
            name = (
                s.xpath('./displayName/text()').get() or
                s.xpath('./name/text()').get() or
                ''
            ).strip()

            street = s.xpath('./address/streetname/text()').get(default='').strip()
            number = s.xpath('./address/streetnumber/text()').get(default='').strip()
            town   = s.xpath('./address/town/text()').get(default='').strip()
            address = ", ".join(filter(None, [street, number, town]))

            qty_text = s.xpath('./stockInfo/stockLevel/text()').get(default='0')
            try:
                qty = int(qty_text)
            except ValueError:
                qty = 0

            avail = (s.xpath('./stockInfo/stockLevelSemaphore/text()')
                     .get(default='')
                     .upper())

            stores.append({
                'store':        name,
                'address':      address,
                'quantity':     qty,
                'availability': avail,
            })

            if qty > top['qty']:
                top = {'name': name, 'qty': qty}

        item['availability'] = stores
        item['top_store']    = top['name']
        yield item

