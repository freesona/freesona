from utils.rss import parse_feed

nitter_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">
  <channel>
    <item>
      <title>PODCAST: Shein's fraying profit sets up drab IPO: podcast http://reut.rs/4bknF8U http://reut.rs/4bknF8U</title>
      <dc:creator>@Reuters</dc:creator>
      <description><![CDATA[<p>PODCAST: Shein's fraying profit sets up drab IPO: podcast <a href="http://reut.rs/4bknF8U">reut.rs/4bknF8U</a> <a href="http://reut.rs/4bknF8U">reut.rs/4bknF8U</a></p>
<hr/>
<b>Link</b><br>
<a href="http://reut.rs/4bknF8U">
<img src="https://nitter.net/pic/card_img%2F2082792082930802688%2FPTHQdymJ%3Fformat%3Djpg%26name%3D800x419" style="max-width:250px;" />
<br>
<b>PODCAST: Shein's fraying profit sets up drab IPO: podcast</b>
</a>
<p>The Chinese-founded fast-fashion retailer has released financial details ahead of its long-awaited Hong Kong float. In this Viewsroom podcast, Breakingviews columnists explain how a pushback against...</p>
<small><a href="http://reut.rs/4bknF8U">reuters.com</a></small>]]></description>
      <pubDate>Thu, 30 Jul 2026 11:35:03 GMT</pubDate>
      <guid isPermaLink="false">2082792081873912297</guid>
      <link>https://nitter.net/Reuters/status/2082792081873912297#m</link>
    </item>
  </channel>
</rss>'''

items = parse_feed(nitter_xml)
for item in items:
    print('Title:', repr(item.title))
    print('Summary:', repr(item.summary))
    print('---')