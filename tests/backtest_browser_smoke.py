"""Explicit isolated UI test: python tests/backtest_browser_smoke.py. No broker calls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import threading
from collections import deque
from flask import Flask, render_template
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from deriv_backtest.store import Store
from deriv_backtest.engine import ResearchEngine
from deriv_backtest.strategies import Strategy
from deriv_backtest.statistics import accumulate, empty
from deriv_backtest.web import register


def main():
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Path(directory)/'test.sqlite3')
        strategy=Strategy('probe','Test-only strategy',1,('DIGITUNDER',),lambda d:None)
        e=ResearchEngine(store,(strategy,))
        e.set_market('R_25','Volatility 25',2,['DIGITUNDER'])
        e.seq['R_25']=500
        stats=empty();rows=[]
        for i in range(2,501):
            won=i>450
            r=dict(id=str(i),symbol='R_25',strategy='probe',entry_seq=i-1,exit_seq=i,
                created=i,won=won,payout_ratio=1.2,profit=.2 if won else -1,origin='forward',
                contract='DIGITUNDER',barrier=9,duration=1,pricing='Observed proposal')
            rows.append(r);accumulate(stats,r)
            e.paper_batch.append((r['id'],r['symbol'],r['strategy'],r['entry_seq'],r['exit_seq'],r['created'],__import__('json').dumps(r)))
        e.totals['R_25:probe']=stats;e.recent['R_25:probe']=deque(rows);e.snapshots();e.health('STOPPED')
        app=Flask('backtest-ui-test',template_folder=str(root/'templates'),static_folder=str(root/'static'))
        app.secret_key='temporary-ui-fixture'
        register(app,lambda:True,lambda:True,store)
        @app.get('/fixture-admin')
        def admin():return render_template('intelligence_admin.html')
        server=make_server('127.0.0.1',0,app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='msedge',headless=True)
                page=browser.new_page(viewport={'width':1366,'height':900})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                base=f'http://127.0.0.1:{server.server_port}'
                page.goto(base+'/backtest-tools')
                assert page.locator('.brand img').count() == 0
                page.locator('#btRows tr').wait_for()
                assert page.locator('#btRows tr').count()==1
                count500=page.locator('#btRows tr td').nth(6).inner_text()
                page.select_option('#btWindow','50')
                page.wait_for_function("document.querySelector('#btRows tr td:nth-child(7)').textContent === '49'")
                assert count500=='499'
                page.get_by_role('button',name='Details for Test-only strategy on Volatility 25').click()
                page.locator('#btComparison tr').nth(5).wait_for()
                assert page.locator('#btEquity svg').count() == 1
                for width in (390,768,1366):
                    page.set_viewport_size({'width':width,'height':844})
                    page.evaluate('scrollTo(0, 0)')
                    page.screenshot(path=str(Path(tempfile.gettempdir())/f'koolkid-backtest-{width}.png'),full_page=True)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate("[...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > innerWidth + 1 && getComputedStyle(e).position !== 'absolute').slice(0,12).map(e=>[e.tagName,e.className,e.getBoundingClientRect().width])")
                page.select_option('#btStatus','VALIDATED')
                page.locator('#btEmptyTitle').filter(has_text='No results match').wait_for()
                page.get_by_role('button',name='Clear filters').click()
                page.locator('#btRows tr').wait_for()
                page.goto(base+'/fixture-admin')
                page.wait_for_function("document.querySelector('#globalIntelligenceStatus').textContent.includes('STOPPED')")
                assert page.locator('#globalIntelligencePat').get_attribute('type')=='password'
                assert page.locator('[data-intelligence]').count()==6
                page.locator('#globalConfirmationEnabled').uncheck()
                page.get_by_role('button',name='Save confirmation settings').click()
                page.wait_for_function("!document.querySelector('[data-intelligence=confirmation]').disabled")
                assert store.get('confirmation_policy')['enabled'] is False
                assert not errors,errors
                browser.close()
                print('PASS: desktop/mobile layout, window changes, details, admin masking, confirmation settings, no JS errors. Isolated fixture; no broker trades.')
        finally:
            server.shutdown();thread.join(timeout=5)


if __name__=='__main__':main()
